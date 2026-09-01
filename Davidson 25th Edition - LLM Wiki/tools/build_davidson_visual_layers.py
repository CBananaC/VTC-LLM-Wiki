#!/usr/bin/env python3
"""Build Davidson's visual manifest and coordinate-preserving table layer.

Tables receive a full, generated reconstruction from the PDF's embedded word
coordinates. Other visual candidates receive metadata only. The source PDF,
the raw embedded-text JSON, and the layout inventory are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
import clean_davidson_full_text as full  # noqa: E402
import structure_davidson_ch01_text as ch1  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--raw-text", type=Path, required=True)
    parser.add_argument("--chapter-map", type=Path, required=True)
    parser.add_argument("--layout-inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def point_bbox_from_px(
    bbox_px: list[float], render: dict[str, Any], page_width: float, page_height: float
) -> list[float]:
    sx = page_width / float(render["width"])
    sy = page_height / float(render["height"])
    return [
        bbox_px[0] * sx,
        bbox_px[1] * sy,
        bbox_px[2] * sx,
        bbox_px[3] * sy,
    ]


def bbox_union(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def bbox_gap(a: list[float], b: list[float]) -> tuple[float, float]:
    horizontal = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    vertical = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return horizontal, vertical


def flatten_page_lines(page_bbox: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for flow in page_bbox["flows"]:
        for block in flow["blocks"]:
            for line in block["lines"]:
                words = line["words"]
                text = ch1.join_line_words(words)
                if not text:
                    continue
                bbox = [
                    min(word["bbox"][0] for word in words),
                    min(word["bbox"][1] for word in words),
                    max(word["bbox"][2] for word in words),
                    max(word["bbox"][3] for word in words),
                ]
                lines.append(
                    {
                        "flow_index": flow["flow_index"],
                        "block_index": block["block_index"],
                        "line_index": line["line_index"],
                        "source_line_id": (
                            f"DAV25-PDF{page_bbox['pdf_page']:04d}-F{flow['flow_index']:03d}-"
                            f"B{block['block_index']:03d}-L{line['line_index']:03d}"
                        ),
                        "bbox_points": [round(value, 3) for value in bbox],
                        "text": text,
                        "words": words,
                    }
                )
    return sorted(lines, key=lambda line: (line["bbox_points"][1], line["bbox_points"][0]))


def lines_in_bbox(
    lines: list[dict[str, Any]], bbox_points: list[float]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    region = tuple(bbox_points)
    for line in lines:
        words = [word for word in line["words"] if ch1.intersects(word, region)]
        if not words:
            continue
        text = ch1.join_line_words(words)
        if not text:
            continue
        bbox = [
            min(word["bbox"][0] for word in words),
            min(word["bbox"][1] for word in words),
            max(word["bbox"][2] for word in words),
            max(word["bbox"][3] for word in words),
        ]
        result.append(
            {
                "source_line_id": line["source_line_id"],
                "bbox_points": [round(value, 3) for value in bbox],
                "text": text,
                "words": words,
            }
        )
    return sorted(result, key=lambda line: (line["bbox_points"][1], line["bbox_points"][0]))


def text_from_lines(lines: list[dict[str, Any]]) -> str:
    return " ".join(line["text"] for line in lines).strip()


def concise_visual_name(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    protected = re.sub(
        r"(?i)\b(fig(?:ure)?|tab(?:le)?|box|algorithm)\.", r"\1<abbrdot>", text
    )
    sentences = re.split(r"(?<=[.!?])\s+", protected)
    return sentences[0].replace("<abbrdot>", ".").strip() if sentences else text


def candidate_name_from_table_lines(lines: list[dict[str, Any]]) -> str | None:
    if not lines:
        return None
    for line in lines[:4]:
        if re.match(r"(?i)^(?:table|tab\.?|box)\s*[\w.-]+", line["text"]):
            return line["text"]
    return lines[0]["text"]


def caption_score(visual_bbox: list[float], caption_bbox: list[float]) -> tuple[float, float, float]:
    horizontal_gap, vertical_gap = bbox_gap(visual_bbox, caption_bbox)
    visual_center = (visual_bbox[0] + visual_bbox[2]) / 2
    caption_center = (caption_bbox[0] + caption_bbox[2]) / 2
    center_gap = abs(visual_center - caption_center)
    return (vertical_gap * 3.0 + horizontal_gap + center_gap * 0.15, vertical_gap, horizontal_gap)


def nearest_caption(
    visual_bbox: list[float], captions: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not captions:
        return None
    ranked = sorted(captions, key=lambda item: caption_score(visual_bbox, item["bbox_points"]))
    best = ranked[0]
    score, vertical_gap, horizontal_gap = caption_score(visual_bbox, best["bbox_points"])
    if score <= 260.0 or vertical_gap <= 35.0 or horizontal_gap <= 35.0:
        return best
    return None


def split_line_cells(line: dict[str, Any]) -> list[dict[str, Any]]:
    words = sorted(line["words"], key=lambda word: word["bbox"][0])
    if not words:
        return []
    groups: list[list[dict[str, Any]]] = [[words[0]]]
    for word in words[1:]:
        previous = groups[-1][-1]
        gap = word["bbox"][0] - previous["bbox"][2]
        if gap > 18.0:
            groups.append([word])
        else:
            groups[-1].append(word)
    cells: list[dict[str, Any]] = []
    for cell_index, group in enumerate(groups, 1):
        cells.append(
            {
                "cell_fragment_index": cell_index,
                "text": ch1.join_line_words(group),
                "bbox_points": [
                    round(min(word["bbox"][0] for word in group), 3),
                    round(min(word["bbox"][1] for word in group), 3),
                    round(max(word["bbox"][2] for word in group), 3),
                    round(max(word["bbox"][3] for word in group), 3),
                ],
                "source_line_id": line["source_line_id"],
            }
        )
    return cells


def reconstruct_table(
    table_id: str,
    candidate: dict[str, Any],
    table_lines: list[dict[str, Any]],
    name: str | None,
    page_role: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for line in table_lines:
        y = line["bbox_points"][1]
        if not rows or abs(y - rows[-1]["baseline_y"]) > 3.0:
            rows.append(
                {
                    "row_index": len(rows) + 1,
                    "baseline_y": y,
                    "y_top": line["bbox_points"][1],
                    "y_bottom": line["bbox_points"][3],
                    "cells": [],
                    "source_line_ids": [],
                }
            )
        row = rows[-1]
        row["y_top"] = min(row["y_top"], line["bbox_points"][1])
        row["y_bottom"] = max(row["y_bottom"], line["bbox_points"][3])
        row["source_line_ids"].append(line["source_line_id"])
        row["cells"].extend(split_line_cells(line))
    for row in rows:
        row.pop("baseline_y", None)
        row["cells"].sort(key=lambda cell: cell["bbox_points"][0])
        row["text"] = " | ".join(cell["text"] for cell in row["cells"])

    anchors: list[float] = []
    for row in rows:
        for cell in row["cells"]:
            x = cell["bbox_points"][0]
            if not anchors or x - anchors[-1] > 8.0:
                anchors.append(x)
            else:
                anchors[-1] = round((anchors[-1] + x) / 2, 3)

    return {
        "table_id": table_id,
        "visual_id": table_id.replace("-TBL-", "-VIS-"),
        "page_role": page_role,
        "name": name,
        "location": {
            "pdf_page": candidate["pdf_page"],
            "bbox_px": candidate["bbox_px"],
            "bbox_points": candidate["bbox_points"],
            "coordinate_origin": "top-left",
        },
        "content": {
            "text": "\n".join(line["text"] for line in table_lines),
            "rows": rows,
            "column_anchors_points": anchors,
        },
        "reconstruction": {
            "method": "embedded_pdf_text_bbox_reconstruction",
            "layout_model": "coordinate-preserving line and cell fragments",
            "source_word_count": sum(len(line["words"]) for line in table_lines),
            "source_line_count": len(table_lines),
            "merged_cells": "not inferred; inspect row/cell coordinates",
            "footnotes": "retained when located inside the detected table bbox",
        },
        "status": (
            "not_applicable_noncontent_candidate"
            if page_role != "chapter_content"
            else ("generated_not_verified" if table_lines else "needs_visual_ocr")
        ),
        "verification_status": "generated_not_verified",
    }


def visual_type(label: str) -> str:
    return {
        "image": "illustration_or_image",
        "chart": "chart_or_graph",
        "algorithm": "algorithm_or_flowchart",
        "formula": "formula",
        "seal": "seal_or_mark",
    }.get(label, label)


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    raw_text_path = args.raw_text.expanduser().resolve()
    chapter_map_path = args.chapter_map.expanduser().resolve()
    inventory_path = args.layout_inventory.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    chapter_map, chapters = full.load_chapters(chapter_map_path)
    inventory = ch1.load_inventory(inventory_path)
    roles = full.noncontent_roles(chapters, int(chapter_map["pdf_page_count"]))
    output_dir.mkdir(parents=True, exist_ok=True)

    visuals: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = []
    layout_candidates: list[dict[str, Any]] = []
    counts = Counter()
    pdftotext = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"

    with tempfile.TemporaryDirectory(prefix="davidson25-visual-layer-") as temp:
        xml_path = Path(temp) / "full_bbox.html"
        subprocess.run(
            [
                pdftotext,
                "-bbox-layout",
                "-enc",
                "UTF-8",
                "-f",
                "1",
                "-l",
                str(chapter_map["pdf_page_count"]),
                str(source),
                str(xml_path),
            ],
            check=True,
            capture_output=True,
        )
        sanitized_xml_path = Path(temp) / "full_bbox_sanitized.html"
        bbox_invalid_characters_removed = full.sanitize_bbox_xml(xml_path, sanitized_xml_path)
        parsed_pages = 0
        for page_bbox in full.iter_bbox_pages(sanitized_xml_path):
            parsed_pages += 1
            pdf_page = page_bbox["pdf_page"]
            page_source = inventory[pdf_page]
            page_role = roles.get(pdf_page, "chapter_content")
            chapter = full.chapter_for_page(chapters, pdf_page)
            page_lines = flatten_page_lines(page_bbox)
            render = page_source["render"]
            candidate_rows: list[dict[str, Any]] = []
            page_caption_records: list[dict[str, Any]] = []

            for candidate in page_source.get("visual_candidates", []):
                bbox_px = [float(value) for value in candidate["bbox"]]
                bbox_points = point_bbox_from_px(
                    bbox_px, render, page_bbox["width"], page_bbox["height"]
                )
                candidate_lines = lines_in_bbox(page_lines, bbox_points)
                candidate_id = candidate["layout_id"]
                row = {
                    "candidate_id": candidate_id,
                    "pdf_page": pdf_page,
                    "source_page_id": page_source["source_page_id"],
                    "page_role": page_role,
                    "candidate_label": candidate.get("label"),
                    "confidence": candidate.get("confidence"),
                    "bbox_px": bbox_px,
                    "bbox_points": [round(value, 3) for value in bbox_points],
                    "candidate_text": text_from_lines(candidate_lines),
                    "candidate_line_count": len(candidate_lines),
                }
                candidate_rows.append({**row, "lines": candidate_lines})
                layout_candidates.append(
                    {
                        **row,
                        "candidate_role": (
                            "caption_or_title_candidate"
                            if candidate.get("label") == "figure_title"
                            else "visual_candidate"
                        ),
                    }
                )
                counts[f"candidate_{candidate.get('label', 'unknown')}"] += 1
                if candidate.get("label") == "figure_title":
                    caption = {
                        "caption_id": f"DAV25-CAP-P{pdf_page:04d}-C{candidate['layout_index']:04d}",
                        "candidate_id": candidate_id,
                        "pdf_page": pdf_page,
                        "source_page_id": page_source["source_page_id"],
                        "page_role": page_role,
                        "text": text_from_lines(candidate_lines) or None,
                        "bbox_px": bbox_px,
                        "bbox_points": [round(value, 3) for value in bbox_points],
                    }
                    captions.append(caption)
                    page_caption_records.append(caption)

            for row in candidate_rows:
                label = row["candidate_label"]
                if label == "figure_title":
                    continue
                visual_id = f"DAV25-VIS-P{pdf_page:04d}-C{row['candidate_id'].rsplit('L', 1)[-1]}"
                table_id = (
                    f"DAV25-TBL-P{pdf_page:04d}-C{row['candidate_id'].rsplit('L', 1)[-1]}"
                    if label == "table"
                    else None
                )
                caption = nearest_caption(row["bbox_points"], page_caption_records)
                name = concise_visual_name(caption["text"] if caption else None)
                if label == "table":
                    name = candidate_name_from_table_lines(row["lines"]) or name
                if not name and row["candidate_text"]:
                    name_match = re.search(
                        r"(?i)((?:fig(?:ure)?|algorithm|table|box)\.?\s*[\w.-]+[^\n]*)",
                        row["candidate_text"],
                    )
                    if name_match:
                        name = concise_visual_name(name_match.group(1).strip())
                false_table_classification = bool(
                    label == "table"
                    and name
                    and re.match(r"(?i)^\s*(?:fig(?:ure)?|chart)\b", name)
                )
                printed_page = None
                if chapter:
                    printed_page = int(chapter["printed_page_start"]) + pdf_page - int(
                        chapter["pdf_page_start"]
                    )
                policy = (
                    "full_table_reconstruction"
                    if label == "table"
                    and not false_table_classification
                    and page_role == "chapter_content"
                    else "metadata_only"
                )
                visual = {
                    "visual_id": visual_id,
                    "candidate_id": row["candidate_id"],
                    "pdf_page": pdf_page,
                    "printed_page": printed_page,
                    "source_page_id": page_source["source_page_id"],
                    "chapter_number": chapter["chapter_number"] if chapter else None,
                    "chapter_title": chapter["title"] if chapter else None,
                    "page_role": page_role,
                    "visual_type": (
                        "table"
                        if label == "table" and not false_table_classification
                        else ("figure_or_illustration" if false_table_classification else visual_type(label))
                    ),
                    "candidate_label": label,
                    "name": name,
                    "caption_candidate_id": caption["caption_id"] if caption else None,
                    "location": {
                        "bbox_px": row["bbox_px"],
                        "bbox_points": row["bbox_points"],
                        "coordinate_origin": "top-left",
                        "render_dpi": render["dpi"],
                    },
                    "policy": policy,
                    "table_id": None if false_table_classification else table_id,
                    "classification_note": (
                        "layout model labelled this candidate as table, but its nearby name is a figure/chart; treated as metadata-only"
                        if false_table_classification
                        else None
                    ),
                    "content_reconstruction": (
                        "see table record"
                        if label == "table" and not false_table_classification
                        else "not reconstructed"
                    ),
                    "source_crop": {
                        "source_pdf": str(source),
                        "pdf_page": pdf_page,
                        "bbox_px": row["bbox_px"],
                    },
                    "status": "generated_not_verified",
                    "verification_status": "generated_not_verified",
                }
                visuals.append(visual)
                if label == "table" and not false_table_classification:
                    table_record = reconstruct_table(
                        table_id,
                        {
                            **row,
                            "pdf_page": pdf_page,
                            "bbox_px": row["bbox_px"],
                            "bbox_points": row["bbox_points"],
                        },
                        row["lines"],
                        name,
                        page_role,
                    )
                    tables.append(table_record)

            # Link captions to the metadata records nearest to them for audit.
            for caption in page_caption_records:
                linked = [
                    visual["visual_id"]
                    for visual in visuals
                    if visual["pdf_page"] == pdf_page
                    and visual.get("caption_candidate_id") == caption["caption_id"]
                ]
                caption["linked_visual_ids"] = linked

        if parsed_pages != int(chapter_map["pdf_page_count"]):
            raise RuntimeError(
                f"Expected {chapter_map['pdf_page_count']} bbox pages, got {parsed_pages}"
            )

    source = source.resolve()
    common = {
        "book_id": "DAV25",
        "source": {
            "filename": source.name,
            "path": str(source),
            "sha256": sha256_file(source),
        },
        "derived_from": {
            "raw_text_json": str(raw_text_path),
            "chapter_map": str(chapter_map_path),
            "layout_inventory": str(inventory_path),
        },
        "visual_policy": {
            "tables": "reconstruct full contents and coordinate-preserving row/cell layout",
            "non_tables": "retain type, name/caption, page, and location only",
            "raw_source": "immutable",
            "verification": "generated_not_verified until visual/manual review",
        },
        "bbox_xml_sanitization": {
            "invalid_control_characters_removed": bbox_invalid_characters_removed,
            "reason": "Poppler emitted XML-1.0-invalid controls; only temporary bbox parser input was sanitized",
        },
        "status": "generated",
        "verification_status": "generated_not_verified",
    }
    manifest = {
        "schema_version": "vtc-davidson25.visual-manifest.v1",
        "record_type": "visual_manifest_with_table_policy",
        **common,
        "counts": {
            "pages_scanned": int(chapter_map["pdf_page_count"]),
            "layout_candidates": len(layout_candidates),
            "visual_records": len(visuals),
            "table_candidates": counts["candidate_table"],
            "table_records": len(tables),
            "table_content_records": sum(
                table["page_role"] == "chapter_content" for table in tables
            ),
            "non_table_visual_records": sum(
                visual["visual_type"] != "table" for visual in visuals
            ),
            "false_table_classifications": sum(
                visual.get("classification_note") is not None for visual in visuals
            ),
            "caption_candidates": len(captions),
            "visuals_with_names": sum(bool(visual.get("name")) for visual in visuals),
        },
        "candidate_label_counts": {
            key.removeprefix("candidate_"): value
            for key, value in sorted(counts.items())
            if key.startswith("candidate_")
        },
        "layout_candidates": layout_candidates,
        "visuals": visuals,
        "caption_candidates": captions,
    }
    tables_output = {
        "schema_version": "vtc-davidson25.tables-reconstructed.v1",
        "record_type": "full_table_reconstructions",
        **common,
        "counts": {
            "tables": len(tables),
            "content_tables": sum(table["page_role"] == "chapter_content" for table in tables),
            "tables_with_embedded_text": sum(
                table["reconstruction"]["source_word_count"] > 0 for table in tables
            ),
            "tables_needing_visual_ocr": sum(table["status"] == "needs_visual_ocr" for table in tables),
        },
        "tables": tables,
    }
    manifest_path = output_dir / "davidson25_visual_manifest_generated.json"
    tables_path = output_dir / "davidson25_tables_reconstructed_generated.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tables_path.write_text(json.dumps(tables_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "tables": str(tables_path),
                "pages": int(chapter_map["pdf_page_count"]),
                **manifest["counts"],
                "tables_with_embedded_text": tables_output["counts"]["tables_with_embedded_text"],
                "tables_needing_visual_ocr": tables_output["counts"]["tables_needing_visual_ocr"],
                "bbox_invalid_characters_removed": bbox_invalid_characters_removed,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reconstruct detected table regions and catalogue every visual region.

This is deliberately a selective visual-content pass for the Stroke
Rehabilitation source.  Tables are reconstructed from embedded PDF text and
the PDF's drawn geometry with pdfplumber.  Non-table visual candidates are
recorded as locations only; their contents are not OCRed or interpreted.

The PaddleOCR layout inventory is retained as the authoritative candidate
inventory.  Overlapping table candidates that are almost wholly contained by
another table candidate are linked to the larger canonical record, rather
than generating duplicate table contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pdfplumber


TABLE_SETTINGS: list[tuple[str, dict[str, Any]]] = [
    (
        "lines_lines",
        {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
        },
    ),
    (
        "lines_text",
        {
            "vertical_strategy": "lines",
            "horizontal_strategy": "text",
        },
    ),
    (
        "text_lines",
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "lines",
        },
    ),
    (
        "text_text",
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
        },
    ),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--layout-inventory", type=Path, required=True)
    parser.add_argument("--page-text", type=Path, required=True)
    parser.add_argument("--visual-cues", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ")
    # pdfplumber exposes a common bullet glyph as a CID token in this PDF.
    # Keep other unknown CID tokens unchanged so no symbol is silently guessed.
    text = text.replace("(cid:127)", "•")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def nonempty_count(table: list[list[str]]) -> int:
    return sum(bool(cell.strip()) for row in table for cell in row)


def table_score(tables: list[list[list[str]]]) -> tuple[int, int, int]:
    nonempty = sum(nonempty_count(table) for table in tables)
    rows = sum(len(table) for table in tables)
    columns = max((len(row) for table in tables for row in table), default=0)
    return nonempty, rows, columns


def bbox_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def intersection_area(first: list[float], second: list[float]) -> float:
    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    return width * height


def contained_duplicate(candidate: dict[str, Any], others: list[dict[str, Any]]) -> str | None:
    candidate_area = bbox_area(candidate["bbox"])
    if candidate_area <= 0:
        return None
    for other in others:
        if other is candidate:
            continue
        other_area = bbox_area(other["bbox"])
        if other_area <= candidate_area:
            continue
        overlap_ratio = intersection_area(candidate["bbox"], other["bbox"]) / candidate_area
        if overlap_ratio >= 0.85:
            return str(other["layout_id"])
    return None


def point_bbox_from_px(
    bbox_px: list[float], render: dict[str, Any], page_width: float, page_height: float
) -> list[float]:
    sx = page_width / float(render["width"])
    sy = page_height / float(render["height"])
    return [
        round(bbox_px[0] * sx, 3),
        round(bbox_px[1] * sy, 3),
        round(bbox_px[2] * sx, 3),
        round(bbox_px[3] * sy, 3),
    ]


def human_location(bbox: list[float], page_width: float, page_height: float) -> str:
    x0, y0, x1, y1 = bbox
    width_ratio = (x1 - x0) / page_width
    height_ratio = (y1 - y0) / page_height
    if width_ratio >= 0.75 and height_ratio >= 0.75:
        return "full-page region"
    horizontal = "left" if (x0 + x1) / 2 < page_width * 0.42 else "right" if (x0 + x1) / 2 > page_width * 0.58 else "central"
    vertical = "upper" if (y0 + y1) / 2 < page_height * 0.34 else "lower" if (y0 + y1) / 2 > page_height * 0.66 else "middle"
    return f"{vertical} {horizontal} page region"


def group_words_into_lines(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        if not word.get("text", "").strip():
            continue
        top = float(word["top"])
        target: dict[str, Any] | None = None
        word_x0 = float(word["x0"])
        for line in reversed(lines[-4:]):
            previous_x1 = max(float(existing["x1"]) for existing in line["words"])
            # Separate same-baseline text in facing columns.  Without this,
            # a table caption on the left can absorb the first words of body
            # text on the right.
            if abs(top - line["top"]) <= 2.5 and word_x0 - previous_x1 <= 20:
                target = line
                break
        if target is None:
            target = {
                "top": top,
                "bottom": float(word["bottom"]),
                "words": [],
            }
            lines.append(target)
        target["words"].append(word)
        target["top"] = min(target["top"], top)
        target["bottom"] = max(target["bottom"], float(word["bottom"]))
    result: list[dict[str, Any]] = []
    for line in sorted(lines, key=lambda item: (item["top"], min(float(w["x0"]) for w in item["words"]))):
        sorted_words = sorted(line["words"], key=lambda item: float(item["x0"]))
        result.append(
            {
                "top": round(line["top"], 3),
                "bottom": round(line["bottom"], 3),
                "bbox": [
                    round(min(float(w["x0"]) for w in sorted_words), 3),
                    round(line["top"], 3),
                    round(max(float(w["x1"]) for w in sorted_words), 3),
                    round(line["bottom"], 3),
                ],
                "text": clean_cell(" ".join(str(w["text"]) for w in sorted_words)),
            }
        )
    return result


def overlaps_x(line: dict[str, Any], bbox: list[float]) -> bool:
    return line["bbox"][2] > bbox[0] - 2 and line["bbox"][0] < bbox[2] + 2


def caption_and_context(page: Any, bbox: list[float]) -> dict[str, Any]:
    words = [
        word
        for word in page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
        if bbox[0] - 2 <= (float(word["x0"]) + float(word["x1"])) / 2 <= bbox[2] + 2
    ]
    lines = group_words_into_lines(words)
    caption_candidates = [
        line
        for line in lines
        if overlaps_x(line, bbox)
        and bbox[1] - 35 <= line["top"] <= bbox[1] + 15
        and re.match(r"(?i)^(?:table|box)(?:\s|$)", line["text"])
    ]
    caption = None
    if caption_candidates:
        candidate = caption_candidates[0]
        caption_lines = [candidate]
        caption_can_wrap = re.match(r"(?i)^table\b", candidate["text"]) or (
            re.match(r"(?i)^box\b", candidate["text"])
            and re.search(r"(?i)\b(?:during|for|of|and|with|to)$", candidate["text"])
        )
        if caption_can_wrap:
            for line in lines:
                if line is candidate:
                    continue
                if line["top"] < candidate["bottom"] or line["top"] - candidate["bottom"] > 16:
                    continue
                if not overlaps_x(line, bbox):
                    continue
                # A wrapped caption is short; a long line here is normally
                # the first body row of a box/table and must not be absorbed.
                if len(line["text"]) > 45:
                    continue
                if re.match(r"(?i)^table\b", candidate["text"]):
                    if not re.search(r"[.!?:]$", line["text"]):
                        continue
                elif line["text"].lower() != "acute stroke rehabilitation":
                    continue
                if re.match(
                    r"(?i)^(?:table|box|figure|algorithm|type of risk|relative risk|results|severity code|recommendations)\b",
                    line["text"],
                ):
                    continue
                caption_lines.append(line)
                break
        caption = {
            "text": clean_cell(" ".join(line["text"] for line in caption_lines)),
            "bbox_points": [
                round(min(line["bbox"][0] for line in caption_lines), 3),
                round(min(line["bbox"][1] for line in caption_lines), 3),
                round(max(line["bbox"][2] for line in caption_lines), 3),
                round(max(line["bbox"][3] for line in caption_lines), 3),
            ],
            "source": "embedded_pdf_text",
            "status": "generated_not_verified",
        }
    else:
        # A few appendix tables use a running name rather than a TABLE n.n
        # caption (for example the medication table). Preserve that name when
        # it begins at the visual region's upper edge.
        generic_candidates = [
            line
            for line in lines
            if overlaps_x(line, bbox)
            and bbox[1] - 8 <= line["top"] <= bbox[1] + 15
            and re.match(r"(?i)^medications commonly used\b", line["text"])
        ]
        if generic_candidates:
            candidate = generic_candidates[0]
            caption = {
                "text": candidate["text"],
                "bbox_points": candidate["bbox"],
                "source": "embedded_pdf_text",
                "status": "generated_not_verified",
            }

    context_lines = [
        {
            "text": line["text"],
            "bbox_points": line["bbox"],
        }
        for line in lines
        if overlaps_x(line, bbox)
        and bbox[1] - 8 <= line["top"] <= bbox[1] + 45
        and (caption is None or line["text"] != caption["text"])
    ]
    return {
        "caption": caption,
        "nearby_pre_table_lines": context_lines,
    }


def extracted_rows(table_obj: Any, extracted: list[list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    row_objects = getattr(table_obj, "rows", [])
    for row_index, values in enumerate(extracted):
        cells: list[dict[str, Any]] = []
        geometry = row_objects[row_index].cells if row_index < len(row_objects) else []
        for column_index, value in enumerate(values):
            cell_bbox = geometry[column_index] if column_index < len(geometry) else None
            cells.append(
                {
                    "column_index": column_index,
                    "text": clean_cell(value),
                    "bbox_points": [round(float(v), 3) for v in cell_bbox] if cell_bbox else None,
                    "status": "generated_not_verified",
                }
            )
        rows.append(
            {
                "row_index": row_index,
                "cells": cells,
                "status": "generated_not_verified",
            }
        )
    return rows


def rows_as_text(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        " | ".join(cell["text"] for cell in row["cells"]).rstrip(" | ")
        for row in rows
    ).strip()


def extract_table_fragments(page: Any, bbox: list[float]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    crop = page.crop(tuple(bbox))
    layout_text = clean_cell(crop.extract_text(layout=True) or "")
    attempts: list[dict[str, Any]] = []
    chosen: tuple[str, dict[str, Any], list[Any], tuple[int, int, int]] | None = None
    # A real drawn grid is materially more reliable than a text-inferred grid
    # for this book.  Text strategies are retained as fallbacks for borderless
    # forms, but must not win merely because they split long words into more
    # artificial cells.
    method_rank = {
        "lines_lines": 4,
        "lines_text": 3,
        "text_lines": 2,
        "text_text": 1,
    }
    chosen_key: tuple[int, int, int, int] | None = None
    for method, settings in TABLE_SETTINGS:
        try:
            table_objects = crop.find_tables(settings)
            extracted = [table.extract() for table in table_objects]
            normalized = [
                [[clean_cell(value) for value in row] for row in table]
                for table in extracted
            ]
            score = table_score(normalized)
            attempts.append(
                {
                    "method": method,
                    "table_count": len(normalized),
                    "nonempty_cell_count": score[0],
                    "row_count": score[1],
                    "max_column_count": score[2],
                }
            )
            candidate_key = (method_rank[method], score[0], score[1], score[2])
            if score[0] and (chosen is None or candidate_key > chosen_key):
                chosen = (method, settings, table_objects, score)
                chosen_key = candidate_key
        except Exception as error:  # pragma: no cover - depends on malformed PDF regions
            attempts.append(
                {
                    "method": method,
                    "error": str(error),
                    "table_count": 0,
                    "nonempty_cell_count": 0,
                }
            )

    fragments: list[dict[str, Any]] = []
    if chosen is not None:
        method, settings, table_objects, score = chosen
        for fragment_index, table_obj in enumerate(table_objects):
            extracted = table_obj.extract()
            rows = extracted_rows(table_obj, extracted)
            if not any(cell["text"] for row in rows for cell in row["cells"]):
                continue
            fragments.append(
                {
                    "fragment_id": fragment_index + 1,
                    "extraction_method": method,
                    "table_bbox_points": [round(float(v), 3) for v in table_obj.bbox],
                    "layout_text": layout_text,
                    "layout_text_lines": layout_text.splitlines() if layout_text else [],
                    "rows": rows,
                    "content_text": layout_text or rows_as_text(rows),
                    "row_count": len(rows),
                    "max_column_count": max((len(row["cells"]) for row in rows), default=0),
                    "nonempty_cell_count": sum(
                        bool(cell["text"]) for row in rows for cell in row["cells"]
                    ),
                    "status": "generated_not_verified",
                }
            )

    if fragments:
        return fragments, {
            "selected_method": chosen[0] if chosen else None,
            "selected_score": list(chosen[3]) if chosen else [0, 0, 0],
            "attempts": attempts,
            "fallback_used": False,
        }

    # Some borderless/form-style tables do not form a pdfplumber grid. Keep a
    # line-preserving fallback so the region is still searchable and auditable.
    words = crop.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
    lines = group_words_into_lines(words)
    fallback_lines = [
        {
            "line_index": index,
            "text": line["text"],
            "bbox_points": line["bbox"],
            "status": "generated_not_verified",
        }
        for index, line in enumerate(lines)
        if line["text"]
    ]
    return [], {
        "selected_method": None,
        "selected_score": [0, 0, 0],
        "attempts": attempts,
        "fallback_used": True,
        "fallback_lines": fallback_lines,
        "fallback_note": "No reliable pdfplumber cell grid was found; embedded text lines and geometry are retained for manual reconstruction.",
    }


def page_text_map(page_text_path: Path) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for line in page_text_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            result[int(record["pdf_page"])] = record
    return result


def visual_cue_map(cues_path: Path) -> dict[int, list[dict[str, Any]]]:
    data = json.loads(cues_path.read_text(encoding="utf-8"))
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cue in data.get("cues", []):
        result[int(cue["pdf_page"])].append(cue)
    return result


def bbox_iou(first: list[float], second: list[float]) -> float:
    intersection = intersection_area(first, second)
    union = bbox_area(first) + bbox_area(second) - intersection
    return intersection / union if union else 0.0


def cue_for_visual(
    visual_label: str | None, bbox: list[float], cues: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not cues:
        return None
    if visual_label == "table":
        allowed_types = {"table"}
    elif visual_label in {"figure_title", "image", "chart"}:
        allowed_types = {"figure"}
    elif visual_label == "algorithm":
        allowed_types = {"algorithm"}
    else:
        allowed_types = set()
    candidates = [cue for cue in cues if cue.get("cue_type") in allowed_types]
    if not candidates:
        return None

    def score(cue: dict[str, Any]) -> tuple[float, float]:
        cue_bbox = [float(value) for value in cue.get("bbox_points", [])]
        overlap = bbox_iou(bbox, cue_bbox) if len(cue_bbox) == 4 else 0.0
        x_overlap = max(0.0, min(bbox[2], cue_bbox[2]) - max(bbox[0], cue_bbox[0])) if len(cue_bbox) == 4 else 0.0
        y_distance = min(abs(bbox[1] - cue_bbox[3]), abs(cue_bbox[1] - bbox[3])) if len(cue_bbox) == 4 else 9999.0
        # Captions usually sit immediately below an image or immediately above
        # a table; a title candidate itself should match by overlap.
        if visual_label == "figure_title":
            return (overlap * 1000 - y_distance, overlap)
        if visual_label == "table":
            return (overlap * 1000 - y_distance, x_overlap)
        return (x_overlap * 2 - y_distance, overlap)

    ranked = sorted(candidates, key=score, reverse=True)
    selected = ranked[0]
    cue_bbox = [float(value) for value in selected.get("bbox_points", [])]
    overlap = bbox_iou(bbox, cue_bbox) if len(cue_bbox) == 4 else 0.0
    x_overlap = max(0.0, min(bbox[2], cue_bbox[2]) - max(bbox[0], cue_bbox[0])) if len(cue_bbox) == 4 else 0.0
    y_distance = min(abs(bbox[1] - cue_bbox[3]), abs(cue_bbox[1] - bbox[3])) if len(cue_bbox) == 4 else 9999.0
    if visual_label == "figure_title" and overlap < 0.05:
        return None
    if visual_label == "table" and overlap < 0.01 and x_overlap < (bbox[2] - bbox[0]) * 0.25 and y_distance > 100:
        return None
    if visual_label in {"image", "chart"} and x_overlap < (bbox[2] - bbox[0]) * 0.25 and y_distance > 160:
        return None
    return selected


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    inventory_path = args.layout_inventory.expanduser().resolve()
    page_text_path = args.page_text.expanduser().resolve()
    cues_path = args.visual_cues.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    for path in (source, inventory_path, page_text_path, cues_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    text_by_page = page_text_map(page_text_path)
    cues_by_page = visual_cue_map(cues_path)
    all_candidates: list[dict[str, Any]] = []
    candidates_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for page_record in inventory.get("pages", []):
        pdf_page = int(page_record["pdf_page"])
        for candidate in page_record.get("visual_candidates", []):
            candidate_record = {
                "page_record": page_record,
                "pdf_page": pdf_page,
                "candidate": candidate,
            }
            all_candidates.append(candidate_record)
            candidates_by_page[pdf_page].append(candidate_record)

    canonical_table_by_layout_id: dict[str, dict[str, Any]] = {}
    for page_number, page_candidates in candidates_by_page.items():
        table_candidates = [
            record["candidate"]
            for record in page_candidates
            if record["candidate"].get("label") == "table"
        ]
        for candidate in table_candidates:
            duplicate_of = contained_duplicate(candidate, table_candidates)
            canonical_table_by_layout_id[str(candidate["layout_id"])] = {
                "canonical": duplicate_of is None,
                "duplicate_of_layout_id": duplicate_of,
            }

    canonical_groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for record in all_candidates:
        candidate = record["candidate"]
        if candidate.get("label") != "table":
            continue
        layout_id = str(candidate["layout_id"])
        table_meta = canonical_table_by_layout_id[layout_id]
        canonical_id = table_meta["duplicate_of_layout_id"] or layout_id
        canonical_groups[(record["pdf_page"], canonical_id)].append(record)

    visual_locations: list[dict[str, Any]] = []
    for index, record in enumerate(all_candidates, start=1):
        page_record = record["page_record"]
        candidate = record["candidate"]
        bbox_px = [round(float(value), 3) for value in candidate.get("bbox", [])]
        page_number = record["pdf_page"]
        page_text = text_by_page.get(page_number, {})
        page_width = 612.0
        page_height = 792.0
        # Actual page dimensions are filled from pdfplumber below.  These
        # values only act as a harmless placeholder until that pass runs.
        table_meta = canonical_table_by_layout_id.get(str(candidate["layout_id"]))
        canonical_id = None
        if candidate.get("label") == "table" and table_meta:
            canonical_id = table_meta["duplicate_of_layout_id"] or str(candidate["layout_id"])
        visual_locations.append(
            {
                "visual_id": f"STROKE5-VISUAL-{index:04d}",
                "source_layout_id": candidate.get("layout_id"),
                "pdf_page": page_number,
                "source_page_id": page_record.get("source_page_id"),
                "printed_page": page_text.get("printed_page", page_record.get("printed_page")),
                "page_type": page_text.get("page_type", page_record.get("page_type")),
                "part_number": page_text.get("part_number", page_record.get("part_number")),
                "chapter_number": page_text.get("chapter_number", page_record.get("chapter_number")),
                "chapter_title": page_text.get("chapter_title", page_record.get("chapter_title")),
                "section_id": page_text.get("section_id"),
                "section_title": page_text.get("section_title"),
                "label": candidate.get("label"),
                "visual_role": "table" if candidate.get("label") == "table" else "non_table_visual",
                "name": None,
                "visual_cue_id": None,
                "visual_cue_type": None,
                "confidence": candidate.get("confidence"),
                "bbox_px": bbox_px,
                "bbox_points": None,
                "location_description": None,
                "table_id": f"STROKE5-TABLE-{canonical_id}" if canonical_id else None,
                "duplicate_of_source_layout_id": table_meta["duplicate_of_layout_id"] if table_meta else None,
                "content_reconstruction": "table_reconstructed" if candidate.get("label") == "table" else "location_only",
                "status": "generated_not_verified",
                "verification_status": "generated_not_verified",
            }
        )

    tables: list[dict[str, Any]] = []
    with pdfplumber.open(source) as pdf:
        # Complete the location records with real page geometry and points.
        for location in visual_locations:
            page = pdf.pages[location["pdf_page"] - 1]
            page_record = next(
                item for item in inventory["pages"] if int(item["pdf_page"]) == location["pdf_page"]
            )
            points = point_bbox_from_px(
                location["bbox_px"], page_record["render"], float(page.width), float(page.height)
            )
            location["bbox_points"] = points
            location["location_description"] = human_location(points, float(page.width), float(page.height))
            cue = cue_for_visual(
                location.get("label"), points, cues_by_page.get(location["pdf_page"], [])
            )
            if cue:
                location["name"] = cue.get("line_text")
                location["visual_cue_id"] = cue.get("visual_cue_id")
                location["visual_cue_type"] = cue.get("cue_type")

        for table_index, ((page_number, canonical_layout_id), source_records) in enumerate(
            sorted(canonical_groups.items()), start=1
        ):
            page = pdf.pages[page_number - 1]
            page_record = source_records[0]["page_record"]
            candidate = next(
                record["candidate"]
                for record in source_records
                if str(record["candidate"]["layout_id"]) == canonical_layout_id
            )
            bbox_px = [round(float(value), 3) for value in candidate["bbox"]]
            bbox_points = point_bbox_from_px(
                bbox_px, page_record["render"], float(page.width), float(page.height)
            )
            context = caption_and_context(page, bbox_points)
            fragments, extraction = extract_table_fragments(page, bbox_points)
            table_id = f"STROKE5-TABLE-{canonical_layout_id}"
            table_cue = cue_for_visual(
                "table", bbox_points, cues_by_page.get(page_number, [])
            )
            table_name = (
                context["caption"]["text"]
                if context["caption"]
                else table_cue.get("line_text") if table_cue else None
            )
            tables.append(
                {
                    "table_id": table_id,
                    "source_layout_id": canonical_layout_id,
                    "source_candidate_ids": [
                        record["candidate"].get("layout_id") for record in source_records
                    ],
                    "pdf_page": page_number,
                    "source_page_id": page_record.get("source_page_id"),
                    "printed_page": text_by_page.get(page_number, {}).get(
                        "printed_page", page_record.get("printed_page")
                    ),
                    "part_number": text_by_page.get(page_number, {}).get(
                        "part_number", page_record.get("part_number")
                    ),
                    "chapter_number": text_by_page.get(page_number, {}).get(
                        "chapter_number", page_record.get("chapter_number")
                    ),
                    "chapter_title": text_by_page.get(page_number, {}).get(
                        "chapter_title", page_record.get("chapter_title")
                    ),
                    "section_id": text_by_page.get(page_number, {}).get("section_id"),
                    "section_title": text_by_page.get(page_number, {}).get("section_title"),
                    "bbox_px": bbox_px,
                    "bbox_points": bbox_points,
                    "location_description": human_location(
                        bbox_points, float(page.width), float(page.height)
                    ),
                    "name": table_name,
                    "caption": context["caption"],
                    "visual_cue_ids": [
                        cue["visual_cue_id"]
                        for cue in cues_by_page.get(page_number, [])
                        if cue.get("cue_type") == "table"
                        and (
                            (cue.get("label_candidate") or "").lower()
                            in (context["caption"]["text"].lower() if context["caption"] else "")
                            or bbox_iou(
                                bbox_points,
                                [float(value) for value in cue.get("bbox_points", [])],
                            )
                            > 0.01
                        )
                    ],
                    "nearby_pre_table_lines": context["nearby_pre_table_lines"],
                    "fragments": fragments,
                    "fragment_count": len(fragments),
                    "extraction": extraction,
                    "content_policy": "Table cell text and drawn cell geometry reconstructed from embedded PDF text/layout; manual verification is still required.",
                    "status": "generated_not_verified",
                    "verification_status": "generated_not_verified",
                }
            )

    # Add table ids to the now-complete visual records and index tables by page
    # for other AI systems that prefer page-first retrieval.
    table_by_layout = {table["source_layout_id"]: table for table in tables}
    page_visual_summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"pdf_page": None, "visual_ids": [], "table_ids": []}
    )
    for location in visual_locations:
        if location["table_id"]:
            canonical_id = location["table_id"].removeprefix("STROKE5-TABLE-")
            location["table_id"] = table_by_layout.get(canonical_id, {}).get("table_id")
        page_key = str(location["pdf_page"])
        summary = page_visual_summary[page_key]
        summary["pdf_page"] = location["pdf_page"]
        summary["visual_ids"].append(location["visual_id"])
        if location["table_id"] and location["table_id"] not in summary["table_ids"]:
            summary["table_ids"].append(location["table_id"])

    table_candidates = [record for record in all_candidates if record["candidate"].get("label") == "table"]
    non_table_locations = [
        record for record in all_candidates if record["candidate"].get("label") != "table"
    ]
    successful_tables = [table for table in tables if table["fragments"]]
    fallback_tables = [table for table in tables if table["extraction"].get("fallback_used")]
    output = {
        "schema_version": "vtc-stroke-rehabilitation-5e.visual-locations-and-tables.v1",
        "record_type": "all_visual_locations_and_reconstructed_tables",
        "book_id": "STROKE5",
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
        "source": {
            "source_id": "HHS4185-REF-STROKE-REHAB-5E",
            "filename": source.name,
            "path": str(source),
            "sha256": sha256_file(source),
        },
        "scope": {
            "pages": len(inventory.get("pages", [])),
            "visual_inventory_source": str(inventory_path),
            "visual_cue_source": str(cues_path),
            "table_reconstruction_source": "embedded PDF text and PDF geometry via pdfplumber",
            "non_table_visual_policy": "Record page and bounding-box location, label, and name/caption when available; do not OCR or reconstruct visual contents.",
        },
        "counts": {
            "pages": len(inventory.get("pages", [])),
            "visual_candidates": len(all_candidates),
            "visual_locations": len(visual_locations),
            "pages_with_visual_candidates": sum(
                bool(page.get("visual_candidates")) for page in inventory.get("pages", [])
            ),
            "table_candidates": len(table_candidates),
            "canonical_tables": len(tables),
            "canonical_tables_with_cell_fragments": len(successful_tables),
            "canonical_tables_using_line_fallback": len(fallback_tables),
            "non_table_visual_locations": len(non_table_locations),
            "non_table_visual_labels": len(
                {record["candidate"].get("label") for record in non_table_locations}
            ),
        },
        "visual_locations": visual_locations,
        "tables": tables,
        "page_visual_summary": [
            page_visual_summary[key] for key in sorted(page_visual_summary, key=lambda value: int(value))
        ],
        "retrieval_guidance": {
            "table_record_key": "table_id",
            "visual_record_key": "visual_id",
            "page_provenance_keys": ["pdf_page", "printed_page", "source_page_id"],
            "location_keys": ["bbox_px", "bbox_points", "location_description"],
            "answering_policy": "Read the reconstructed table rows and the source page before answering; cite table_id, PDF page, and printed page where available.",
            "verification_policy": "All table cells, captions, and visual interpretations are generated_not_verified until checked against the source page.",
        },
        "derived_from": {
            "source": str(source),
            "layout_inventory": str(inventory_path),
            "page_text": str(page_text_path),
            "visual_cues": str(cues_path),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

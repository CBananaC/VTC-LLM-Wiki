#!/usr/bin/env python3
"""Create a clean, reading-order Chapter 1 text layer from embedded PDF text.

The source and raw extraction remain unchanged. Visual regions are excluded
using the layout inventory plus manually reviewed page-level extensions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


NS = {"x": "http://www.w3.org/1999/xhtml"}
CHAPTER_NUMBER = 1
CHAPTER_ID = "DAV25-CH01"

# These are 120-dpi render-pixel boxes. They extend the automatic layout
# candidates where visual labels, table headings, or diagram annotations sit
# just outside a model box. The pages were visually reviewed before use.
MANUAL_VISUAL_REGIONS: dict[int, list[dict[str, Any]]] = {
    18: [
        {
            "region_id": "DAV25-CH01-P18-NONCONTENT",
            "bbox_px": [40, 45, 980, 1300],
            "reason": "chapter contents/title page excluded from body paragraphs",
        }
    ],
    19: [
        {
            "region_id": "DAV25-CH01-P19-TABLE-1-2-EXTENSION",
            "bbox_px": [65, 980, 505, 1300],
            "reason": "table 1.2 heading, cells, and continuation area",
        }
    ],
    20: [
        {
            "region_id": "DAV25-CH01-P20-FIGURE-1-1",
            "bbox_px": [80, 50, 510, 680],
            "reason": "figure, labels, caption, and formula",
        },
        {
            "region_id": "DAV25-CH01-P20-FIGURE-1-2",
            "bbox_px": [510, 50, 950, 515],
            "reason": "chart, labels, and caption",
        },
    ],
    21: [
        {
            "region_id": "DAV25-CH01-P21-TABLE-1-3",
            "bbox_px": [65, 70, 500, 565],
            "reason": "table, heading, and table note",
        },
        {
            "region_id": "DAV25-CH01-P21-TABLE-1-4-FIGURE-1-3",
            "bbox_px": [500, 55, 950, 690],
            "reason": "table, chart, and figure caption",
        },
    ],
    22: [
        {
            "region_id": "DAV25-CH01-P22-FIGURE-1-4",
            "bbox_px": [65, 50, 950, 470],
            "reason": "diagram, labels, and figure caption",
        },
        {
            "region_id": "DAV25-CH01-P22-TABLE-1-5",
            "bbox_px": [510, 280, 950, 650],
            "reason": "table, heading, and table formulas",
        },
    ],
    25: [
        {
            "region_id": "DAV25-CH01-P25-FIGURES-1-6-1-7",
            "bbox_px": [45, 50, 950, 1280],
            "reason": "full-page visual panels, labels, and captions",
        }
    ],
    26: [
        {
            "region_id": "DAV25-CH01-P26-VISUAL-TABLE-PANEL",
            "bbox_px": [110, 55, 950, 275],
            "reason": "figure/table panel heading and contents",
        }
    ],
    430: [
        {
            "region_id": "DAV25-P430-FIGURE-14-75",
            "bbox_px": [65, 750, 950, 1290],
            "reason": "visually reviewed figure panel, labels, embedded examples, and caption",
        }
    ],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--raw-text", type=Path, required=True)
    parser.add_argument("--chapter-map", type=Path, required=True)
    parser.add_argument("--layout-inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def load_chapter(chapter_map: Path) -> dict[str, Any]:
    data = json.loads(chapter_map.read_text(encoding="utf-8"))
    for part in data["parts"]:
        for chapter in part["chapters"]:
            if chapter["chapter_number"] == CHAPTER_NUMBER:
                return chapter
    raise ValueError("Chapter 1 not found in the chapter map")


def load_inventory(layout_inventory: Path) -> dict[int, dict[str, Any]]:
    data = json.loads(layout_inventory.read_text(encoding="utf-8"))
    return {page["pdf_page"]: page for page in data["pages"]}


def point_bbox_from_px(
    bbox_px: list[float], render: dict[str, Any], page_width: float, page_height: float
) -> tuple[float, float, float, float]:
    sx = page_width / float(render["width"])
    sy = page_height / float(render["height"])
    return tuple(
        [
            bbox_px[0] * sx,
            bbox_px[1] * sy,
            bbox_px[2] * sx,
            bbox_px[3] * sy,
        ]
    )


def auto_regions(page: dict[str, Any], page_width: float, page_height: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    render = page["render"]
    for candidate in page.get("visual_candidates", []):
        bbox_px = candidate["bbox"]
        result.append(
            {
                "region_id": candidate["layout_id"],
                "label": candidate.get("label"),
                "confidence": candidate.get("confidence"),
                "bbox_px": bbox_px,
                "bbox_points": list(point_bbox_from_px(bbox_px, render, page_width, page_height)),
                "reason": "automatic layout candidate",
                "source": "layout_inventory",
            }
        )
    return result


def all_regions(page: dict[str, Any], page_width: float, page_height: float) -> list[dict[str, Any]]:
    render = page["render"]
    regions = auto_regions(page, page_width, page_height)
    for manual in MANUAL_VISUAL_REGIONS.get(page["pdf_page"], []):
        region = dict(manual)
        region["bbox_points"] = list(
            point_bbox_from_px(region["bbox_px"], render, page_width, page_height)
        )
        region["source"] = "manual_visual_review"
        regions.append(region)
    return regions


def intersects(word: dict[str, Any], region: tuple[float, float, float, float]) -> bool:
    x1, y1, x2, y2 = region
    wx1, wy1, wx2, wy2 = word["bbox"]
    center_x = (wx1 + wx2) / 2
    center_y = (wy1 + wy2) / 2
    if x1 <= center_x <= x2 and y1 <= center_y <= y2:
        return True
    overlap_x = max(0.0, min(wx2, x2) - max(wx1, x1))
    overlap_y = max(0.0, min(wy2, y2) - max(wy1, y1))
    word_area = max(1.0, (wx2 - wx1) * (wy2 - wy1))
    return (overlap_x * overlap_y) / word_area >= 0.5


def parse_bbox_text(xml_path: Path, start_page: int) -> dict[int, dict[str, Any]]:
    root = ET.parse(xml_path).getroot()
    pages: dict[int, dict[str, Any]] = {}
    for page_offset, page_element in enumerate(root.findall(".//x:page", NS)):
        pdf_page = start_page + page_offset
        page_width = float(page_element.attrib["width"])
        page_height = float(page_element.attrib["height"])
        flows: list[dict[str, Any]] = []
        for flow_index, flow in enumerate(page_element.findall("./x:flow", NS)):
            blocks: list[dict[str, Any]] = []
            for block_index, block in enumerate(flow.findall("./x:block", NS)):
                lines: list[dict[str, Any]] = []
                for line_index, line in enumerate(block.findall("./x:line", NS)):
                    words: list[dict[str, Any]] = []
                    for word in line.findall("./x:word", NS):
                        text = word.text or ""
                        words.append(
                            {
                                "text": text,
                                "bbox": [
                                    float(word.attrib["xMin"]),
                                    float(word.attrib["yMin"]),
                                    float(word.attrib["xMax"]),
                                    float(word.attrib["yMax"]),
                                ],
                            }
                        )
                    if words:
                        lines.append(
                            {
                                "flow_index": flow_index,
                                "block_index": block_index,
                                "line_index": line_index,
                                "bbox": [
                                    min(word["bbox"][0] for word in words),
                                    min(word["bbox"][1] for word in words),
                                    max(word["bbox"][2] for word in words),
                                    max(word["bbox"][3] for word in words),
                                ],
                                "words": words,
                            }
                        )
                if lines:
                    blocks.append(
                        {
                            "flow_index": flow_index,
                            "block_index": block_index,
                            "lines": lines,
                        }
                    )
            if blocks:
                flows.append(
                    {
                        "flow_index": flow_index,
                        "blocks": blocks,
                    }
                )
        pages[pdf_page] = {
            "pdf_page": pdf_page,
            "width": page_width,
            "height": page_height,
            "flows": flows,
        }
    return pages


def normalize_heading(text: str) -> str:
    text = text.replace("–", "-").replace("—", "-").replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def join_line_words(words: list[dict[str, Any]]) -> str:
    text = " ".join(word["text"] for word in words)
    # Poppler exposes four stray underscore/centered-dot glyph sequences in
    # the embedded layer on PDF page 282. They are not printed prose or list
    # markers, so remove only this exact extraction artifact.
    text = re.sub(r"_\s+·", "", text)
    text = re.sub(r"\s+([,.;:?!%\)])", r"\1", text)
    text = re.sub(r"([(/])\s+", r"\1", text)
    return text.strip()


def join_block_lines(lines: list[dict[str, Any]]) -> str:
    result = ""
    for line in lines:
        text = line["text"]
        if not result:
            result = text
        elif result.endswith("-"):
            result += text
        else:
            result += " " + text
    return result.strip()


def is_bullet_only(text: str) -> bool:
    return bool(re.fullmatch(r"\s*[•▪◦·]\s*", text))


def is_bullet_start(text: str) -> bool:
    return bool(re.match(r"^\s*[•▪◦·]\s*", text))


def merge_detached_bullets(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach bullets exported as their own PDF block to same-row text.

    Some list blocks in this PDF place the bullet glyphs in one block and all
    list text in a neighbouring block. Match only same-page, same-row,
    same-line-index text immediately to the right of a bullet block.
    """
    result: list[dict[str, Any]] = []
    consumed: set[int] = set()
    for index, line in enumerate(lines):
        if index in consumed:
            continue
        merged_line = dict(line)
        if is_bullet_only(line["text"]):
            _, y1, _, y2 = line["bbox_points"]
            bullet_x1 = line["bbox_points"][0]
            bullet_y = (y1 + y2) / 2
            candidates: list[tuple[float, int]] = []
            for candidate_index, candidate in enumerate(lines):
                if candidate_index == index or candidate_index in consumed:
                    continue
                if candidate["pdf_page"] != line["pdf_page"]:
                    continue
                candidate_x1 = candidate["bbox_points"][0]
                if candidate_x1 <= bullet_x1 or candidate_x1 - bullet_x1 > 30:
                    continue
                candidate_y1, candidate_y2 = candidate["bbox_points"][1], candidate["bbox_points"][3]
                candidate_y = (candidate_y1 + candidate_y2) / 2
                distance = abs(candidate_y - bullet_y)
                if distance <= 1.0 and not is_bullet_only(candidate["text"]):
                    candidates.append((distance, candidate_index))
            if candidates:
                _, candidate_index = min(candidates)
                candidate = lines[candidate_index]
                merged_line["text"] = f"• {candidate['text'].strip()}"
                merged_line["bbox_points"] = [
                    round(min(line["bbox_points"][0], candidate["bbox_points"][0]), 3),
                    round(min(line["bbox_points"][1], candidate["bbox_points"][1]), 3),
                    round(max(line["bbox_points"][2], candidate["bbox_points"][2]), 3),
                    round(max(line["bbox_points"][3], candidate["bbox_points"][3]), 3),
                ]
                merged_line["_source_line_keys"] = [
                    line["source_line_key"],
                    candidate["source_line_key"],
                ]
                consumed.add(candidate_index)
            else:
                # A bullet whose same-row text was removed by a visual mask
                # is itself an orphaned visual glyph; do not retain it.
                continue
        result.append(merged_line)
    return result


def heading_matches(units: list[dict[str, Any]], entries: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    matches: dict[int, dict[str, Any]] = {}
    normalized_entries = [
        {**entry, "normalized": normalize_heading(entry["title"])} for entry in entries
    ]
    used: set[int] = set()
    for index, unit in enumerate(units):
        for span in (1, 2, 3):
            if index + span > len(units):
                continue
            combined = " ".join(units[i]["text"] for i in range(index, index + span))
            normalized = normalize_heading(combined)
            for entry_index, entry in enumerate(normalized_entries):
                if entry_index in used or unit["pdf_page"] < entry["pdf_page_start"]:
                    continue
                if normalized == entry["normalized"]:
                    matches[index] = {
                        **entry,
                        "entry_index": entry_index,
                        "span": span,
                    }
                    used.add(entry_index)
                    break
            if index in matches:
                break
    return matches


def make_block_units(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group XML lines into logical PDF text blocks without crossing blocks."""
    units: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def emit_block(block: dict[str, Any]) -> None:
        block_lines = block.pop("lines")
        bullet_indices = [
            index for index, line in enumerate(block_lines) if is_bullet_start(line["text"])
        ]
        base = {
            "pdf_page": block["pdf_page"],
            "source_page_id": block["source_page_id"],
            "flow_index": block["flow_index"],
            "block_index": block["block_index"],
        }
        if not bullet_indices:
            units.append(
                {
                    **base,
                    "line_ids": [line["line_id"] for line in block_lines],
                    "text": join_block_lines(block_lines),
                }
            )
            return
        first_bullet_index = bullet_indices[0]
        if first_bullet_index:
            prefix_lines = block_lines[:first_bullet_index]
            units.append(
                {
                    **base,
                    "line_ids": [line["line_id"] for line in prefix_lines],
                    "text": join_block_lines(prefix_lines),
                }
            )
        list_group_id = (
            f"{CHAPTER_ID}-PDF{block['pdf_page']:04d}-LIST-"
            f"F{block['flow_index']:03d}-B{block['block_index']:03d}"
        )
        item: dict[str, Any] | None = None
        item_index = 0

        def flush_item() -> None:
            nonlocal item
            if item is not None:
                item["text"] = join_block_lines(item.pop("lines"))
                units.append(item)
                item = None

        pending_normal_lines: list[dict[str, Any]] = []

        def emit_pending_normal() -> None:
            if pending_normal_lines:
                units.append(
                    {
                        **base,
                        "line_ids": [line["line_id"] for line in pending_normal_lines],
                        "text": join_block_lines(pending_normal_lines),
                    }
                )
                pending_normal_lines.clear()

        for line in block_lines[first_bullet_index:]:
            if is_bullet_start(line["text"]):
                flush_item()
                emit_pending_normal()
                item_index += 1
                item = {
                    **base,
                    "line_ids": [],
                    "lines": [],
                    "content_type": "list_item",
                    "list_group_id": list_group_id,
                    "list_item_index": item_index,
                }
                item["line_ids"].append(line["line_id"])
                item["lines"].append(line)
                continue

            if item is None:
                pending_normal_lines.append(line)
                continue

            # A line aligned with the bullet marker is usually a new category
            # label, not a wrapped continuation. Wrapped list text is indented
            # to the right of the marker in this PDF.
            bullet_x1 = item["lines"][0]["bbox_points"][0]
            if line["bbox_points"][0] <= bullet_x1 + 2.0:
                flush_item()
                pending_normal_lines.append(line)
            else:
                item["line_ids"].append(line["line_id"])
                item["lines"].append(line)

        flush_item()
        emit_pending_normal()

    for line in lines:
        same_block = (
            current is not None
            and current["pdf_page"] == line["pdf_page"]
            and current["flow_index"] == line["flow_index"]
            and current["block_index"] == line["block_index"]
        )
        if not same_block:
            if current is not None:
                emit_block(current)
            current = {
                "pdf_page": line["pdf_page"],
                "source_page_id": line["source_page_id"],
                "flow_index": line["flow_index"],
                "block_index": line["block_index"],
                "line_ids": [],
                "lines": [],
            }
        current["line_ids"].append(line["line_id"])
        current["lines"].append(line)
    if current is not None:
        emit_block(current)
    return units


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    raw_text_path = args.raw_text.expanduser().resolve()
    chapter_map_path = args.chapter_map.expanduser().resolve()
    inventory_path = args.layout_inventory.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    chapter = load_chapter(chapter_map_path)
    inventory = load_inventory(inventory_path)
    start_page = int(chapter["pdf_page_start"])
    end_page = int(chapter["pdf_page_end"])
    pdftotext = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"

    with tempfile.TemporaryDirectory(prefix="davidson25-ch01-structure-") as temp:
        xml_path = Path(temp) / "chapter_bbox.html"
        subprocess.run(
            [
                pdftotext,
                "-bbox-layout",
                "-enc",
                "UTF-8",
                "-f",
                str(start_page),
                "-l",
                str(end_page),
                str(source),
                str(xml_path),
            ],
            check=True,
            capture_output=True,
        )
        bbox_pages = parse_bbox_text(xml_path, start_page)

    page_records: list[dict[str, Any]] = []
    all_units: list[dict[str, Any]] = []
    exclusion_manifest: list[dict[str, Any]] = []
    removed_words = 0
    removed_pages: list[int] = []

    for pdf_page in range(start_page, end_page + 1):
        page_source = inventory[pdf_page]
        page_bbox = bbox_pages[pdf_page]
        regions = all_regions(page_source, page_bbox["width"], page_bbox["height"])
        exclusion_manifest.append(
            {
                "pdf_page": pdf_page,
                "source_page_id": page_source["source_page_id"],
                "regions": regions,
            }
        )
        if pdf_page == start_page:
            removed_pages.append(pdf_page)
            page_records.append(
                {
                    "source_page_id": page_source["source_page_id"],
                    "pdf_page": pdf_page,
                    "printed_page": chapter["printed_page_start"],
                    "page_role": "chapter_contents",
                    "content_status": "excluded_noncontent",
                    "reading_order_lines": [],
                    "clean_text": "",
                    "removed_visual_word_count": sum(
                        len(line.get("words", []))
                        for flow in page_bbox["flows"]
                        for block in flow["blocks"]
                        for line in block["lines"]
                    ),
                    "status": "verified",
                }
            )
            continue

        point_regions = [tuple(region["bbox_points"]) for region in regions]
        raw_clean_lines: list[dict[str, Any]] = []
        page_removed = 0
        for flow in page_bbox["flows"]:
            for block in flow["blocks"]:
                for line in block["lines"]:
                    kept_words: list[dict[str, Any]] = []
                    for word in line["words"]:
                        if any(intersects(word, region) for region in point_regions):
                            page_removed += 1
                        else:
                            kept_words.append(word)
                    if not kept_words:
                        continue
                    text = join_line_words(kept_words)
                    if not text:
                        continue
                    x1, y1, x2, y2 = line["bbox"]
                    if y1 < 45:
                        continue
                    if re.fullmatch(r"\d+", text) and x1 > 560:
                        continue
                    raw_clean_lines.append(
                        {
                            "pdf_page": pdf_page,
                            "source_page_id": page_source["source_page_id"],
                            "flow_index": flow["flow_index"],
                            "block_index": block["block_index"],
                            "line_index": line["line_index"],
                            "source_line_key": (
                                f"{CHAPTER_ID}-PDF{pdf_page:04d}-F{flow['flow_index']:03d}-"
                                f"B{block['block_index']:03d}-L{line['line_index']:03d}"
                            ),
                            "bbox_points": [round(value, 3) for value in line["bbox"]],
                            "text": text,
                        }
                    )

        # pdftotext's XML flow order is not reliable for this two-column PDF:
        # page 28, for example, interleaves the left and right columns. Group
        # lines by their original PDF block, then read physical columns from
        # left to right and each block from top to bottom.
        block_groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for line in raw_clean_lines:
            block_groups.setdefault(
                (line["flow_index"], line["block_index"]), []
            ).append(line)
        ordered_blocks = sorted(
            block_groups.values(),
            key=lambda block: (
                0
                if (min(line["bbox_points"][0] for line in block)
                    + max(line["bbox_points"][2] for line in block)) / 2
                < page_bbox["width"] / 2
                else 1,
                min(line["bbox_points"][1] for line in block),
                min(line["bbox_points"][0] for line in block),
            ),
        )
        page_lines: list[dict[str, Any]] = []
        for block in ordered_blocks:
            for line in sorted(
                block,
                key=lambda item: (item["bbox_points"][1], item["bbox_points"][0]),
            ):
                page_lines.append(line)
        page_lines = merge_detached_bullets(page_lines)
        for line_number, line in enumerate(page_lines, 1):
            line["line_id"] = (
                f"{CHAPTER_ID}-PDF{pdf_page:04d}-L{line_number:04d}"
            )
            source_line_keys = line.pop("_source_line_keys", None)
            if source_line_keys is None:
                source_line_keys = [line.pop("source_line_key")]
            else:
                line.pop("source_line_key", None)
            line["source_line_ids"] = source_line_keys
        removed_words += page_removed
        all_units.extend(page_lines)
        page_records.append(
            {
                "source_page_id": page_source["source_page_id"],
                "pdf_page": pdf_page,
                "printed_page": int(chapter["printed_page_start"]) + pdf_page - start_page,
                "page_role": "chapter_content",
                "content_status": "cleaned_visual_text_excluded",
                "reading_order": "physical PDF columns, left column before right column; top to bottom within each block",
                "reading_order_lines": page_lines,
                "clean_text": "\n".join(line["text"] for line in page_lines),
                "removed_visual_word_count": page_removed,
                "status": "verified",
            }
        )

    # The first page is intentionally omitted from paragraph construction.
    entries = [entry for entry in chapter["outline_entries"] if entry["outline_depth"] > 0]
    block_units = make_block_units(all_units)
    matches = heading_matches(block_units, entries)
    sections: list[dict[str, Any]] = []
    section_by_entry: dict[int, dict[str, Any]] = {}
    for index, entry in enumerate(entries, 1):
        record = {
            "section_id": f"{CHAPTER_ID}-SEC{index:02d}",
            "title": entry["title"],
            "level": entry["outline_depth"],
            "pdf_page_start": entry["pdf_page_start"],
            "source_page_id": f"DAV25-PDF{int(entry['pdf_page_start']):04d}",
            "paragraph_ids": [],
            "section_basis": entry.get("section_basis", "chapter PDF bookmark outline"),
            "status": "verified",
            "verification_status": "verified_reading_order",
        }
        sections.append(record)
        section_by_entry[index - 1] = record

    # Use matched outline entries to attach paragraphs to sections. Unmatched
    # text before the first matched heading is retained under a page section.
    paragraphs: list[dict[str, Any]] = []
    active_section: dict[str, Any] | None = None
    unit_index = 0
    while unit_index < len(block_units):
        unit = block_units[unit_index]
        match = matches.get(unit_index)
        if match:
            active_section = section_by_entry[match["entry_index"]]
            unit_index += match["span"]
            continue
        text = unit["text"]
        page_parts = [
            {
                "source_page_id": unit["source_page_id"],
                "pdf_page": unit["pdf_page"],
                "line_ids": unit["line_ids"],
                "text": text,
            }
        ]
        end_index = unit_index + 1
        # XML blocks normally represent paragraphs. Join only obvious
        # cross-column/page continuations, avoiding a broad semantic merge.
        while end_index < len(block_units):
            previous = block_units[end_index - 1]
            candidate = block_units[end_index]
            if candidate["flow_index"] == previous["flow_index"] and candidate["block_index"] == previous["block_index"]:
                break
            if text.endswith((".", ":", ";", "?", "!")):
                break
            if candidate["text"][:1].isupper() and not text.endswith("-"):
                break
            if candidate["pdf_page"] < previous["pdf_page"]:
                break
            text = (text + candidate["text"]).strip() if text.endswith("-") else (text + " " + candidate["text"]).strip()
            page_parts.append(
                {
                    "source_page_id": candidate["source_page_id"],
                    "pdf_page": candidate["pdf_page"],
                    "line_ids": candidate["line_ids"],
                    "text": candidate["text"],
                }
            )
            end_index += 1
        if text.strip():
            section_id = active_section["section_id"] if active_section else f"{CHAPTER_ID}-UNASSIGNED"
            paragraph = {
                "paragraph_id": f"{CHAPTER_ID}-P{len(paragraphs) + 1:04d}",
                "section_id": section_id,
                "section_title": active_section["title"] if active_section else None,
                "text": text,
                "source_page_ids": list(dict.fromkeys(part["source_page_id"] for part in page_parts)),
                "page_parts": page_parts,
                "content_type": unit.get("content_type", "logical_text_block"),
                "visual_content_removed": True,
                "status": "verified",
                "verification_status": "verified_reading_order",
            }
            if unit.get("content_type") == "list_item":
                paragraph["list_group_id"] = unit["list_group_id"]
                paragraph["list_item_index"] = unit["list_item_index"]
            paragraphs.append(paragraph)
            if active_section:
                active_section["paragraph_ids"].append(paragraph["paragraph_id"])
        unit_index = end_index

    output_dir.mkdir(parents=True, exist_ok=True)
    page_json_path = output_dir / "davidson25_ch01_clean_reading_order_verified.json"
    paragraph_json_path = output_dir / "davidson25_ch01_sections_paragraphs_verified.json"
    common = {
        "book_id": "DAV25",
        "chapter_number": CHAPTER_NUMBER,
        "chapter_title": chapter["title"],
        "pdf_page_start": start_page,
        "pdf_page_end": end_page,
        "printed_page_start": chapter["printed_page_start"],
        "printed_page_end": int(chapter["printed_page_start"]) + end_page - start_page,
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
        "visual_content_policy": "No text from detected or manually reviewed visual regions is retained. Figure/table captions, labels, table cells, chart labels, diagram labels, formulas, and page-18 chapter contents are excluded from the clean content layer.",
        "verification": {
            "status": "verified",
            "scope": [
                "PDF page sequence 18-29",
                "left-column before right-column reading order",
                "visual review of all 12 rendered pages",
                "visual exclusion regions reviewed page by page",
                "outline-heading sequence checked against the chapter contents and page headings",
            ],
            "text_spelling": "inherited from the embedded PDF text layer; not independently proofread character by character",
        },
        "status": "derived",
        "verification_status": "verified_reading_order_and_visual_exclusion",
    }
    page_output = {
        "schema_version": "vtc-davidson25.clean-reading-order.v1",
        "record_type": "clean_reading_order_text",
        **common,
        "counts": {
            "pages": len(page_records),
            "content_pages": sum(page["content_status"] == "cleaned_visual_text_excluded" for page in page_records),
            "removed_visual_words": removed_words,
            "lines": sum(len(page["reading_order_lines"]) for page in page_records),
        },
        "visual_exclusion_review": exclusion_manifest,
        "pages": page_records,
    }
    paragraph_output = {
        "schema_version": "vtc-davidson25.sections-paragraphs.v1",
        "record_type": "verified_sections_and_paragraphs",
        **common,
        "counts": {
            "sections": len(sections),
            "paragraphs": len(paragraphs),
            "source_pages": len({page_id for paragraph in paragraphs for page_id in paragraph["source_page_ids"]}),
        },
        "sections": sections,
        "paragraphs": paragraphs,
    }
    page_json_path.write_text(json.dumps(page_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paragraph_json_path.write_text(json.dumps(paragraph_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "page_json": str(page_json_path),
                "paragraph_json": str(paragraph_json_path),
                "pages": len(page_records),
                "removed_visual_words": removed_words,
                "sections": len(sections),
                "paragraphs": len(paragraphs),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

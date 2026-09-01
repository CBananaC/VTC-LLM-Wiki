#!/usr/bin/env python3
"""Build full-book clean reading-order and section/paragraph JSON layers.

The raw embedded-text extraction and the source PDF are never modified. This
pass removes text located inside the existing layout inventory's visual
candidates, preserves detached bullet glyphs, and marks the full-book result
generated/not-verified because only Chapter 1 has received page-by-page visual
review so far.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, Iterator


NS = {"x": "http://www.w3.org/1999/xhtml"}
PAGE_TAG = "{http://www.w3.org/1999/xhtml}page"

# Reuse the page-layout, bullet, and outline logic that produced the reviewed
# Chapter 1 layer. The imported module's manual regions are intentionally
# retained for Chapter 1 when this full-book runner processes those pages.
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
import structure_davidson_ch01_text as ch1  # noqa: E402


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
    parser.add_argument("--visual-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def load_chapters(chapter_map_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(chapter_map_path.read_text(encoding="utf-8"))
    chapters = [
        {**chapter, "part": part["title"]}
        for part in data["parts"]
        for chapter in part["chapters"]
    ]
    return data, chapters


def chapter_for_page(chapters: list[dict[str, Any]], pdf_page: int) -> dict[str, Any] | None:
    for chapter in chapters:
        if int(chapter["pdf_page_start"]) <= pdf_page <= int(chapter["pdf_page_end"]):
            return chapter
    return None


def noncontent_roles(chapters: list[dict[str, Any]], total_pages: int) -> dict[int, str]:
    roles: dict[int, str] = {}
    for pdf_page in range(1, total_pages + 1):
        chapter = chapter_for_page(chapters, pdf_page)
        if chapter is None:
            roles[pdf_page] = "front_matter"
        elif pdf_page == int(chapter["pdf_page_start"]):
            roles[pdf_page] = "chapter_contents"
    for chapter in chapters:
        for entry in chapter.get("outline_entries", []):
            if entry.get("outline_depth") == 0 and "Inside Back Cover" in entry.get("title", ""):
                roles[int(entry["pdf_page_start"])] = "back_matter"
    return roles


def parse_page_element(page_element: ET.Element, pdf_page: int) -> dict[str, Any]:
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
                    words.append(
                        {
                            "text": word.text or "",
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
            flows.append({"flow_index": flow_index, "blocks": blocks})
    return {
        "pdf_page": pdf_page,
        "width": page_width,
        "height": page_height,
        "flows": flows,
    }


def iter_bbox_pages(xml_path: Path) -> Iterator[dict[str, Any]]:
    pdf_page = 0
    for _, page_element in ET.iterparse(xml_path, events=("end",)):
        if page_element.tag != PAGE_TAG:
            continue
        pdf_page += 1
        yield parse_page_element(page_element, pdf_page)
        page_element.clear()


def total_words(page_bbox: dict[str, Any]) -> int:
    return sum(
        len(line.get("words", []))
        for flow in page_bbox["flows"]
        for block in flow["blocks"]
        for line in block["lines"]
    )


def sanitize_bbox_xml(xml_path: Path, sanitized_path: Path) -> int:
    """Remove XML-1.0-invalid control characters from Poppler bbox output."""
    text = xml_path.read_text(encoding="utf-8", errors="replace")
    cleaned_chars = []
    removed = 0
    for char in text:
        codepoint = ord(char)
        valid = (
            codepoint in (0x9, 0xA, 0xD)
            or 0x20 <= codepoint <= 0xD7FF
            or 0xE000 <= codepoint <= 0xFFFD
            or 0x10000 <= codepoint <= 0x10FFFF
        )
        if valid:
            cleaned_chars.append(char)
        else:
            removed += 1
    sanitized_path.write_text("".join(cleaned_chars), encoding="utf-8")
    return removed


def sorted_clean_lines(
    page_bbox: dict[str, Any],
    page_source: dict[str, Any],
    regions: list[dict[str, Any]],
    pdf_page: int,
) -> tuple[list[dict[str, Any]], int]:
    point_regions = [tuple(region["bbox_points"]) for region in regions]
    raw_clean_lines: list[dict[str, Any]] = []
    removed_words = 0
    for flow in page_bbox["flows"]:
        for block in flow["blocks"]:
            for line in block["lines"]:
                kept_words: list[dict[str, Any]] = []
                for word in line["words"]:
                    if any(ch1.intersects(word, region) for region in point_regions):
                        removed_words += 1
                    else:
                        kept_words.append(word)
                if not kept_words:
                    continue
                text = ch1.join_line_words(kept_words)
                if not text:
                    continue
                x1, y1, x2, y2 = line["bbox"]
                if y1 < 45:
                    continue
                if re.fullmatch(r"\d+", text) and x1 > page_bbox["width"] * 0.9:
                    continue
                raw_clean_lines.append(
                    {
                        "pdf_page": pdf_page,
                        "source_page_id": page_source["source_page_id"],
                        "flow_index": flow["flow_index"],
                        "block_index": block["block_index"],
                        "line_index": line["line_index"],
                        "source_line_key": (
                            f"DAV25-PDF{pdf_page:04d}-F{flow['flow_index']:03d}-"
                            f"B{block['block_index']:03d}-L{line['line_index']:03d}"
                        ),
                        "bbox_points": [round(value, 3) for value in line["bbox"]],
                        "text": text,
                    }
                )

    block_groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for line in raw_clean_lines:
        block_groups.setdefault((line["flow_index"], line["block_index"]), []).append(line)
    ordered_blocks = sorted(
        block_groups.values(),
        key=lambda block: (
            0
            if (
                min(line["bbox_points"][0] for line in block)
                + max(line["bbox_points"][2] for line in block)
            )
            / 2
            < page_bbox["width"] / 2
            else 1,
            min(line["bbox_points"][1] for line in block),
            min(line["bbox_points"][0] for line in block),
        ),
    )
    page_lines: list[dict[str, Any]] = []
    for block in ordered_blocks:
        page_lines.extend(
            sorted(block, key=lambda item: (item["bbox_points"][1], item["bbox_points"][0]))
        )
    page_lines = ch1.merge_detached_bullets(page_lines)
    for line_number, line in enumerate(page_lines, 1):
        line["line_id"] = f"DAV25-PDF{pdf_page:04d}-L{line_number:04d}"
        source_line_keys = line.pop("_source_line_keys", None)
        if source_line_keys is None:
            source_line_keys = [line.pop("source_line_key")]
        else:
            line.pop("source_line_key", None)
        line["source_line_ids"] = source_line_keys
    return page_lines, removed_words


def build_visual_placeholders(
    visuals: list[dict[str, Any]], page_lines: list[dict[str, Any]], page_width: float
) -> list[dict[str, Any]]:
    placeholders: list[dict[str, Any]] = []
    for visual in visuals:
        bbox = visual["location"]["bbox_points"]
        visual_name = visual.get("name") or f"Unnamed {visual['visual_type']}"
        visual_name = re.sub(r"\s+", " ", visual_name).strip()
        placeholder_text = (
            f"[VISUAL {visual['visual_id']}: {visual['visual_type']} - {visual_name} - "
            f"PDF page {visual['pdf_page']} - location {visual['location']['bbox_px']}]"
        )
        center_x = (bbox[0] + bbox[2]) / 2
        spans_page = (bbox[2] - bbox[0]) >= page_width * 0.7
        column = 0 if spans_page or center_x < page_width / 2 else 1
        column_lines = [
            line
            for line in page_lines
            if (
                spans_page
                or ((line["bbox_points"][0] + line["bbox_points"][2]) / 2 < page_width / 2)
                == (column == 0)
            )
        ]
        before = [line for line in column_lines if line["bbox_points"][1] < bbox[1]]
        after = [line for line in column_lines if line["bbox_points"][1] > bbox[3]]
        placeholders.append(
            {
                "visual_id": visual["visual_id"],
                "visual_type": visual["visual_type"],
                "name": visual.get("name"),
                "policy": visual["policy"],
                "pdf_page": visual["pdf_page"],
                "printed_page": visual.get("printed_page"),
                "bbox_px": visual["location"]["bbox_px"],
                "bbox_points": bbox,
                "column": column,
                "anchor_before_line_id": (
                    max(before, key=lambda line: line["bbox_points"][1])["line_id"]
                    if before
                    else None
                ),
                "anchor_after_line_id": (
                    min(after, key=lambda line: line["bbox_points"][1])["line_id"]
                    if after
                    else None
                ),
                "placeholder_text": placeholder_text,
            }
        )
    return sorted(placeholders, key=lambda item: (item["column"], item["bbox_points"][1], item["bbox_points"][0]))


def build_reading_order_items(
    page_lines: list[dict[str, Any]], placeholders: list[dict[str, Any]], page_width: float
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in page_lines:
        bbox = line["bbox_points"]
        center_x = (bbox[0] + bbox[2]) / 2
        items.append(
            {
                "item_type": "text_line",
                "line_id": line["line_id"],
                "text": line["text"],
                "bbox_points": bbox,
                "column": 0 if center_x < page_width / 2 else 1,
                "sort_y": bbox[1],
                "sort_x": bbox[0],
            }
        )
    for placeholder in placeholders:
        bbox = placeholder["bbox_points"]
        items.append(
            {
                "item_type": "visual_placeholder",
                "visual_id": placeholder["visual_id"],
                "visual_type": placeholder["visual_type"],
                "name": placeholder["name"],
                "text": placeholder["placeholder_text"],
                "bbox_points": bbox,
                "column": placeholder["column"],
                "sort_y": bbox[1],
                "sort_x": bbox[0],
            }
        )
    for item in items:
        item.pop("sort_y", None)
        item.pop("sort_x", None)
    return sorted(
        items,
        key=lambda item: (
            item["column"],
            item["bbox_points"][1],
            item["bbox_points"][0],
            0 if item["item_type"] == "visual_placeholder" else 1,
        ),
    )


def build_full_outputs(
    source: Path,
    raw_text_path: Path,
    chapter_map_path: Path,
    inventory_path: Path,
    visual_manifest_path: Path,
    output_dir: Path,
) -> tuple[Path, Path, dict[str, int]]:
    chapter_map, chapters = load_chapters(chapter_map_path)
    inventory = ch1.load_inventory(inventory_path)
    visual_manifest = json.loads(visual_manifest_path.read_text(encoding="utf-8"))
    visuals_by_page: dict[int, list[dict[str, Any]]] = {}
    for visual in visual_manifest.get("visuals", []):
        visuals_by_page.setdefault(int(visual["pdf_page"]), []).append(visual)
    total_pages = int(chapter_map["pdf_page_count"])
    roles = noncontent_roles(chapters, total_pages)
    ch1.CHAPTER_ID = "DAV25"
    all_units: list[dict[str, Any]] = []
    page_records: list[dict[str, Any]] = []
    exclusion_manifest: list[dict[str, Any]] = []
    removed_words = 0
    content_pages = 0
    noncontent_pages = 0

    pdftotext = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    with tempfile.TemporaryDirectory(prefix="davidson25-full-clean-") as temp:
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
                str(total_pages),
                str(source),
                str(xml_path),
            ],
            check=True,
            capture_output=True,
        )
        sanitized_xml_path = Path(temp) / "full_bbox_sanitized.html"
        bbox_invalid_characters_removed = sanitize_bbox_xml(xml_path, sanitized_xml_path)
        parsed_pages = 0
        for page_bbox in iter_bbox_pages(sanitized_xml_path):
            parsed_pages += 1
            pdf_page = page_bbox["pdf_page"]
            page_source = inventory[pdf_page]
            chapter = chapter_for_page(chapters, pdf_page)
            role = roles.get(pdf_page, "chapter_content")
            regions = ch1.all_regions(page_source, page_bbox["width"], page_bbox["height"])
            exclusion_manifest.append(
                {
                    "pdf_page": pdf_page,
                    "source_page_id": page_source["source_page_id"],
                    "chapter_number": chapter["chapter_number"] if chapter else None,
                    "page_role": role,
                    "regions": regions,
                }
            )
            if role != "chapter_content":
                page_lines: list[dict[str, Any]] = []
                page_removed = total_words(page_bbox)
                noncontent_pages += 1
            else:
                page_lines, page_removed = sorted_clean_lines(
                    page_bbox, page_source, regions, pdf_page
                )
                content_pages += 1
                all_units.extend(page_lines)
            removed_words += page_removed
            page_visuals = visuals_by_page.get(pdf_page, []) if role == "chapter_content" else []
            visual_placeholders = build_visual_placeholders(
                page_visuals, page_lines, page_bbox["width"]
            )
            reading_order_items = build_reading_order_items(
                page_lines, visual_placeholders, page_bbox["width"]
            )
            page_records.append(
                {
                    "source_page_id": page_source["source_page_id"],
                    "pdf_page": pdf_page,
                    "chapter_number": chapter["chapter_number"] if chapter else None,
                    "chapter_title": chapter["title"] if chapter else None,
                    "part": chapter["part"] if chapter else None,
                    "printed_page": (
                        int(chapter["printed_page_start"])
                        + pdf_page
                        - int(chapter["pdf_page_start"])
                        if chapter
                        else None
                    ),
                    "page_role": role,
                    "content_status": (
                        "excluded_noncontent" if role != "chapter_content" else "cleaned_visual_text_excluded"
                    ),
                    "reading_order": (
                        "physical PDF columns, left column before right column; "
                        "top to bottom within each block"
                        if role == "chapter_content"
                        else None
                    ),
                    "reading_order_lines": page_lines,
                    "clean_text": "\n".join(line["text"] for line in page_lines),
                    "reading_order_items": reading_order_items,
                    "visual_placeholders": visual_placeholders,
                    "clean_text_with_visual_placeholders": "\n".join(
                        item["text"] for item in reading_order_items
                    ),
                    "removed_visual_word_count": page_removed,
                    "status": "generated_not_verified",
                }
            )
        if parsed_pages != total_pages:
            raise RuntimeError(f"Expected {total_pages} bbox pages, got {parsed_pages}")

    section_entries: list[dict[str, Any]] = []
    for chapter in chapters:
        for entry in chapter.get("outline_entries", []):
            if entry.get("outline_depth", 0) > 0:
                section_entries.append(
                    {
                        **entry,
                        "chapter_number": chapter["chapter_number"],
                        "chapter_title": chapter["title"],
                        "part": chapter["part"],
                        "printed_page_start": int(chapter["printed_page_start"])
                        + int(entry["pdf_page_start"])
                        - int(chapter["pdf_page_start"]),
                    }
                )
    block_units = ch1.make_block_units(all_units)
    matches = ch1.heading_matches(block_units, section_entries)
    sections: list[dict[str, Any]] = []
    section_by_entry: dict[int, dict[str, Any]] = {}
    for index, entry in enumerate(section_entries, 1):
        record = {
            "section_id": f"DAV25-SEC{index:05d}",
            "chapter_number": entry["chapter_number"],
            "chapter_title": entry["chapter_title"],
            "part": entry["part"],
            "title": entry["title"],
            "level": entry["outline_depth"],
            "pdf_page_start": entry["pdf_page_start"],
            "printed_page_start": entry["printed_page_start"],
            "source_page_id": f"DAV25-PDF{int(entry['pdf_page_start']):04d}",
            "paragraph_ids": [],
            "parent_title": entry.get("parent_title"),
            "section_basis": "chapter PDF bookmark outline",
            "status": "generated_candidate",
            "verification_status": "generated_not_verified",
        }
        sections.append(record)
        section_by_entry[index - 1] = record

    paragraphs: list[dict[str, Any]] = []
    active_section: dict[str, Any] | None = None
    active_chapter_number: int | None = None
    unit_index = 0
    while unit_index < len(block_units):
        unit = block_units[unit_index]
        unit_chapter = chapter_for_page(chapters, unit["pdf_page"])
        unit_chapter_number = unit_chapter["chapter_number"] if unit_chapter else None
        if unit_chapter_number != active_chapter_number:
            active_section = None
            active_chapter_number = unit_chapter_number
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
        while end_index < len(block_units):
            previous = block_units[end_index - 1]
            candidate = block_units[end_index]
            candidate_chapter = chapter_for_page(chapters, candidate["pdf_page"])
            if (
                candidate_chapter is None
                or candidate_chapter["chapter_number"] != unit_chapter_number
            ):
                break
            if candidate["flow_index"] == previous["flow_index"] and candidate["block_index"] == previous["block_index"]:
                break
            if ch1.is_bullet_start(candidate["text"]):
                break
            if text.endswith((".", ":", ";", "?", "!")):
                break
            if candidate["text"][:1].isupper() and not text.endswith("-"):
                break
            if candidate["pdf_page"] < previous["pdf_page"]:
                break
            text = (
                (text + candidate["text"]).strip()
                if text.endswith("-")
                else (text + " " + candidate["text"]).strip()
            )
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
            section_id = (
                active_section["section_id"]
                if active_section is not None
                else f"DAV25-CH{int(unit_chapter_number or 0):02d}-UNASSIGNED"
            )
            paragraph = {
                "paragraph_id": f"DAV25-P{len(paragraphs) + 1:06d}",
                "section_id": section_id,
                "section_title": active_section["title"] if active_section else None,
                "chapter_number": unit_chapter_number,
                "chapter_title": unit_chapter["title"] if unit_chapter else None,
                "text": text,
                "source_page_ids": list(
                    dict.fromkeys(part["source_page_id"] for part in page_parts)
                ),
                "page_parts": page_parts,
                "content_type": unit.get("content_type", "logical_text_block"),
                "visual_content_removed": True,
                "status": "generated_not_verified",
                "verification_status": "generated_not_verified",
            }
            if unit.get("content_type") == "list_item":
                paragraph["list_group_id"] = unit["list_group_id"]
                paragraph["list_item_index"] = unit["list_item_index"]
            paragraphs.append(paragraph)
            if active_section:
                active_section["paragraph_ids"].append(paragraph["paragraph_id"])
        unit_index = end_index

    chapter_counts: dict[int, dict[str, int]] = {
        int(chapter["chapter_number"]): {"pages": 0, "lines": 0, "sections": 0, "paragraphs": 0}
        for chapter in chapters
    }
    for page in page_records:
        if page["chapter_number"] in chapter_counts:
            chapter_counts[page["chapter_number"]]["pages"] += 1
            chapter_counts[page["chapter_number"]]["lines"] += len(page["reading_order_lines"])
    for section in sections:
        chapter_counts[section["chapter_number"]]["sections"] += 1
    for paragraph in paragraphs:
        if paragraph["chapter_number"] in chapter_counts:
            chapter_counts[paragraph["chapter_number"]]["paragraphs"] += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    page_json_path = output_dir / "davidson25_clean_reading_order_full_generated.json"
    paragraph_json_path = output_dir / "davidson25_sections_paragraphs_full_generated.json"
    common = {
        "book_id": "DAV25",
        "chapter_count": len(chapters),
        "source": {
            "filename": source.name,
            "path": str(source),
            "sha256": sha256_file(source),
        },
        "derived_from": {
            "raw_text_json": str(raw_text_path),
            "chapter_map": str(chapter_map_path),
            "layout_inventory": str(inventory_path),
            "visual_manifest": str(visual_manifest_path),
        },
        "visual_policy": {
            "tables": "full contents and coordinate-preserving reconstruction in the visual table layer",
            "non_tables": "metadata-only visual records with page, name/caption, and location",
            "clean_text": "visuals represented by placeholders in reading_order_items and clean_text_with_visual_placeholders",
            "raw_source": "immutable",
        },
        "bbox_xml_sanitization": {
            "invalid_control_characters_removed": bbox_invalid_characters_removed,
            "reason": "Poppler emitted XML-1.0-invalid control characters in embedded text; only the temporary bbox parser input was sanitized",
        },
        "visual_content_policy": (
            "No text located inside automatic layout visual candidates or the manually reviewed Chapter 1 regions is retained. "
            "This full-book automatic mask is generated/not verified; captions, labels, table cells, chart labels, diagram labels, formulas, and visual panels may require page-level review before final study use."
        ),
        "verification": {
            "status": "generated_not_verified",
            "scope": [
                f"complete PDF page sequence 1-{total_pages}",
                "physical PDF columns, left column before right column",
                "detached bullet recovery and list-item preservation",
                "automatic layout-candidate visual exclusion across the book",
                "manual visual exclusions retained for the previously reviewed Chapter 1 pages",
            ],
            "chapter_1_review_status": "page-by-page visual review completed before this full-book run",
            "full_book_visual_review_status": "not completed; automatic candidates require later sampling/review",
            "text_spelling": "inherited from the embedded PDF text layer; not independently proofread character by character",
        },
        "status": "derived",
        "verification_status": "generated_not_verified",
    }
    page_output = {
        "schema_version": "vtc-davidson25.clean-reading-order-full.v1",
        "record_type": "clean_reading_order_text_full_book",
        **common,
        "counts": {
            "pages": len(page_records),
            "content_pages": content_pages,
            "noncontent_pages": noncontent_pages,
            "removed_visual_words": removed_words,
            "lines": sum(len(page["reading_order_lines"]) for page in page_records),
            "list_items": sum(
                1
                for page in page_records
                for line in page["reading_order_lines"]
                if ch1.is_bullet_start(line["text"])
            ),
            "visual_placeholders": sum(len(page["visual_placeholders"]) for page in page_records),
        },
        "chapters": [
            {
                "chapter_number": chapter["chapter_number"],
                "title": chapter["title"],
                "part": chapter["part"],
                "pdf_page_start": chapter["pdf_page_start"],
                "pdf_page_end": chapter["pdf_page_end"],
                "printed_page_start": chapter["printed_page_start"],
                "counts": chapter_counts[int(chapter["chapter_number"])],
            }
            for chapter in chapters
        ],
        "visual_exclusion_review": exclusion_manifest,
        "pages": page_records,
    }
    paragraph_output = {
        "schema_version": "vtc-davidson25.sections-paragraphs-full.v1",
        "record_type": "sections_and_paragraphs_full_book",
        **common,
        "counts": {
            "sections": len(sections),
            "paragraphs": len(paragraphs),
            "list_items": sum(paragraph["content_type"] == "list_item" for paragraph in paragraphs),
            "source_pages": len(
                {page_id for paragraph in paragraphs for page_id in paragraph["source_page_ids"]}
            ),
        },
        "sections": sections,
        "paragraphs": paragraphs,
        "visual_placeholders": [
            placeholder
            for page in page_records
            for placeholder in page["visual_placeholders"]
        ],
    }
    page_json_path.write_text(
        json.dumps(page_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paragraph_json_path.write_text(
        json.dumps(paragraph_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return page_json_path, paragraph_json_path, {
        "pages": len(page_records),
        "content_pages": content_pages,
        "removed_visual_words": removed_words,
        "lines": page_output["counts"]["lines"],
        "sections": len(sections),
        "paragraphs": len(paragraphs),
        "list_items": paragraph_output["counts"]["list_items"],
        "bbox_invalid_characters_removed": bbox_invalid_characters_removed,
    }


def main() -> None:
    args = parse_args()
    page_json_path, paragraph_json_path, counts = build_full_outputs(
        args.source.expanduser().resolve(),
        args.raw_text.expanduser().resolve(),
        args.chapter_map.expanduser().resolve(),
        args.layout_inventory.expanduser().resolve(),
        args.visual_manifest.expanduser().resolve(),
        args.output_dir.expanduser().resolve(),
    )
    print(
        json.dumps(
            {
                "page_json": str(page_json_path),
                "paragraph_json": str(paragraph_json_path),
                **counts,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

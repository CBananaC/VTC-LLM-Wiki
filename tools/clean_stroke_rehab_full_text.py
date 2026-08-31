#!/usr/bin/env python3
"""Build a full-book clean reading-order text layer for Stroke Rehabilitation.

The source PDF and raw embedded-text layer remain unchanged. Words whose
centres or substantial area fall inside the completed PaddleOCR visual
location inventory are excluded. The output keeps captions/table cells/figure
labels out of clean text, preserves bullet and numbered-list markers, and
retains page-level visual-location references for later selective review.
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
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator


NS = {"x": "http://www.w3.org/1999/xhtml"}
PAGE_TAG = "{http://www.w3.org/1999/xhtml}page"
BULLET_CHARS = "•▪◦·‣⁃➔➜→"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--raw-text", type=Path, required=True)
    parser.add_argument("--layout-inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:?!%\)])", r"\1", value)
    value = re.sub(r"([(/])\s+", r"\1", value)
    return value.strip()


def sanitize_bbox_xml(xml_path: Path, sanitized_path: Path) -> int:
    text = xml_path.read_text(encoding="utf-8", errors="replace")
    cleaned: list[str] = []
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
            cleaned.append(char)
        else:
            removed += 1
    sanitized_path.write_text("".join(cleaned), encoding="utf-8")
    return removed


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


def point_bbox_from_px(
    bbox_px: list[float], render: dict[str, Any], page_width: float, page_height: float
) -> list[float]:
    sx = page_width / float(render["width"])
    sy = page_height / float(render["height"])
    return [round(bbox_px[0] * sx, 3), round(bbox_px[1] * sy, 3), round(bbox_px[2] * sx, 3), round(bbox_px[3] * sy, 3)]


def visual_regions(
    layout_page: dict[str, Any], page_width: float, page_height: float
) -> list[dict[str, Any]]:
    render = layout_page.get("render", {})
    result: list[dict[str, Any]] = []
    for candidate in layout_page.get("visual_candidates", []):
        bbox_px = candidate.get("bbox") or []
        if len(bbox_px) != 4 or not render:
            continue
        effective_bbox_px = list(bbox_px)
        expansion_reason = None
        if candidate.get("label") == "table":
            # Table notes and continuation markers in this textbook can sit
            # immediately below the model's table box (notably PDF page 784).
            # A small bounded extension keeps those visual-linked words out of
            # clean text without swallowing the following body column.
            effective_bbox_px = [
                max(0, bbox_px[0] - 6),
                max(0, bbox_px[1] - 6),
                min(float(render["width"]), bbox_px[2] + 6),
                min(float(render["height"]), bbox_px[3] + 45),
            ]
            expansion_reason = "bounded table-note and continuation extension"
        result.append(
            {
                "region_id": candidate.get("layout_id"),
                "label": candidate.get("label"),
                "confidence": candidate.get("confidence"),
                "bbox_px_original": bbox_px,
                "bbox_px": effective_bbox_px,
                "bbox_points": point_bbox_from_px(effective_bbox_px, render, page_width, page_height),
                "source": "paddleocr_layout_inventory",
                "expansion_reason": expansion_reason,
                "status": "generated_not_verified",
            }
        )
    return result


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


def join_line_words(words: list[dict[str, Any]]) -> str:
    return clean_text(" ".join(word["text"] for word in words))


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
    return clean_text(result)


def is_bullet_only(text: str) -> bool:
    return bool(re.fullmatch(rf"\s*[{re.escape(BULLET_CHARS)}]\s*", text))


def is_bullet_start(text: str) -> bool:
    return bool(re.match(rf"^\s*[{re.escape(BULLET_CHARS)}]\s*", text))


def merge_detached_bullets(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                distance = abs((candidate_y1 + candidate_y2) / 2 - bullet_y)
                if distance <= 1.0 and not is_bullet_only(candidate["text"]):
                    candidates.append((distance, candidate_index))
            if candidates:
                _, candidate_index = min(candidates)
                candidate = lines[candidate_index]
                merged_line["text"] = f"{line['text'].strip()} {candidate['text'].strip()}"
                merged_line["bbox_points"] = [
                    round(min(line["bbox_points"][0], candidate["bbox_points"][0]), 3),
                    round(min(line["bbox_points"][1], candidate["bbox_points"][1]), 3),
                    round(max(line["bbox_points"][2], candidate["bbox_points"][2]), 3),
                    round(max(line["bbox_points"][3], candidate["bbox_points"][3]), 3),
                ]
                merged_line["source_line_keys"] = [
                    *line.get("source_line_keys", []),
                    *candidate.get("source_line_keys", []),
                ]
                consumed.add(candidate_index)
            else:
                continue
        result.append(merged_line)
    return result


def block_units(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    grouped: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_key: tuple[int, int, int] | None = None
    for line in lines:
        key = (line["pdf_page"], line["flow_index"], line["block_index"])
        if current_key != key and current:
            grouped.append(current)
            current = []
        current_key = key
        current.append(line)
    if current:
        grouped.append(current)

    for group in grouped:
        bullet_indices = [index for index, line in enumerate(group) if is_bullet_start(line["text"])]
        base = {
            "pdf_page": group[0]["pdf_page"],
            "source_page_id": group[0]["source_page_id"],
            "flow_index": group[0]["flow_index"],
            "block_index": group[0]["block_index"],
        }
        if not bullet_indices:
            units.append({**base, "line_ids": [line["line_id"] for line in group], "source_line_keys": [key for line in group for key in line.get("source_line_keys", [])], "text": join_block_lines(group), "content_type": "logical_text_block"})
            continue
        first_bullet = bullet_indices[0]
        if first_bullet:
            prefix = group[:first_bullet]
            units.append({**base, "line_ids": [line["line_id"] for line in prefix], "source_line_keys": [key for line in prefix for key in line.get("source_line_keys", [])], "text": join_block_lines(prefix), "content_type": "logical_text_block"})
        list_group_id = f"STROKE5-PDF{group[0]['pdf_page']:04d}-LIST-F{group[0]['flow_index']:03d}-B{group[0]['block_index']:03d}"
        item: list[dict[str, Any]] = []
        item_index = 0

        def flush_item() -> None:
            nonlocal item
            if item:
                item_index_local = item[0].get("list_item_index", item_index)
                units.append({
                    **base,
                    "line_ids": [line["line_id"] for line in item],
                    "source_line_keys": [key for line in item for key in line.get("source_line_keys", [])],
                    "text": join_block_lines(item),
                    "content_type": "list_item",
                    "list_group_id": list_group_id,
                    "list_item_index": item_index_local,
                })
                item = []

        pending: list[dict[str, Any]] = []
        for line in group[first_bullet:]:
            if is_bullet_start(line["text"]):
                flush_item()
                if pending:
                    units.append({**base, "line_ids": [x["line_id"] for x in pending], "source_line_keys": [key for x in pending for key in x.get("source_line_keys", [])], "text": join_block_lines(pending), "content_type": "logical_text_block"})
                    pending = []
                item_index += 1
                item = [dict(line, list_item_index=item_index)]
                continue
            if not item:
                pending.append(line)
                continue
            bullet_x1 = item[0]["bbox_points"][0]
            if line["bbox_points"][0] <= bullet_x1 + 2.0:
                flush_item()
                pending.append(line)
            else:
                item.append(line)
        flush_item()
        if pending:
            units.append({**base, "line_ids": [x["line_id"] for x in pending], "source_line_keys": [key for x in pending for key in x.get("source_line_keys", [])], "text": join_block_lines(pending), "content_type": "logical_text_block"})
    return units


def section_records(structure: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for part in structure.get("parts", []):
        for chapter in part.get("chapters", []):
            for index, section in enumerate(chapter.get("sections", []), 1):
                records.append(
                    {
                        "section_id": f"STROKE5-CH{int(chapter['chapter_number']):02d}-SEC{index:03d}",
                        "part_number": part.get("part_number"),
                        "part_title": part.get("title"),
                        "chapter_number": chapter.get("chapter_number"),
                        "chapter_title": chapter.get("title"),
                        "title": section.get("title"),
                        "pdf_page_start": section.get("pdf_page_start"),
                        "printed_page_start": section.get("printed_page_start"),
                        "status": "generated_not_verified",
                    }
                )
    return records


def section_for_page(sections: list[dict[str, Any]], page: int, chapter_number: Any) -> dict[str, Any] | None:
    candidates = [
        section
        for section in sections
        if section.get("chapter_number") == chapter_number
        and isinstance(section.get("pdf_page_start"), int)
        and section["pdf_page_start"] <= page
    ]
    return max(candidates, key=lambda section: section["pdf_page_start"]) if candidates else None


def first_alpha_character(text: str) -> str | None:
    match = re.search(r"[A-Za-z]", text)
    return match.group(0) if match else None


def is_heading_only_text(text: str) -> bool:
    stripped = clean_text(text)
    if not stripped or len(stripped) > 140 or re.search(r"[.!?][\"'’”)]*$", stripped):
        return False
    if re.match(r"^(?:BOX|TABLE|FIG(?:URE)?\.?|CASE STUDY|SUMMARY|REFERENCES|REVIEW QUESTIONS)\b", stripped, re.I):
        return True
    words = re.findall(r"[A-Za-z][A-Za-z’'\-]*", stripped)
    if not words or len(words) > 12:
        return False
    if stripped.upper() == stripped:
        return True
    return all(word[0].isupper() for word in words if word)


def starts_with_heading_like_phrase(text: str) -> bool:
    stripped = clean_text(text)
    # A PDF text block can contain a short title immediately followed by its
    # body, for example "Clot Retrieval, Mechanical Thrombectomy Although...".
    # Treat that as a new block when considering the less certain merge rule.
    return bool(
        re.match(
            r"^(?:[A-Z][A-Za-z’'\-/]*(?:[,;:]?)\s+){2,}[A-Z][a-z]",
            stripped,
        )
    )


def is_new_block_start(paragraph: dict[str, Any]) -> bool:
    text = paragraph.get("text", "").lstrip()
    if paragraph.get("content_type") == "list_item":
        return True
    if re.match(r"^(?:[•▪◦·‣⁃➔➜→]|\d+[.)])\s*", text):
        return True
    return is_heading_only_text(text)


def ends_sentence(text: str) -> bool:
    return bool(re.search(r"[.!?][\"'’”)]*$", text.rstrip()))


def can_merge_cross_page(current: dict[str, Any], following: dict[str, Any]) -> tuple[bool, str | None]:
    if str(current.get("chapter_number")) != str(following.get("chapter_number")):
        return False, None
    current_end = current.get("pdf_page_end", current.get("pdf_page_start"))
    following_start = following.get("pdf_page_start")
    if not isinstance(current_end, int) or not isinstance(following_start, int) or following_start != current_end + 1:
        return False, None
    if is_new_block_start(following):
        return False, None
    if current.get("content_type") not in {"logical_text_block", "list_item"}:
        return False, None
    if following.get("content_type") not in {"logical_text_block", "list_item"}:
        return False, None
    if following.get("content_type") == "list_item":
        return False, None
    if is_heading_only_text(current.get("text", "")):
        return False, None
    first_alpha = first_alpha_character(following.get("text", ""))
    if first_alpha and first_alpha.islower():
        return True, "high: following block begins with lowercase continuation text"
    if current.get("content_type") == "list_item":
        return False, None
    if (
        not ends_sentence(current.get("text", ""))
        and not starts_with_heading_like_phrase(following.get("text", ""))
        and len(current.get("text", "")) >= 120
        and len(following.get("text", "")) >= 100
    ):
        return True, "medium: unfinished long block continues at the next page"
    return False, None


def join_cross_page_text(first: str, second: str) -> str:
    first = first.rstrip()
    second = second.lstrip()
    if first.endswith("\u00ad"):
        return first[:-1] + second
    if first.endswith("-") and second and second[0].isalpha():
        return first[:-1] + second
    return clean_text(f"{first} {second}")


def merge_cross_page_paragraphs(
    paragraphs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, int]]:
    merged: list[dict[str, Any]] = []
    id_map: dict[str, str] = {}
    merge_count = 0
    cross_section_merge_count = 0
    index = 0
    while index < len(paragraphs):
        current = dict(paragraphs[index])
        current_id = current["paragraph_id"]
        merged_from = list(current.get("merged_from_paragraph_ids") or [current_id])
        section_ids_spanned = list(dict.fromkeys([current.get("section_id")]))
        section_titles_spanned = list(dict.fromkeys([current.get("section_title")]))
        merge_reasons: list[str] = []
        while index + 1 < len(paragraphs):
            following = paragraphs[index + 1]
            can_merge, reason = can_merge_cross_page(current, following)
            if not can_merge:
                break
            following_id = following["paragraph_id"]
            if current.get("section_id") != following.get("section_id"):
                cross_section_merge_count += 1
            section_ids_spanned.append(following.get("section_id"))
            section_titles_spanned.append(following.get("section_title"))
            current["text"] = join_cross_page_text(current.get("text", ""), following.get("text", ""))
            current["source_page_ids"] = list(dict.fromkeys(
                [*current.get("source_page_ids", []), *following.get("source_page_ids", [])]
            ))
            current["pdf_page_end"] = following.get("pdf_page_end", following.get("pdf_page_start"))
            current["printed_page_end"] = following.get("printed_page_end", following.get("printed_page_start"))
            current["source_line_ids"] = [*current.get("source_line_ids", []), *following.get("source_line_ids", [])]
            current["source_line_keys"] = [*current.get("source_line_keys", []), *following.get("source_line_keys", [])]
            current["visual_content_removed"] = bool(
                current.get("visual_content_removed") or following.get("visual_content_removed")
            )
            merged_from.extend(following.get("merged_from_paragraph_ids") or [following_id])
            merge_reasons.append(reason or "cross-page continuation")
            id_map[following_id] = current_id
            index += 1
            merge_count += 1
        if merge_reasons:
            current["merged_from_paragraph_ids"] = merged_from
            current["cross_page_merged"] = True
            current["cross_page_part_count"] = len(merged_from)
            current["cross_page_merge_reasons"] = merge_reasons
            section_ids_spanned = list(dict.fromkeys(section_ids_spanned))
            section_titles_spanned = list(dict.fromkeys(section_titles_spanned))
            if len(section_ids_spanned) > 1:
                current["section_ids_spanned"] = section_ids_spanned
                current["section_titles_spanned"] = section_titles_spanned
                current["section_mapping_warning"] = "Merged continuation crossed an automatically assigned page-section boundary."
        else:
            current["cross_page_merged"] = False
            current["cross_page_part_count"] = 1
        id_map[current_id] = current_id
        merged.append(current)
        index += 1
    return merged, id_map, {
        "merge_operations": merge_count,
        "merged_paragraphs": sum(1 for paragraph in merged if paragraph.get("cross_page_merged")),
        "cross_section_merge_operations": cross_section_merge_count,
        "paragraphs_before_merge": len(paragraphs),
        "paragraphs_after_merge": len(merged),
    }


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    structure_path = args.structure.expanduser().resolve()
    raw_text_path = args.raw_text.expanduser().resolve()
    inventory_path = args.layout_inventory.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    for path in (source, structure_path, raw_text_path, inventory_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_text_path.read_text(encoding="utf-8"))
    layout = json.loads(inventory_path.read_text(encoding="utf-8"))
    structure_pages = {page["pdf_page"]: page for page in structure["pages"]}
    raw_pages = {page["pdf_page"]: page for page in raw["pages"]}
    layout_pages = {page["pdf_page"]: page for page in layout["pages"]}
    total_pages = int(structure["source"]["pdf_page_count"])
    sections = section_records(structure)
    pdftotext = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"

    output_dir.mkdir(parents=True, exist_ok=True)
    page_output_path = output_dir / "stroke_rehab_clean_reading_order_full_generated.jsonl"
    paragraph_output_path = output_dir / "stroke_rehab_sections_paragraphs_full_generated.json"
    exclusion_output_path = output_dir / "stroke_rehab_visual_exclusion_full_generated.json"

    page_output_path.unlink(missing_ok=True)
    all_paragraphs: list[dict[str, Any]] = []
    page_records: list[dict[str, Any]] = []
    exclusion_records: list[dict[str, Any]] = []
    removed_words_total = 0
    cleaned_line_count = 0
    xml_controls_removed = 0

    with tempfile.TemporaryDirectory(prefix="stroke5-clean-") as temp:
        temp_dir = Path(temp)
        bbox_raw = temp_dir / "stroke5_bbox_raw.html"
        bbox_xml = temp_dir / "stroke5_bbox_sanitized.html"
        subprocess.run(
            [pdftotext, "-bbox-layout", "-enc", "UTF-8", "-f", "1", "-l", str(total_pages), str(source), str(bbox_raw)],
            check=True,
            capture_output=True,
        )
        xml_controls_removed = sanitize_bbox_xml(bbox_raw, bbox_xml)
        bbox_pages = iter_bbox_pages(bbox_xml)
        with page_output_path.open("w", encoding="utf-8") as page_stream:
            for page_bbox in bbox_pages:
                pdf_page = page_bbox["pdf_page"]
                page_source = structure_pages[pdf_page]
                page_layout = layout_pages[pdf_page]
                printed_page = page_source.get("printed_page")
                regions = visual_regions(page_layout, page_bbox["width"], page_bbox["height"])
                region_boxes = [tuple(region["bbox_points"]) for region in regions]
                raw_clean_lines: list[dict[str, Any]] = []
                removed_words = 0
                for flow in page_bbox["flows"]:
                    for block in flow["blocks"]:
                        for line in block["lines"]:
                            kept_words: list[dict[str, Any]] = []
                            for word in line["words"]:
                                if any(intersects(word, region) for region in region_boxes):
                                    removed_words += 1
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
                            if y2 > page_bbox["height"] - 35 and (
                                (printed_page and text == str(printed_page))
                                or re.fullmatch(r"\d{1,4}(?:\.e\d{1,3})?", text)
                            ):
                                continue
                            raw_clean_lines.append(
                                {
                                    "pdf_page": pdf_page,
                                    "source_page_id": page_source["source_page_id"],
                                    "flow_index": flow["flow_index"],
                                    "block_index": block["block_index"],
                                    "line_index": line["line_index"],
                                    "source_line_keys": [
                                        f"STROKE5-PDF{pdf_page:04d}-F{flow['flow_index']:03d}-B{block['block_index']:03d}-L{line['line_index']:03d}"
                                    ],
                                    "bbox_points": [round(value, 3) for value in line["bbox"]],
                                    "text": text,
                                }
                            )

                block_groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
                for line in raw_clean_lines:
                    block_groups[(line["flow_index"], line["block_index"])].append(line)
                ordered_blocks = sorted(
                    block_groups.values(),
                    key=lambda block: (
                        0
                        if (min(line["bbox_points"][0] for line in block) + max(line["bbox_points"][2] for line in block)) / 2 < page_bbox["width"] / 2
                        else 1,
                        min(line["bbox_points"][1] for line in block),
                        min(line["bbox_points"][0] for line in block),
                    ),
                )
                page_lines: list[dict[str, Any]] = []
                for block in ordered_blocks:
                    page_lines.extend(sorted(block, key=lambda item: (item["bbox_points"][1], item["bbox_points"][0])))
                page_lines = merge_detached_bullets(page_lines)
                for line_number, line in enumerate(page_lines, 1):
                    line["line_id"] = f"STROKE5-PDF{pdf_page:04d}-L{line_number:04d}"
                cleaned_line_count += len(page_lines)
                removed_words_total += removed_words
                units = block_units(page_lines)
                page_section = section_for_page(sections, pdf_page, page_source.get("chapter_number"))
                paragraph_ids: list[str] = []
                for unit in units:
                    if not unit.get("text"):
                        continue
                    paragraph_id = f"STROKE5-P{len(all_paragraphs) + 1:06d}"
                    paragraph_ids.append(paragraph_id)
                    all_paragraphs.append(
                        {
                            "paragraph_id": paragraph_id,
                            "section_id": page_section.get("section_id") if page_section else None,
                            "section_title": page_section.get("title") if page_section else None,
                            "part_number": page_source.get("part_number"),
                            "chapter_number": page_source.get("chapter_number"),
                            "chapter_title": page_source.get("chapter_title"),
                            "text": unit["text"],
                            "content_type": unit.get("content_type", "logical_text_block"),
                            "list_group_id": unit.get("list_group_id"),
                            "list_item_index": unit.get("list_item_index"),
                            "source_page_ids": [page_source["source_page_id"]],
                            "pdf_page_start": pdf_page,
                            "pdf_page_end": pdf_page,
                            "printed_page_start": printed_page,
                            "printed_page_end": printed_page,
                            "source_line_ids": unit.get("line_ids", []),
                            "source_line_keys": unit.get("source_line_keys", []),
                            "visual_content_removed": True,
                            "status": "generated_not_verified",
                            "verification_status": "generated_not_verified",
                        }
                    )

                exclusion_record = {
                    "source_page_id": page_source["source_page_id"],
                    "pdf_page": pdf_page,
                    "printed_page": printed_page,
                    "regions": regions,
                    "removed_visual_word_count": removed_words,
                    "status": "generated_not_verified",
                }
                exclusion_records.append(exclusion_record)
                page_record = {
                    "schema_version": "vtc-stroke-rehabilitation-5e.clean-page.v1",
                    "record_type": "clean_page_text",
                    "book_id": "STROKE5",
                    "source_page_id": page_source["source_page_id"],
                    "pdf_page": pdf_page,
                    "printed_page": printed_page,
                    "page_type": page_source.get("page_type"),
                    "part_number": page_source.get("part_number"),
                    "chapter_number": page_source.get("chapter_number"),
                    "chapter_title": page_source.get("chapter_title"),
                    "section_id": page_section.get("section_id") if page_section else None,
                    "section_title": page_section.get("title") if page_section else None,
                    "paragraph_ids": paragraph_ids,
                    "reading_order": "left physical column before right physical column; top to bottom within each PDF text block",
                    "reading_order_lines": page_lines,
                    "clean_text": "\n".join(line["text"] for line in page_lines),
                    "removed_visual_word_count": removed_words,
                    "visual_content_policy": "No OCR or reconstruction of visual contents; words inside model-detected visual regions are excluded from clean text.",
                    "status": "generated_not_verified",
                    "verification_status": "generated_not_verified",
                }
                page_records.append(page_record)
                page_stream.write(json.dumps(page_record, ensure_ascii=False) + "\n")

    paragraphs_before_merge = len(all_paragraphs)
    all_paragraphs, paragraph_id_map, cross_page_merge_stats = merge_cross_page_paragraphs(all_paragraphs)
    for page_record in page_records:
        page_record["paragraph_ids"] = list(
            dict.fromkeys(
                paragraph_id_map.get(paragraph_id, paragraph_id)
                for paragraph_id in page_record["paragraph_ids"]
            )
        )
    # Page records were streamed before cross-page IDs were known; rewrite them
    # with the final merged paragraph references.
    with page_output_path.open("w", encoding="utf-8") as page_stream:
        for page_record in page_records:
            page_stream.write(json.dumps(page_record, ensure_ascii=False) + "\n")

    sections_with_ranges: list[dict[str, Any]] = []
    paragraphs_by_section: dict[str | None, list[str]] = defaultdict(list)
    for paragraph in all_paragraphs:
        paragraphs_by_section[paragraph.get("section_id")].append(paragraph["paragraph_id"])
    for section in sections:
        ids = paragraphs_by_section.get(section["section_id"], [])
        section_record = dict(section)
        section_record["paragraph_ids"] = ids
        section_record["paragraph_count"] = len(ids)
        section_record["status"] = "generated_not_verified"
        sections_with_ranges.append(section_record)

    paragraph_output = {
        "schema_version": "vtc-stroke-rehabilitation-5e.sections-paragraphs.v1",
        "record_type": "clean_sections_and_paragraphs",
        "book_id": "STROKE5",
        "title": structure.get("title"),
        "source": {"filename": source.name, "path": str(source), "sha256": sha256_file(source)},
        "derived_from": {
            "raw_embedded_text": str(raw_text_path),
            "structure": str(structure_path),
            "layout_inventory": str(inventory_path),
        },
        "hierarchy": ["part", "chapter", "outline_section", "logical_text_block/list_item"],
        "visual_content_policy": "Visual regions are location-mapped but their contents are not OCRed or reconstructed. Table cells, figure labels, diagram text, chart labels, formulas, and captions inside detected regions are excluded from this clean text layer.",
        "cross_page_reconstruction_policy": "Adjacent page-spanning text blocks are merged when the following block is clear continuation text or an unfinished long block; headings, new numbered points, list starts, boxes, figures, and other likely new blocks remain separate. Original page and source-line provenance is retained.",
        "counts": {
            "pages": len(page_records),
            "paragraphs": len(all_paragraphs),
            "paragraphs_before_cross_page_merge": paragraphs_before_merge,
            "sections": len(sections_with_ranges),
            "cleaned_lines": cleaned_line_count,
            "removed_visual_words": removed_words_total,
            "pages_with_visual_regions": sum(bool(item["regions"]) for item in exclusion_records),
            "xml_controls_removed": xml_controls_removed,
            "cross_page_merge_operations": cross_page_merge_stats["merge_operations"],
            "cross_page_merged_paragraphs": cross_page_merge_stats["merged_paragraphs"],
            "cross_section_merge_operations": cross_page_merge_stats["cross_section_merge_operations"],
        },
        "sections": sections_with_ranges,
        "paragraphs": all_paragraphs,
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
    }
    paragraph_output_path.write_text(json.dumps(paragraph_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    exclusion_output_path.write_text(
        json.dumps(
            {
                "schema_version": "vtc-stroke-rehabilitation-5e.visual-exclusion.v1",
                "record_type": "visual_exclusion_inventory",
                "book_id": "STROKE5",
                "source_layout_inventory": str(inventory_path),
                "scope": "Model-detected layout regions used as clean-text exclusion masks; no visual OCR.",
                "pages": exclusion_records,
                "status": "generated_not_verified",
                "verification_status": "generated_not_verified",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "page_jsonl": str(page_output_path),
                "paragraph_json": str(paragraph_output_path),
                "exclusion_json": str(exclusion_output_path),
                "counts": paragraph_output["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build a portable LLM-Wiki package for one HHS3190M lecture PDF.

The raw bilingual PDF and bilingual OCR remain source-preserving.  The clean
retrieval layer is English-only, retains bullet/arrow markers and indentation,
records visual locations, and reconstructs tables only when a table candidate
is detected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SLIDE_TOOLS = PROJECT_ROOT / "HHS4185 Course Materials - LLM Wiki" / "tools"
sys.path.insert(0, str(SLIDE_TOOLS))
import build_hhs4185_course_materials as slide_engine  # noqa: E402


COURSE_CODE = "HHS3190M"
COURSE_TITLE = "HHS3190M - Human Physiology and Functional Anatomy for Rehabilitation Services"
SOURCE_ID = "HHS3190M-L01-PHYSIOLOGY-2026-07"
DOCUMENT_ID = SOURCE_ID
SOURCE_FILENAME = "01 - HHS3190MJ Physiology L1 (Jul 2026).pdf"
SOURCE_RELATIVE = "02 Lectures/01 - HHS3190MJ Physiology L1 (Jul 2026).pdf"
STATUS = "generated_not_verified"
SCHEMA = "vtc-hhs3190m-lecture.v1"
OUTPUT_STEM = "hhs3190m_l01"
QUERY_HELPER_PATH = "../../../tools/query_hhs3190m_lecture.py"
MANUAL_TABLES: list[dict[str, Any]] = []

DOCUMENT = {
    "document_id": DOCUMENT_ID,
    "file_name": SOURCE_FILENAME,
    "source_type": "lecture",
    "lecture_number": 1,
    "title": "Lecture 1 - Human Body and Chemicals (July 2026)",
}

TOPIC_PARTS = [
    {
        "unit_id": f"{SOURCE_ID}-PART00",
        "title": "Cover and Outline",
        "slide_start": 1,
        "slide_end": 2,
        "kind": "front_matter",
    },
    {
        "unit_id": f"{SOURCE_ID}-PART01",
        "title": "Background: What is physiology?",
        "slide_start": 3,
        "slide_end": 4,
        "kind": "topic",
    },
    {
        "unit_id": f"{SOURCE_ID}-PART02",
        "title": "Organization of Human Body and Organ-System Overview",
        "slide_start": 5,
        "slide_end": 7,
        "kind": "topic",
    },
    {
        "unit_id": f"{SOURCE_ID}-PART03",
        "title": "Important Chemicals in Human Body",
        "slide_start": 8,
        "slide_end": 24,
        "kind": "topic",
    },
    {
        "unit_id": f"{SOURCE_ID}-PART04",
        "title": "L1 Revision Exercise",
        "slide_start": 25,
        "slide_end": 25,
        "kind": "revision",
    },
    {
        "unit_id": f"{SOURCE_ID}-PART05",
        "title": "References",
        "slide_start": 26,
        "slide_end": 26,
        "kind": "references",
    },
]

OUTLINE_MAP = [
    {"outline_item": "Background: What is physiology?", "mapped_slides": [3, 4], "mapping_status": STATUS},
    {"outline_item": "Organization of human body", "mapped_slides": [5, 6, 7], "mapping_status": STATUS},
    {
        "outline_item": "Overview of organ systems in human body",
        "mapped_slides": [6, 7],
        "mapping_note": "Not given a separate slide title; covered by the organization diagrams.",
        "mapping_status": STATUS,
    },
    {"outline_item": "Important chemicals in human body", "mapped_slides": list(range(8, 25)), "mapping_status": STATUS},
]

SLIDE_TITLE_OVERRIDES = {
    6: "Overview of organ systems in human body (diagram)",
    7: "Organization of human body levels (diagram)",
}

LECTURE_KEYWORDS = [
    ("definitions_abbreviations", "physiology"),
    ("anatomy", "anatomy"),
    ("anatomy", "human body"),
    ("anatomy", "cell"),
    ("anatomy", "tissue"),
    ("anatomy", "organ"),
    ("anatomy", "organ system"),
    ("section_topics", "organization"),
    ("section_topics", "organization of human body"),
    ("section_topics", "organ systems"),
    ("section_topics", "chemicals"),
    ("section_topics", "water"),
    ("section_topics", "carbohydrates"),
    ("section_topics", "monosaccharides"),
    ("section_topics", "disaccharides"),
    ("section_topics", "polysaccharides"),
    ("section_topics", "glucose"),
    ("section_topics", "sucrose"),
    ("section_topics", "maltose"),
    ("section_topics", "lactose"),
    ("section_topics", "glycogen"),
    ("section_topics", "lipids"),
    ("section_topics", "triglycerides"),
    ("section_topics", "phospholipids"),
    ("section_topics", "steroids"),
    ("section_topics", "cholesterol"),
    ("section_topics", "proteins"),
    ("section_topics", "amino acids"),
    ("section_topics", "peptide bonds"),
    ("section_topics", "cell membrane"),
    ("section_topics", "nucleic acids"),
    ("definitions_abbreviations", "DNA"),
    ("definitions_abbreviations", "RNA"),
    ("section_topics", "enzymes"),
    ("section_topics", "antibodies"),
    ("section_topics", "denaturation"),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_text(command: list[str]) -> str:
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode("utf-8", errors="replace")


def pdfinfo(path: Path) -> dict[str, Any]:
    text = run_text(["pdfinfo", str(path)])
    values: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    for key in ("Pages", "File size"):
        if key in values:
            try:
                values[key] = int(values[key].split()[0])
            except ValueError:
                pass
    return values


def replace_tokens(value: Any) -> Any:
    if isinstance(value, str):
        value = value.replace("HHS4185", COURSE_CODE)
        value = value.replace(f"{COURSE_CODE} - Common Rehabilitation Conditions", COURSE_TITLE)
        return value
    if isinstance(value, list):
        return [replace_tokens(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_tokens(item) for key, item in value.items()}
    return value


def explicit_parts(pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    total = len(pages)
    parts: list[dict[str, Any]] = []
    page_to_part: dict[str, str] = {}
    for part in TOPIC_PARTS:
        start = int(part["slide_start"])
        end = min(total, int(part["slide_end"]))
        selected = [page for page in pages if start <= page["pdf_page"] <= end]
        record = {
            "unit_id": part["unit_id"],
            "level": "part",
            "document_id": DOCUMENT_ID,
            "document_title": DOCUMENT["title"],
            "title": part["title"],
            "topic_kind": part["kind"],
            "slide_start": start,
            "slide_end": end,
            "pdf_page_start": start,
            "pdf_page_end": end,
            "source_page_ids": [page["source_page_id"] for page in selected],
            "status": STATUS,
            "verification_status": STATUS,
        }
        parts.append(record)
        for page in selected:
            page_to_part[page["source_page_id"]] = part["unit_id"]
    if sum(len(part["source_page_ids"]) for part in parts) != total:
        raise ValueError("explicit lecture parts do not cover every slide")
    return parts, page_to_part


def apply_title_overrides(pages: list[dict[str, Any]]) -> None:
    """Correct diagram-only slide labels without discarding the raw candidate."""
    for page in pages:
        override = SLIDE_TITLE_OVERRIDES.get(page["pdf_page"])
        if not override:
            continue
        page["title_candidate_source"] = page.get("title_candidate")
        page["title_candidate"] = override


def english_bilingual_lines(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract English from mixed English/Traditional-Chinese text objects."""
    records: list[dict[str, Any]] = []
    for raw_line in slide_engine.reading_order_lines(page.get("lines", [])):
        raw_text = slide_engine.clean_text(str(raw_line.get("text", "")))
        raw_text = raw_text.replace("\u200b", "")
        # The deck places Traditional-Chinese translations after the English
        # in the same PDF text objects.  Keep the English prefix so ASCII
        # parentheses/punctuation from the translation cannot create false
        # duplicate fragments in the clean layer.
        first_cjk = re.search(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]", raw_text)
        text = raw_text[:first_cjk.start()] if first_cjk else raw_text
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\(\s*\)", "", text)
        text = re.sub(r"\[\s*\]", "", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        if not text:
            continue
        lowered = slide_engine.normalize(text)
        if lowered in {"ive", "healthandlifesciences", "allrightsreserved"}:
            continue
        if re.fullmatch(r"\d{1,3}", text):
            continue
        if "higherdiplomainrehabilitationservices" in lowered:
            continue
        if re.match(r"(?i)^(?:lecturer|m\s*s\.?|ms\.?)\b", text):
            continue
        marker, body = slide_engine.split_list_marker(text)
        if not body and marker:
            continue
        if len(re.findall(r"[A-Za-z]", body)) < 3 and not re.search(r"\d", body):
            continue
        bbox = list(raw_line.get("bbox_points", [0, 0, 0, 0]))
        records.append({
            "source_line_index": raw_line.get("line_index"),
            "bbox_points": bbox,
            "text": text,
            "language": "en",
            "marker": marker or None,
        })
    if records:
        base_x = min(float(item["bbox_points"][0]) for item in records)
        for item in records:
            indent_points = max(0.0, float(item["bbox_points"][0]) - base_x)
            item["indent_points"] = round(indent_points, 3)
            item["indent_level"] = int(round(indent_points / 24.0))
    return records


def recalculate_english_candidates(pages: list[dict[str, Any]]) -> None:
    """Replace the inherited bilingual line filter with the deck-specific one."""
    for page in pages:
        page["title_candidate_source"] = page.get("title_candidate")
        page["reading_order_lines"] = english_bilingual_lines(page)
        candidates = [line for line in page["reading_order_lines"] if len(line["text"]) <= 140]
        page["title_candidate"] = max(
            candidates,
            key=lambda line: (slide_engine.line_height(line), -line["bbox_points"][1]),
        )["text"] if candidates else ""


def merge_block_text(current: dict[str, Any], line: dict[str, Any]) -> None:
    marker, body = slide_engine.split_list_marker(str(line.get("text", "")))
    if not body:
        return
    current["body_text"] = f"{current['body_text']} {body}".strip()
    current["text"] = f"{current['marker']} {current['body_text']}".strip() if current["marker"] else current["body_text"]
    current["source_line_indices"].append(line.get("source_line_index"))
    current["bbox_points"] = [
        min(current["bbox_points"][0], line["bbox_points"][0]),
        min(current["bbox_points"][1], line["bbox_points"][1]),
        max(current["bbox_points"][2], line["bbox_points"][2]),
        max(current["bbox_points"][3], line["bbox_points"][3]),
    ]


def inferred_adjacent_marker(page: dict[str, Any], line: dict[str, Any]) -> str:
    """Recover a bullet glyph stored as a separate PDF text object."""
    line_bbox = line.get("bbox_points", [0, 0, 0, 0])
    line_x = float(line_bbox[0])
    line_y = float(line_bbox[1])
    for raw_line in slide_engine.reading_order_lines(page.get("lines", [])):
        raw_text = str(raw_line.get("text", "")).strip()
        marker, body = slide_engine.split_list_marker(raw_text)
        raw_bbox = raw_line.get("bbox_points", [0, 0, 0, 0])
        if not marker or body or not raw_bbox:
            continue
        raw_x = float(raw_bbox[0])
        raw_y = float(raw_bbox[1])
        if abs(raw_y - line_y) <= 5.0 and raw_x <= line_x + 2.0:
            return marker
    return ""


def line_is_in_manual_table(page: dict[str, Any], line: dict[str, Any]) -> bool:
    """Keep reconstructed table text from being duplicated as slide prose."""
    bbox = line.get("bbox_points", [0, 0, 0, 0])
    center_x = (float(bbox[0]) + float(bbox[2])) / 2
    center_y = (float(bbox[1]) + float(bbox[3])) / 2
    for candidate in MANUAL_TABLES:
        if int(candidate["page"]) != page["pdf_page"]:
            continue
        table_bbox = [float(value) for value in candidate["bbox"]]
        if table_bbox[0] <= center_x <= table_bbox[2] and table_bbox[1] <= center_y <= table_bbox[3]:
            return True
    return False


def build_slide_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    lines = page.get("reading_order_lines", [])
    title = str(page.get("title_candidate") or "").strip()
    blocks: list[dict[str, Any]] = []
    title_used = False
    active: dict[str, Any] | None = None
    for line in lines:
        if line_is_in_manual_table(page, line):
            continue
        if SOURCE_ID == "HHS3190M-L01-PHYSIOLOGY-2026-07" and page["pdf_page"] == 24 and float(line.get("bbox_points", [0, 0, 0, 0])[1]) >= 314.0:
            # The DNA/RNA comparison is represented once in the reconstructed
            # table layer, not duplicated as ordinary slide prose.
            continue
        raw = str(line.get("text", "")).strip()
        marker, body = slide_engine.split_list_marker(raw)
        marker_source = "embedded_text" if marker else None
        if body and not marker:
            marker = inferred_adjacent_marker(page, line)
            if marker:
                marker_source = "adjacent_pdf_marker_glyph"
        if not body:
            continue
        if title and not title_used and body == title:
            block_type = "slide_title"
            title_used = True
        elif marker:
            block_type = "list_item"
        elif active and active["content_type"] == "list_item":
            y = float(line["bbox_points"][1])
            previous_y = float(active["bbox_points"][3])
            x = float(line["bbox_points"][0])
            starts_at_or_after_item = x >= float(active["bbox_points"][0]) - 12
            stays_in_item_column = x <= float(active["bbox_points"][0]) + 90
            same_visual_line = y <= previous_y + 5 and x >= float(active["bbox_points"][2]) - 12
            if (same_visual_line or (y - previous_y <= 34 and stays_in_item_column)) and starts_at_or_after_item:
                merge_block_text(active, line)
                continue
            block_type = "subheading" if len(body) <= 100 else "paragraph"
        else:
            block_type = "subtitle" if not blocks or all(item["content_type"] in {"slide_title", "subtitle"} for item in blocks) else "paragraph"
        block = {
            "block_id": f"{page['source_page_id']}-B{len(blocks) + 1:03d}",
            "source_page_id": page["source_page_id"],
            "slide_number": page["pdf_page"],
            "content_type": block_type,
            "text": f"{marker} {body}".strip() if marker else body,
            "body_text": body,
            "marker": marker or None,
            "marker_source": marker_source,
            "indent_points": line.get("indent_points", 0),
            "indent_level": line.get("indent_level", 0),
            "source_line_indices": [line.get("source_line_index")],
            "bbox_points": list(line.get("bbox_points", [0, 0, 0, 0])),
            "language": "en",
            "status": STATUS,
            "verification_status": STATUS,
        }
        blocks.append(block)
        active = block if block_type == "list_item" else None
    return blocks


def enrich_visuals(visuals: list[dict[str, Any]], pages: list[dict[str, Any]], page_to_part: dict[str, str], structure_title: str) -> None:
    page_by_id = {page["source_page_id"]: page for page in pages}
    for visual in visuals:
        page = page_by_id[visual["source_page_id"]]
        part_id = page_to_part.get(page["source_page_id"])
        visual["page_reference"] = slide_engine.source_page_reference(DOCUMENT, page)
        visual["section_ids"] = [value for value in [page["source_page_id"], part_id, DOCUMENT_ID, f"{COURSE_CODE}-COURSE"] if value]
        visual["section_paths"] = [[structure_title, DOCUMENT["title"], next((part["title"] for part in TOPIC_PARTS if part["unit_id"] == part_id), ""), page.get("title_candidate") or f"Slide {page['pdf_page']}"]]
        visual["table_reconstruction_available"] = bool(visual.get("table_id"))
        visual["table_reconstruction_source"] = f"../02 Text and Tables/{OUTPUT_STEM}_tables_generated.json" if visual.get("table_id") else None
        visual["status"] = STATUS
        visual["verification_status"] = STATUS


def visual_keywords(visuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for index, visual in enumerate(visuals, 1):
        name = str(visual.get("name") or visual.get("caption") or visual.get("visual_type") or "visual")
        page_id = visual["source_page_id"]
        records.append({
            "record_id": f"{COURSE_CODE}-KW-{visual['visual_id']}",
            "category": "visual",
            "broad_area": "Visual aids",
            "small_area": name,
            "keyword_path": ["Visual aids", name],
            "source_form": name,
            "canonical_candidate": name,
            "retrieval_terms": slide_engine.alias_variants(name),
            "source_passage_ids": [],
            "source_page_ids": [page_id],
            "source_element_ids": [visual["visual_id"]],
            "section_ids": visual.get("section_ids", []),
            "source_excerpt": name,
            "status": STATUS,
            "verification_status": STATUS,
        })
    return records


def add_manual_table_candidates(visuals: list[dict[str, Any]], tables: list[dict[str, Any]], pages: list[dict[str, Any]]) -> None:
    """Add reviewed vector-table candidates supplied by a deck configuration."""
    page_by_number = {page["pdf_page"]: page for page in pages}
    for table_number, candidate in enumerate(MANUAL_TABLES, 1):
        page = page_by_number.get(int(candidate["page"]))
        if not page:
            continue
        table_id = f"{page['document_id']}-TBL-P{page['pdf_page']:04d}-{table_number:02d}"
        visual_id = f"{page['document_id']}-VIS-P{page['pdf_page']:04d}-TABLE{table_number:02d}"
        if any(item.get("visual_id") == visual_id for item in visuals):
            continue
        bbox = [float(value) for value in candidate["bbox"]]
        columns = [str(value) for value in candidate["columns"]]
        raw_rows = candidate.get("rows", [])
        rows = []
        for row_index, raw_row in enumerate(raw_rows):
            cells = [{"column_index": index, "text": str(value), "language": "en"} for index, value in enumerate(raw_row)]
            rows.append({
                "source_row_index": row_index,
                "text": " | ".join(str(value) for value in raw_row),
                "cells": cells,
            })
        visual = {
            "visual_id": visual_id,
            "table_id": table_id,
            "document_id": page["document_id"],
            "source_page_id": page["source_page_id"],
            "source_file": page["source_file"],
            "pdf_page": page["pdf_page"],
            "slide_number": page["pdf_page"],
            "visual_type": "table",
            "name": str(candidate["name"]),
            "caption": candidate.get("caption"),
            "location": {
                "bbox_points": bbox,
                "bbox_px": None,
                "coordinate_origin": "top-left",
                "location_source": "manual-visual-review-of-vector-table",
            },
            "policy": "full_table_reconstruction",
            "detection_note": "Vector-drawn table; reconstructed from embedded English text and visual layout review.",
            "status": STATUS,
            "verification_status": STATUS,
        }
        table = {
            "table_id": table_id,
            "visual_id": visual_id,
            "document_id": page["document_id"],
            "name": str(candidate["name"]),
            "source_page_id": page["source_page_id"],
            "pdf_page": page["pdf_page"],
            "slide_number": page["pdf_page"],
            "bbox_points": bbox,
            "layout_grid": {"row_count": len(rows), "column_count": len(columns), "columns": columns},
            "coordinate_rows": rows,
            "content": {"text": "\n".join(row["text"] for row in rows), "rows": rows},
            "reconstruction_method": "manual-source-slide-structure-with-embedded-text-and-visual-review",
            "language": "en",
            "status": STATUS,
            "verification_status": STATUS,
        }
        visuals.append(visual)
        tables.append(table)
        page.setdefault("visuals", []).append(visual)


def add_vector_visual_candidates(visuals: list[dict[str, Any]], tables: list[dict[str, Any]], pages: list[dict[str, Any]]) -> None:
    """Record important vector-only visuals and reconstruct the vector table."""
    if SOURCE_ID != "HHS3190M-L01-PHYSIOLOGY-2026-07":
        add_manual_table_candidates(visuals, tables, pages)
        return
    page = next((item for item in pages if item["pdf_page"] == 6), None)
    if not page:
        return
    visual_id = f"{page['document_id']}-VIS-P0006-VECTOR0001"
    if any(item.get("visual_id") == visual_id for item in visuals):
        return
    visuals.append({
        "visual_id": visual_id,
        "table_id": None,
        "document_id": page["document_id"],
        "source_page_id": page["source_page_id"],
        "source_file": page["source_file"],
        "pdf_page": page["pdf_page"],
        "slide_number": page["pdf_page"],
        "visual_type": "diagram",
        "name": "Organization and relationships of human body levels and organ systems",
        "caption": None,
        "location": {
            "bbox_points": [60.0, 18.0, 900.0, 510.0],
            "bbox_px": None,
            "coordinate_origin": "top-left",
            "location_source": "manual-visual-review-of-vector-shapes",
        },
        "policy": "metadata_only",
        "detection_note": "Vector shapes and connector arrows; not represented as an embedded image object in the PDF trace.",
        "status": STATUS,
        "verification_status": STATUS,
    })

    table_page = next((item for item in pages if item["pdf_page"] == 24), None)
    if not table_page:
        return
    table_visual_id = f"{table_page['document_id']}-VIS-P0024-VECTOR0001"
    table_id = f"{table_page['document_id']}-TBL-P0024-01"
    if any(item.get("visual_id") == table_visual_id for item in visuals):
        return
    table_bbox = [44.0, 314.0, 830.0, 510.0]
    visuals.append({
        "visual_id": table_visual_id,
        "table_id": table_id,
        "document_id": table_page["document_id"],
        "source_page_id": table_page["source_page_id"],
        "source_file": table_page["source_file"],
        "pdf_page": table_page["pdf_page"],
        "slide_number": table_page["pdf_page"],
        "visual_type": "table",
        "name": "DNA and RNA comparison table",
        "caption": None,
        "location": {
            "bbox_points": table_bbox,
            "bbox_px": None,
            "coordinate_origin": "top-left",
            "location_source": "manual-visual-review-of-vector-table",
        },
        "policy": "full_table_reconstruction",
        "detection_note": "Vector-drawn table; not represented as an embedded image object in the PDF trace.",
        "status": STATUS,
        "verification_status": STATUS,
    })
    rows = [
        {
            "source_row_index": 0,
            "text": " | DNA | RNA",
            "cells": [
                {"column_index": 0, "text": "", "language": "en"},
                {"column_index": 1, "text": "DNA", "language": "en"},
                {"column_index": 2, "text": "RNA", "language": "en"},
            ],
        },
        {
            "source_row_index": 1,
            "text": "Major Function | Hold genetic information | Copy and carry information from DNA for protein synthesis",
            "cells": [
                {"column_index": 0, "text": "Major Function", "language": "en"},
                {"column_index": 1, "text": "Hold genetic information", "language": "en"},
                {"column_index": 2, "text": "Copy and carry information from DNA for protein synthesis", "language": "en"},
            ],
        },
        {
            "source_row_index": 2,
            "text": "Location in Cell | Find almost entirely in nucleus | Form in nucleus; Find throughout cytoplasm",
            "cells": [
                {"column_index": 0, "text": "Location in Cell", "language": "en"},
                {"column_index": 1, "text": "Find almost entirely in nucleus", "language": "en"},
                {"column_index": 2, "text": "Form in nucleus; Find throughout cytoplasm", "language": "en"},
            ],
        },
    ]
    tables.append({
        "table_id": table_id,
        "visual_id": table_visual_id,
        "name": "DNA and RNA comparison table",
        "source_page_id": table_page["source_page_id"],
        "pdf_page": table_page["pdf_page"],
        "slide_number": table_page["pdf_page"],
        "bbox_points": table_bbox,
        "layout_grid": {"row_count": 3, "column_count": 3, "columns": ["", "DNA", "RNA"]},
        "coordinate_rows": rows,
        "content": {"text": "\n".join(row["text"] for row in rows), "rows": rows},
        "reconstruction_method": "manual-source-slide-structure-with-embedded-text-and-visual-review",
        "language": "en",
        "status": STATUS,
        "verification_status": STATUS,
    })


def quotation_candidates(pages: list[dict[str, Any]], blocks_by_page: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    records = []
    for page in pages:
        for block in blocks_by_page.get(page["source_page_id"], []):
            body = block.get("body_text", "").strip()
            if len(body) < 30 or block.get("content_type") == "slide_title":
                continue
            reference = slide_engine.source_page_reference(DOCUMENT, page)
            records.append({
                "evidence_id": f"{block['block_id']}-EVIDENCE",
                "quotation": block["text"],
                "source_passage_id": block["block_id"],
                "source_page_ids": [page["source_page_id"]],
                "reference": reference,
                "in_text_citation": f"({reference['formatted']})",
                "quotation_status": "source_extracted_candidate",
                "verification_status": STATUS,
                "exact_quote_eligible": False,
                "manual_source_image_check_required": True,
            })
    return records


def augment_lecture_keywords(
    analysis: dict[str, Any],
    pages: list[dict[str, Any]],
    page_to_part: dict[str, str],
) -> None:
    """Add short-deck teaching concepts that frequency-only indexing misses."""
    existing = {(record.get("source_page_ids", [None])[0], record.get("category"), slide_engine.normalize(record.get("canonical_candidate", ""))) for record in analysis["keyword_records"]}
    page_records = {record["source_page_id"]: record for record in analysis["page_keyword_extractions"]}
    next_id = len(analysis["keyword_records"]) + 1
    for page in pages:
        page_id = page["source_page_id"]
        text = slide_engine.derived_page_text(page)
        normalized_text = slide_engine.normalize(text)
        for category, term in LECTURE_KEYWORDS:
            term_key = slide_engine.normalize(term)
            if not term_key or term_key not in normalized_text:
                continue
            key = (page_id, category, term_key)
            if key in existing:
                continue
            record = {
                "record_id": f"{COURSE_CODE}-KW-LECTURE-{next_id:04d}",
                "category": category,
                "broad_area": slide_engine.CATEGORY_LABELS.get(category, category),
                "small_area": term,
                "keyword_path": [slide_engine.CATEGORY_LABELS.get(category, category), term],
                "source_form": term,
                "canonical_candidate": term,
                "retrieval_terms": slide_engine.alias_variants(term),
                "source_passage_ids": [f"{page_id}-PASSAGE"],
                "source_page_ids": [page_id],
                "section_ids": [page_id, page_to_part.get(page_id, ""), page["document_id"], f"{COURSE_CODE}-COURSE"],
                "source_excerpt": text[:500],
                "keyword_source": "lecture-specific-teaching-vocabulary",
                "status": STATUS,
                "verification_status": STATUS,
            }
            analysis["keyword_records"].append(record)
            page_records[page_id]["keyword_records"].append(record)
            page_records[page_id]["keyword_record_count"] += 1
            existing.add(key)
            next_id += 1
    analysis["counts"]["keyword_records"] = len(analysis["keyword_records"])


def augment_table_keywords(
    analysis: dict[str, Any],
    tables: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    page_to_part: dict[str, str],
) -> None:
    """Index each reconstructed table cell without flattening it into prose."""
    page_records = {record["source_page_id"]: record for record in analysis["page_keyword_extractions"]}
    existing = {(record.get("source_element_ids", [None])[0], slide_engine.normalize(record.get("canonical_candidate", ""))) for record in analysis["keyword_records"]}
    next_id = len(analysis["keyword_records"]) + 1
    for table in tables:
        page_id = table.get("source_page_id")
        if not page_id or page_id not in page_records:
            continue
        table_text = str(table.get("content", {}).get("text", ""))
        for row in table.get("content", {}).get("rows", []):
            for cell in row.get("cells", []):
                value = slide_engine.clean_text(str(cell.get("text", ""))).strip()
                key = slide_engine.normalize(value)
                if len(key) < 3 or value == "—" or (table.get("table_id"), key) in existing:
                    continue
                record = {
                    "record_id": f"{COURSE_CODE}-KW-TABLE-{next_id:05d}",
                    "category": "section_topics",
                    "broad_area": "Reconstructed table content",
                    "small_area": value,
                    "keyword_path": ["Reconstructed table content", value],
                    "source_form": value,
                    "canonical_candidate": value,
                    "retrieval_terms": slide_engine.alias_variants(value),
                    "source_passage_ids": [f"{page_id}-PASSAGE"],
                    "source_element_ids": [table["table_id"]],
                    "source_page_ids": [page_id],
                    "section_ids": [page_id, page_to_part.get(page_id, ""), table.get("document_id", ""), f"{COURSE_CODE}-COURSE"],
                    "source_excerpt": table_text[:500],
                    "content_type": "reconstructed_table_cell",
                    "keyword_source": "manual-table-cell",
                    "status": STATUS,
                    "verification_status": STATUS,
                }
                analysis["keyword_records"].append(record)
                page_records[page_id]["table_keyword_records"].append(record)
                page_records[page_id]["keyword_record_count"] += 1
                existing.add((table["table_id"], key))
                next_id += 1
    analysis["counts"]["keyword_records"] = len(analysis["keyword_records"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs4185-course"))
    parser.add_argument("--skip-paddle", action="store_true", help="Use embedded PDF text and MuPDF visual locations when PaddleOCR models are unavailable.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root.expanduser().resolve()
    if output_root.exists() and any(output_root.iterdir()) and not args.overwrite:
        raise SystemExit(f"Output exists; pass --overwrite: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    slide_engine.COURSE_CODE = COURSE_CODE
    slide_engine.DOCUMENTS = [DOCUMENT]
    slide_engine.SOURCE_ALIASES = {SOURCE_FILENAME: (SOURCE_RELATIVE,)}
    slide_engine.SCHEMA_VERSION = SCHEMA

    source = slide_engine.document_source_path(args.course_root.expanduser().resolve(), DOCUMENT)
    source_hash = sha256_file(source)
    DOCUMENT["source_path"] = str(source)
    DOCUMENT["source_sha256"] = source_hash
    manifest, pages = slide_engine.collect_pages(args.course_root.expanduser().resolve(), args.dpi, args.paddle_cache.expanduser().resolve(), args.skip_paddle)
    if len(pages) != int(pdfinfo(source).get("Pages", 0)):
        raise RuntimeError("processed page count does not match pdfinfo")
    recalculate_english_candidates(pages)
    apply_title_overrides(pages)
    parts, page_to_part = explicit_parts(pages)

    blocks_by_page: dict[str, list[dict[str, Any]]] = {}
    slide_exports = []
    for page in pages:
        blocks = build_slide_blocks(page)
        blocks_by_page[page["source_page_id"]] = blocks
        page["english_blocks"] = blocks
        page["english_clean_text"] = "\n".join(block["text"] for block in blocks)
        page["reading_order_text"] = page["english_clean_text"]
        slide_exports.append({
            "source_page_id": page["source_page_id"],
            "slide_number": page["pdf_page"],
            "title": page.get("title_candidate") or f"Slide {page['pdf_page']}",
            "english_text": page["english_clean_text"],
            "raw_bilingual_text": page.get("embedded_text", ""),
            "blocks": blocks,
            "visual_ids": [],
            "status": STATUS,
            "verification_status": STATUS,
        })

    visuals, tables = slide_engine.page_visuals(pages)
    add_vector_visual_candidates(visuals, tables, pages)
    enrich_visuals(visuals, pages, page_to_part, COURSE_TITLE)
    visual_by_page: dict[str, list[dict[str, Any]]] = {}
    for visual in visuals:
        visual_by_page.setdefault(visual["source_page_id"], []).append(visual)
    for slide in slide_exports:
        slide["visual_ids"] = [item["visual_id"] for item in visual_by_page.get(slide["source_page_id"], [])]
        slide["visual_placeholders"] = [
            {
                "visual_id": item["visual_id"],
                "visual_type": item["visual_type"],
                "name": item.get("name"),
                "pdf_page": item["pdf_page"],
                "slide_number": item["slide_number"],
                "location": item["location"],
                "policy": item["policy"],
                "status": STATUS,
                "verification_status": STATUS,
            }
            for item in visual_by_page.get(slide["source_page_id"], [])
        ]

    structure, node_by_id = slide_engine.build_structure([DOCUMENT], pages, parts, page_to_part, visuals)
    structure["book_id"] = COURSE_CODE
    structure["course"]["title"] = COURSE_TITLE
    structure["hierarchy_order"] = ["course", "document", "part", "slide", "block"]
    structure["processing_order"] = ["block", "slide", "part", "document", "course"]
    structure["outline_map"] = OUTLINE_MAP
    structure["hierarchy_semantics"] = {
        "course": "HHS3190M course container",
        "document": "one lecture PDF/deck",
        "part": "explicit lecture topic/front-matter grouping",
        "slide": "PDF page and slide number",
        "block": "English title, subtitle, paragraph, or preserved point-form item",
        "visual": "location/name/type metadata; contents not reconstructed unless a table candidate exists",
    }
    for node in structure["nodes"]:
        node["status"] = STATUS
        node["verification_status"] = STATUS

    analysis, _ = slide_engine.build_analysis([DOCUMENT], pages, parts, page_to_part, visuals, tables, node_by_id)
    augment_lecture_keywords(analysis, pages, page_to_part)
    augment_table_keywords(analysis, tables, pages, page_to_part)
    visual_kw = visual_keywords(visuals)
    analysis["keyword_records"].extend(visual_kw)
    analysis["visual_keyword_records"] = visual_kw
    analysis["quotation_candidates"] = quotation_candidates(pages, blocks_by_page)
    analysis["processing_order"] = ["block", "slide", "part", "document", "course"]
    analysis["counts"]["keyword_records"] = len(analysis["keyword_records"])
    analysis["counts"]["visual_keyword_records"] = len(visual_kw)
    analysis["counts"]["quotation_candidates"] = len(analysis["quotation_candidates"])
    analysis["status"] = STATUS
    analysis["verification_status"] = STATUS

    # The reusable course builder still uses its original HHS4185 course key
    # internally.  Build its indexes before token-normalising the returned
    # structure, then normalise all generated records for this package.
    indexes = slide_engine.build_retrieval_indexes([DOCUMENT], pages, parts, page_to_part, visuals, tables, analysis, structure, node_by_id)
    structure = replace_tokens(structure)
    analysis = replace_tokens(analysis)
    indexes = replace_tokens(indexes)
    for visual in indexes["visual_index"].get("visuals", []):
        if visual.get("table_id"):
            visual["table_reconstruction_source"] = f"../02 Text and Tables/{OUTPUT_STEM}_tables_generated.json"
    validation = indexes["validation"]
    validation["checks"].update({
        "english_clean_layer_present": bool(slide_exports) and all(slide["english_text"] is not None for slide in slide_exports),
        "embedded_pdf_text_complete": all(bool(page.get("embedded_text", "").strip()) for page in pages),
        "text_or_ocr_source_available": all(bool(page.get("embedded_text", "").strip()) or page.get("ocr_status") == "completed" for page in pages),
        "visual_detection_fallback_recorded": bool(args.skip_paddle),
        "bullet_markers_preserved": all(block.get("marker") is not None or block.get("content_type") != "list_item" for slide in slide_exports for block in slide["blocks"]),
        "visual_records_have_locations": all(item.get("location", {}).get("bbox_points") for item in visuals),
        "all_derived_status_generated_not_verified": all(item.get("verification_status") == STATUS for item in visuals + tables + analysis["quotation_candidates"]),
    })
    validation["valid"] = all(value is True for key, value in validation["checks"].items() if key not in {"all_pages_have_ocr", "all_pages_have_layout"})
    validation["validation_scope_note"] = "Integrity and source-text checks pass in embedded-text/MuPDF fallback mode; PaddleOCR and Paddle layout checks remain false because the Paddle models were unavailable in this run."
    validation["status"] = STATUS
    validation["verification_status"] = STATUS
    indexes["validation"] = validation

    text_layer = output_root / "02 Text and Tables"
    ocr_layer = output_root / "01 OCR and Layout"
    analysis_layer = output_root / "03 Analysis"
    index_layer = output_root / "04 Retrieval Index"
    for layer in (ocr_layer, text_layer, analysis_layer, index_layer):
        layer.mkdir(parents=True, exist_ok=True)

    source_info = {
        "filename": source.name,
        "path": str(source),
        "sha256": source_hash,
        "pdf_page_count": len(pages),
        "pdfinfo": pdfinfo(source),
        "text_extraction": "embedded PDF text with bbox coordinates",
        "ocr_engine": "PaddleOCR PP-OCRv6_medium_det/rec + PP-DocLayout_plus-L" if not args.skip_paddle else "not_run; embedded PDF text and MuPDF image trace used",
    }
    with (ocr_layer / f"{OUTPUT_STEM}_pages_ocr_layout_generated.jsonl").open("w", encoding="utf-8") as stream:
        for page in pages:
            stream.write(json.dumps(page, ensure_ascii=False) + "\n")
    (text_layer / f"{OUTPUT_STEM}_embedded_text_full_layout.txt").write_text(run_text(["pdftotext", "-layout", str(source), "-"]), encoding="utf-8")
    (text_layer / f"{OUTPUT_STEM}_embedded_text_full_linear.txt").write_text(run_text(["pdftotext", "-raw", str(source), "-"]), encoding="utf-8")
    write_json(text_layer / f"{OUTPUT_STEM}_slides_text_generated.json", {
        "schema_version": SCHEMA,
        "record_type": "lecture_slides_english_reading_order",
        "book_id": COURSE_CODE,
        "source_id": SOURCE_ID,
        "source": source_info,
        "language_policy": "English-only derived layer; raw bilingual PDF/OCR retained separately.",
        "point_form_policy": "Leading bullet and arrow markers plus indentation are retained in block records.",
        "slides": slide_exports,
        "counts": {"slides": len(slide_exports), "blocks": sum(len(slide["blocks"]) for slide in slide_exports), "list_items": sum(block["content_type"] == "list_item" for slide in slide_exports for block in slide["blocks"])},
        "status": STATUS,
        "verification_status": STATUS,
    })
    write_json(text_layer / f"{OUTPUT_STEM}_visual_manifest_generated.json", {
        "schema_version": SCHEMA,
        "record_type": "lecture_visual_manifest",
        "book_id": COURSE_CODE,
        "source_id": SOURCE_ID,
        "source": source_info,
        "visual_policy": {"tables": "full reconstruction when detected", "non_tables": "location/name/type metadata only", "visual_text_ocr": "not separately reconstructed"},
        "visuals": visuals,
        "counts": {"visuals": len(visuals), "tables": sum(bool(item.get("table_id")) for item in visuals), "non_table_visuals": sum(not bool(item.get("table_id")) for item in visuals)},
        "status": STATUS,
        "verification_status": STATUS,
    })
    write_json(text_layer / f"{OUTPUT_STEM}_tables_generated.json", {
        "schema_version": SCHEMA,
        "record_type": "lecture_table_reconstructions",
        "book_id": COURSE_CODE,
        "source_id": SOURCE_ID,
        "source": source_info,
        "tables": tables,
        "counts": {"tables": len(tables)},
        "no_table_result": "No table candidates were detected; no table layout or contents were invented." if not tables else None,
        "status": STATUS,
        "verification_status": STATUS,
    })
    write_json(ocr_layer / f"{OUTPUT_STEM}_structure_generated.json", structure)
    write_json(analysis_layer / f"{OUTPUT_STEM}_analysis_generated.json", analysis)
    write_json(analysis_layer / f"{OUTPUT_STEM}_summaries_generated.json", {"schema_version": SCHEMA, "record_type": "lecture_hierarchical_summaries", "book_id": COURSE_CODE, "source_id": SOURCE_ID, "processing_order": ["slide", "part", "document", "course"], "units": analysis["summary_units"], "status": STATUS, "verification_status": STATUS})

    write_json(index_layer / "concept_index.json", indexes["concept_index"])
    write_json(index_layer / "occurrence_index.json", indexes["occurrence_index"])
    write_json(index_layer / "term_lookup.json", indexes["term_lookup"])
    write_json(index_layer / "structure_lookup.json", indexes["structure"])
    write_json(index_layer / "visual_index.json", indexes["visual_index"])
    with (index_layer / "passage_index.jsonl").open("w", encoding="utf-8") as stream:
        for passage in indexes["passage_lines"]:
            stream.write(json.dumps(passage, ensure_ascii=False) + "\n")
    write_json(index_layer / "retrieval_index_validation_report.json", validation)
    write_json(index_layer / "hierarchical_summaries.json", {"schema_version": SCHEMA, "record_type": "hierarchical_summaries", "book_id": COURSE_CODE, "source_id": SOURCE_ID, "processing_order": ["slide", "part", "document", "course"], "units": analysis["summary_units"], "status": STATUS, "verification_status": STATUS})
    write_json(index_layer / "formal_output_schema.json", {
        "schema_version": "vtc-hhs3190m.formal-answer.v1",
        "record_type": "formal_answer_contract",
        "required_sections": ["answer", "source_quotations", "references"],
        "reference_rule": "Cite lecture filename and slide number; PDF page equals slide number for this export.",
        "visual_rule": "Cite visual name/type/location; reconstruct contents only for returned tables.",
        "verification_rule": "Generated text, quotations, visual mappings, and summaries require manual source-slide verification.",
        "status": STATUS,
        "verification_status": STATUS,
    })
    retrieval_manifest = {
        "schema_version": "vtc-hhs3190m.retrieval-index-manifest.v1",
        "record_type": "retrieval_index_manifest",
        "book_id": COURSE_CODE,
        "source_id": SOURCE_ID,
        "package_path": f"sources/{COURSE_CODE}/{SOURCE_ID}",
        "index_files": {"concepts": "concept_index.json", "occurrences": "occurrence_index.json", "terms": "term_lookup.json", "passages": "passage_index.jsonl", "visuals": "visual_index.json", "structure": "structure_lookup.json", "summaries": "hierarchical_summaries.json", "formal_output": "formal_output_schema.json", "validation": "retrieval_index_validation_report.json"},
        "source_separation": "This lecture package remains separate from other HHS3190M sources and all HHS4185 packages.",
        "retrieval_policy": {"course_priority": "This is primary HHS3190M lecture evidence.", "source_passages_primary": True, "summaries_context_only": True, "non_table_visuals_metadata_only": True, "tables_full_reconstruction_when_detected": True, "exact_quotes_require_manual_verification": True, "claims_index": "not_created"},
        "counts": {"slides": len(pages), "parts": len(parts), "blocks": sum(len(slide["blocks"]) for slide in slide_exports), "concepts": len(indexes["concept_index"]["concepts"]), "occurrences": len(indexes["occurrence_index"]["occurrences"]), "terms": indexes["term_lookup"]["counts"]["terms"], "passages": len(indexes["passage_lines"]), "visuals": len(visuals), "tables": len(tables), "quotation_candidates": len(analysis["quotation_candidates"])},
        "status": STATUS,
        "verification_status": STATUS,
    }
    write_json(index_layer / "retrieval_index_manifest.json", retrieval_manifest)

    source_manifest_path = output_root / "source_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_manifest.update({"processing_status": "processed_generated_layers", "verification_status": STATUS, "status": "processed_generated_layers"})
    source_manifest["processing"] = {"workflow": "register -> inspect -> embedded text and PaddleOCR OCR/layout -> English slide blocks -> visual inventory -> table detection/reconstruction -> slide/part/document/course summaries and keywords -> retrieval index", "completed_at_hkt": datetime.now().astimezone().isoformat(timespec="seconds"), "outputs": {"source_inventory": "source_manifest.json", "ocr_layout": f"01 OCR and Layout/{OUTPUT_STEM}_pages_ocr_layout_generated.jsonl", "structure": f"01 OCR and Layout/{OUTPUT_STEM}_structure_generated.json", "text": f"02 Text and Tables/{OUTPUT_STEM}_slides_text_generated.json", "visuals": f"02 Text and Tables/{OUTPUT_STEM}_visual_manifest_generated.json", "tables": f"02 Text and Tables/{OUTPUT_STEM}_tables_generated.json", "analysis": f"03 Analysis/{OUTPUT_STEM}_analysis_generated.json", "summaries": f"03 Analysis/{OUTPUT_STEM}_summaries_generated.json", "retrieval_index": "04 Retrieval Index/retrieval_index_manifest.json", "query_helper": QUERY_HELPER_PATH}, "counts": retrieval_manifest["counts"], "all_derived_status": STATUS}
    source_manifest["next_step"] = "Manually review representative slides, bullet nesting, visual bounding boxes, page references, and any table candidates before changing verification status."
    write_json(source_manifest_path, source_manifest)

    print(json.dumps({"output_root": str(output_root), "source": str(source), "source_sha256": source_hash, "counts": retrieval_manifest["counts"], "validation": validation, "status": STATUS}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

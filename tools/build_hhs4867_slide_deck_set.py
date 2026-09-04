#!/usr/bin/env python3
"""Build source-preserving LLM-Wiki packages for unique HHS4867 slide PDFs.

The Movement Science course folder contains PDF exports of presentation decks
rather than .ppt/.pptx files.  The canonical input list below is SHA-256
deduplicated: duplicate lecture/workshop copies are recorded in the source
manifest and are never rendered or extracted a second time.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COURSE_ROOT_DEFAULT = Path("/Users/creamybanana/Downloads/Movement Science")
COURSE_CODE = "HHS4867"
COURSE_TITLE = "HHS4867 - Functional Movement Science"
STATUS = "generated_not_verified"
SCHEMA = "vtc-hhs4867-slide-deck.v1"

# These are the first paths in the sorted SHA-256 groups.  The builder reads
# only these canonical inputs; DUPLICATE_PATHS is written as provenance below.
DECKS: list[dict[str, Any]] = [
    {"source_id": "HHS4867-L01-AMBULATION-TRANSFER", "source_relative": "02 Lectures/01 - 1. Ambulation Transfer.pdf", "title": "Lecture 1 - Ambulation & Transfer", "source_kind": "lecture"},
    {"source_id": "HHS4867-L02-MANUAL-MUSCLE-TESTING", "source_relative": "02 Lectures/04 - 2. Manual Muscle Testing.pdf", "title": "Lecture 2 - Manual Muscle Testing (MMT)", "source_kind": "lecture"},
    {"source_id": "HHS4867-L02-NEUROMUSCULAR-CONTROL", "source_relative": "02 Lectures/05 - 2. Neuromuscular control of movement 人體運動神經控制.pdf", "title": "Lecture 2 - Neuromuscular Control of Human Movement", "source_kind": "lecture"},
    {"source_id": "HHS4867-L03-ANALYSIS-OF-MOVEMENT", "source_relative": "02 Lectures/07 - 3. Analysis of Movement 運動動作分析.pdf", "title": "Lecture 3 - Analysis of Movement", "source_kind": "lecture"},
    {"source_id": "HHS4867-L03-RANGE-OF-MOTION", "source_relative": "02 Lectures/09 - 3. Range of Motion.pdf", "title": "Lecture 3 - Measurement of Range of Motion (ROM)", "source_kind": "lecture"},
    {"source_id": "HHS4867-L04-MFAC", "source_relative": "02 Lectures/10 - 4. Modified Functional Ambulation Categories.pdf", "title": "Lecture 4 - Modified Functional Ambulation Categories", "source_kind": "lecture"},
    {"source_id": "HHS4867-L04-TUG", "source_relative": "02 Lectures/11 - 4. Timed up and go.pdf", "title": "Lecture 4 - Timed Up and Go (TUG) Test", "source_kind": "lecture"},
    {"source_id": "HHS4867-L04-TRANSFER-WHEELCHAIRS", "source_relative": "02 Lectures/12 - 4. Transfer techniques and standard wheelchairs 轉移技巧及輪椅使用.pdf", "title": "Lecture 4 - Transfer Technique and Standard Wheelchairs", "source_kind": "lecture"},
    {"source_id": "HHS4867-SCHEDULE-1A", "source_relative": "02 Lectures/14 - 4867 1A.pdf", "title": "Functional Movement Science - Class 1A Lecture Schedule", "source_kind": "lecture_schedule"},
    {"source_id": "HHS4867-SCHEDULE-1B", "source_relative": "02 Lectures/15 - 4867 1B.pdf", "title": "Functional Movement Science - Class 1B Lecture Schedule", "source_kind": "lecture_schedule"},
    {"source_id": "HHS4867-SCHEDULE-1C", "source_relative": "02 Lectures/16 - 4867 1C.pdf", "title": "Functional Movement Science - Class 1C Lecture Schedule", "source_kind": "lecture_schedule"},
    {"source_id": "HHS4867-L05-MOBILITY-WALKING-AIDS", "source_relative": "02 Lectures/17 - 5. Mobility Walking Aids 助行工具.pdf", "title": "Lecture 5 - Mobility and Walking Aids", "source_kind": "lecture"},
    {"source_id": "HHS4867-L06-POSTURAL-GAIT", "source_relative": "02 Lectures/19 - 6. Postural and Gait 姿勢及步態評估.pdf", "title": "Lecture 6 - Postural and Gait Assessment", "source_kind": "lecture"},
    {"source_id": "HHS4867-L07-MANUAL-MUSCLE-TESTING", "source_relative": "02 Lectures/21 - 7.1 Manual Muscle Testing 手動肌肉測試.pdf", "title": "Lecture 7.1 - Manual Muscle Testing", "source_kind": "lecture"},
    {"source_id": "HHS4867-L07-JOINT-RANGE-OF-MOTION", "source_relative": "02 Lectures/23 - 7.2 Joint Range of Motion 關節活動幅度測量.pdf", "title": "Lecture 7.2 - Joint Range of Motion", "source_kind": "lecture"},
]

EXISTING_DECK = {
    "source_id": "HHS4867-L01-MUSCULOSKELETAL-BASIS",
    "source_relative": "02 Lectures/02 - 1. Musculsketal basis for movement 人體肌肉骨骼基礎.pdf",
    "title": "Lecture 1 - Musculoskeletal Basis for Human Movement",
    "source_kind": "lecture",
}

SEED_KEYWORDS: dict[str, list[tuple[str, str]]] = {
    "HHS4867-L01-AMBULATION-TRANSFER": [("rehabilitation", "ambulation"), ("rehabilitation", "transfer"), ("rehabilitation", "bed mobility"), ("rehabilitation", "walking aid")],
    "HHS4867-L02-MANUAL-MUSCLE-TESTING": [("measurements", "manual muscle testing"), ("measurements", "muscle strength"), ("measurements", "Oxford scale"), ("anatomy", "shoulder joint"), ("anatomy", "hip joint")],
    "HHS4867-L02-NEUROMUSCULAR-CONTROL": [("physiology", "neuromuscular control"), ("anatomy", "nervous system"), ("anatomy", "motor unit"), ("rehabilitation", "muscle contraction")],
    "HHS4867-L03-ANALYSIS-OF-MOVEMENT": [("measurements", "analysis of movement"), ("measurements", "range of motion"), ("rehabilitation", "gait"), ("anatomy", "joint movement")],
    "HHS4867-L03-RANGE-OF-MOTION": [("measurements", "range of motion"), ("measurements", "goniometer"), ("measurements", "normal range of motion"), ("anatomy", "shoulder joint"), ("anatomy", "hip joint")],
    "HHS4867-L04-MFAC": [("measurements", "Modified Functional Ambulation Categories"), ("measurements", "MFAC"), ("rehabilitation", "ambulation")],
    "HHS4867-L04-TUG": [("measurements", "Timed Up and Go"), ("measurements", "TUG test"), ("rehabilitation", "functional mobility")],
    "HHS4867-L04-TRANSFER-WHEELCHAIRS": [("rehabilitation", "transfer"), ("rehabilitation", "wheelchair"), ("rehabilitation", "wheelchair transfer"), ("rehabilitation", "standard wheelchair")],
    "HHS4867-SCHEDULE-1A": [("document_concepts", "learning content"), ("document_concepts", "assessment")],
    "HHS4867-SCHEDULE-1B": [("document_concepts", "learning content"), ("document_concepts", "assessment")],
    "HHS4867-SCHEDULE-1C": [("document_concepts", "learning content"), ("document_concepts", "assessment")],
    "HHS4867-L05-MOBILITY-WALKING-AIDS": [("rehabilitation", "mobility"), ("rehabilitation", "walking aids"), ("rehabilitation", "walker"), ("rehabilitation", "crutches"), ("rehabilitation", "cane"), ("rehabilitation", "gait")],
    "HHS4867-L06-POSTURAL-GAIT": [("measurements", "postural assessment"), ("measurements", "gait assessment"), ("anatomy", "posture"), ("rehabilitation", "gait"), ("measurements", "MFAC")],
    "HHS4867-L07-MANUAL-MUSCLE-TESTING": [("measurements", "manual muscle testing"), ("measurements", "muscle strength"), ("measurements", "Oxford scale"), ("anatomy", "shoulder joint"), ("anatomy", "hip joint")],
    "HHS4867-L07-JOINT-RANGE-OF-MOTION": [("measurements", "joint range of motion"), ("measurements", "goniometer"), ("measurements", "normal range of motion"), ("anatomy", "shoulder joint"), ("anatomy", "hip joint")],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def run_text(command: list[str]) -> str:
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode("utf-8", errors="replace")


def pdfinfo(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in run_text(["pdfinfo", str(path)]).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    for key in ("Pages", "File size"):
        if key in values:
            try:
                values[key] = int(str(values[key]).split()[0])
            except ValueError:
                pass
    return values


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def build_duplicate_audit(course_root: Path) -> dict[str, Any]:
    files = sorted(
        (path for folder in ("02 Lectures", "03 Workshops") for path in (course_root / folder).glob("*.pdf")),
        key=lambda path: str(path),
    )
    groups: dict[str, list[Path]] = {}
    for path in files:
        groups.setdefault(sha256_file(path), []).append(path)
    entries = []
    for digest, paths in sorted(groups.items(), key=lambda item: str(item[1][0])):
        entries.append({
            "sha256": digest,
            "canonical_path": str(paths[0].relative_to(course_root)),
            "duplicate_paths": [str(path.relative_to(course_root)) for path in paths[1:]],
            "file_count": len(paths),
            "duplicate_action": "process canonical path once; record other paths as exact-byte duplicates",
            "status": STATUS,
            "verification_status": STATUS,
        })
    return {
        "schema_version": "vtc-hhs4867.presentation-deduplication.v1",
        "record_type": "presentation_deduplication_audit",
        "course_code": COURSE_CODE,
        "course_title": COURSE_TITLE,
        "scope": ["02 Lectures/*.pdf", "03 Workshops/*.pdf"],
        "scope_note": "The source folder contains PDF exports rather than .ppt/.pptx files. Reference PDFs and media-link PDFs were excluded because they are not presentation decks.",
        "candidate_file_count": len(files),
        "unique_sha256_count": len(entries),
        "groups": entries,
        "existing_processed_package": {
            "source_id": EXISTING_DECK["source_id"],
            "canonical_path": EXISTING_DECK["source_relative"],
            "action": "reuse existing processed package; do not rescan",
        },
        "status": STATUS,
        "verification_status": STATUS,
    }


def import_adapters() -> tuple[Any, Any, Any]:
    tools_dir = str(PROJECT_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import build_hhs4867_lecture_pdf as adapter
    import build_hhs3190m_lecture_pdf as base
    import build_hhs4185_course_materials as slide_engine
    return adapter, base, slide_engine


def configure_adapter(adapter: Any, base: Any, course_root: Path, deck: dict[str, Any], package_root: Path, page_count: int) -> tuple[Any, Any, Any]:
    source_filename = Path(deck["source_relative"]).name
    document = {
        "document_id": deck["source_id"],
        "file_name": source_filename,
        "source_type": deck["source_kind"],
        "title": deck["title"],
    }
    adapter.COURSE_CODE = COURSE_CODE
    adapter.COURSE_TITLE = COURSE_TITLE
    adapter.SOURCE_ID = deck["source_id"]
    adapter.DOCUMENT_ID = deck["source_id"]
    adapter.SOURCE_FILENAME = source_filename
    adapter.SOURCE_RELATIVE = deck["source_relative"]
    adapter.SOURCE_PACKAGE_PDF = package_root / "00 Source" / source_filename
    adapter.SCHEMA = SCHEMA
    adapter.DOCUMENT = document
    adapter.TOPIC_PARTS = [{
        "unit_id": f"{deck['source_id']}-PART01",
        "title": deck["title"],
        "slide_start": 1,
        "slide_end": page_count,
        "kind": "synthetic_topic",
    }]
    adapter.OUTLINE_MAP = []
    adapter.SLIDE_TITLES = {}
    adapter.LECTURE_KEYWORDS = SEED_KEYWORDS.get(deck["source_id"], [])
    adapter.VISUAL_NAMES = {}
    adapter.patch_base_globals()
    # The adapter imports the same base module, but make the source aliases
    # explicit after every configuration to avoid state leaking across decks.
    adapter.SOURCE_PACKAGE_PDF = package_root / "00 Source" / source_filename
    return adapter, base, document


CJK_RE = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")


def english_table_cell(value: Any) -> tuple[str, str]:
    raw = "" if value is None else str(value)
    raw = raw.replace("\u200b", "").replace("\ufeff", "")
    raw_clean = " ".join(raw.split())
    english_lines: list[str] = []
    for line in raw.splitlines() or [raw]:
        line = " ".join(line.split()).strip()
        if not line:
            continue
        match = CJK_RE.search(line)
        candidate = line[: match.start()].strip() if match else line
        if candidate:
            english_lines.append(candidate)
    return " ".join(english_lines).strip(), raw_clean


def table_rows(table: Any) -> list[list[dict[str, str]]]:
    rows: list[list[dict[str, str]]] = []
    for raw_row in table.extract() or []:
        row: list[dict[str, str]] = []
        for cell in raw_row or []:
            english, raw = english_table_cell(cell)
            row.append({"text": english, "raw_text": raw})
        if any(item["raw_text"] for item in row):
            rows.append(row)
    return rows


def table_content(rows: list[list[dict[str, str]]]) -> dict[str, Any]:
    readable_rows = []
    for row_index, row in enumerate(rows):
        cells = []
        for column_index, cell in enumerate(row):
            cells.append({
                "text": cell["text"],
                "raw_text": cell["raw_text"],
                "column_index": column_index,
                "row_span": 1,
                "col_span": 1,
            })
        readable_rows.append({"row_index": row_index, "cells": cells})
    text_rows = [" | ".join(cell["text"] for cell in row) for row in rows]
    return {"text": "\n".join(text_rows), "rows": readable_rows}


def bbox_area(bbox: list[float]) -> float:
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))


def overlap_ratio(a: list[float], b: list[float]) -> float:
    area = bbox_area(a)
    if not area:
        return 0.0
    intersection = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return bbox_area(intersection) / area


def center_inside_bbox(item_bbox: list[float], container: list[float]) -> bool:
    if len(item_bbox) != 4 or len(container) != 4:
        return False
    center_x = (float(item_bbox[0]) + float(item_bbox[2])) / 2
    center_y = (float(item_bbox[1]) + float(item_bbox[3])) / 2
    return float(container[0]) <= center_x <= float(container[2]) and float(container[1]) <= center_y <= float(container[3])


def extract_tables(source: Path, pages: list[dict[str, Any]], deck: dict[str, Any], slide_engine: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        import pdfplumber
    except ImportError:
        return [], []
    page_by_number = {page["pdf_page"]: page for page in pages}
    visuals: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    with pdfplumber.open(source) as pdf:
        for page_number, pdf_page in enumerate(pdf.pages, 1):
            page_record = page_by_number[page_number]
            try:
                candidates = pdf_page.find_tables()
            except Exception:
                candidates = []
            table_index = 0
            for candidate in candidates:
                rows = table_rows(candidate)
                if len(rows) < 2 or max((len(row) for row in rows), default=0) < 2:
                    continue
                table_index += 1
                bbox = [round(float(value), 3) for value in candidate.bbox]
                table_id = f"{deck['source_id']}-TBL-P{page_number:04d}-C{table_index:02d}"
                visual_id = f"{deck['source_id']}-VIS-P{page_number:04d}-T{table_index:02d}"
                page_title = page_record.get("title_candidate") or f"Slide {page_number}"
                name = f"Table on slide {page_number}: {page_title}"
                content = table_content(rows)
                table_record = {
                    "table_id": table_id,
                    "visual_id": visual_id,
                    "name": name,
                    "source_page_id": page_record["source_page_id"],
                    "pdf_page": page_number,
                    "slide_number": page_number,
                    "bbox_points": bbox,
                    "coordinate_origin": "top-left",
                    "content": content,
                    "raw_table_rows_preserved": rows,
                    "reconstruction_method": "pdfplumber-table-grid-with-English-derived-cells-and-raw-cell-text",
                    "table_reconstruction_available": True,
                    "status": STATUS,
                    "verification_status": STATUS,
                }
                tables.append(table_record)
                visuals.append({
                    "visual_id": visual_id,
                    "table_id": table_id,
                    "document_id": deck["source_id"],
                    "source_page_id": page_record["source_page_id"],
                    "source_file": Path(deck["source_relative"]).name,
                    "pdf_page": page_number,
                    "slide_number": page_number,
                    "visual_type": "table",
                    "name": name,
                    "caption": None,
                    "location": {"bbox_points": bbox, "bbox_px": None, "coordinate_origin": "top-left", "location_source": "pdfplumber-find-tables"},
                    "policy": "full_table_reconstruction",
                    "table_reconstruction_available": True,
                    "table_reconstruction_source": f"../02 Text and Tables/{safe_slug(deck['source_id'])}_tables_generated.json",
                    "status": STATUS,
                    "verification_status": STATUS,
                })
    return visuals, tables


def add_section_metadata(visuals: list[dict[str, Any]], tables: list[dict[str, Any]], pages: list[dict[str, Any]], deck: dict[str, Any], adapter: Any, slide_engine: Any) -> None:
    page_by_id = {page["source_page_id"]: page for page in pages}
    part_id = f"{deck['source_id']}-PART01"
    for visual in visuals:
        page = page_by_id[visual["source_page_id"]]
        visual["page_reference"] = slide_engine.source_page_reference(adapter.DOCUMENT, page)
        visual["section_ids"] = [page["source_page_id"], part_id, deck["source_id"], f"{COURSE_CODE}-COURSE"]
        visual["section_paths"] = [[COURSE_TITLE, deck["title"], deck["title"], page.get("title_candidate") or f"Slide {page['pdf_page']}"]]
        visual.setdefault("table_reconstruction_available", False)
        visual.setdefault("table_reconstruction_source", None)
        visual["status"] = STATUS
        visual["verification_status"] = STATUS
    for table in tables:
        page = page_by_id[table["source_page_id"]]
        table["page_reference"] = slide_engine.source_page_reference(adapter.DOCUMENT, page)
        table["section_ids"] = [page["source_page_id"], part_id, deck["source_id"], f"{COURSE_CODE}-COURSE"]
        table["status"] = STATUS
        table["verification_status"] = STATUS


def add_table_keywords(analysis: dict[str, Any], tables: list[dict[str, Any]], pages: list[dict[str, Any]], page_to_part: dict[str, str], slide_engine: Any) -> None:
    page_record_by_id = {item["source_page_id"]: item for item in analysis["page_keyword_extractions"]}
    for table in tables:
        page_id = table["source_page_id"]
        table_text = slide_engine.clean_text(table.get("content", {}).get("text", ""))
        if not table_text or page_id not in page_record_by_id:
            continue
        page = next(page for page in pages if page["source_page_id"] == page_id)
        ancestors = [page_id, page_to_part.get(page_id, ""), page["document_id"], f"{COURSE_CODE}-COURSE"]
        global_counts = Counter(slide_engine.normalize(token) for token in slide_engine.TOKEN_RE.findall(table_text))
        local = slide_engine.token_candidates(table_text, global_counts, source_kind="table")
        table_records = []
        for index, ((category, term_key), forms) in enumerate(sorted(local.items()), 1):
            source_form = slide_engine.display_form(forms, term_key)
            table_records.append({
                "record_id": f"{COURSE_CODE}-KW-{table['table_id']}-{index:03d}",
                "category": category,
                "broad_area": slide_engine.CATEGORY_LABELS.get(category, category),
                "small_area": source_form,
                "keyword_path": [slide_engine.CATEGORY_LABELS.get(category, category), source_form],
                "source_form": source_form,
                "canonical_candidate": source_form,
                "retrieval_terms": slide_engine.alias_variants(source_form),
                "source_passage_ids": [f"{page_id}-PASSAGE"],
                "source_element_ids": [table["table_id"]],
                "source_page_ids": [page_id],
                "section_ids": [value for value in ancestors if value],
                "source_excerpt": table_text[:500],
                "content_type": "reconstructed_table",
                "status": STATUS,
                "verification_status": STATUS,
            })
        analysis["keyword_records"].extend(table_records)
        page_record_by_id[page_id].setdefault("table_keyword_records", []).extend(table_records)
        page_record_by_id[page_id]["table_keyword_record_count"] = len(page_record_by_id[page_id].get("table_keyword_records", []))


def ai_instructions(deck: dict[str, Any], package_root: Path) -> str:
    return f"""# AI usage instructions\n\n- Source: `{deck['source_id']}` — `{deck['title']}`.\n- Search `04 Retrieval Index/term_lookup.json`, follow term -> concept -> occurrence -> passage/visual/table links, then read the returned passage.\n- Use the slide number and PDF page number in the returned locator.\n- Tables are separate records in `02 Text and Tables/{safe_slug(deck['source_id'])}_tables_generated.json`; non-table visuals are metadata-only unless explicitly marked otherwise.\n- All extracted, reconstructed, summarized, quoted, and indexed records are `generated_not_verified`; check the original slide before treating wording or table cells as authoritative.\n- Keep this course material ahead of supplemental sources, and distinguish source evidence from AI inference.\n- For medical study questions, provide educational source-grounded information, not individualized diagnosis or treatment.\n\nQuery helper (relative to this file): `../../../../tools/query_{safe_slug(deck['source_id'])}.py`\n"""


def build_one(deck: dict[str, Any], course_root: Path, output_root: Path, dpi: int, use_paddle: bool) -> dict[str, Any]:
    adapter, base, slide_engine = import_adapters()
    source = course_root / deck["source_relative"]
    package_root = output_root / deck["source_id"]
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = sha256_file(source)
    source_filename = source.name
    package_source = package_root / "00 Source" / source_filename
    if not package_source.is_file():
        raise FileNotFoundError(f"Registered raw source is missing: {package_source}")
    if sha256_file(package_source) != source_hash:
        raise RuntimeError(f"package source hash mismatch for {deck['source_id']}")
    info = pdfinfo(source)
    page_count = int(info.get("Pages", 0))
    adapter, base, document = configure_adapter(adapter, base, course_root, deck, package_root, page_count)
    document["source_path"] = str(source)
    document["source_sha256"] = source_hash
    manifest, pages = slide_engine.collect_pages(course_root, dpi, Path("/private/tmp/paddlex-hhs4867-course"), not use_paddle)
    if len(pages) != page_count:
        raise RuntimeError(f"page count mismatch for {deck['source_id']}: {len(pages)} != {page_count}")
    adapter.filter_visual_backgrounds_and_text(pages)
    for page in pages:
        if page["pdf_page"] == 1:
            page["title_candidate_source"] = page.get("title_candidate")
            page["title_candidate"] = deck["title"]
    table_visuals, tables = extract_tables(source, pages, deck, slide_engine)
    table_bboxes_by_page: dict[int, list[list[float]]] = {}
    for visual in table_visuals:
        table_bboxes_by_page.setdefault(int(visual["pdf_page"]), []).append(list(visual["location"]["bbox_points"]))
    for page in pages:
        table_bboxes = table_bboxes_by_page.get(int(page["pdf_page"]), [])
        if table_bboxes:
            page["reading_order_lines"] = [
                line for line in page.get("reading_order_lines", [])
                if not any(center_inside_bbox(list(line.get("bbox_points", [])), bbox) for bbox in table_bboxes)
            ]
            page["reading_order_text"] = "\n".join(line["text"] for line in page["reading_order_lines"])
    adapter.SLIDE_TITLES = {int(page["pdf_page"]): (page.get("title_candidate") or f"Slide {page['pdf_page']}") for page in pages}
    parts, page_to_part = base.explicit_parts(pages)
    blocks_by_page: dict[str, list[dict[str, Any]]] = {}
    slide_exports = []
    for page in pages:
        blocks = adapter.build_blocks(page)
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
    visuals, _page_tables = slide_engine.page_visuals(pages)
    adapter.name_visuals(visuals)
    adapter.enrich_visuals(visuals, pages, page_to_part)
    visual_bboxes = [list(item.get("location", {}).get("bbox_points", [])) for item in table_visuals]
    if visual_bboxes:
        visuals = [item for item in visuals if not any(len(table_bbox) == 4 and len(item.get("location", {}).get("bbox_points", [])) == 4 and overlap_ratio(list(item["location"]["bbox_points"]), table_bbox) > 0.8 for table_bbox in visual_bboxes)]
    visuals.extend(table_visuals)
    add_section_metadata(visuals, tables, pages, deck, adapter, slide_engine)
    visual_by_page: dict[str, list[dict[str, Any]]] = {}
    for visual in visuals:
        visual_by_page.setdefault(visual["source_page_id"], []).append(visual)
    for slide in slide_exports:
        slide["visual_ids"] = [item["visual_id"] for item in visual_by_page.get(slide["source_page_id"], [])]
        slide["visual_placeholders"] = [{
            "visual_id": item["visual_id"], "visual_type": item["visual_type"], "name": item.get("name"),
            "pdf_page": item["pdf_page"], "slide_number": item["slide_number"], "location": item["location"],
            "policy": item["policy"], "status": STATUS, "verification_status": STATUS,
        } for item in visual_by_page.get(slide["source_page_id"], [])]
    structure, node_by_id = slide_engine.build_structure([document], pages, parts, page_to_part, visuals)
    structure["book_id"] = COURSE_CODE
    structure["course"]["title"] = COURSE_TITLE
    structure["hierarchy_order"] = ["course", "document", "part", "slide", "block"]
    structure["processing_order"] = ["block", "slide", "part", "document", "course"]
    structure["outline_map"] = []
    structure["hierarchy_semantics"] = {
        "course": "HHS4867 course container",
        "document": "one source PDF presentation deck",
        "part": "one synthetic topic container matching the deck title; slide titles remain separate",
        "slide": "PDF page and slide number",
        "block": "English title, subtitle, paragraph, or preserved point-form item",
        "visual": "location/name/type metadata only for non-table visuals",
        "table": "complete grid reconstruction from pdfplumber cells, with raw cell text retained",
    }
    structure["visual_content_policy"] = "Non-table visual contents were not separately OCRed or reconstructed; tables were extracted into the table layer when a coordinate grid was detected."
    for node in structure["nodes"]:
        node["status"] = STATUS
        node["verification_status"] = STATUS
    analysis, _ = slide_engine.build_analysis([document], pages, parts, page_to_part, visuals, tables, node_by_id)
    base.augment_lecture_keywords(analysis, pages, page_to_part)
    visual_kw = adapter.visual_keywords(visuals)
    analysis["keyword_records"].extend(visual_kw)
    analysis["visual_keyword_records"] = visual_kw
    add_table_keywords(analysis, tables, pages, page_to_part, slide_engine)
    analysis["quotation_candidates"] = base.quotation_candidates(pages, blocks_by_page)
    analysis["processing_order"] = ["block", "slide", "part", "document", "course"]
    analysis["counts"]["keyword_records"] = len(analysis["keyword_records"])
    analysis["counts"]["visual_keyword_records"] = len(visual_kw)
    analysis["counts"]["quotation_candidates"] = len(analysis["quotation_candidates"])
    indexes = slide_engine.build_retrieval_indexes([document], pages, parts, page_to_part, visuals, tables, analysis, structure, node_by_id)
    structure = base.replace_tokens(structure)
    analysis = base.replace_tokens(analysis)
    indexes = base.replace_tokens(indexes)
    validation = indexes["validation"]
    validation["checks"].update({
        "english_clean_layer_present": len(slide_exports) == page_count and all(slide["english_text"] is not None for slide in slide_exports),
        "embedded_pdf_text_complete": all(bool(page.get("embedded_text", "").strip()) for page in pages),
        "text_or_ocr_source_available": all(bool(page.get("embedded_text", "").strip()) or page.get("ocr_status") == "completed" for page in pages),
        "full_page_backgrounds_excluded": all(not item.get("full_page") for page in pages for item in page.get("embedded_image_objects", [])),
        "visual_records_have_locations": all(item.get("location", {}).get("bbox_points") for item in visuals),
        "non_table_visuals_metadata_only": all(item.get("policy") == "metadata_only" for item in visuals if not item.get("table_id")),
        "table_records_have_grids": all(item.get("content", {}).get("rows") for item in tables),
        "table_visual_links_resolve": all(item.get("table_id") in {table["table_id"] for table in tables} for item in visuals if item.get("table_id")),
        "bullet_markers_preserved": all(block.get("marker") is not None or block.get("content_type") != "list_item" for slide in slide_exports for block in slide["blocks"]),
        "all_derived_status_generated_not_verified": all(item.get("verification_status") == STATUS for item in visuals + tables + analysis["quotation_candidates"]),
    })
    empty_embedded_text_pages = [page["pdf_page"] for page in pages if not page.get("embedded_text", "").strip()]
    validation["coverage"] = {
        "ocr_engine": "not_run_paddlex_unavailable",
        "layout_engine": "not_run_paddlex_unavailable",
        "embedded_text_pages": [page["pdf_page"] for page in pages if page.get("embedded_text", "").strip()],
        "empty_embedded_text_pages": empty_embedded_text_pages,
        "ocr_skipped_pages": [page["pdf_page"] for page in pages if page.get("ocr_status") != "completed"],
        "layout_skipped_pages": [page["pdf_page"] for page in pages if page.get("layout_status") != "completed"],
        "manual_review_required": True,
        "note": "Pages listed as empty_embedded_text_pages require source-image review or a later OCR/layout pass; no derived record is treated as verified.",
    }
    validation["valid"] = all(value is True for key, value in validation["checks"].items() if key not in {"all_pages_have_ocr", "all_pages_have_layout"})
    validation["validation_scope_note"] = "Embedded-text and MuPDF visual-trace fallback was used because PaddleOCR is unavailable in the bundled runtime; pdfplumber table grids were extracted separately. All derived records remain generated_not_verified."
    validation["status"] = STATUS
    validation["verification_status"] = STATUS
    indexes["validation"] = validation
    source_info = {
        "filename": source_filename,
        "path": str(source),
        "package_source_path": str(package_source),
        "sha256": source_hash,
        "size_bytes": source.stat().st_size,
        "pdf_page_count": page_count,
        "pdfinfo": info,
        "text_extraction": "embedded PDF text with bbox coordinates",
        "ocr_engine": "not_run; embedded PDF text and MuPDF image trace used",
        "layout_engine": "not_run; MuPDF image trace and pdfplumber table grid used",
        "visual_text_policy": "Non-table visual contents were not separately OCRed or reconstructed.",
    }
    slug = safe_slug(deck["source_id"])
    ocr_layer = package_root / "01 OCR and Layout"
    text_layer = package_root / "02 Text and Tables"
    analysis_layer = package_root / "03 Analysis"
    index_layer = package_root / "04 Retrieval Index"
    for layer in (ocr_layer, text_layer, analysis_layer, index_layer):
        layer.mkdir(parents=True, exist_ok=True)
    with (ocr_layer / f"{slug}_pages_ocr_layout_generated.jsonl").open("w", encoding="utf-8") as stream:
        for page in pages:
            stream.write(json.dumps(page, ensure_ascii=False) + "\n")
    write_json(ocr_layer / f"{slug}_structure_generated.json", structure)
    write_text(text_layer / f"{slug}_embedded_text_full_layout.txt", run_text(["pdftotext", "-layout", str(source), "-"]))
    write_text(text_layer / f"{slug}_embedded_text_full_linear.txt", run_text(["pdftotext", "-raw", str(source), "-"]))
    write_json(text_layer / f"{slug}_slides_text_generated.json", {
        "schema_version": SCHEMA, "record_type": "lecture_slides_english_reading_order", "book_id": COURSE_CODE,
        "source_id": deck["source_id"], "source": source_info,
        "language_policy": "English-only derived layer; raw bilingual PDF/OCR text retained separately.",
        "point_form_policy": "Leading bullet/arrow markers and indentation are retained when readable from the embedded text layer.",
        "visual_text_policy": "Text inside non-table visual regions is not separately OCRed or reconstructed.",
        "slides": slide_exports,
        "counts": {"slides": len(slide_exports), "blocks": sum(len(slide["blocks"]) for slide in slide_exports), "list_items": sum(block["content_type"] == "list_item" for slide in slide_exports for block in slide["blocks"])},
        "status": STATUS, "verification_status": STATUS,
    })
    write_json(text_layer / f"{slug}_visual_manifest_generated.json", {
        "schema_version": SCHEMA, "record_type": "lecture_visual_manifest", "book_id": COURSE_CODE, "source_id": deck["source_id"],
        "source": source_info, "visual_policy": {"tables": "full reconstruction when detected", "non_tables": "location/name/type metadata only", "visual_text_ocr": "not separately reconstructed"},
        "visuals": visuals, "counts": {"visuals": len(visuals), "tables": len(tables), "non_table_visuals": sum(not bool(item.get("table_id")) for item in visuals)},
        "status": STATUS, "verification_status": STATUS,
    })
    write_json(text_layer / f"{slug}_tables_generated.json", {
        "schema_version": SCHEMA, "record_type": "lecture_table_reconstructions", "book_id": COURSE_CODE, "source_id": deck["source_id"],
        "source": source_info, "tables": tables, "counts": {"tables": len(tables)},
        "no_table_result": "No coordinate table grids were detected; no table layout or contents were invented." if not tables else None,
        "status": STATUS, "verification_status": STATUS,
    })
    write_json(analysis_layer / f"{slug}_analysis_generated.json", analysis)
    write_json(analysis_layer / f"{slug}_summaries_generated.json", {"schema_version": SCHEMA, "record_type": "lecture_hierarchical_summaries", "book_id": COURSE_CODE, "source_id": deck["source_id"], "processing_order": ["slide", "part", "document", "course"], "units": analysis["summary_units"], "status": STATUS, "verification_status": STATUS})
    write_json(index_layer / "concept_index.json", indexes["concept_index"])
    write_json(index_layer / "occurrence_index.json", indexes["occurrence_index"])
    write_json(index_layer / "term_lookup.json", indexes["term_lookup"])
    write_json(index_layer / "structure_lookup.json", indexes["structure"])
    write_json(index_layer / "visual_index.json", indexes["visual_index"])
    with (index_layer / "passage_index.jsonl").open("w", encoding="utf-8") as stream:
        for passage in indexes["passage_lines"]:
            stream.write(json.dumps(passage, ensure_ascii=False) + "\n")
    write_json(index_layer / "retrieval_index_validation_report.json", validation)
    write_json(index_layer / "hierarchical_summaries.json", {"schema_version": SCHEMA, "record_type": "hierarchical_summaries", "book_id": COURSE_CODE, "source_id": deck["source_id"], "processing_order": ["slide", "part", "document", "course"], "units": analysis["summary_units"], "status": STATUS, "verification_status": STATUS})
    write_json(index_layer / "formal_output_schema.json", {
        "schema_version": "vtc-hhs4867.formal-answer.v1", "record_type": "formal_answer_contract", "required_sections": ["answer", "source_quotations", "references"],
        "reference_rule": "Cite the source filename and slide/PDF page number; this deck uses one slide per PDF page.",
        "visual_rule": "Cite non-table visual name/type/location only; use the linked table record for reconstructed tables.",
        "verification_rule": "Generated text, quotations, visual mappings, table grids, and summaries require manual source-slide verification.",
        "status": STATUS, "verification_status": STATUS,
    })
    counts = {"slides": len(pages), "parts": len(parts), "blocks": sum(len(slide["blocks"]) for slide in slide_exports), "concepts": len(indexes["concept_index"]["concepts"]), "occurrences": len(indexes["occurrence_index"]["occurrences"]), "terms": indexes["term_lookup"]["counts"]["terms"], "passages": len(indexes["passage_lines"]), "visuals": len(visuals), "tables": len(tables), "quotation_candidates": len(analysis["quotation_candidates"])}
    write_json(index_layer / "retrieval_index_manifest.json", {
        "schema_version": "vtc-hhs4867.retrieval-index-manifest.v1", "record_type": "retrieval_index_manifest", "book_id": COURSE_CODE, "source_id": deck["source_id"],
        "package_path": f"sources/{COURSE_CODE}/{deck['source_id']}",
        "index_files": {"concepts": "concept_index.json", "occurrences": "occurrence_index.json", "terms": "term_lookup.json", "passages": "passage_index.jsonl", "visuals": "visual_index.json", "structure": "structure_lookup.json", "summaries": "hierarchical_summaries.json", "formal_output": "formal_output_schema.json", "validation": "retrieval_index_validation_report.json"},
        "source_separation": "This deck remains separate from all other HHS4867 and supplemental source packages.",
        "retrieval_policy": {"course_priority": "This is primary HHS4867 course evidence.", "source_passages_primary": True, "summaries_context_only": True, "non_table_visuals_metadata_only": True, "tables_full_reconstruction_when_detected": True, "exact_quotes_require_manual_verification": True, "claims_index": "not_created"},
        "counts": counts, "status": STATUS, "verification_status": STATUS,
    })
    source_manifest_path = package_root / "source_manifest.json"
    if source_manifest_path.is_file():
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    else:
        source_manifest = {
            "schema_version": "vtc-llm-wiki.source-manifest.v1",
            "record_type": "source_manifest",
            "source_id": deck["source_id"],
            "title": deck["title"],
            "course_code": COURSE_CODE,
            "package_path": f"sources/{COURSE_CODE}/{deck['source_id']}",
            "source_input": {"source_files": [{"file_name": source_filename, "original_path": deck["source_relative"], "size_bytes": source.stat().st_size, "sha256": source_hash, "copied_path": str(package_source), "copy_status": "copied"}]},
        }
    audit = build_duplicate_audit(course_root)
    group = next(item for item in audit["groups"] if item["canonical_path"] == deck["source_relative"])
    duplicate_decision = {"canonical_path": group["canonical_path"], "sha256": group["sha256"], "duplicate_paths": group["duplicate_paths"], "decision": "process canonical path once; do not scan duplicate paths"}
    source_manifest["source_input"]["duplicate_decision"] = duplicate_decision
    source_manifest.update({"processing_status": "processed_generated_layers", "verification_status": STATUS, "status": "processed_generated_layers"})
    source_manifest["processing"] = {"workflow": "register -> SHA-256 duplicate check -> inspect -> embedded text and MuPDF visual trace -> English slide blocks -> visual inventory -> pdfplumber table reconstruction -> slide/part/document/course summaries and keywords -> retrieval index -> validation", "completed_at_hkt": datetime.now().astimezone().isoformat(timespec="seconds"), "source_info": source_info, "duplicate_decision": duplicate_decision, "outputs": {"ocr_layout": f"01 OCR and Layout/{slug}_pages_ocr_layout_generated.jsonl", "structure": f"01 OCR and Layout/{slug}_structure_generated.json", "text": f"02 Text and Tables/{slug}_slides_text_generated.json", "visuals": f"02 Text and Tables/{slug}_visual_manifest_generated.json", "tables": f"02 Text and Tables/{slug}_tables_generated.json", "analysis": f"03 Analysis/{slug}_analysis_generated.json", "summaries": f"03 Analysis/{slug}_summaries_generated.json", "retrieval_index": "04 Retrieval Index/retrieval_index_manifest.json", "ai_usage": "04 Retrieval Index/AI_USAGE_INSTRUCTIONS.md"}, "counts": counts, "all_derived_status": STATUS, "ocr_layout_coverage": "embedded_text_and_mupdf_fallback"}
    source_manifest["next_step"] = "Manually review representative slides, every detected table type, bullet nesting, visual bounding boxes, page references, and exact quotations before changing verification status."
    write_json(source_manifest_path, source_manifest)
    package_readme = f"""# {deck['title']}\n\n- Source ID: `{deck['source_id']}`\n- Course: `{COURSE_CODE}`\n- Source file: `{source_filename}`\n- Original path: `{deck['source_relative']}`\n- SHA-256: `{source_hash}`\n- Slides/PDF pages: `{page_count}`\n- Verification: `{STATUS}`\n\nThis is a source-preserving presentation package. The raw PDF in `00 Source` is immutable. The duplicate decision is recorded in `source_manifest.json`; exact-byte duplicate paths are not scanned again.\n\nProcessing layers are `00 Source`, `01 OCR and Layout`, `02 Text and Tables`, `03 Analysis`, and `04 Retrieval Index`. The derived layer keeps English slide blocks separate from raw bilingual text, records non-table visuals as metadata-only, and reconstructs detected tables separately.\n"""
    write_text(package_root / "README.md", package_readme)
    write_text(index_layer / "AI_USAGE_INSTRUCTIONS.md", ai_instructions(deck, package_root))
    return {"source_id": deck["source_id"], "source": str(source), "sha256": source_hash, "counts": counts, "validation_valid": validation.get("valid"), "validation_checks": validation.get("checks", {})}


def update_registry(registry_path: Path, deck_results: list[dict[str, Any]], audit_rel: str) -> None:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    result_by_id = {item["source_id"]: item for item in deck_results}
    for item in registry.get("sources", []):
        if item.get("course_code") != COURSE_CODE:
            continue
        source_id = item.get("source_id")
        if source_id == EXISTING_DECK["source_id"] or source_id in result_by_id:
            item["course_title"] = COURSE_TITLE
            item["retrieval_group"] = "HHS4867-course-first"
            item["retrieval_index_path"] = f"sources/{COURSE_CODE}/{source_id}/04 Retrieval Index"
            item["query_helper_path"] = f"tools/query_{safe_slug(source_id)}.py"
            item["package_status"] = "processed_lecture_package" if source_id == EXISTING_DECK["source_id"] or source_id in result_by_id else item.get("package_status")
            item["coverage_status"] = "processed_presentation_deck"
            item["verification_status"] = STATUS
            item["claims_index"] = "not_created"
            item["deduplication_audit_path"] = audit_rel
    registry["updated_at"] = datetime.now().astimezone().date().isoformat()
    write_json(registry_path, registry)


def write_query_wrappers(deck_ids: list[str]) -> None:
    for source_id in deck_ids:
        slug = safe_slug(source_id)
        wrapper = f'''#!/usr/bin/env python3\n"""Source-specific HHS4867 retrieval wrapper."""\nfrom pathlib import Path\nimport sys\nsys.path.insert(0, str(Path(__file__).resolve().parent))\nfrom query_hhs4867_retrieval import main\n\nif __name__ == "__main__":\n    raise SystemExit(main(default_source_id="{source_id}"))\n'''
        path = PROJECT_ROOT / "tools" / f"query_{slug}.py"
        write_text(path, wrapper)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, default=COURSE_ROOT_DEFAULT)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "sources/HHS4867")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--source-id", action="append", dest="source_ids", help="Build only the selected new source ID; repeatable")
    args = parser.parse_args()
    course_root = args.course_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    audit = build_duplicate_audit(course_root)
    write_json(output_root / "duplicate_audit_generated.json", audit)
    paddle_available = importlib.util.find_spec("paddleocr") is not None
    use_paddle = paddle_available and not args.skip_paddle
    selected = [deck for deck in DECKS if not args.source_ids or deck["source_id"] in set(args.source_ids)]
    results = []
    for deck in selected:
        results.append(build_one(deck, course_root, output_root, args.dpi, use_paddle))
    all_ids = [EXISTING_DECK["source_id"]] + [deck["source_id"] for deck in DECKS]
    write_query_wrappers(all_ids)
    update_registry(PROJECT_ROOT / "source_registry.json", results, "sources/HHS4867/duplicate_audit_generated.json")
    print(json.dumps({"candidate_pdf_files": audit["candidate_file_count"], "unique_sha256_count": audit["unique_sha256_count"], "built": results, "paddle_available": paddle_available, "paddle_used": use_paddle}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

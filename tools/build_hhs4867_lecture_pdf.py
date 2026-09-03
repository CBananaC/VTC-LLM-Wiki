#!/usr/bin/env python3
"""Build the HHS4867 Lecture 1 PDF-to-LLM-Wiki package.

This adapter reuses the course slide extraction/index engine while applying
the HHS4867 deck's bilingual-line, title, visual, and topic-part rules.  The
raw PDF and raw bilingual embedded text remain separate from the English
derived layer.  Non-table visual contents are deliberately not OCRed or
reconstructed; their names, locations, and source-page references are kept.
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
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SLIDE_TOOLS = PROJECT_ROOT / "HHS4185 Course Materials - LLM Wiki" / "tools"
sys.path.insert(0, str(SLIDE_TOOLS))
import build_hhs4185_course_materials as slide_engine  # noqa: E402
import build_hhs3190m_lecture_pdf as base  # noqa: E402


COURSE_CODE = "HHS4867"
COURSE_TITLE = "HHS4867 - Functional Movement Science"
SOURCE_ID = "HHS4867-L01-MUSCULOSKELETAL-BASIS"
DOCUMENT_ID = SOURCE_ID
SOURCE_FILENAME = "02 - 1. Musculsketal basis for movement 人體肌肉骨骼基礎.pdf"
SOURCE_RELATIVE = "02 Lectures/02 - 1. Musculsketal basis for movement 人體肌肉骨骼基礎.pdf"
SOURCE_PACKAGE_PDF = PROJECT_ROOT / "sources/HHS4867" / SOURCE_ID / "00 Source" / SOURCE_FILENAME
STATUS = "generated_not_verified"
SCHEMA = "vtc-hhs4867-lecture.v1"

DOCUMENT = {
    "document_id": DOCUMENT_ID,
    "file_name": SOURCE_FILENAME,
    "source_type": "lecture",
    "lecture_number": 1,
    "title": "Lecture 1 - Musculoskeletal Basis for Human Movement",
}

TOPIC_PARTS = [
    {"unit_id": f"{SOURCE_ID}-PART00", "title": "Overview of the movement system", "slide_start": 1, "slide_end": 3, "kind": "topic"},
    {"unit_id": f"{SOURCE_ID}-PART01", "title": "Skeleton, cartilage, and ligaments", "slide_start": 4, "slide_end": 9, "kind": "topic"},
    {"unit_id": f"{SOURCE_ID}-PART02", "title": "Joint types", "slide_start": 10, "slide_end": 12, "kind": "topic"},
    {"unit_id": f"{SOURCE_ID}-PART03", "title": "Skeletal muscles and force transmission", "slide_start": 13, "slide_end": 15, "kind": "topic"},
    {"unit_id": f"{SOURCE_ID}-PART04", "title": "Muscle roles and actions", "slide_start": 16, "slide_end": 20, "kind": "topic"},
]

OUTLINE_MAP = [
    {"outline_item": "Movement system components", "mapped_slides": [2], "mapping_status": STATUS},
    {"outline_item": "Human skeleton and bone tissue", "mapped_slides": [3, 4, 5], "mapping_status": STATUS},
    {"outline_item": "Cartilage, ligaments, and joints", "mapped_slides": [6, 7, 8, 9, 10, 11, 12], "mapping_status": STATUS},
    {"outline_item": "Skeletal muscle functions and attachments", "mapped_slides": [13, 14, 15], "mapping_status": STATUS},
    {"outline_item": "Muscle roles, torque, and contraction types", "mapped_slides": [16, 17, 18, 19, 20], "mapping_status": STATUS},
]

SLIDE_TITLES = {
    1: "Musculoskeletal basis for human movement",
    2: "The movement system: parts working together",
    3: "Anterior & Posterior View of Human Body",
    4: "Skeleton & Bone Tissue",
    5: "Bone Tissue Function",
    6: "Cartilage",
    7: "Meniscus",
    8: "Ligaments",
    9: "Ligaments: Bone → bone • guides and limits movement",
    10: "Joint – Synovial Joint",
    11: "Other Types of Joints",
    12: "Types of Joints in the Human Body (diagram)",
    13: "Skeletal muscles of human body",
    14: "Functions of Skeletal muscle",
    15: "Transmission of Muscle force to Bone",
    16: "Role of Muscle",
    17: "Role of Muscle",
    18: "Role of Muscle – Shoulder Abduction",
    19: "Net Muscle Actions",
    20: "Net Muscle Actions (diagram)",
}

LECTURE_KEYWORDS = [
    ("section_topics", "movement system"),
    ("section_topics", "bones"),
    ("section_topics", "joints"),
    ("section_topics", "muscles"),
    ("section_topics", "connective tissue"),
    ("anatomy", "skeleton"),
    ("anatomy", "bone tissue"),
    ("anatomy", "cartilage"),
    ("anatomy", "articular cartilage"),
    ("anatomy", "fibrocartilage"),
    ("anatomy", "meniscus"),
    ("anatomy", "ligaments"),
    ("anatomy", "joint capsule"),
    ("anatomy", "synovial membrane"),
    ("anatomy", "synovial fluid"),
    ("section_topics", "fibrous joints"),
    ("section_topics", "cartilaginous joints"),
    ("section_topics", "synovial joints"),
    ("anatomy", "skeletal muscles"),
    ("section_topics", "muscle movement"),
    ("section_topics", "muscle force"),
    ("section_topics", "tendon"),
    ("section_topics", "aponeurosis"),
    ("definitions_abbreviations", "origin"),
    ("definitions_abbreviations", "insertion"),
    ("definitions_abbreviations", "torque"),
    ("section_topics", "agonist"),
    ("section_topics", "antagonist"),
    ("section_topics", "stabilizer"),
    ("section_topics", "neutralizer"),
    ("section_topics", "shoulder abduction"),
    ("definitions_abbreviations", "isometric"),
    ("definitions_abbreviations", "concentric"),
    ("definitions_abbreviations", "eccentric"),
]

VISUAL_NAMES = {
    2: [
        "Movement-system exercise photograph",
        "Bones component box",
        "Joints component box",
        "Muscles component box",
        "Connective tissue component box",
    ],
    3: ["Anterior and posterior views of the human skeleton"],
    7: ["Articular cartilage of the knee", "Meniscus of the knee"],
    9: ["Ligament examples around the knee"],
    10: ["Synovial joint anatomy diagram"],
    12: ["Types of joints in the human body diagram"],
    13: ["Skeletal muscles of the human body"],
    15: ["Three muscle-to-bone attachment examples"],
    18: ["Shoulder-abduction agonist, antagonist, stabilizer, and neutralizer diagram"],
    20: ["Isometric, concentric, and eccentric muscle actions diagram"],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


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


def patch_base_globals() -> None:
    """Configure reusable HHS3190 helpers without editing their source."""
    slide_engine.COURSE_CODE = COURSE_CODE
    slide_engine.DOCUMENTS = [DOCUMENT]
    slide_engine.SOURCE_ALIASES = {SOURCE_FILENAME: (SOURCE_RELATIVE,)}
    slide_engine.SCHEMA_VERSION = SCHEMA
    slide_engine.LIST_MARKER_CHARS = "•●▪◦◉➢➤→⇒↔⚫"
    slide_engine.LIST_MARKER_RE = re.compile(r"^\s*(?P<marker>[•●▪◦◉➢➤→⇒↔⚫]+|[-–—])(?:\s+|$)")
    for name, value in {
        "COURSE_CODE": COURSE_CODE,
        "COURSE_TITLE": COURSE_TITLE,
        "SOURCE_ID": SOURCE_ID,
        "DOCUMENT_ID": DOCUMENT_ID,
        "SOURCE_FILENAME": SOURCE_FILENAME,
        "SOURCE_RELATIVE": SOURCE_RELATIVE,
        "SCHEMA": SCHEMA,
        "DOCUMENT": DOCUMENT,
        "TOPIC_PARTS": TOPIC_PARTS,
        "LECTURE_KEYWORDS": LECTURE_KEYWORDS,
        "SLIDE_TITLE_OVERRIDES": SLIDE_TITLES,
    }.items():
        setattr(base, name, value)


def center_inside(bbox: list[float], container: list[float]) -> bool:
    cx = (float(bbox[0]) + float(bbox[2])) / 2
    cy = (float(bbox[1]) + float(bbox[3])) / 2
    return float(container[0]) <= cx <= float(container[2]) and float(container[1]) <= cy <= float(container[3])


def filter_visual_backgrounds_and_text(pages: list[dict[str, Any]]) -> None:
    """Exclude template backgrounds and image-internal embedded text."""
    for page in pages:
        objects = [item for item in page.get("embedded_image_objects", []) if not item.get("full_page")]
        page["embedded_image_objects"] = objects
        boxes = [list(item["bbox_points"]) for item in objects if item.get("bbox_points")]
        page["visual_exclusion_boxes"] = boxes
        lines = base.english_bilingual_lines(page)
        lines = [line for line in lines if not any(center_inside(list(line.get("bbox_points", [0, 0, 0, 0])), box) for box in boxes)]
        if lines:
            base_x = min(float(item["bbox_points"][0]) for item in lines)
            for item in lines:
                indent = max(0.0, float(item["bbox_points"][0]) - base_x)
                item["indent_points"] = round(indent, 3)
                item["indent_level"] = int(round(indent / 24.0))
        page["reading_order_lines"] = lines
        page["title_candidate_source"] = page.get("title_candidate")
        page["title_candidate"] = SLIDE_TITLES.get(page["pdf_page"], "")
        page["reading_order_text"] = "\n".join(item["text"] for item in lines)


def merge_title_blocks(page: dict[str, Any], blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join title lines split into multiple text objects on slides 3 and 13."""
    title = SLIDE_TITLES.get(page["pdf_page"], "").strip()
    if not title or not blocks:
        return blocks
    target = slide_engine.normalize(title)
    for end in range(1, min(5, len(blocks)) + 1):
        candidate = slide_engine.normalize(" ".join(block.get("body_text", "") for block in blocks[:end]))
        if candidate != target:
            continue
        chosen = blocks[0]
        chosen["content_type"] = "slide_title"
        chosen["text"] = title
        chosen["body_text"] = title
        chosen["marker"] = None
        chosen["marker_source"] = "manual-title-line-reconstruction"
        chosen["source_line_indices"] = [idx for block in blocks[:end] for idx in block.get("source_line_indices", []) if idx is not None]
        chosen["bbox_points"] = [
            min(block["bbox_points"][0] for block in blocks[:end]),
            min(block["bbox_points"][1] for block in blocks[:end]),
            max(block["bbox_points"][2] for block in blocks[:end]),
            max(block["bbox_points"][3] for block in blocks[:end]),
        ]
        return [chosen] + blocks[end:]
    return blocks


def build_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = merge_title_blocks(page, base.build_slide_blocks(page))
    if page["pdf_page"] in {18, 20} and blocks:
        # The slide title is embedded as "Role of Muscle" or "Net Muscle
        # Actions" while the slide's visual makes the topic qualifier clear.
        first = blocks[0]
        if slide_engine.normalize(first.get("body_text", "")) in {"roleofmuscle", "netmuscleactions"}:
            first["content_type"] = "slide_title"
            first["text"] = SLIDE_TITLES[page["pdf_page"]]
            first["body_text"] = SLIDE_TITLES[page["pdf_page"]]
            first["marker"] = None
            first["marker_source"] = "manual-visual-review-title-context"
    if page["pdf_page"] == 12 and not blocks:
        blocks = [{
            "block_id": f"{page['source_page_id']}-B001",
            "source_page_id": page["source_page_id"],
            "slide_number": page["pdf_page"],
            "content_type": "slide_title",
            "text": SLIDE_TITLES[12],
            "body_text": SLIDE_TITLES[12],
            "marker": None,
            "marker_source": "manual-visual-review",
            "indent_points": 0,
            "indent_level": 0,
            "source_line_indices": [],
            "bbox_points": [0, 0, 0, 0],
            "language": "en",
            "content_source": "visual-review-title-only",
            "status": STATUS,
            "verification_status": STATUS,
        }]
    for block in blocks:
        # These are unambiguous PDF text-object spacing artifacts confirmed
        # against the rendered source slides; all other source wording is
        # retained as extracted.
        block["text"] = block["text"].replace("andstabilizing", "and stabilizing")
        block["body_text"] = block["body_text"].replace("andstabilizing", "and stabilizing")
        block["text"] = block["text"].replace("OriginV.S.", "Origin V.S.")
        block["body_text"] = block["body_text"].replace("OriginV.S.", "Origin V.S.")
        block["text"] = block["text"].replace("Deltoid(abductor)", "Deltoid (abductor)")
        block["body_text"] = block["body_text"].replace("Deltoid(abductor)", "Deltoid (abductor)")
        block["text"] = block["text"].replace("dorsi(adductor)", "dorsi (adductor)")
        block["body_text"] = block["body_text"].replace("dorsi(adductor)", "dorsi (adductor)")
        block.setdefault("content_source", "embedded-pdf-text")
    return blocks


def name_visuals(visuals: list[dict[str, Any]]) -> None:
    by_page: dict[int, list[dict[str, Any]]] = {}
    for visual in visuals:
        by_page.setdefault(int(visual["pdf_page"]), []).append(visual)
    for page_number, items in by_page.items():
        names = VISUAL_NAMES.get(page_number, [])
        items.sort(key=lambda item: (item["location"]["bbox_points"][1], item["location"]["bbox_points"][0]))
        for index, item in enumerate(items):
            if index < len(names):
                item["name"] = names[index]
            item["caption"] = None
            item["policy"] = "metadata_only"
            item["detection_note"] = "Non-table visual; visual contents were not separately OCRed or reconstructed."


def enrich_visuals(visuals: list[dict[str, Any]], pages: list[dict[str, Any]], page_to_part: dict[str, str]) -> None:
    page_by_id = {page["source_page_id"]: page for page in pages}
    for visual in visuals:
        page = page_by_id[visual["source_page_id"]]
        part_id = page_to_part.get(page["source_page_id"])
        visual["page_reference"] = slide_engine.source_page_reference(DOCUMENT, page)
        visual["section_ids"] = [value for value in [page["source_page_id"], part_id, DOCUMENT_ID, f"{COURSE_CODE}-COURSE"] if value]
        visual["section_paths"] = [[COURSE_TITLE, DOCUMENT["title"], next((part["title"] for part in TOPIC_PARTS if part["unit_id"] == part_id), ""), SLIDE_TITLES.get(page["pdf_page"], f"Slide {page['pdf_page']}")]]
        visual["table_reconstruction_available"] = False
        visual["table_reconstruction_source"] = None
        visual["status"] = STATUS
        visual["verification_status"] = STATUS


def visual_keywords(visuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for visual in visuals:
        name = str(visual.get("name") or visual.get("visual_type") or "visual")
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
            "source_page_ids": [visual["source_page_id"]],
            "source_element_ids": [visual["visual_id"]],
            "section_ids": visual.get("section_ids", []),
            "source_excerpt": name,
            "status": STATUS,
            "verification_status": STATUS,
        })
    return records


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, default=Path("/Users/creamybanana/Downloads/Movement Science"))
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "sources/HHS4867" / SOURCE_ID)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs4867-course"))
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root.expanduser().resolve()
    if output_root.exists() and any(item.name != "00 Source" for item in output_root.iterdir()) and not args.overwrite:
        raise SystemExit(f"Output exists; pass --overwrite: {output_root}")
    patch_base_globals()
    course_root = args.course_root.expanduser().resolve()
    source = slide_engine.document_source_path(course_root, DOCUMENT)
    source_hash = sha256_file(source)
    if SOURCE_PACKAGE_PDF.exists() and sha256_file(SOURCE_PACKAGE_PDF) != source_hash:
        raise RuntimeError("package source hash does not match the selected original source")
    DOCUMENT["source_path"] = str(source)
    DOCUMENT["source_sha256"] = source_hash
    manifest, pages = slide_engine.collect_pages(course_root, args.dpi, args.paddle_cache.expanduser().resolve(), args.skip_paddle)
    expected_pages = int(pdfinfo(source).get("Pages", 0))
    if len(pages) != expected_pages:
        raise RuntimeError(f"processed page count mismatch: {len(pages)} != {expected_pages}")
    filter_visual_backgrounds_and_text(pages)
    parts, page_to_part = base.explicit_parts(pages)

    blocks_by_page: dict[str, list[dict[str, Any]]] = {}
    slide_exports = []
    for page in pages:
        blocks = build_blocks(page)
        blocks_by_page[page["source_page_id"]] = blocks
        page["english_blocks"] = blocks
        page["english_clean_text"] = "\n".join(block["text"] for block in blocks)
        page["reading_order_text"] = page["english_clean_text"]
        slide_exports.append({
            "source_page_id": page["source_page_id"],
            "slide_number": page["pdf_page"],
            "title": SLIDE_TITLES.get(page["pdf_page"], f"Slide {page['pdf_page']}"),
            "english_text": page["english_clean_text"],
            "raw_bilingual_text": page.get("embedded_text", ""),
            "blocks": blocks,
            "visual_ids": [],
            "status": STATUS,
            "verification_status": STATUS,
        })

    visuals, tables = slide_engine.page_visuals(pages)
    name_visuals(visuals)
    enrich_visuals(visuals, pages, page_to_part)
    visual_by_page: dict[str, list[dict[str, Any]]] = {}
    for visual in visuals:
        visual_by_page.setdefault(visual["source_page_id"], []).append(visual)
    for slide in slide_exports:
        slide["visual_ids"] = [item["visual_id"] for item in visual_by_page.get(slide["source_page_id"], [])]
        slide["visual_placeholders"] = [{
            "visual_id": item["visual_id"],
            "visual_type": item["visual_type"],
            "name": item.get("name"),
            "pdf_page": item["pdf_page"],
            "slide_number": item["slide_number"],
            "location": item["location"],
            "policy": item["policy"],
            "status": STATUS,
            "verification_status": STATUS,
        } for item in visual_by_page.get(slide["source_page_id"], [])]

    structure, node_by_id = slide_engine.build_structure([DOCUMENT], pages, parts, page_to_part, visuals)
    structure["book_id"] = COURSE_CODE
    structure["course"]["title"] = COURSE_TITLE
    structure["hierarchy_order"] = ["course", "document", "part", "slide", "block"]
    structure["processing_order"] = ["block", "slide", "part", "document", "course"]
    structure["outline_map"] = OUTLINE_MAP
    structure["hierarchy_semantics"] = {
        "course": "HHS4867 course container",
        "document": "one lecture PDF/deck",
        "part": "inferred lecture topic grouping from slide sequence",
        "slide": "PDF page and slide number",
        "block": "English title, subtitle, paragraph, or preserved point-form item",
        "visual": "location/name/type metadata only; visual contents are not reconstructed",
        "table": "no table candidates detected in this deck",
    }
    structure["visual_content_policy"] = "Non-table visual contents were not separately OCRed; only source-page location, name, and type are indexed."
    for node in structure["nodes"]:
        node["status"] = STATUS
        node["verification_status"] = STATUS

    analysis, _ = slide_engine.build_analysis([DOCUMENT], pages, parts, page_to_part, visuals, tables, node_by_id)
    base.augment_lecture_keywords(analysis, pages, page_to_part)
    visual_kw = visual_keywords(visuals)
    analysis["keyword_records"].extend(visual_kw)
    analysis["visual_keyword_records"] = visual_kw
    analysis["quotation_candidates"] = base.quotation_candidates(pages, blocks_by_page)
    analysis["processing_order"] = ["block", "slide", "part", "document", "course"]
    analysis["counts"]["keyword_records"] = len(analysis["keyword_records"])
    analysis["counts"]["visual_keyword_records"] = len(visual_kw)
    analysis["counts"]["quotation_candidates"] = len(analysis["quotation_candidates"])
    analysis["status"] = STATUS
    analysis["verification_status"] = STATUS

    indexes = slide_engine.build_retrieval_indexes([DOCUMENT], pages, parts, page_to_part, visuals, tables, analysis, structure, node_by_id)
    structure = base.replace_tokens(structure)
    analysis = base.replace_tokens(analysis)
    indexes = base.replace_tokens(indexes)
    validation = indexes["validation"]
    validation["checks"].update({
        "english_clean_layer_present": len(slide_exports) == expected_pages and all(slide["english_text"] is not None for slide in slide_exports),
        "embedded_pdf_text_complete": all(bool(page.get("embedded_text", "").strip()) for page in pages),
        "text_or_ocr_source_available": all(bool(page.get("embedded_text", "").strip()) or page.get("ocr_status") == "completed" for page in pages),
        "full_page_backgrounds_excluded": all(not item.get("full_page") for page in pages for item in page.get("embedded_image_objects", [])),
        "visual_records_have_locations": all(item.get("location", {}).get("bbox_points") for item in visuals),
        "non_table_visuals_metadata_only": all(item.get("policy") == "metadata_only" and not item.get("table_id") for item in visuals),
        "no_table_result_recorded": not tables,
        "bullet_markers_preserved": all(block.get("marker") is not None or block.get("content_type") != "list_item" for slide in slide_exports for block in slide["blocks"]),
        "all_derived_status_generated_not_verified": all(item.get("verification_status") == STATUS for item in visuals + tables + analysis["quotation_candidates"]),
    })
    validation["valid"] = all(value is True for key, value in validation["checks"].items() if key not in {"all_pages_have_ocr", "all_pages_have_layout"})
    validation["validation_scope_note"] = "Embedded-text and MuPDF visual-trace fallback passed. PaddleOCR/layout checks remain false when --skip-paddle is used; visual contents were intentionally not OCRed."
    validation["status"] = STATUS
    validation["verification_status"] = STATUS
    indexes["validation"] = validation

    source_info = {
        "filename": source.name,
        "path": str(source),
        "package_source_path": str(SOURCE_PACKAGE_PDF),
        "sha256": source_hash,
        "pdf_page_count": expected_pages,
        "pdfinfo": pdfinfo(source),
        "text_extraction": "embedded PDF text with bbox coordinates",
        "ocr_engine": "PaddleOCR PP-OCRv6_medium_det/rec + PP-DocLayout_plus-L" if not args.skip_paddle else "not_run; embedded PDF text and MuPDF image trace used",
        "visual_text_policy": "Non-table visual contents were not separately OCRed or reconstructed.",
    }
    ocr_layer = output_root / "01 OCR and Layout"
    text_layer = output_root / "02 Text and Tables"
    analysis_layer = output_root / "03 Analysis"
    index_layer = output_root / "04 Retrieval Index"
    for layer in (ocr_layer, text_layer, analysis_layer, index_layer):
        layer.mkdir(parents=True, exist_ok=True)
    with (ocr_layer / "hhs4867_l01_pages_ocr_layout_generated.jsonl").open("w", encoding="utf-8") as stream:
        for page in pages:
            stream.write(json.dumps(page, ensure_ascii=False) + "\n")
    write_json(ocr_layer / "hhs4867_l01_structure_generated.json", structure)
    write_text(text_layer / "hhs4867_l01_embedded_text_full_layout.txt", run_text(["pdftotext", "-layout", str(source), "-"]))
    write_text(text_layer / "hhs4867_l01_embedded_text_full_linear.txt", run_text(["pdftotext", "-raw", str(source), "-"]))
    write_json(text_layer / "hhs4867_l01_slides_text_generated.json", {
        "schema_version": SCHEMA,
        "record_type": "lecture_slides_english_reading_order",
        "book_id": COURSE_CODE,
        "source_id": SOURCE_ID,
        "source": source_info,
        "language_policy": "English-only derived layer; raw bilingual PDF/OCR retained separately.",
        "point_form_policy": "Leading bullet/arrow markers and indentation are retained, including the deck's ⚫ markers.",
        "visual_text_policy": "Text inside non-table visual regions is not separately OCRed or reconstructed.",
        "slides": slide_exports,
        "counts": {"slides": len(slide_exports), "blocks": sum(len(slide["blocks"]) for slide in slide_exports), "list_items": sum(block["content_type"] == "list_item" for slide in slide_exports for block in slide["blocks"])},
        "status": STATUS,
        "verification_status": STATUS,
    })
    write_json(text_layer / "hhs4867_l01_visual_manifest_generated.json", {
        "schema_version": SCHEMA,
        "record_type": "lecture_visual_manifest",
        "book_id": COURSE_CODE,
        "source_id": SOURCE_ID,
        "source": source_info,
        "visual_policy": {"tables": "full reconstruction when detected", "non_tables": "location/name/type metadata only", "visual_text_ocr": "not separately reconstructed"},
        "visuals": visuals,
        "counts": {"visuals": len(visuals), "tables": 0, "non_table_visuals": len(visuals)},
        "status": STATUS,
        "verification_status": STATUS,
    })
    write_json(text_layer / "hhs4867_l01_tables_generated.json", {
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
    write_json(analysis_layer / "hhs4867_l01_analysis_generated.json", analysis)
    write_json(analysis_layer / "hhs4867_l01_summaries_generated.json", {"schema_version": SCHEMA, "record_type": "lecture_hierarchical_summaries", "book_id": COURSE_CODE, "source_id": SOURCE_ID, "processing_order": ["slide", "part", "document", "course"], "units": analysis["summary_units"], "status": STATUS, "verification_status": STATUS})

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
        "schema_version": "vtc-hhs4867m.formal-answer.v1",
        "record_type": "formal_answer_contract",
        "required_sections": ["answer", "source_quotations", "references"],
        "reference_rule": "Cite the lecture filename and slide/PDF page number; this deck uses one slide per PDF page.",
        "visual_rule": "Cite visual name/type/location only; reconstruct contents only for a detected table.",
        "verification_rule": "Generated text, quotations, visual mappings, and summaries require manual source-slide verification.",
        "status": STATUS,
        "verification_status": STATUS,
    })
    retrieval_manifest = {
        "schema_version": "vtc-hhs4867.retrieval-index-manifest.v1",
        "record_type": "retrieval_index_manifest",
        "book_id": COURSE_CODE,
        "source_id": SOURCE_ID,
        "package_path": f"sources/{COURSE_CODE}/{SOURCE_ID}",
        "index_files": {"concepts": "concept_index.json", "occurrences": "occurrence_index.json", "terms": "term_lookup.json", "passages": "passage_index.jsonl", "visuals": "visual_index.json", "structure": "structure_lookup.json", "summaries": "hierarchical_summaries.json", "formal_output": "formal_output_schema.json", "validation": "retrieval_index_validation_report.json"},
        "source_separation": "This lecture package remains separate from all other HHS4867, HHS3190M, HHS4185, and supplemental source packages.",
        "retrieval_policy": {"course_priority": "This is primary HHS4867 lecture evidence.", "source_passages_primary": True, "summaries_context_only": True, "non_table_visuals_metadata_only": True, "tables_full_reconstruction_when_detected": True, "exact_quotes_require_manual_verification": True, "claims_index": "not_created"},
        "counts": {"slides": len(pages), "parts": len(parts), "blocks": sum(len(slide["blocks"]) for slide in slide_exports), "concepts": len(indexes["concept_index"]["concepts"]), "occurrences": len(indexes["occurrence_index"]["occurrences"]), "terms": indexes["term_lookup"]["counts"]["terms"], "passages": len(indexes["passage_lines"]), "visuals": len(visuals), "tables": len(tables), "quotation_candidates": len(analysis["quotation_candidates"])},
        "status": STATUS,
        "verification_status": STATUS,
    }
    write_json(index_layer / "retrieval_index_manifest.json", retrieval_manifest)

    source_manifest_path = output_root / "source_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8")) if source_manifest_path.exists() else {"schema_version": "vtc-llm-wiki.source-manifest.v1", "record_type": "source_manifest", "source_id": SOURCE_ID, "title": DOCUMENT["title"], "course_code": COURSE_CODE, "package_path": str(output_root.relative_to(PROJECT_ROOT))}
    source_manifest.update({"processing_status": "processed_generated_layers", "verification_status": STATUS, "status": "processed_generated_layers"})
    source_manifest["processing"] = {"workflow": "register -> inspect -> embedded text and optional PaddleOCR OCR/layout -> English slide blocks -> background and visual-text separation -> visual inventory -> table detection/reconstruction -> slide/part/document/course summaries and keywords -> retrieval index", "completed_at_hkt": datetime.now().astimezone().isoformat(timespec="seconds"), "outputs": {"ocr_layout": "01 OCR and Layout/hhs4867_l01_pages_ocr_layout_generated.jsonl", "structure": "01 OCR and Layout/hhs4867_l01_structure_generated.json", "text": "02 Text and Tables/hhs4867_l01_slides_text_generated.json", "visuals": "02 Text and Tables/hhs4867_l01_visual_manifest_generated.json", "tables": "02 Text and Tables/hhs4867_l01_tables_generated.json", "analysis": "03 Analysis/hhs4867_l01_analysis_generated.json", "summaries": "03 Analysis/hhs4867_l01_summaries_generated.json", "retrieval_index": "04 Retrieval Index/retrieval_index_manifest.json", "query_helper": "../../tools/query_hhs4867_lecture.py"}, "counts": retrieval_manifest["counts"], "all_derived_status": STATUS}
    source_manifest["next_step"] = "Manually review representative slides, bullet nesting, visual bounding boxes, page references, and the no-table result before changing verification status."
    write_json(source_manifest_path, source_manifest)
    print(json.dumps({"output_root": str(output_root), "source": str(source), "source_sha256": source_hash, "counts": retrieval_manifest["counts"], "validation": validation, "status": STATUS}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

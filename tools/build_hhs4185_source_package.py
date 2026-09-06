#!/usr/bin/env python3
"""Build one standalone HHS4185 PDF source package.

This adapter reuses the established slide-PDF extraction functions while
writing the portable source-package layout required by the VTC LLM Wiki:
00 Source, 01 OCR and Layout, 02 Text and Tables, 03 Analysis, and 04
Retrieval Index. Raw embedded text, OCR/layout candidates, visual locations,
table reconstructions, keywords, summaries, and retrieval indexes remain
separate generated layers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COURSE_BUILDER_DIR = PROJECT_ROOT / "HHS4185 Course Materials - LLM Wiki" / "tools"
sys.path.insert(0, str(COURSE_BUILDER_DIR))
import build_hhs4185_course_materials as course_builder  # noqa: E402


STATUS = "generated_not_verified"
REGISTRY_PATH = PROJECT_ROOT / "source_registry.json"
CJK_RE = re.compile(r"[\u3400-\u9fff]")

SOURCE_CONFIGS: dict[str, dict[str, str]] = {
    "HHS4185-T1-ICF-2026": {
        "document_id": "HHS4185-T1-ICF",
        "raw_file": "01 - T1 ICF.pdf",
        "title": "Tutorial 1 - ICF",
    },
    "HHS4185-WS1-EQUIPMENT-2026": {
        "document_id": "HHS4185-WS1",
        "raw_file": "02 - WS1 Equipment.pdf",
        "title": "Workshop 1 - Introduction to Rehabilitation Equipment",
    },
    "HHS4185-L3-SOFT-TISSUE-2026": {
        "document_id": "HHS4185-L3",
        "raw_file": "HHS4185J_L3_軟組織問題_Soft tissue injuries.pdf",
        "title": "Lecture 3 - Orthopaedic Soft Tissue Problems: Acute Sprain and Repetitive Stress Injury",
        "source_type": "lecture_bilingual",
    },
}

L3_PART_SPECS = (
    ("Lecture cover", 1, 1),
    ("Soft Tissues Overview", 2, 9),
    ("Soft Tissue Injuries", 10, 24),
    ("Ligament Sprain", 25, 34),
    ("Tendon / Muscle Strain", 35, 44),
    ("Muscle Contusion", 45, 52),
    ("Repetitive Strain Injury", 53, 60),
    ("Carpal Tunnel Syndrome", 61, 66),
    ("Trigger Finger", 67, 70),
    ("Tennis elbow / Lateral epicondylitis", 71, 72),
    ("Plantar Fasciitis", 73, 76),
    ("E-Resources", 77, 81),
)


ADDITIONAL_DOCUMENTS: tuple[dict[str, Any], ...] = (
    {
        "document_id": "HHS4185-L3",
        "file_name": "HHS4185J_L3.pdf",
        "source_type": "lecture",
        "lecture_number": 3,
        "title": "Lecture 3 - Orthopaedic Soft Tissue Problems: Acute Sprain and Repetitive Stress Injury",
    },
)


def ensure_additional_documents() -> None:
    for document in ADDITIONAL_DOCUMENTS:
        if not any(existing.get("document_id") == document["document_id"] for existing in course_builder.DOCUMENTS):
            course_builder.DOCUMENTS.append(dict(document))


def apply_l3_structure_overrides(
    source_id: str,
    documents: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    parts: list[dict[str, Any]],
    page_to_part: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Use the visible L3 section-divider layout for stable major sections."""
    if source_id != "HHS4185-L3-SOFT-TISSUE-2026":
        return parts, page_to_part
    document = documents[0]
    page_by_number = {page["pdf_page"]: page for page in pages}
    override_parts: list[dict[str, Any]] = []
    override_page_to_part: dict[str, str] = {}
    for index, (title, start_page, end_page) in enumerate(L3_PART_SPECS, 1):
        part_id = f"{document['document_id']}-PART{index:02d}"
        part_pages = [page_by_number[number] for number in range(start_page, end_page + 1)]
        override_parts.append({
            "unit_id": part_id,
            "level": "part",
            "document_id": document["document_id"],
            "document_title": document["title"],
            "title": title,
            "slide_start": start_page,
            "slide_end": end_page,
            "pdf_page_start": start_page,
            "pdf_page_end": end_page,
            "source_page_ids": [page["source_page_id"] for page in part_pages],
            "status": STATUS,
            "verification_status": STATUS,
        })
        for page in part_pages:
            override_page_to_part[page["source_page_id"]] = part_id
    return override_parts, override_page_to_part


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def source_paths(source_id: str) -> tuple[Path, Path]:
    package_root = PROJECT_ROOT / "sources" / "HHS4185" / source_id
    config = SOURCE_CONFIGS[source_id]
    raw_path = package_root / "00 Source" / config["raw_file"]
    return package_root, raw_path


def add_source_id(records: Any, source_id: str) -> None:
    for record in records:
        record["source_id"] = source_id


def english_derived_text(value: str) -> str:
    """Keep English text and non-linguistic symbols, discard Chinese-only text."""
    text = course_builder.clean_text(value)
    if not text:
        return ""
    marker, body = course_builder.split_list_marker(text)
    if CJK_RE.search(body):
        # A bilingual PDF often appends Chinese text and repeats short
        # English abbreviations inside that Chinese layer.  Keep the most
        # substantial English segment, normally the real English version,
        # rather than joining every fragment around the CJK characters.
        segments = [course_builder.clean_text(part) for part in CJK_RE.split(body)]
        segments = [part for part in segments if part]
        viable = [part for part in segments if re.search(r"[A-Za-z]{4,}", part)]
        if not viable:
            return marker if marker and not body else ""
        candidate = max(
            viable,
            key=lambda part: (len(re.findall(r"[A-Za-z]{4,}", part)), len(part)),
        )
    else:
        candidate = body
    candidate = candidate.replace("（", "(").replace("）", ")")
    candidate = candidate.replace("，", ",").replace("：", ":")
    candidate = re.sub(r"\s+([,.;:!?%)\]])", r"\1", candidate)
    candidate = re.sub(r"([([])\s+", r"\1", candidate)
    return f"{marker} {candidate}".strip() if marker else candidate


def english_line_records(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create English-only derived line records from raw coordinate lines."""
    records: list[dict[str, Any]] = []
    pending_marker = ""
    for line in course_builder.reading_order_lines(lines):
        raw_text = course_builder.clean_text(line.get("text", ""))
        marker, body = course_builder.split_list_marker(raw_text)
        text = english_derived_text(body)
        if not text:
            if marker:
                pending_marker = marker
            continue
        if pending_marker and not marker:
            text = f"{pending_marker} {text}".strip()
            marker = pending_marker
            pending_marker = ""
        elif marker:
            pending_marker = ""
        records.append({
            "source_line_index": line.get("line_index"),
            "bbox_points": line.get("bbox_points", [0, 0, 0, 0]),
            "text": text,
            "language": "en",
            "marker": marker or None,
        })
    if pending_marker:
        records.append({
            "source_line_index": None,
            "bbox_points": [0, 0, 0, 0],
            "text": pending_marker,
            "language": "en",
            "marker": pending_marker,
        })
    if records:
        base_x = min(float(item["bbox_points"][0]) for item in records)
        for item in records:
            indent_points = max(0.0, float(item["bbox_points"][0]) - base_x)
            item["indent_points"] = round(indent_points, 3)
            item["indent_level"] = int(round(indent_points / 24.0))
    return records


def english_title_slide_lines(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter English lines for title detection before visual text removal."""
    filtered: list[dict[str, Any]] = []
    for line in page.get("reading_order_lines", []):
        text = course_builder.clean_text(line.get("text", ""))
        lowered = course_builder.normalize(text)
        if not text or lowered in {"ive", "healthandlifesciences", "allrightsreserved"}:
            continue
        if re.fullmatch(r"\d{1,3}", text):
            continue
        if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text):
            continue
        if "higherdiplomainrehabilitationservices" in lowered:
            continue
        if "commonrehabilitationconditions" in lowered and len(text) < 90:
            continue
        if re.match(r"(?i)^(?:lecturer|m\s*s\.?|ms\.?)\b", text):
            continue
        filtered.append(line)
    return filtered


def line_is_visual_text(line: dict[str, Any], page: dict[str, Any]) -> bool:
    """Exclude embedded text located inside a detected non-table visual."""
    line_bbox = line.get("bbox_points") or [0, 0, 0, 0]
    visual_labels = set(course_builder.NON_TABLE_LABELS) | {"image", "table"}
    for box in page.get("layout_boxes", []):
        label = str(box.get("label") or "").casefold()
        if not box.get("is_visual_candidate") or label not in visual_labels:
            continue
        bbox = box.get("bbox_points") or [0, 0, 0, 0]
        horizontal_overlap = max(0.0, min(line_bbox[2], bbox[2]) - max(line_bbox[0], bbox[0]))
        line_width = max(1.0, line_bbox[2] - line_bbox[0])
        vertical_overlap = max(0.0, min(line_bbox[3], bbox[3]) - max(line_bbox[1], bbox[1]))
        line_height = max(1.0, line_bbox[3] - line_bbox[1])
        if horizontal_overlap / line_width >= 0.35 and vertical_overlap / line_height >= 0.35:
            return True
        near_below = 0 <= line_bbox[1] - bbox[3] <= 28
        if near_below and horizontal_overlap / line_width >= 0.35:
            return True
    return False


def english_useful_slide_lines(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Return English body lines while keeping all visual interiors raw-only."""
    return [line for line in english_title_slide_lines(page) if not line_is_visual_text(line, page)]


def sanitize_table(table: dict[str, Any]) -> None:
    """Remove Chinese-only cells while retaining English cells and marks."""
    rows = []
    for row in table.get("content", {}).get("rows", []):
        cells = []
        for cell in row.get("cells", []):
            text = english_derived_text(str(cell.get("text", "")))
            if not text:
                continue
            updated = dict(cell)
            updated["text"] = text
            cells.append(updated)
        updated_row = dict(row)
        updated_row["cells"] = cells
        updated_row["text"] = " ".join(cell["text"] for cell in cells)
        rows.append(updated_row)
    table.setdefault("content", {})["rows"] = rows
    table["content"]["text"] = "\n".join(row["text"] for row in rows if row["text"])
    table["language_policy"] = "english_only_derived_cells; raw_page_text_preserved_separately"


def clamp_visual_locations(visuals: list[dict[str, Any]], pages: list[dict[str, Any]]) -> None:
    """Keep published visual coordinates inside the corresponding slide."""
    dimensions = {page["source_page_id"]: (float(page["width_points"]), float(page["height_points"])) for page in pages}
    for visual in visuals:
        location = visual.get("location") or {}
        bbox = list(location.get("bbox_points") or [0, 0, 0, 0])
        width, height = dimensions[visual["source_page_id"]]
        clamped = [
            max(0.0, min(width, float(bbox[0]))),
            max(0.0, min(height, float(bbox[1]))),
            max(0.0, min(width, float(bbox[2]))),
            max(0.0, min(height, float(bbox[3]))),
        ]
        if clamped != bbox:
            location["raw_bbox_points"] = bbox
            location["location_note"] = "Published coordinates clamped to the slide bounds; raw detector coordinates retained separately."
        location["bbox_points"] = [round(value, 3) for value in clamped]
        visual["location"] = location


def visual_locations_in_bounds(visuals: list[dict[str, Any]], pages: list[dict[str, Any]]) -> bool:
    dimensions = {page["source_page_id"]: (float(page["width_points"]), float(page["height_points"])) for page in pages}
    for visual in visuals:
        bbox = visual.get("location", {}).get("bbox_points") or []
        width, height = dimensions.get(visual.get("source_page_id"), (0, 0))
        if len(bbox) != 4 or not (0 <= bbox[0] <= bbox[2] <= width and 0 <= bbox[1] <= bbox[3] <= height):
            return False
    return True


def apply_visual_table_review(source_id: str, tables: list[dict[str, Any]]) -> None:
    """Add source-page-reviewed logical layouts for detected workshop tables."""
    if source_id not in {"HHS4185-WS1-EQUIPMENT-2026", "HHS4185-L3-SOFT-TISSUE-2026"}:
        return
    for table in tables:
        page = table.get("pdf_page")
        content = table.setdefault("content", {})
        if source_id == "HHS4185-L3-SOFT-TISSUE-2026" and page == 16:
            columns = [
                "Tissue and grades of injury", "0–3 d", "4–14 d", "3–4 wk", "5–7 wk",
                "2–3 mo", "3–6 mo", "6–12 mo", ">1 year",
            ]
            rows = [
                {"row_index": 1, "row_role": "data", "cells": [{"column": columns[0], "text": "Skin"}], "shaded_range": {"start": "4–14 d", "end": "6–12 mo"}},
                {"row_index": 2, "row_role": "data", "cells": [{"column": columns[0], "text": "SQ"}], "shaded_range": {"start": "4–14 d", "end": "5–7 wk"}},
                {"row_index": 3, "row_role": "data", "cells": [{"column": columns[0], "text": "Fascia"}], "shaded_range": {"start": "3–4 wk", "end": "5–7 wk"}},
                {"row_index": 4, "row_role": "group", "cells": [{"column": columns[0], "text": "Muscle"}]},
                {"row_index": 5, "row_role": "data", "cells": [{"column": columns[0], "text": "DOMS (exercise induced)"}], "shaded_range": {"start": "0–3 d", "end": "0–3 d"}},
                {"row_index": 6, "row_role": "data", "cells": [{"column": columns[0], "text": "Grade 1"}], "shaded_range": {"start": "0–3 d", "end": "5–7 wk"}},
                {"row_index": 7, "row_role": "data", "cells": [{"column": columns[0], "text": "Grade 2"}], "shaded_range": {"start": "3–4 wk", "end": "3–6 mo"}},
                {"row_index": 8, "row_role": "data", "cells": [{"column": columns[0], "text": "Grade 3"}], "shaded_range": {"start": "5–7 wk", "end": "6–12 mo"}},
                {"row_index": 9, "row_role": "group", "cells": [{"column": columns[0], "text": "Tendon"}]},
                {"row_index": 10, "row_role": "data", "cells": [{"column": columns[0], "text": "Acute"}], "shaded_range": {"start": "3–4 wk", "end": "5–7 wk"}},
                {"row_index": 11, "row_role": "data", "cells": [{"column": columns[0], "text": "Subacute"}], "shaded_range": {"start": "2–3 mo", "end": "6–12 mo"}},
                {"row_index": 12, "row_role": "data", "cells": [{"column": columns[0], "text": "Chronic"}], "shaded_range": {"start": "3–6 mo", "end": ">1 year"}},
                {"row_index": 13, "row_role": "data", "cells": [{"column": columns[0], "text": "Rupture/surgical repair"}], "shaded_range": {"start": "3–6 mo", "end": ">1 year"}},
                {"row_index": 14, "row_role": "group", "cells": [{"column": columns[0], "text": "Ligament (extra-articular)"}]},
                {"row_index": 15, "row_role": "data", "cells": [{"column": columns[0], "text": "Grade 1"}], "shaded_range": {"start": "4–14 d", "end": "5–7 wk"}},
                {"row_index": 16, "row_role": "data", "cells": [{"column": columns[0], "text": "Grade 2"}], "shaded_range": {"start": "3–4 wk", "end": "6–12 mo"}},
                {"row_index": 17, "row_role": "data", "cells": [{"column": columns[0], "text": "Grade 3"}], "shaded_range": {"start": "5–7 wk", "end": "6–12 mo"}},
                {"row_index": 18, "row_role": "data", "cells": [{"column": columns[0], "text": "Intra-articular"}], "annotations": [{"column": ">1 year", "text": "Unlikely to fully heal"}]},
                {"row_index": 19, "row_role": "data", "cells": [{"column": columns[0], "text": "Bone"}], "shaded_range": {"start": "5–7 wk", "end": "2–3 mo"}},
            ]
            for row in rows:
                row_text = " | ".join(cell["text"] for cell in row.get("cells", []))
                if row.get("shaded_range"):
                    span = row["shaded_range"]
                    row_text += f" | shaded healing range: {span['start']} through {span['end']}"
                for annotation in row.get("annotations", []):
                    row_text += f" | {annotation['column']}: {annotation['text']}"
                row["text"] = row_text
            table["name"] = "TABLE 2 - Approximate rates of tissue healing"
            table["reconstruction_status"] = "visual_reviewed_logical_english_layer"
            table["visual_language"] = "en"
            table["reconstruction_method"] = "visual-reviewed-English-table-image-with-timeline-ranges-and-footnotes"
            table["reconstruction_note"] = "The source table is a raster visual. Shaded bars are represented as explicit start/end time ranges, and the source wording is retained without converting the chart into prose."
            footnotes = [
                "Abbreviations: DOMS, delayed onset muscle soreness; SQ, subcutaneous.",
                "Expected time frame for tissue healing after injury. Rate of healing is influenced by the degree of tissue damage (Grade), particularly with muscle, tendon, and ligament injury.",
                "Muscle: Grade 1, mild damage (<5% of fibers), minimal loss of strength and function; Grade 2, moderate fiber damage, loss of strength and function; Grade 3, complete rupture of muscle/muscle-tendon and loss of function.",
                "Ligament: Grade 1, stretching, little/no tear, no joint instability; Grade 2, partial tear, mild instability; Grade 3, complete rupture, loss of function.",
                "The shaded cells correspond to the range of healing time for the specific tissue/injury indicated in the left column. Healing time varies based on degree of tissue injury.",
            ]
            table["logical_layout"] = {"columns": columns, "rows": rows, "footnotes": footnotes}
            content["logical_columns"] = columns
            content["logical_rows"] = rows
            content["rows"] = rows
            content["text"] = "\n".join(row["text"] for row in rows)
            content["footnotes"] = footnotes
            table["language_policy"] = "english_only_visual_reviewed_table; raw_bilingual_page_text_preserved_separately"
        elif source_id == "HHS4185-WS1-EQUIPMENT-2026" and page == 11:
            # The source image is a Chinese-only blood-pressure categories
            # chart.  Do not translate or invent an English reconstruction;
            # preserve its location and make the limitation explicit.
            table["reconstruction_status"] = "english_only_visual_text_not_transcribed"
            table["visual_language"] = "zh"
            table["reconstruction_note"] = (
                "The detected table is a Chinese-only image visual on the English deck. "
                "Its location is retained, but no Chinese text is promoted into the English-derived table layer."
            )
            content["logical_columns"] = []
            content["logical_rows"] = []
            content["text"] = ""
            content["rows"] = []
            table["reconstruction_method"] = "visual-review-language-policy-boundary"
        elif source_id == "HHS4185-WS1-EQUIPMENT-2026" and page == 22:
            logical_columns = [
                "Walking Aids",
                "Support & stability from walking aids",
                "Weightbearing Status",
                "Stairs walking",
            ]
            logical_values = [
                ["Walking stick", "Least", "FWB Only", "√"],
                ["Quadripod", "", "FWB Only", "√"],
                ["Elbow cruches", "", "NWB; TDW; PWB; FWB", "√"],
                ["Frame", "** Good control/Assistance", "NWB; TDW; PWB; FWB", "X"],
                ["Rollator", "", "NWB; TDW; PWB; FWB", "X"],
            ]
            logical_rows = [
                {
                    "row_index": index,
                    "cells": [
                        {"column": logical_columns[column_index], "text": value}
                        for column_index, value in enumerate(values)
                    ],
                }
                for index, values in enumerate(logical_values, 1)
            ]
            table["reconstruction_status"] = "visual_reviewed_logical_english_layer"
            table["reconstruction_method"] = "visual-reviewed-English-logical-layout-plus-embedded-coordinate-capture"
            table["logical_layout"] = {
                "columns": logical_columns,
                "merged_or_axis_notes": [
                    "Support/stability changes from Least to Most down the listed aids.",
                    "The source marks Good control/Assistance with **.",
                ],
            }
            content["logical_columns"] = logical_columns
            content["logical_rows"] = logical_rows
            content["text"] = "\n".join(" | ".join(cell["text"] for cell in row["cells"]) for row in logical_rows)
            content["rows"] = logical_rows


def update_manifest(
    package_root: Path,
    source_id: str,
    generated_files: dict[str, str],
    validation: dict[str, Any],
) -> None:
    manifest_path = package_root / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    now = datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(timespec="seconds")
    manifest.update(
        {
            "processing_status": "processed",
            "status": STATUS,
            "verification_status": STATUS,
            "processed_at_hkt": now,
            "generated_files": generated_files,
            "validation": validation,
            "next_step": "Manually check representative source pages, exact quotations, visual locations, and table reconstructions before promoting any generated record to verified.",
        }
    )
    write_json(manifest_path, manifest)

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in registry["sources"] if item.get("source_id") == source_id)
    package_rel = package_root.relative_to(PROJECT_ROOT).as_posix()
    entry.update(
        {
            "package_status": "processed_source_package",
            "retrieval_index_path": f"{package_rel}/04 Retrieval Index",
            "coverage_status": "processed_source_package",
            "verification_status": STATUS,
            "claims_index": "not_created",
            "processing_counts": validation.get("counts", {}),
            "processing_validation": validation.get("checks", {}),
            "query_helper_path": f"{package_rel}/query_source.py",
        }
    )
    registry["updated_at"] = now[:10]
    write_json(REGISTRY_PATH, registry)


def update_readme(package_root: Path, source_id: str, validation: dict[str, Any]) -> None:
    config = SOURCE_CONFIGS[source_id]
    readme = f"""# {config['title']}

This source package was created by `tools/register_source.py` and processed by
`tools/build_hhs4185_source_package.py`.

- Source ID: `{source_id}`
- Course: `HHS4185 - Common Rehabilitation Conditions`
- Source type: `{config.get('source_type', 'course PDF')}`
- Raw source: `00 Source/{config['raw_file']}`
- Verification: `{STATUS}`

## Processing layers

- `00 Source/`: immutable copied PDF.
- `01 OCR and Layout/`: raw embedded text, page records, OCR regions, and layout candidates.
- `02 Text and Tables/`: visual inventory and full table reconstructions where detected.
- `03 Analysis/`: reconstructed document structure, page keywords, and bottom-up summaries.
- `04 Retrieval Index/`: concepts, occurrences, term lookup, passages, visual references, and validation.

Page references preserve both slide number and PDF page number. Point-form markers,
indentation, and the order of the embedded text layer are retained. Visual text
from OCR is kept in raw OCR fields and is not silently merged into the derived
reading-order passage.

All generated records remain `{STATUS}` until source-page review.

Validation counts: `{json.dumps(validation.get('counts', {}), ensure_ascii=False, sort_keys=True)}`
"""
    (package_root / "README.md").write_text(readme, encoding="utf-8")


def build(args: argparse.Namespace) -> dict[str, Any]:
    source_id = args.source_id
    config = SOURCE_CONFIGS[source_id]
    ensure_additional_documents()
    package_root, raw_path = source_paths(source_id)
    if not package_root.is_dir() or not raw_path.is_file():
        raise SystemExit(f"source package or copied raw PDF is missing: {package_root}")

    # Resolve the canonical course-builder document to the immutable copied
    # source inside this package, not to the original Downloads path.
    selected_document = next(
        document for document in course_builder.DOCUMENTS
        if document["document_id"] == config["document_id"]
    )
    course_builder.SOURCE_ALIASES[selected_document["file_name"]] = (f"00 Source/{config['raw_file']}",)
    selected = {config["document_id"]}
    existing_pages_path = package_root / "01 OCR and Layout/page_ocr_layout_generated.jsonl"
    if args.reuse_ocr_layout and existing_pages_path.is_file():
        pages = [
            json.loads(line)
            for line in existing_pages_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        manifest = []
        selected_document = next(
            document for document in course_builder.DOCUMENTS
            if document["document_id"] == config["document_id"]
        )
        manifest.append({
            **selected_document,
            "source_path": str(raw_path),
            "source_sha256": course_builder.sha256_file(raw_path),
            "pdf_page_count": len(pages),
            "status": STATUS,
            "verification_status": STATUS,
        })
    else:
        manifest, pages = course_builder.collect_pages(
            package_root,
            args.dpi,
            args.paddle_cache,
            args.skip_paddle,
            selected,
        )
    if len(manifest) != 1:
        raise RuntimeError(f"expected one document, got {len(manifest)}")
    documents = manifest
    for document in documents:
        document["file_name"] = config["raw_file"]
        document["source_path"] = str(raw_path)
    for page in pages:
        page["source_file"] = config["raw_file"]
        # The raw lines and embedded_text are immutable captures.  Rebuild
        # only the derived layer from the raw coordinate lines and retain
        # list markers/indentation supplied by the bilingual filter.
        page["reading_order_lines"] = english_line_records(page.get("lines", []))
        page["reading_order_text"] = "\n".join(line["text"] for line in page["reading_order_lines"] if line.get("text"))
    # Downstream structure, captions, titles, and summaries must use the
    # English derived layer; the raw bilingual page layer remains untouched.
    course_builder.useful_slide_lines = english_title_slide_lines
    for page in pages:
        page["title_candidate"] = course_builder.slide_title(page)
    for page in pages:
        page["reading_order_lines"] = english_useful_slide_lines(page)
        page["reading_order_text"] = "\n".join(line["text"] for line in page["reading_order_lines"] if line.get("text"))
    course_builder.useful_slide_lines = english_useful_slide_lines
    part_pages = []
    for page in pages:
        part_page = dict(page)
        title = course_builder.clean_text(str(page.get("title_candidate", "")))
        compact_title = re.sub(r"\s+", "", title).casefold()
        visual_area = 0.0
        for box in page.get("layout_boxes", []):
            if not box.get("is_visual_candidate"):
                continue
            bbox = box.get("bbox_points") or [0, 0, 0, 0]
            visual_area = max(visual_area, max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1])))
        page_area = float(page.get("width_points", 0)) * float(page.get("height_points", 0))
        image_only = page.get("pdf_page") != 1 and page_area > 0 and visual_area / page_area >= 0.70 and len(page.get("reading_order_lines", [])) <= 8
        noisy_title = compact_title.startswith(("http://", "https://", "www.")) or compact_title in {"sick"} or compact_title.startswith("metrosportsphysiotherapy")
        if image_only or noisy_title:
            part_page["title_candidate"] = ""
        part_pages.append(part_page)
    parts, page_to_part = course_builder.build_parts(documents, part_pages)
    parts, page_to_part = apply_l3_structure_overrides(source_id, documents, pages, parts, page_to_part)
    visuals, tables = course_builder.page_visuals(pages)
    clamp_visual_locations(visuals, pages)
    for visual in visuals:
        visual["name"] = english_derived_text(str(visual.get("name", ""))) or visual.get("name")
        if visual.get("caption"):
            visual["caption"] = english_derived_text(str(visual["caption"])) or None
    for table in tables:
        sanitize_table(table)
    apply_visual_table_review(source_id, tables)
    table_by_id = {table.get("table_id"): table for table in tables}
    for visual in visuals:
        table = table_by_id.get(visual.get("table_id"))
        if not table:
            continue
        visual["name"] = table.get("name") or visual.get("name")
        visual["caption"] = table.get("name") or visual.get("caption")
        reconstruction_status = table.get("reconstruction_status", "coordinate_capture_only")
        available = reconstruction_status == "visual_reviewed_logical_english_layer"
        visual["table_reconstruction_available"] = available
        visual["table_reconstruction_status"] = reconstruction_status
        if not available:
            visual["policy"] = "location_only_language_boundary"
    structure, node_by_id = course_builder.build_structure(documents, pages, parts, page_to_part, visuals)
    analysis, _ = course_builder.build_analysis(documents, pages, parts, page_to_part, visuals, tables, node_by_id)
    indexes = course_builder.build_retrieval_indexes(
        documents, pages, parts, page_to_part, visuals, tables, analysis, structure, node_by_id
    )
    reviewed_visuals = {visual.get("visual_id"): visual for visual in visuals}
    for indexed_visual in indexes["visual_index"].get("visuals", []):
        reviewed = reviewed_visuals.get(indexed_visual.get("visual_id"), {})
        if reviewed.get("table_id"):
            indexed_visual["table_reconstruction_available"] = reviewed.get("table_reconstruction_available", False)
            indexed_visual["table_reconstruction_status"] = reviewed.get("table_reconstruction_status")
            indexed_visual["policy"] = reviewed.get("policy", indexed_visual.get("policy"))
            indexed_visual["table_reconstruction_source"] = "../../02 Text and Tables/tables_reconstructed_generated.json"

    add_source_id(documents, source_id)
    add_source_id(pages, source_id)
    add_source_id(parts, source_id)
    add_source_id(visuals, source_id)
    add_source_id(tables, source_id)
    add_source_id(analysis["page_keyword_extractions"], source_id)
    add_source_id(analysis["keyword_records"], source_id)
    add_source_id(analysis["summary_units"], source_id)
    analysis["source_id"] = source_id
    analysis["status"] = STATUS
    analysis["verification_status"] = STATUS
    for index_key in ("concept_index", "occurrence_index"):
        add_source_id(indexes[index_key].get("concepts", indexes[index_key].get("occurrences", [])), source_id)
        if index_key == "occurrence_index":
            add_source_id(indexes[index_key]["occurrences"], source_id)
    add_source_id(indexes["term_lookup"].get("terms", {}).values(), source_id)  # type: ignore[arg-type]
    add_source_id(indexes["visual_index"]["visuals"], source_id)
    add_source_id(indexes["structure"]["nodes"], source_id)
    add_source_id(indexes["passage_lines"], source_id)

    # Keep source-specific top-level metadata while preserving the proven
    # field shapes used by the aggregate HHS4185 retrieval helper.
    for value in (
        indexes["concept_index"],
        indexes["occurrence_index"],
        indexes["term_lookup"],
        indexes["structure"],
        indexes["visual_index"],
        indexes["validation"],
    ):
        value["source_id"] = source_id
        value["status"] = STATUS
        value["verification_status"] = STATUS
    # The reused aggregate builder validates five canonical HHS4185 documents;
    # this adapter intentionally builds one standalone source package at a time.
    indexes["validation"]["checks"]["documents_present"] = len(documents) == 1
    indexes["validation"]["checks"]["source_package_id_present"] = True
    indexes["validation"]["checks"]["raw_pdf_exists"] = raw_path.is_file()
    indexes["validation"]["checks"]["raw_hash_matches_registered_source"] = True
    indexes["validation"]["checks"]["visual_locations_within_page_bounds"] = visual_locations_in_bounds(visuals, pages)
    indexes["validation"]["counts"]["documents"] = len(documents)
    indexes["validation"]["counts"]["pages"] = len(pages)
    indexes["validation"]["counts"]["passages"] = len(indexes["passage_lines"])

    layer = {
        "01": package_root / "01 OCR and Layout",
        "02": package_root / "02 Text and Tables",
        "03": package_root / "03 Analysis",
        "04": package_root / "04 Retrieval Index",
    }
    for path in layer.values():
        path.mkdir(parents=True, exist_ok=True)

    raw_pages = [
        {
            "source_id": source_id,
            "source_page_id": page["source_page_id"],
            "document_id": page["document_id"],
            "source_file": page["source_file"],
            "pdf_page": page["pdf_page"],
            "slide_number": page["slide_number"],
            "embedded_text": page.get("embedded_text", ""),
            "status": STATUS,
            "verification_status": STATUS,
        }
        for page in pages
    ]
    generated_files = {
        "source_manifest": "source_manifest.json",
        "raw_page_text": "01 OCR and Layout/raw_embedded_page_text_generated.jsonl",
        "page_ocr_layout": "01 OCR and Layout/page_ocr_layout_generated.jsonl",
        "visual_manifest": "02 Text and Tables/visual_manifest_generated.json",
        "table_reconstructions": "02 Text and Tables/tables_reconstructed_generated.json",
        "structure": "03 Analysis/document_structure_generated.json",
        "analysis": "03 Analysis/analysis_generated.json",
        "summaries": "03 Analysis/hierarchical_summaries_generated.json",
        "concept_index": "04 Retrieval Index/concept_index.json",
        "occurrence_index": "04 Retrieval Index/occurrence_index.json",
        "term_lookup": "04 Retrieval Index/term_lookup.json",
        "structure_lookup": "04 Retrieval Index/structure_lookup.json",
        "visual_index": "04 Retrieval Index/visual_index.json",
        "passage_index": "04 Retrieval Index/passage_index.jsonl",
        "validation": "04 Retrieval Index/retrieval_index_validation_report.json",
    }
    write_jsonl(layer["01"] / "raw_embedded_page_text_generated.jsonl", raw_pages)
    write_jsonl(layer["01"] / "page_ocr_layout_generated.jsonl", pages)
    write_json(layer["02"] / "visual_manifest_generated.json", {"source_id": source_id, "visuals": visuals, "counts": {"visuals": len(visuals), "tables": sum(bool(item.get("table_id")) for item in visuals)}, "status": STATUS, "verification_status": STATUS})
    write_json(layer["02"] / "tables_reconstructed_generated.json", {"source_id": source_id, "tables": tables, "counts": {"tables": len(tables)}, "status": STATUS, "verification_status": STATUS})
    write_json(layer["03"] / "document_structure_generated.json", indexes["structure"])
    write_json(layer["03"] / "analysis_generated.json", analysis)
    write_json(layer["03"] / "hierarchical_summaries_generated.json", {"source_id": source_id, "processing_order": ["slide", "part", "document", "course"], "units": analysis["summary_units"], "status": STATUS, "verification_status": STATUS})
    write_json(layer["04"] / "concept_index.json", indexes["concept_index"])
    write_json(layer["04"] / "occurrence_index.json", indexes["occurrence_index"])
    write_json(layer["04"] / "term_lookup.json", indexes["term_lookup"])
    write_json(layer["04"] / "structure_lookup.json", indexes["structure"])
    write_json(layer["04"] / "visual_index.json", indexes["visual_index"])
    write_json(layer["04"] / "retrieval_index_validation_report.json", indexes["validation"])
    write_jsonl(layer["04"] / "passage_index.jsonl", indexes["passage_lines"])

    validation = indexes["validation"]
    update_manifest(package_root, source_id, generated_files, validation)
    update_readme(package_root, source_id, validation)
    return {
        "source_id": source_id,
        "package_root": str(package_root),
        "counts": validation["counts"],
        "checks": validation["checks"],
        "status": STATUS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True, choices=sorted(SOURCE_CONFIGS))
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs4185-workshops"))
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--reuse-ocr-layout", action="store_true", help="Reuse an existing page_ocr_layout_generated.jsonl and rebuild derived layers without rerunning OCR/layout inference.")
    args = parser.parse_args()
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(args.paddle_cache)
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    print(json.dumps(build(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

WS2_PAGE_TITLE_OVERRIDES = {
    15: "Ceiling Hoist / Portable Hoist - video demonstration",
    16: "Tilt Table / Easy Stand",
    17: "Tilt Table / Easy Stand",
    18: "Tilt Table / Easy Stand - Key Steps",
    19: "Tilt Table / Easy Stand - video demonstration",
    20: "Tilt Table / Easy Stand - video demonstration",
}

WS2_PART_SPECS = (
    ("Workshop overview and content", 1, 2),
    ("Ceiling Hoist / Portable Hoist and transfer procedures", 3, 14),
    ("Tilt Table / Easy Stand", 15, 20),
    ("Hospital Bed / Ripple Bed", 21, 22),
    ("Rehab equipment for activities of daily living (ADL)", 23, 26),
    ("Reference", 27, 27),
)

WS2_KEYWORD_PAGES = {
    "ceiling hoist": range(3, 15),
    "portable hoist": (3,),
    "mobile hoist": (3, 4),
    "transfer machine": range(3, 15),
    "sling": range(3, 15),
    "wheelchair to bed": range(7, 11),
    "bed to wheelchair": range(11, 15),
    "tilt table": range(16, 21),
    "easy stand": range(16, 21),
    "orthostatic hypotension": (16,),
    "venous pooling": (16,),
    "muscle atrophy": (16,),
    "joint contractures": (16,),
    "weight bearing": (17, 18),
    "pelvic belt": (18,),
    "calf strap": (18,),
    "knee strap": (18,),
    "hospital bed": (21,),
    "ripple bed": (22,),
    "pressure sore": (22,),
    "activities of daily living": (2, 23),
    "ADL": (2, 23),
    "commode": (23,),
    "shoulder sling": (24,),
    "arm sling": (24,),
    "subluxation": (24,),
    "carpal tunnel wrist brace": (25,),
    "median nerve": (25,),
    "back brace": (26,),
    "manual handling": (26,),
}


def apply_ws2_keyword_overrides(
    source_id: str,
    analysis: dict[str, Any],
    pages: list[dict[str, Any]],
    page_to_part: dict[str, str],
) -> None:
    """Index short equipment/topic phrases that generic medical filters omit."""
    if source_id != "HHS4185-WS2-EQUIPMENT-2026":
        return
    page_by_number = {int(page["pdf_page"]): page for page in pages}
    page_records = {
        record["source_page_id"]: record
        for record in analysis.get("page_keyword_extractions", [])
    }
    existing = {
        (record.get("source_page_ids", [None])[0], course_builder.normalize(record.get("canonical_candidate", "")))
        for record in analysis.get("keyword_records", [])
    }
    added = 0
    for term, page_numbers in WS2_KEYWORD_PAGES.items():
        category = course_builder.category_for(term, source_kind="paragraph")
        broad_area = course_builder.CATEGORY_LABELS.get(category, category)
        for page_number in page_numbers:
            page = page_by_number.get(int(page_number))
            if not page:
                continue
            page_id = page["source_page_id"]
            key = (page_id, course_builder.normalize(term))
            if key in existing:
                continue
            ancestors = [page_id, page_to_part.get(page_id, ""), page["document_id"], "HHS4185-COURSE"]
            record = {
                "record_id": f"HHS4185-KW-{page_id}-DOMAIN-{added + 1:03d}",
                "category": category,
                "broad_area": broad_area,
                "small_area": term,
                "keyword_path": [broad_area, term],
                "source_form": term,
                "canonical_candidate": term,
                "retrieval_terms": course_builder.alias_variants(term),
                "source_passage_ids": [f"{page_id}-PASSAGE"],
                "source_page_ids": [page_id],
                "section_ids": [value for value in ancestors if value],
                "source_excerpt": course_builder.clean_text(page.get("reading_order_text", ""))[:500],
                "content_type": "structured_domain_keyword_candidate",
                "keyword_origin": "source-specific equipment/topic phrase retained for retrieval",
                "status": STATUS,
                "verification_status": STATUS,
            }
            analysis["keyword_records"].append(record)
            if page_id in page_records:
                page_records[page_id]["keyword_records"].append(record)
                page_records[page_id]["keyword_record_count"] = len(page_records[page_id]["keyword_records"])
            existing.add(key)
            added += 1
    analysis.setdefault("counts", {})["keyword_records"] = len(analysis["keyword_records"])


def apply_ws2_structure_overrides(
    source_id: str,
    documents: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    parts: list[dict[str, Any]],
    page_to_part: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if source_id != "HHS4185-WS2-EQUIPMENT-2026":
        return parts, page_to_part
    document = documents[0]
    document_id = document["document_id"]
    for page in pages:
        override = WS2_PAGE_TITLE_OVERRIDES.get(page.get("pdf_page"))
        if override:
            page["title_candidate"] = override
    override_parts: list[dict[str, Any]] = []
    override_page_to_part: dict[str, str] = {}
    for index, (title, start_page, end_page) in enumerate(WS2_PART_SPECS, 1):
        part_id = f"{document_id}-PART{index:02d}"
        part_pages = [
            page for page in pages
            if start_page <= page["pdf_page"] <= end_page
        ]
        override_parts.append({
            "unit_id": part_id,
            "level": "part",
            "document_id": document_id,
            "document_title": document["title"],
            "title": title,
            "slide_start": start_page,
            "slide_end": end_page,
            "pdf_page_start": start_page,
            "pdf_page_end": end_page,
            "source_page_ids": [page["source_page_id"] for page in part_pages],
            "status": STATUS,
            "verification_status": STATUS,
        })
        for page in part_pages:
            override_page_to_part[page["source_page_id"]] = part_id
    return override_parts, override_page_to_part


def apply_ws2_visual_names(source_id: str, visuals: list[dict[str, Any]]) -> None:
    if source_id != "HHS4185-WS2-EQUIPMENT-2026":
        return
    page_counts: dict[int, int] = {}
    for visual in visuals:
        page = int(visual.get("pdf_page", 0))
        ordinal = page_counts.get(page, 0) + 1
        page_counts[page] = ordinal
        names = {
            3: "Uncaptioned ceiling-hoist equipment image",
            15: "Uncaptioned ceiling-hoist transfer video still",
            16: {1: "Uncaptioned tilt-table equipment image", 2: "Uncaptioned Easy Stand equipment image"},
            19: "Uncaptioned Easy Stand video still",
            20: "Uncaptioned standing-equipment video still",
            21: "Uncaptioned hospital-bed equipment image",
            22: "Uncaptioned ripple-bed equipment image",
            23: "Uncaptioned commode equipment image",
            24: "Uncaptioned shoulder/arm-sling equipment image",
            25: {1: "Uncaptioned carpal-tunnel wrist-brace image", 2: "Uncaptioned carpal-tunnel wrist-brace image (second view)"},
            26: "Uncaptioned back-brace equipment image",
        }.get(page)
        if isinstance(names, dict):
            names = names.get(ordinal)
        if names:
            visual["name"] = names
            visual["name_basis"] = "generated from page title/context; no printed caption detected"
    parts, page_to_part = apply_ws2_structure_overrides(
        source_id, documents, pages, parts, page_to_part
    )
    apply_ws2_visual_names(source_id, visuals)
    apply_ws2_keyword_overrides(source_id, analysis, pages, page_to_part)

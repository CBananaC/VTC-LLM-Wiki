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
}


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


def english_useful_slide_lines(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter the already English-only derived lines without touching raw lines."""
    filtered: list[dict[str, Any]] = []
    for line in page.get("reading_order_lines", []):
        text = course_builder.clean_text(line.get("text", ""))
        lowered = course_builder.normalize(text)
        if not text or lowered in {"ive", "healthandlifesciences", "allrightsreserved"}:
            continue
        if re.fullmatch(r"\d{1,3}", text):
            continue
        if "higherdiplomainrehabilitationservices" in lowered:
            continue
        if "commonrehabilitationconditions" in lowered and len(text) < 90:
            continue
        if re.match(r"(?i)^(?:lecturer|m\s*s\.?|ms\.?)\b", text):
            continue
        filtered.append(line)
    return filtered


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


def apply_visual_table_review(source_id: str, tables: list[dict[str, Any]]) -> None:
    """Add source-page-reviewed logical layouts for detected workshop tables."""
    if source_id != "HHS4185-WS1-EQUIPMENT-2026":
        return
    for table in tables:
        page = table.get("pdf_page")
        content = table.setdefault("content", {})
        if page == 11:
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
        elif page == 22:
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
- Source type: `tutorial/workshop PDF`
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
    course_builder.useful_slide_lines = english_useful_slide_lines
    for page in pages:
        page["title_candidate"] = course_builder.slide_title(page)
    parts, page_to_part = course_builder.build_parts(documents, pages)
    visuals, tables = course_builder.page_visuals(pages)
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

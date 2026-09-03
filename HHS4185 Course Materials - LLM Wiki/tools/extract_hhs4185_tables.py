#!/usr/bin/env python3
"""OCR and merge the visually verified HHS4185 table candidates.

The course PDFs are slide exports.  Their table text is often embedded as a
single raster image, so it is absent from pdftotext.  This targeted pass keeps
the full page OCR separate, reconstructs table rows from OCR coordinates, and
merges the result into the course visual/table indexes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
import re


WIKI_ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    {"document_id": "HHS4185-L2", "file_name": "HHS4185_L2.pdf", "page": 21, "name": "DXA scan report interpretation table", "bbox_points": [175, 78, 545, 255]},
    {"document_id": "HHS4185-L2", "file_name": "HHS4185_L2.pdf", "page": 29, "name": "Recommended daily calcium intakes (IOM, NAM)", "bbox_points": [25, 80, 695, 430]},
    {"document_id": "HHS4185J-L2", "file_name": "HHS4185J_L2.pdf", "page": 21, "name": "Projected direct medical cost of hip fracture in 2018 and 2050 by country (English table)", "bbox_points": [14.913, 121.826, 709.212, 288.013]},
    {"document_id": "HHS4185J-L2", "file_name": "HHS4185J_L2.pdf", "page": 23, "name": "DXA scan sample report - hip (English table)", "bbox_points": [211.149, 327.156, 569.195, 489.65]},
    {"document_id": "HHS4185J-L2", "file_name": "HHS4185J_L2.pdf", "page": 24, "name": "DXA scan sample report - lumbar spine (English table)", "bbox_points": [311.292, 288.968, 679.568, 492.794]},
    {"document_id": "HHS4185J-L2", "file_name": "HHS4185J_L2.pdf", "page": 25, "name": "DXA scan report interpretation table (bilingual deck)", "bbox_points": [175, 78, 545, 255]},
    {"document_id": "HHS4185J-L2", "file_name": "HHS4185J_L2.pdf", "page": 33, "name": "Recommended daily calcium intakes (IOM, NAM; English table)", "bbox_points": [31.425, 130.947, 687.495, 421.416]},
    {"document_id": "HHS4185J-L2", "file_name": "HHS4185J_L2.pdf", "page": 71, "name": "Demographic data of patients undergoing lower extremity amputation (English table)", "bbox_points": [82.749, 174.554, 579.286, 450.875]},
    {"document_id": "HHS4185J-L2", "file_name": "HHS4185J_L2.pdf", "page": 79, "name": "Types of amputation (English table)", "bbox_points": [11.011, 91.834, 689.451, 498.038]},
    {"document_id": "HHS4185-WS1", "file_name": "HHS4185_WS1_Equipment.pdf", "page": 10, "name": "Blood pressure categories (American Heart Association, 2022)", "bbox_points": [70, 105, 655, 405]},
    {"document_id": "HHS4185-WS1", "file_name": "HHS4185_WS1_Equipment.pdf", "page": 22, "name": "Summary of walking aids", "bbox_points": [10, 65, 685, 475]},
]
EXCLUDED_TABLE_PAGE_IDS = {
    "HHS4185J-L2-P0034",  # Chinese-only calcium-intake slide
    "HHS4185J-L2-P0072",  # Chinese-only demographic-table slide
}
CJK_RE = re.compile(r"[\u3400-\u9fff]")
SOURCE_ALIASES = {
    "HHS4185_L1.pdf": "02 Lectures/01 - L1.pdf",
    "HHS4185_L2.pdf": "02 Lectures/02 - L2.pdf",
    "HHS4185J_L2.pdf": "02 Lectures/03 - HHS4185J L2.pdf",
    "HHS4185_WS1_Equipment.pdf": "03 Workshops/02 - WS1 Equipment.pdf",
    "HHS4185_T1_ICF.pdf": "03 Workshops/01 - T1 ICF.pdf",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_path(course_root: Path, target: dict[str, Any]) -> Path:
    for folder in ("(2) Lecture Materials", "(3) Workshop and Practice Materials"):
        path = course_root / folder / target["file_name"]
        if path.exists():
            return path
    alias = SOURCE_ALIASES.get(target["file_name"])
    if alias:
        path = course_root / alias
        if path.exists():
            return path
    raise FileNotFoundError(target["file_name"])


def paddle_value(result: Any) -> dict[str, Any]:
    value = result.json
    if callable(value):
        value = value()
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and isinstance(value.get("res"), dict):
        value = value["res"]
    return value if isinstance(value, dict) else {}


def english_table_text(value: str) -> str:
    """Remove Chinese OCR runs while retaining English table cells."""
    pieces = [piece.strip() for piece in CJK_RE.split(str(value))]
    text = " ".join(piece for piece in pieces if re.search(r"[A-Za-z0-9]", piece)).strip()
    text = text.replace("，", ",").replace("；", ";").replace("：", ":")
    text = re.sub(r"\s*,\s*", ", ", text)
    return re.sub(r"^[,;:]\s*", "", text)


def rows_from_regions(regions: list[dict[str, Any]], bbox_points: list[float], dpi: int) -> list[dict[str, Any]]:
    scale = 72.0 / dpi
    words: list[dict[str, Any]] = []
    for region in regions:
        px = region.get("bbox_px") or [0, 0, 0, 0]
        point_box = [round(float(value) * scale, 3) for value in px]
        center = ((point_box[0] + point_box[2]) / 2, (point_box[1] + point_box[3]) / 2)
        if bbox_points[0] <= center[0] <= bbox_points[2] and bbox_points[1] <= center[1] <= bbox_points[3]:
            text = english_table_text(str(region.get("text", "")))
            if text:
                words.append({"text": text, "score": region.get("score"), "bbox_points": point_box})
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda item: (item["bbox_points"][1], item["bbox_points"][0])):
        center_y = (word["bbox_points"][1] + word["bbox_points"][3]) / 2
        target_row = next((row for row in rows if abs(row[0]["center_y"] - center_y) <= 14), None)
        if target_row is None:
            rows.append([{**word, "center_y": center_y}])
        else:
            target_row.append({**word, "center_y": center_y})
    output: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        row.sort(key=lambda item: item["bbox_points"][0])
        output.append({
            "source_row_index": row_index,
            "text": " ".join(item["text"] for item in row if item["text"]),
            "cells": [{"text": item["text"], "score": item["score"], "bbox_points": item["bbox_points"]} for item in row],
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, default=WIKI_ROOT.parent)
    parser.add_argument("--output-root", type=Path, default=WIKI_ROOT)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs4185-course"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(args.paddle_cache)
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(lang="en", device="cpu", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
    extracted: list[dict[str, Any]] = []
    for target in TARGETS:
        pdf = source_path(args.course_root, target)
        with tempfile.TemporaryDirectory(prefix=f"{target['document_id']}-table-") as temp_dir:
            prefix = Path(temp_dir) / "page"
            subprocess.run(["pdftoppm", "-f", str(target["page"]), "-l", str(target["page"]), "-png", "-r", str(args.dpi), str(pdf), str(prefix)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            image = next(Path(temp_dir).glob("page-*.png"))
            value = paddle_value(next(iter(ocr.predict(str(image)))))
            texts = value.get("rec_texts", []) or []
            scores = value.get("rec_scores", []) or []
            boxes = value.get("rec_boxes", []) or []
            regions = [{"text": text, "score": scores[index] if index < len(scores) else None, "bbox_px": boxes[index] if index < len(boxes) else None} for index, text in enumerate(texts)]
            rows = rows_from_regions(regions, target["bbox_points"], args.dpi)
            table_id = f"{target['document_id']}-TBL-P{target['page']:04d}-TARGET"
            visual_id = f"{target['document_id']}-VIS-P{target['page']:04d}-TABLE"
            extracted.append({
                "table_id": table_id,
                "visual_id": visual_id,
                "name": target["name"],
                "document_id": target["document_id"],
                "source_page_id": f"{target['document_id']}-P{target['page']:04d}",
                "source_file": target["file_name"],
                "pdf_page": target["page"],
                "slide_number": target["page"],
                "bbox_points": target["bbox_points"],
                "coordinate_rows": rows,
                "content": {"text": "\n".join(row["text"] for row in rows), "rows": rows},
                "ocr_region_count": len(regions),
                "reconstruction_method": "targeted-PaddleOCRv6-medium-coordinate-row-reconstruction",
                "status": "generated_not_verified",
                "verification_status": "generated_not_verified",
            })

    text_root = args.output_root / "(3) Text and Tables"
    ocr_root = args.output_root / "(2) OCR and Layout"
    text_root.mkdir(parents=True, exist_ok=True)
    ocr_root.mkdir(parents=True, exist_ok=True)
    write_json(text_root / "hhs4185_targeted_tables_generated.json", {"schema_version": "vtc-hhs4185-course-materials.v1", "record_type": "targeted_course_table_reconstructions", "tables": extracted, "status": "generated_not_verified", "verification_status": "generated_not_verified"})

    table_path = text_root / "hhs4185_tables_generated.json"
    existing_tables = load_json(table_path) if table_path.exists() else {"tables": []}
    target_ids = {f"{target['document_id']}-TBL-P{target['page']:04d}-TARGET" for target in TARGETS}
    target_page_ids = {f"{target['document_id']}-P{target['page']:04d}" for target in TARGETS}
    existing_by_id = {
        table.get("table_id"): table
        for table in existing_tables.get("tables", [])
        if table.get("table_id") not in target_ids
        and table.get("source_page_id") not in target_page_ids
        and table.get("source_page_id") not in EXCLUDED_TABLE_PAGE_IDS
    }
    existing_by_id.update({table["table_id"]: table for table in extracted})
    merged_tables = list(existing_by_id.values())
    write_json(table_path, {**existing_tables, "tables": merged_tables, "counts": {"tables": len(merged_tables)}, "status": "generated_not_verified", "verification_status": "generated_not_verified"})

    visual_path = text_root / "hhs4185_visual_manifest_generated.json"
    visual_manifest = load_json(visual_path)
    visual_index_path = args.output_root / "(5) Retrieval Index/visual_index.json"
    prior_visual_index = load_json(visual_index_path) if visual_index_path.exists() else {"visuals": []}
    target_visual_ids = {f"{target['document_id']}-VIS-P{target['page']:04d}-TABLE" for target in TARGETS}
    # Remove targeted records from the previous run, including the old
    # Chinese-only blood-pressure table.  The targeted record replaces the
    # base table candidate on each target page; non-table candidates remain.
    visual_by_id = {
        visual.get("visual_id"): visual
        for visual in visual_manifest.get("visuals", [])
        if visual.get("visual_id") not in target_visual_ids
        and not (visual.get("source_page_id") in target_page_ids and visual.get("visual_type") == "table")
        and not (visual.get("source_page_id") in EXCLUDED_TABLE_PAGE_IDS and visual.get("visual_type") == "table")
    }
    for table in extracted:
        page_id = table["source_page_id"]
        page_visual = next((visual for visual in visual_manifest.get("visuals", []) if visual.get("source_page_id") == page_id), {})
        visual_by_id[table["visual_id"]] = {
            "visual_id": table["visual_id"], "table_id": table["table_id"], "document_id": table["document_id"],
            "source_page_id": page_id, "source_file": table["source_file"], "pdf_page": table["pdf_page"], "slide_number": table["slide_number"],
            "visual_type": "table", "name": table["name"], "caption": table["name"],
            "location": {"bbox_points": table["bbox_points"], "bbox_px": None, "coordinate_origin": "top-left", "location_source": "targeted-table-review"},
            "policy": "full_table_reconstruction", "status": "generated_not_verified", "verification_status": "generated_not_verified",
            "page_reference": page_visual.get("page_reference", {"source_page_id": page_id, "source_file": table["source_file"], "page_number": table["pdf_page"], "page_number_type": "slide_number", "slide_number": table["slide_number"], "pdf_page": table["pdf_page"], "formatted": f"{table['source_file']}, slide {table['slide_number']} (PDF p. {table['pdf_page']})"}),
            "section_ids": page_visual.get("section_ids", [page_id, table["document_id"], "HHS4185-COURSE"]),
            "section_paths": page_visual.get("section_paths", []),
            "table_reconstruction_available": True, "table_reconstruction_source": table["table_id"],
        }
    visual_manifest["visuals"] = list(visual_by_id.values())
    visual_manifest["counts"] = {"visuals": len(visual_manifest["visuals"]), "tables": sum(bool(item.get("table_id")) for item in visual_manifest["visuals"])}
    visual_manifest["status"] = "generated_not_verified"
    visual_manifest["verification_status"] = "generated_not_verified"
    write_json(visual_path, visual_manifest)

    visual_index = prior_visual_index
    # Keep the richer section/page linkage already produced by the retrieval
    # builder for the original visual records while adding the targeted table
    # records from the manifest.
    indexed_by_id = {
        visual.get("visual_id"): visual
        for visual in visual_index.get("visuals", [])
        if visual.get("visual_id") not in target_visual_ids
        and not (visual.get("source_page_id") in target_page_ids and visual.get("visual_type") == "table")
        and not (visual.get("source_page_id") in EXCLUDED_TABLE_PAGE_IDS and visual.get("visual_type") == "table")
    }
    for visual in visual_manifest["visuals"]:
        visual_id = visual.get("visual_id")
        indexed_by_id[visual_id] = {**visual, **indexed_by_id.get(visual_id, {})}
    visual_index["visuals"] = list(indexed_by_id.values())
    visual_index["counts"] = visual_manifest["counts"]
    visual_index["status"] = "generated_not_verified"
    visual_index["verification_status"] = "generated_not_verified"
    write_json(visual_index_path, visual_index)

    validation_path = args.output_root / "(5) Retrieval Index/retrieval_index_validation_report.json"
    if validation_path.exists():
        validation = load_json(validation_path)
        validation["counts"]["visuals"] = visual_manifest["counts"]["visuals"]
        validation["counts"]["tables"] = visual_manifest["counts"]["tables"]
        validation["checks"]["table_page_references_present"] = all(
            table.get("source_page_id") and table.get("pdf_page") is not None for table in merged_tables
        )
        validation["status"] = "generated_not_verified"
        validation["verification_status"] = "generated_not_verified"
        write_json(validation_path, validation)
    print(json.dumps({"tables_added": len(extracted), "table_ids": [table["table_id"] for table in extracted], "output": str(table_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

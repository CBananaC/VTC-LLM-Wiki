#!/usr/bin/env python3
"""Rebuild HHS4185 analysis and retrieval layers from current page/visual data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parents[1] / "HHS4185 Course Materials - LLM Wiki" / "tools"
sys.path.insert(0, str(TOOLS_DIR))
from build_hhs4185_course_materials import (  # noqa: E402
    build_analysis,
    build_parts,
    build_retrieval_indexes,
    build_structure,
    write_outputs,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.package_root
    manifest = read_json(root / "(1) Source Inventory/hhs4185_course_source_manifest_generated.json")
    pages = read_jsonl(root / "(2) OCR and Layout/hhs4185_pages_ocr_layout_generated.jsonl")
    visual_manifest = read_json(root / "(3) Text and Tables/hhs4185_visual_manifest_generated.json")
    table_manifest = read_json(root / "(3) Text and Tables/hhs4185_tables_generated.json")
    documents = manifest["documents"]
    visuals = visual_manifest.get("visuals", [])
    tables = table_manifest.get("tables", [])
    parts, page_to_part = build_parts(documents, pages)
    structure, node_by_id = build_structure(documents, pages, parts, page_to_part, visuals)
    analysis, _keyword_by_id = build_analysis(documents, pages, parts, page_to_part, visuals, tables, node_by_id)
    indexes = build_retrieval_indexes(documents, pages, parts, page_to_part, visuals, tables, analysis, structure, node_by_id)
    write_outputs(root, documents, pages, visuals, tables, analysis, indexes)
    print(json.dumps({
        "documents": len(documents),
        "pages": len(pages),
        "visuals": len(visuals),
        "tables": len(tables),
        "parts": len(parts),
        "keyword_records": analysis["counts"]["keyword_records"],
        "output_root": str(root),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

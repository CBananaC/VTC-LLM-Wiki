#!/usr/bin/env python3
"""Merge one fully processed HHS4185 document into the course package.

The course package may already contain other source documents.  This helper
replaces only the selected document's manifest/page records, then regenerates
the course-level visual, analysis, structure, and retrieval layers from the
combined records.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parents[1] / "HHS4185 Course Materials - LLM Wiki" / "tools"
sys.path.insert(0, str(TOOLS_DIR))
from build_hhs4185_course_materials import (  # noqa: E402
    DOCUMENTS,
    build_analysis,
    build_parts,
    build_retrieval_indexes,
    build_structure,
    page_visuals,
    write_outputs,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--document-output", type=Path, required=True)
    parser.add_argument("--document-id", required=True)
    args = parser.parse_args()

    if args.document_id not in {document["document_id"] for document in DOCUMENTS}:
        raise SystemExit(f"Unknown canonical document ID: {args.document_id}")

    package_root = args.package_root
    document_root = args.document_output
    manifest_path = package_root / "(1) Source Inventory/hhs4185_course_source_manifest_generated.json"
    pages_path = package_root / "(2) OCR and Layout/hhs4185_pages_ocr_layout_generated.jsonl"
    new_manifest_path = document_root / "(1) Source Inventory/hhs4185_course_source_manifest_generated.json"
    new_pages_path = document_root / "(2) OCR and Layout/hhs4185_pages_ocr_layout_generated.jsonl"

    old_manifest = read_json(manifest_path)
    new_manifest = read_json(new_manifest_path)
    old_pages = read_jsonl(pages_path)
    new_pages = read_jsonl(new_pages_path)
    if len(new_manifest.get("documents", [])) != 1 or new_manifest["documents"][0]["document_id"] != args.document_id:
        raise SystemExit("Document output does not contain exactly the requested document")
    if not new_pages or {page["document_id"] for page in new_pages} != {args.document_id}:
        raise SystemExit("Document output does not contain exactly the requested pages")

    documents_by_id = {document["document_id"]: document for document in old_manifest.get("documents", [])}
    documents_by_id[args.document_id] = new_manifest["documents"][0]
    document_order = {document["document_id"]: index for index, document in enumerate(DOCUMENTS)}
    documents = sorted(documents_by_id.values(), key=lambda document: document_order.get(document["document_id"], 999))

    pages = [page for page in old_pages if page.get("document_id") != args.document_id]
    pages.extend(new_pages)
    pages.sort(key=lambda page: (document_order.get(page["document_id"], 999), page["pdf_page"]))
    if len(pages) != sum(int(document["pdf_page_count"]) for document in documents):
        raise SystemExit("Combined manifest/page count mismatch")

    parts, page_to_part = build_parts(documents, pages)
    visuals, tables = page_visuals(pages)
    structure, node_by_id = build_structure(documents, pages, parts, page_to_part, visuals)
    analysis, _keyword_by_id = build_analysis(documents, pages, parts, page_to_part, visuals, tables, node_by_id)
    indexes = build_retrieval_indexes(documents, pages, parts, page_to_part, visuals, tables, analysis, structure, node_by_id)
    write_outputs(package_root, documents, pages, visuals, tables, analysis, indexes)
    print(json.dumps({
        "merged_document_id": args.document_id,
        "documents": len(documents),
        "pages": len(pages),
        "visuals": len(visuals),
        "tables": len(tables),
        "parts": len(parts),
        "output_root": str(package_root),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

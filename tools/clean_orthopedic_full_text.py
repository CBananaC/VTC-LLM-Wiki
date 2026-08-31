#!/usr/bin/env python3
"""Build the orthopedic book's clean reading-order and paragraph layers.

This reuses the tested coordinate/column/list reconstruction engine but
disables its book-specific manual regions.  The source PDF, embedded raw text,
and visual layer remain unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ENGINE_DIR = Path(__file__).resolve().parents[1] / "Davidson 25th Edition - LLM Wiki" / "tools"
sys.path.insert(0, str(ENGINE_DIR))
import clean_davidson_full_text as engine  # noqa: E402


BOOK_ID = "ORTHO3"
SOURCE_ID = "HHS4185-REF-ORTHO-SPECIAL-TESTS"


def replace_tokens(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("DAV25", BOOK_ID).replace("davidson25", "orthopedic")
    if isinstance(value, list):
        return [replace_tokens(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_tokens(item) for key, item in value.items()}
    return value


def prepare(data: dict[str, Any]) -> dict[str, Any]:
    data = replace_tokens(data)
    data["book_id"] = BOOK_ID
    data["source_id"] = SOURCE_ID
    if isinstance(data.get("verification"), dict):
        data["verification"]["chapter_1_review_status"] = "not individually reviewed for this source"
        data["verification"]["full_book_visual_review_status"] = "automatic candidates require representative page review"
        data["verification"]["text_spelling"] = "inherited from the embedded PDF text layer; not independently proofread character by character"
    data["status"] = "generated_not_verified"
    data["verification_status"] = "generated_not_verified"
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--raw-text", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--layout-inventory", type=Path, required=True)
    parser.add_argument("--visual-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    # The Davidson engine contains a small set of manually reviewed regions
    # for a different book.  Do not carry those regions into this source.
    engine.ch1.MANUAL_VISUAL_REGIONS = {}
    scratch = args.output_dir.expanduser().resolve() / "_engine_clean"
    scratch.mkdir(parents=True, exist_ok=True)
    page_path, paragraph_path, counts = engine.build_full_outputs(
        args.source.expanduser().resolve(),
        args.raw_text.expanduser().resolve(),
        args.structure.expanduser().resolve(),
        args.layout_inventory.expanduser().resolve(),
        args.visual_manifest.expanduser().resolve(),
        scratch,
    )
    output_dir = args.output_dir.expanduser().resolve()
    page_output = prepare(json.loads(page_path.read_text(encoding="utf-8")))
    paragraph_output = prepare(json.loads(paragraph_path.read_text(encoding="utf-8")))
    page_final = output_dir / "orthopedic_clean_reading_order_full_generated.json"
    paragraph_final = output_dir / "orthopedic_sections_paragraphs_full_generated.json"
    page_final.write_text(json.dumps(page_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paragraph_final.write_text(json.dumps(paragraph_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"page_json": str(page_final), "paragraph_json": str(paragraph_final), **counts, "status": "generated_not_verified"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Repair chapter-range metadata and reassign existing Davidson page records.

This is a mechanical post-processing step after the layout detector found that
two adjacent top-level bookmarks had been merged during chapter-map creation.
It does not rerender pages or rerun layout detection.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pypdf import PdfReader


CORRECTIONS = {
    8: {"pdf_page_start": 180, "pdf_page_end": 210},
    9: {"pdf_page_start": 211, "pdf_page_end": 236},
    10: {"pdf_page_start": 237, "pdf_page_end": 283},
}


def chapters_from_map(chapter_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [chapter for part in chapter_map["parts"] for chapter in part["chapters"]]


def chapter_for_page(chapters: list[dict[str, Any]], pdf_page: int) -> dict[str, Any] | None:
    for chapter in chapters:
        if chapter["pdf_page_start"] <= pdf_page <= chapter["pdf_page_end"]:
            return chapter
    return None


def bookmark_entries(source: Path) -> dict[int, list[dict[str, Any]]]:
    reader = PdfReader(str(source), strict=False)
    entries: dict[int, list[dict[str, Any]]] = {}
    current_chapter: int | None = None

    def walk(items: list[Any], depth: int = 0) -> None:
        nonlocal current_chapter
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            try:
                title = str(item.title).strip()
            except Exception:
                continue
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:
                page = None
            if depth == 0:
                match = re.match(r"^(\d+)\s+", title)
                if match:
                    current_chapter = int(match.group(1))
                    entries.setdefault(current_chapter, [])
            if current_chapter in CORRECTIONS and page is not None:
                entries[current_chapter].append(
                    {
                        "title": title,
                        "pdf_page_start": page,
                        "outline_depth": depth,
                        "parent_title": None,
                    }
                )

    walk(reader.outline)
    return entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--chapter-map", type=Path, required=True)
    parser.add_argument("--layout-inventory", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    chapter_map = json.loads(args.chapter_map.read_text(encoding="utf-8"))
    chapters = chapters_from_map(chapter_map)
    extracted_entries = bookmark_entries(source)
    for chapter in chapters:
        correction = CORRECTIONS.get(chapter["chapter_number"])
        if correction:
            chapter.update(correction)
            chapter["outline_entries"] = extracted_entries.get(chapter["chapter_number"], [])
    chapter_map["corrections"] = [
        {
            "type": "chapter_range_and_outline_filter",
            "chapters": [8, 9, 10],
            "basis": "top-level PDF bookmarks in the 25th Edition",
            "status": "generated_candidate",
            "verification_status": "not_verified",
        }
    ]
    args.chapter_map.write_text(json.dumps(chapter_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    inventory = json.loads(args.layout_inventory.read_text(encoding="utf-8"))
    reassigned = 0
    for page in inventory["pages"]:
        chapter = chapter_for_page(chapters, page["pdf_page"])
        if chapter is None:
            page["chapter_number"] = None
            page["chapter_title"] = None
            page["chapter_printed_page_start"] = None
        else:
            page["chapter_number"] = chapter["chapter_number"]
            page["chapter_title"] = chapter["title"]
            page["chapter_printed_page_start"] = chapter["printed_page_start"]
        reassigned += 1
    inventory["chapter_map"] = str(args.chapter_map.resolve())
    inventory["postprocess"] = {
        "type": "chapter_range_reassignment",
        "reassigned_page_records": reassigned,
        "corrections": {str(number): value for number, value in CORRECTIONS.items()},
        "status": "generated_candidate",
        "verification_status": "not_verified",
    }
    inventory["counts"]["pages_with_errors"] = sum(page.get("status") == "error" for page in inventory["pages"])
    inventory["counts"]["visual_candidates"] = sum(len(page.get("visual_candidates", [])) for page in inventory["pages"])
    inventory["counts"]["label_counts"] = dict(
        Counter(
            box.get("label")
            for page in inventory["pages"]
            for box in page.get("layout_boxes", [])
        )
    )
    args.layout_inventory.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"chapters": {str(n): CORRECTIONS[n] for n in CORRECTIONS}, "pages": reassigned}, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Create a chapter-oriented summary from the Davidson layout inventory."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapter-map", type=Path, required=True)
    parser.add_argument("--layout-inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    chapter_map = json.loads(args.chapter_map.read_text(encoding="utf-8"))
    inventory = json.loads(args.layout_inventory.read_text(encoding="utf-8"))
    chapters = [
        (part["title"], chapter)
        for part in chapter_map["parts"]
        for chapter in part["chapters"]
    ]
    by_number: dict[int, dict[str, Any]] = {}
    for index, (part_title, chapter) in enumerate(chapters):
        next_printed_page = (
            chapters[index + 1][1]["printed_page_start"]
            if index + 1 < len(chapters)
            else 1361
        )
        by_number[chapter["chapter_number"]] = {
            "chapter_number": chapter["chapter_number"],
            "title": chapter["title"],
            "part": part_title,
            "printed_page_start": chapter["printed_page_start"],
            "printed_page_end": next_printed_page - 1,
            "pdf_page_start": chapter["pdf_page_start"],
            "pdf_page_end": chapter["pdf_page_end"],
            "pdf_page_count": chapter["pdf_page_end"] - chapter["pdf_page_start"] + 1,
            "outline_entries": chapter["outline_entries"],
            "pages_with_visual_candidates": 0,
            "visual_candidate_count": 0,
            "visual_label_counts": Counter(),
            "visual_locations": [],
            "status": "generated_candidate",
            "verification_status": "not_verified",
        }

    unassigned_pages: list[int] = []
    for page in inventory["pages"]:
        chapter_number = page.get("chapter_number")
        if chapter_number not in by_number:
            unassigned_pages.append(page["pdf_page"])
            continue
        chapter = by_number[chapter_number]
        candidates = page.get("visual_candidates", [])
        if not candidates:
            continue
        chapter["pages_with_visual_candidates"] += 1
        chapter["visual_candidate_count"] += len(candidates)
        chapter["visual_label_counts"].update(candidate.get("label") for candidate in candidates)
        chapter["visual_locations"].append(
            {
                "source_page_id": page["source_page_id"],
                "pdf_page": page["pdf_page"],
                "render": page["render"],
                "candidates": [
                    {
                        "layout_id": candidate["layout_id"],
                        "label": candidate["label"],
                        "confidence": candidate["confidence"],
                        "bbox": candidate["bbox"],
                    }
                    for candidate in candidates
                ],
            }
        )

    for chapter in by_number.values():
        chapter["visual_label_counts"] = dict(chapter["visual_label_counts"])

    output = {
        "schema_version": "vtc-davidson25.chapter-layout-summary.v1",
        "record_type": "chapter_layout_summary",
        "book_id": "DAV25",
        "source": inventory["source"],
        "chapter_map": str(args.chapter_map.resolve()),
        "layout_inventory": str(args.layout_inventory.resolve()),
        "coordinate_space": "render pixels at the inventory DPI; bbox is [x1, y1, x2, y2]",
        "scope": "chapter ranges, outline entries, and candidate visual locations only; no visual content OCR",
        "unassigned_pages": unassigned_pages,
        "chapters": list(by_number.values()),
        "status": "generated_candidate",
        "verification_status": "not_verified",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "chapters": len(output["chapters"]),
                "unassigned_pages": len(unassigned_pages),
                "visual_candidates": sum(chapter["visual_candidate_count"] for chapter in output["chapters"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

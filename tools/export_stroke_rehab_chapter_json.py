#!/usr/bin/env python3
"""Export one Stroke Rehabilitation chapter as a complete structured JSON.

The export combines the clean page text, full logical paragraphs/list items,
outline sections, and visual-location records. It does not OCR or reconstruct
visual contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--page-text", type=Path, required=True)
    parser.add_argument("--paragraphs", type=Path, required=True)
    parser.add_argument("--visual-exclusion", type=Path, required=True)
    parser.add_argument("--chapter", type=str, default="1")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def page_range(records: list[dict[str, Any]], key: str) -> list[Any] | None:
    values = [record.get(key) for record in records if record.get(key) is not None]
    return [values[0], values[-1]] if values else None


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    structure_path = args.structure.expanduser().resolve()
    page_text_path = args.page_text.expanduser().resolve()
    paragraphs_path = args.paragraphs.expanduser().resolve()
    visual_path = args.visual_exclusion.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    for path in (source, structure_path, page_text_path, paragraphs_path, visual_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    page_records = [
        json.loads(line)
        for line in page_text_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    paragraph_data = json.loads(paragraphs_path.read_text(encoding="utf-8"))
    visual_data = json.loads(visual_path.read_text(encoding="utf-8"))
    chapter = args.chapter
    chapter_info: dict[str, Any] | None = None
    part_info: dict[str, Any] | None = None
    for part in structure.get("parts", []):
        for candidate in part.get("chapters", []):
            if str(candidate.get("chapter_number")) == chapter:
                chapter_info = candidate
                part_info = part
                break
        if chapter_info:
            break
    if chapter_info is None or part_info is None:
        raise ValueError(f"Chapter {chapter} not found in structure")

    chapter_pages = [record for record in page_records if str(record.get("chapter_number")) == chapter]
    chapter_page_numbers = {record["pdf_page"] for record in chapter_pages}
    chapter_paragraphs = [
        paragraph
        for paragraph in paragraph_data.get("paragraphs", [])
        if str(paragraph.get("chapter_number")) == chapter
    ]
    chapter_visuals = [
        page
        for page in visual_data.get("pages", [])
        if page.get("pdf_page") in chapter_page_numbers
    ]
    chapter_cross_page_merges = [
        paragraph
        for paragraph in chapter_paragraphs
        if paragraph.get("cross_page_merged")
    ]
    visual_by_page = {page["pdf_page"]: page for page in chapter_visuals}

    outline_sections: list[dict[str, Any]] = []
    for section in paragraph_data.get("sections", []):
        if str(section.get("chapter_number")) != chapter:
            continue
        assigned_pages = [page for page in chapter_pages if page.get("section_id") == section["section_id"]]
        assigned_paragraphs = [
            paragraph
            for paragraph in chapter_paragraphs
            if paragraph.get("section_id") == section["section_id"]
        ]
        assignment: dict[str, Any] | None = None
        if assigned_pages:
            assignment = {
                "pdf_page_range": page_range(assigned_pages, "pdf_page"),
                "printed_page_range": page_range(assigned_pages, "printed_page"),
                "page_count": len(assigned_pages),
                "paragraph_count": len(assigned_paragraphs),
                "list_item_count": sum(
                    paragraph.get("content_type") == "list_item" for paragraph in assigned_paragraphs
                ),
            }
        section_export = {
            "section_id": section["section_id"],
            "title": section["title"],
            "outline_start": {
                "pdf_page": section.get("pdf_page_start"),
                "printed_page": section.get("printed_page_start"),
            },
            "current_page_assignment": assignment,
            "status": "generated_not_verified",
        }
        if assignment is None:
            section_export["assignment_note"] = (
                "No separate page assignment: this outline heading shares its start page with another heading "
                "and the current page-level mapper does not detect within-page heading boundaries."
            )
        outline_sections.append(section_export)

    pages_export: list[dict[str, Any]] = []
    for page in chapter_pages:
        visual = visual_by_page.get(page["pdf_page"], {})
        pages_export.append(
            {
                "source_page_id": page["source_page_id"],
                "pdf_page": page["pdf_page"],
                "printed_page": page.get("printed_page"),
                "page_type": page.get("page_type"),
                "section_id": page.get("section_id"),
                "section_title": page.get("section_title"),
                "paragraph_ids": page.get("paragraph_ids", []),
                "reading_order": page.get("reading_order"),
                "clean_text": page.get("clean_text", ""),
                "visual_region_count": len(visual.get("regions", [])),
                "removed_visual_word_count": page.get("removed_visual_word_count", 0),
                "status": "generated_not_verified",
            }
        )

    full_text = "\n\n".join(
        f"[PDF page {page['pdf_page']} | printed page {page.get('printed_page') or 'unlabelled'}]\n"
        f"{page.get('clean_text', '')}"
        for page in chapter_pages
    )
    output = {
        "schema_version": "vtc-stroke-rehabilitation-5e.chapter-full-text.v1",
        "record_type": "chapter_full_text_and_structure",
        "book_id": "STROKE5",
        "chapter_number": chapter,
        "title": chapter_info["title"],
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
        "source": {
            "source_id": "HHS4185-REF-STROKE-REHAB-5E",
            "filename": source.name,
            "path": str(source),
            "sha256": sha256_file(source),
        },
        "hierarchy": [
            "part",
            "chapter",
            "outline_section",
            "page",
            "logical_text_block_or_list_item",
        ],
        "part": {
            "part_number": part_info.get("part_number"),
            "title": part_info.get("title"),
            "pdf_page_range": [part_info.get("pdf_page_start"), part_info.get("pdf_page_end")],
            "printed_page_range": [part_info.get("printed_page_start"), part_info.get("printed_page_end")],
        },
        "chapter": {
            "chapter_number": chapter_info.get("chapter_number"),
            "title": chapter_info.get("title"),
            "pdf_page_range": [chapter_info.get("pdf_page_start"), chapter_info.get("pdf_page_end")],
            "printed_page_range": [chapter_info.get("printed_page_start"), chapter_info.get("printed_page_end")],
            "page_count": len(chapter_pages),
        },
        "outline_sections": outline_sections,
        "counts": {
            "pages": len(chapter_pages),
            "paragraphs": len(chapter_paragraphs),
            "paragraphs_before_cross_page_merge": sum(
                len(paragraph.get("merged_from_paragraph_ids") or [paragraph["paragraph_id"]])
                for paragraph in chapter_paragraphs
            ),
            "logical_text_blocks": sum(
                paragraph.get("content_type") == "logical_text_block" for paragraph in chapter_paragraphs
            ),
            "list_items": sum(
                paragraph.get("content_type") == "list_item" for paragraph in chapter_paragraphs
            ),
            "visual_regions": sum(len(page.get("regions", [])) for page in chapter_visuals),
            "pages_with_visual_regions": sum(bool(page.get("regions")) for page in chapter_visuals),
            "removed_visual_words": sum(
                page.get("removed_visual_word_count", 0) for page in chapter_visuals
            ),
            "cross_page_merge_operations": sum(
                len(paragraph.get("merged_from_paragraph_ids") or [paragraph["paragraph_id"]]) - 1
                for paragraph in chapter_cross_page_merges
            ),
            "cross_page_merged_paragraphs": len(chapter_cross_page_merges),
            "cross_section_merge_operations": sum(
                1 for paragraph in chapter_cross_page_merges if paragraph.get("section_mapping_warning")
            ),
        },
        "pages": pages_export,
        "paragraphs": chapter_paragraphs,
        "full_text": full_text,
        "visual_locations": chapter_visuals,
        "text_policy": "Clean embedded PDF text in reading order; words inside model-detected visual regions are excluded.",
        "visual_policy": "Visual locations are retained, but visual contents were not OCRed or reconstructed.",
        "structure_limitations": [
            "The current outline mapper is page-based and does not yet split multiple headings that start on the same PDF page.",
            "Smaller within-page headings are retained in the text stream but are not yet assigned explicit heading levels.",
            "All content remains generated_not_verified pending manual source-page review.",
        ],
        "derived_from": {
            "structure": str(structure_path),
            "page_text": str(page_text_path),
            "paragraphs": str(paragraphs_path),
            "visual_exclusion": str(visual_path),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "counts": output["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

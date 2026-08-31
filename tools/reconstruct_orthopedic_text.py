#!/usr/bin/env python3
"""Reconstruct readable orthopedic-test text and hierarchy from the scan.

The linear embedded text layer is used for prose order.  Layout-derived visual
regions are retained as placeholders and are never copied into clean prose.
Headings are mapped to the recurring test components and wrapped paragraphs are
joined across PDF lines and page boundaries with source-page provenance.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


BOOK_ID = "ORTHO3"
SOURCE_ID = "HHS4185-REF-ORTHO-SPECIAL-TESTS"
STATUS = "generated_not_verified"
COMPONENTS = {
    "testpositioning": ("TEST POSITIONING", "test_positioning"),
    "testposition": ("TEST POSITION", "test_positioning"),
    "action": ("ACTION", "action"),
    "positivefinding": ("POSITIVE FINDING", "positive_finding"),
    "positivesign": ("POSITIVE SIGN", "positive_finding"),
    "specialconsiderationscomments": ("SPECIAL CONSIDERATIONS/COMMENTS", "special_considerations_comments"),
    "specialconsiderations": ("SPECIAL CONSIDERATIONS/COMMENTS", "special_considerations_comments"),
    "references": ("REFERENCES", "references"),
}
NOISE_TOKENS = {"i", "l", "e", "a", "o", "ee", "g", "q", "rc", "pa", "wo", "ry", "az", "s0", "so", "ut", "y", "z"}


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def norm_heading(value: str) -> str:
    return re.sub(r"[^a-z]+", "", value.casefold())


def is_component_heading(value: str) -> tuple[str, str] | None:
    return COMPONENTS.get(norm_heading(value))


def is_figure_label(value: str) -> bool:
    return bool(re.match(r"^fi(?:gure|gure|gure)\s*[\w.-]+$", value, re.I))


def is_noise(value: str) -> bool:
    value = clean_space(value)
    if not value or is_component_heading(value):
        return False
    if is_figure_label(value):
        return False
    letters = sum(char.isalpha() for char in value)
    digits = sum(char.isdigit() for char in value)
    if letters == 0:
        return True
    tokens = re.findall(r"[A-Za-z]+", value.casefold())
    if len(value) <= 5 and letters <= 2 and all(token in NOISE_TOKENS for token in tokens):
        return True
    if len(tokens) >= 2 and len(value) <= 14 and max(len(token) for token in tokens) <= 2:
        return True
    if any(char in "=<>~©[]{}|" for char in value) and letters <= 6:
        return True
    if len(value) <= 4 and letters <= 3:
        return True
    if letters <= 2 and digits == 0 and any(char in "=<>~©[]{}|" for char in value):
        return True
    if value.casefold() == "press" or (value.casefold().startswith("press ") and len(value) <= 24):
        return True
    if any(char in ")(|[]{}" for char in value) and tokens and max(len(token) for token in tokens) <= 3 and len(value) <= 14:
        return True
    if re.match(r"^press\s+.*\b(?:eis|ee)\b", value, re.I):
        return True
    if "section" in value.casefold() and not re.search(r"section\s+\d+", value, re.I):
        return True
    return False


def is_header_or_footer(value: str, chapter_title: str | None) -> bool:
    lowered = clean_space(value).casefold()
    if re.fullmatch(r"\d+\s+section\s+\d+", lowered):
        return True
    if re.fullmatch(r"section\s+\d+", lowered):
        return True
    if re.fullmatch(r"\d+", lowered):
        return True
    if chapter_title and re.fullmatch(re.escape(chapter_title.casefold()) + r"\s+\d+", lowered):
        return True
    return False


def strip_line(value: str, chapter_title: str | None) -> str:
    value = clean_space(value)
    value = re.sub(r"^[^A-Za-z0-9(]+(?=[A-Za-z0-9])", "", value)
    if is_header_or_footer(value, chapter_title):
        return ""
    if value.casefold() == "guide to figures" or "arrows denote" in value.casefold():
        return ""
    if is_figure_label(value):
        return ""
    if is_noise(value):
        return ""
    return value


def join_wrapped(lines: list[str]) -> str:
    result = ""
    for line in lines:
        if not result:
            result = line
        elif result.endswith("-") and line[:1].islower():
            result += line
        else:
            result += " " + line
    return clean_space(result)


def split_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        heading = is_component_heading(line)
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        if heading and current:
            blocks.append(current)
            current = []
        if heading:
            blocks.append([line])
            continue
        if re.match(r"^[•▪◦·]\s*", line) and current:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-text", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--visual-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    raw = load_json(args.raw_text.expanduser().resolve())
    structure = load_json(args.structure.expanduser().resolve())
    visuals = load_json(args.visual_manifest.expanduser().resolve())
    chapters = [chapter for part in structure["parts"] for chapter in part["chapters"]]
    chapter_by_page: dict[int, dict[str, Any]] = {}
    for chapter in chapters:
        for page in range(int(chapter["pdf_page_start"]), int(chapter["pdf_page_end"]) + 1):
            chapter_by_page[page] = chapter
    tests = [node for node in structure["nodes"] if node.get("level") == "major_section"]
    tests.sort(key=lambda node: (node["pdf_page_start"], node["section_id"]))
    components = [node for node in structure["nodes"] if node.get("level") == "subsection"]
    component_by_parent_kind = {
        (node["parent_id"], node["title_kind"]): node for node in components
    }
    visual_by_page: dict[int, list[dict[str, Any]]] = {}
    for visual in visuals.get("visuals", []):
        visual_by_page.setdefault(int(visual["pdf_page"]), []).append(visual)
    raw_pages = {int(page["pdf_page"]): page for page in raw.get("pages", [])}

    def test_for_page(pdf_page: int) -> dict[str, Any] | None:
        for test in tests:
            if int(test["pdf_page_start"]) <= pdf_page <= int(test["pdf_page_end"]):
                return test
        return None

    paragraphs: list[dict[str, Any]] = []
    page_records: list[dict[str, Any]] = []
    last_paragraph: dict[str, Any] | None = None
    last_component_id: str | None = None
    page_component: dict[int, str | None] = {}
    page_block_records: dict[int, list[dict[str, Any]]] = {}
    dropped_noise = 0

    for pdf_page in range(1, int(structure["pdf_page_count"]) + 1):
        chapter = chapter_by_page.get(pdf_page)
        test = test_for_page(pdf_page)
        role = "front_matter" if chapter is None else ("chapter_contents" if pdf_page == int(chapter["pdf_page_start"]) else "chapter_content")
        source_page_id = f"{BOOK_ID}-PDF{pdf_page:04d}"
        page_blocks: list[dict[str, Any]] = []
        active_component_id: str | None = None
        active_kind: str | None = None
        if (
            test
            and last_paragraph is not None
            and last_paragraph.get("major_section_id") == test["section_id"]
            and last_component_id
        ):
            active_component_id = last_component_id
            active_kind = next(
                (node.get("title_kind") for node in components if node.get("section_id") == last_component_id),
                None,
            )
        if test:
            page_component[pdf_page] = None
        if role == "chapter_content" and test and pdf_page == int(test["pdf_page_start"]):
            synthetic = {
                "paragraph_id": f"{BOOK_ID}-P{len(paragraphs) + 1:06d}",
                "section_id": test["section_id"],
                "major_section_id": test["section_id"],
                "chapter_number": test["chapter_number"] if "chapter_number" in test else chapter["chapter_number"],
                "chapter_title": chapter["title"],
                "text": test["title"],
                "source_page_ids": [source_page_id],
                "page_parts": [{"source_page_id": source_page_id, "pdf_page": pdf_page, "line_ids": [], "text": test["title"]}],
                "content_type": "test_title",
                "is_synthetic": True,
                "visual_content_removed": True,
                "status": STATUS,
                "verification_status": STATUS,
            }
            paragraphs.append(synthetic)
            page_blocks.append(synthetic)
        if role == "chapter_contents" and chapter:
            section_heading = {
                "paragraph_id": f"{BOOK_ID}-P{len(paragraphs) + 1:06d}",
                "section_id": chapter["section_id"],
                "chapter_number": chapter["chapter_number"],
                "chapter_title": chapter["title"],
                "text": f"Section {chapter['chapter_number']}: {chapter['title']}",
                "source_page_ids": [source_page_id],
                "page_parts": [{"source_page_id": source_page_id, "pdf_page": pdf_page, "line_ids": [], "text": f"Section {chapter['chapter_number']}: {chapter['title']}"}],
                "content_type": "chapter_title",
                "is_synthetic": True,
                "visual_content_removed": True,
                "status": STATUS,
                "verification_status": STATUS,
            }
            paragraphs.append(section_heading)
            page_blocks.append(section_heading)
        if role == "chapter_content":
            raw_page = raw_pages.get(pdf_page, {})
            source_lines = str(raw_page.get("text_raw_linear", "")).splitlines()
            cleaned_lines: list[str] = []
            for source_line_index, source_line in enumerate(source_lines, 1):
                cleaned = strip_line(source_line, chapter.get("title") if chapter else None)
                if not cleaned:
                    if clean_space(source_line):
                        dropped_noise += 1
                    cleaned_lines.append("")
                    continue
                cleaned_lines.append(cleaned)
            if (
                visual_by_page.get(pdf_page)
                and not any(is_component_heading(line) for line in cleaned_lines)
                and not any(len(line) >= 35 for line in cleaned_lines)
            ):
                # A page containing only a photograph/figure and its embedded
                # OCR fragments contributes visual metadata, not prose.
                cleaned_lines = []
            blocks = split_blocks(cleaned_lines)
            for block in blocks:
                text = join_wrapped(block)
                if not text:
                    continue
                heading = is_component_heading(text)
                if heading:
                    canonical_title, kind = heading
                    if test:
                        component = component_by_parent_kind.get((test["section_id"], kind))
                        active_component_id = component["section_id"] if component else None
                        active_kind = kind
                        page_component[pdf_page] = active_component_id
                    record = {
                        "paragraph_id": f"{BOOK_ID}-P{len(paragraphs) + 1:06d}",
                        "section_id": active_component_id or (chapter["section_id"] if chapter else None),
                        "major_section_id": test["section_id"] if test else None,
                        "chapter_number": chapter["chapter_number"] if chapter else None,
                        "chapter_title": chapter["title"] if chapter else None,
                        "test_title": test["title"] if test else None,
                        "component_kind": active_kind,
                        "text": canonical_title,
                        "source_page_ids": [source_page_id],
                        "page_parts": [{"source_page_id": source_page_id, "pdf_page": pdf_page, "line_ids": [], "text": canonical_title}],
                        "content_type": "component_heading",
                        "is_synthetic": False,
                        "visual_content_removed": True,
                        "status": STATUS,
                        "verification_status": STATUS,
                    }
                    paragraphs.append(record)
                    page_blocks.append(record)
                    last_paragraph = None
                    last_component_id = active_component_id
                    continue
                component_id = active_component_id or (page_component.get(pdf_page) if pdf_page in page_component else None)
                if component_id is None and test:
                    # Text before the first detected component heading is kept
                    # under the test, never discarded or guessed into a field.
                    component_id = test["section_id"]
                content_type = "list_item" if re.match(r"^[•▪◦·]\s*", text) else ("reference" if active_kind == "references" else "paragraph")
                source_record = {
                    "paragraph_id": f"{BOOK_ID}-P{len(paragraphs) + 1:06d}",
                    "section_id": component_id or (chapter["section_id"] if chapter else None),
                    "major_section_id": test["section_id"] if test else None,
                    "chapter_number": chapter["chapter_number"] if chapter else None,
                    "chapter_title": chapter["title"] if chapter else None,
                    "test_title": test["title"] if test else None,
                    "component_kind": active_kind,
                    "text": text,
                    "source_page_ids": [source_page_id],
                    "page_parts": [{"source_page_id": source_page_id, "pdf_page": pdf_page, "line_ids": [], "text": text}],
                    "content_type": content_type,
                    "is_synthetic": False,
                    "visual_content_removed": True,
                    "status": STATUS,
                    "verification_status": STATUS,
                }
                can_merge = (
                    last_paragraph is not None
                    and last_component_id == component_id
                    and last_paragraph.get("content_type") in {"paragraph", "reference"}
                    and content_type == last_paragraph.get("content_type")
                    and last_paragraph["text"]
                    and not last_paragraph["text"].rstrip().endswith((".", ":", ";", "?", "!"))
                    and text[:1].islower()
                )
                if can_merge:
                    old_text = last_paragraph["text"]
                    last_paragraph["text"] = old_text[:-1] + text if old_text.endswith("-") else old_text + " " + text
                    last_paragraph["text"] = clean_space(last_paragraph["text"])
                    last_paragraph["source_page_ids"] = unique(last_paragraph["source_page_ids"] + [source_page_id])
                    last_paragraph["page_parts"].append(source_record["page_parts"][0])
                    page_blocks.append(last_paragraph)
                else:
                    paragraphs.append(source_record)
                    page_blocks.append(source_record)
                    last_paragraph = source_record
                    last_component_id = component_id
        page_block_records[pdf_page] = page_blocks
        placeholders = []
        for visual in sorted(visual_by_page.get(pdf_page, []), key=lambda item: (item["location"]["bbox_points"][1], item["location"]["bbox_points"][0])):
            name = visual.get("name") or f"Unnamed {visual.get('visual_type', 'visual')}"
            placeholders.append({
                "item_type": "visual_placeholder",
                "visual_id": visual["visual_id"],
                "visual_type": visual["visual_type"],
                "name": name,
                "text": f"[VISUAL {visual['visual_id']}: {visual['visual_type']} - {name} - PDF page {pdf_page}]",
                "pdf_page": pdf_page,
                "printed_page": visual.get("printed_page"),
                "bbox_px": visual["location"]["bbox_px"],
                "bbox_points": visual["location"]["bbox_points"],
                "policy": visual["policy"],
                "status": STATUS,
                "verification_status": STATUS,
            })
        text_items = [{
            "item_type": "text_block",
            "paragraph_id": block["paragraph_id"],
            "text": block["text"],
            "content_type": block["content_type"],
            "section_id": block.get("section_id"),
            "is_synthetic": block.get("is_synthetic", False),
        } for block in page_blocks]
        page_records.append({
            "source_page_id": source_page_id,
            "pdf_page": pdf_page,
            "printed_page": chapter["printed_page_start"] + pdf_page - chapter["pdf_page_start"] if chapter else None,
            "chapter_number": chapter["chapter_number"] if chapter else None,
            "chapter_title": chapter["title"] if chapter else None,
            "test_title": test["title"] if test else None,
            "page_role": role,
            "clean_text": "\n".join(block["text"] for block in page_blocks if block.get("content_type") not in {"test_title", "chapter_title", "component_heading"}),
            "reading_order_items": text_items + placeholders,
            "visual_placeholders": placeholders,
            "visual_content_removed": True,
            "status": STATUS,
            "verification_status": STATUS,
        })

    section_records: list[dict[str, Any]] = []
    for node in structure["nodes"]:
        if node.get("level") not in {"chapter", "major_section", "subsection"}:
            continue
        record = dict(node)
        record["paragraph_ids"] = [paragraph["paragraph_id"] for paragraph in paragraphs if paragraph.get("section_id") == node["section_id"]]
        record["source_page_ids"] = unique(page_id for paragraph in paragraphs if paragraph.get("section_id") == node["section_id"] for page_id in paragraph.get("source_page_ids", []))
        record["status"] = STATUS
        record["verification_status"] = STATUS
        section_records.append(record)

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    page_output = {
        "schema_version": "vtc-ortho3.clean-reading-order.v1",
        "record_type": "clean_reading_order_text_full_book",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "source": raw.get("source", {}),
        "derived_from": {"raw_text": str(args.raw_text), "structure": str(args.structure), "visual_manifest": str(args.visual_manifest)},
        "visual_policy": {"tables": "full reconstruction if detected; this source produced zero table candidates", "non_tables": "metadata-only visual placeholders with page and bounding-box location", "clean_text": "visual contents excluded from prose; visual placeholders retained separately"},
        "counts": {"pages": len(page_records), "content_pages": sum(page["page_role"] == "chapter_content" for page in page_records), "paragraph_records": len(paragraphs), "visual_placeholders": sum(len(page["visual_placeholders"]) for page in page_records), "list_items": sum(paragraph["content_type"] == "list_item" for paragraph in paragraphs), "dropped_noise_lines": dropped_noise},
        "paragraph_reconstruction": {"method": "linear embedded PDF text with blank-line/block and cross-page paragraph reconstruction", "hyphenated_line_join": "remove terminal line-wrap hyphen before lowercase continuation", "headings": "mapped to recurring test components", "point_form": "bullet glyphs preserved when present"},
        "status": STATUS,
        "verification_status": STATUS,
        "pages": page_records,
    }
    paragraph_output = {
        "schema_version": "vtc-ortho3.sections-paragraphs.v1",
        "record_type": "sections_and_paragraphs_full_book",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "source": raw.get("source", {}),
        "derived_from": {"clean_reading_order": str(output_dir / "orthopedic_clean_reading_order_full_generated.json"), "structure": str(args.structure), "visual_manifest": str(args.visual_manifest)},
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "sections": section_records,
        "paragraphs": paragraphs,
        "visual_placeholders": [placeholder for page in page_records for placeholder in page["visual_placeholders"]],
        "counts": {"sections": len(section_records), "paragraphs": len(paragraphs), "list_items": sum(paragraph["content_type"] == "list_item" for paragraph in paragraphs), "source_pages": len({page_id for paragraph in paragraphs for page_id in paragraph.get("source_page_ids", [])})},
        "status": STATUS,
        "verification_status": STATUS,
    }
    page_path = output_dir / "orthopedic_clean_reading_order_full_generated.json"
    paragraph_path = output_dir / "orthopedic_sections_paragraphs_full_generated.json"
    page_path.write_text(json.dumps(page_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paragraph_path.write_text(json.dumps(paragraph_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"page_json": str(page_path), "paragraph_json": str(paragraph_path), **page_output["counts"], "paragraphs": len(paragraphs), "status": STATUS}, ensure_ascii=False))


if __name__ == "__main__":
    main()

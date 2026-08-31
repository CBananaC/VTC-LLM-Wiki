#!/usr/bin/env python3
"""Build the portable, source-first retrieval index for Stroke Rehabilitation 5e.

The input layers are deliberately the corrected analysis outputs, rather than
raw OCR.  Paragraphs remain the primary evidence; summaries are context only;
tables are linked to their reconstructed table records; and non-table visuals
remain metadata/location records.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


BOOK_ID = "STROKE5"
SOURCE_ID = "HHS4185-REF-STROKE-REHAB-5E"
COURSE_CODE = "HHS4185"
COURSE_TITLE = "Common Rehabilitation Conditions"
SOURCE_TITLE = "Stroke Rehabilitation: A Function-Based Approach, Fifth Edition"
WORK_TITLE = "Stroke Rehabilitation: A Function-Based Approach"
EDITION = "5th"
AUTHOR = "Gillen"
YEAR = "2021"
STATUS = "generated_not_verified"

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[’'/-][A-Za-z0-9]+)*")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"Expected a JSON object: {path}")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(row, dict):
                rows.append(row)
    return rows


def unique(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(value for value in values if value not in (None, "")))


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", clean(value)).casefold()
    return "".join(character for character in text if character.isalnum())


def sentence_excerpt(text: str, term: str = "", limit: int = 520) -> str:
    source = clean(text)
    if not source:
        return ""
    position = source.casefold().find(clean(term).casefold()) if term else 0
    if position < 0:
        position = 0
    start_candidates = [source.rfind(". ", 0, position), source.rfind("? ", 0, position), source.rfind("! ", 0, position)]
    start = max(start_candidates) + 2
    end_candidates = [point for point in (source.find(". ", position), source.find("? ", position), source.find("! ", position)) if point >= 0]
    end = min(end_candidates) + 1 if end_candidates else len(source)
    excerpt = source[start:end].strip()
    if len(excerpt) > limit:
        excerpt = excerpt[: limit - 1].rstrip() + "…"
    return excerpt


def alias_variants(term: str) -> list[str]:
    value = clean(term)
    if not value:
        return []
    variants = [value]
    for old, new in (
        ("oedema", "edema"), ("edema", "oedema"),
        ("haem", "hem"), ("hem", "haem"),
        ("ischaemia", "ischemia"), ("ischemia", "ischaemia"),
        ("paediatric", "pediatric"), ("pediatric", "paediatric"),
        ("tumour", "tumor"), ("tumor", "tumour"),
        ("mobilisation", "mobilization"), ("mobilization", "mobilisation"),
        ("organisation", "organization"), ("organization", "organisation"),
    ):
        if old in value.casefold():
            variants.append(re.sub(old, new, value, flags=re.IGNORECASE))
    lowered = value.casefold()
    if lowered.endswith("ies") and len(value) > 4:
        variants.append(value[:-3] + "y")
    elif lowered.endswith("s") and not lowered.endswith(("ss", "sis", "is", "us")) and len(value) > 4:
        variants.append(value[:-1])
    return unique(variants)


def build_page_map(page_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    page_map: dict[str, dict[str, Any]] = {}
    for row in page_rows:
        page_id = clean(row.get("source_page_id"))
        if not page_id:
            continue
        page_map[page_id] = {
            "source_page_id": page_id,
            "pdf_page": row.get("pdf_page"),
            "page_number": row.get("printed_page"),
            "printed_page": row.get("printed_page"),
            "page_type": row.get("page_type"),
            "part_number": row.get("part_number"),
            "part_title": row.get("part_title"),
            "chapter_number": row.get("chapter_number"),
            "chapter_title": row.get("chapter_title"),
        }
    return page_map


def page_refs(source_page_ids: Iterable[str], page_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for page_id in unique(source_page_ids):
        mapped = page_map.get(str(page_id))
        if mapped:
            references.append(dict(mapped))
            continue
        match = re.search(r"(\d+)$", str(page_id))
        references.append({
            "source_page_id": str(page_id),
            "pdf_page": int(match.group(1)) if match else None,
            "page_number": None,
            "printed_page": None,
            "page_type": None,
            "part_number": None,
            "part_title": None,
            "chapter_number": None,
            "chapter_title": None,
        })
    return references


def ancestor_ids(unit_id: str | None, node_by_id: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []
    cursor = unit_id
    while cursor and cursor in node_by_id:
        result.append(cursor)
        cursor = node_by_id[cursor].get("parent_id")
    return result


def public_node(node: dict[str, Any], concept_ids: list[str]) -> dict[str, Any]:
    value = dict(node)
    unit_id = value.get("unit_id")
    value["section_id"] = unit_id
    value["children"] = list(value.get("child_ids", []))
    value["concept_ids"] = unique(concept_ids)
    value["paragraph_count"] = len(value.get("paragraph_ids", []))
    value["source_page_count"] = len(value.get("source_page_ids", []))
    value["visual_ids"] = unique(value.get("visual_ids", []))
    value["table_ids"] = unique(value.get("table_ids", []))
    # Match the compact proven schema: leaf nodes retain direct source IDs;
    # parent navigation uses child IDs and counts instead of repeating every
    # descendant paragraph.
    if value.get("level") in {"part", "chapter"} or (
        value.get("level") == "major_section" and value.get("child_ids")
    ):
        value.pop("paragraph_ids", None)
        value.pop("source_page_ids", None)
    return value


def citation_reference(
    source_page_ids: list[str],
    section_path: list[str],
    paragraph: dict[str, Any] | None,
    page_map: dict[str, dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pages = page_refs(source_page_ids, page_map)
    primary = next((page for page in pages if page.get("page_number") is not None), pages[0] if pages else {})
    chapter_number = primary.get("chapter_number")
    chapter_title = clean(primary.get("chapter_title")) or None
    part_title = clean(primary.get("part_title")) or None
    unit_title = section_path[-1] if section_path else None
    if paragraph:
        unit_id = paragraph.get("unit_id")
        unit = node_by_id.get(unit_id or "", {})
        chapter_number = chapter_number or unit.get("chapter_number")
        chapter_title = chapter_title or unit.get("chapter_title")
        part_title = part_title or unit.get("part_title")
    page_numbers = unique(page.get("page_number") for page in pages if page.get("page_number") is not None)
    page_number = page_numbers[0] if page_numbers else None
    page_end = page_numbers[-1] if len(page_numbers) > 1 else page_number
    page_label = f"p. {page_number}" if page_number is not None else "PDF page unavailable"
    if len(page_numbers) > 1:
        page_label = f"pp. {page_number}–{page_end}"
    chapter_label = f"Chapter {chapter_number}" if chapter_number is not None else ""
    if chapter_title:
        chapter_label += f": {chapter_title}"
    unit_label = f", {unit_title}" if unit_title else ""
    formatted = f"{AUTHOR}, {SOURCE_TITLE} ({YEAR}), {chapter_label}{unit_label}, {page_label}".replace(", ,", ",")
    short = f"{AUTHOR}, Stroke Rehabilitation, {EDITION} ed."
    if chapter_number is not None:
        short += f", Ch. {chapter_number}"
    short += f", {page_label}"
    return {
        "source_id": SOURCE_ID,
        "source_title": SOURCE_TITLE,
        "work_title": WORK_TITLE,
        "edition": EDITION,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "part_title": part_title,
        "unit_title": unit_title,
        "page_number": page_number,
        "page_number_end": page_end,
        "page_number_type": "printed_textbook_page" if page_number is not None else "not_available_for_page",
        "pdf_page": primary.get("pdf_page"),
        "source_page_id": primary.get("source_page_id"),
        "source_page_ids": unique(source_page_ids),
        "pdf_page_start": paragraph.get("pdf_page_start") if paragraph else primary.get("pdf_page"),
        "pdf_page_end": paragraph.get("pdf_page_end") if paragraph else primary.get("pdf_page"),
        "printed_page_start": paragraph.get("printed_page_start") if paragraph else primary.get("printed_page"),
        "printed_page_end": paragraph.get("printed_page_end") if paragraph else primary.get("printed_page"),
        "section_path": list(section_path),
        "citation_text": formatted,
        "short_form": short,
        "formatted": formatted,
        "status": STATUS,
        "verification_status": STATUS,
        "exact_quote_eligible": False,
    }


def build_structure(
    structure_raw: dict[str, Any],
    visual_by_id: dict[str, dict[str, Any]],
    keyword_concept_ids: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    internal = {node["unit_id"]: dict(node) for node in structure_raw.get("nodes", []) if node.get("unit_id")}
    keyword_concept_ids = keyword_concept_ids or {}
    for node in internal.values():
        node["visual_ids"] = unique(node.get("visual_ids", []))
        node["table_ids"] = unique(node.get("table_ids", []))
        node["child_ids"] = unique(node.get("child_ids", []))
        node["concept_ids"] = unique(node.get("concept_ids", []) + keyword_concept_ids.get(node["unit_id"], []))
    for visual in visual_by_id.values():
        for unit_id in visual.get("section_ids", []):
            if unit_id not in internal:
                continue
            internal[unit_id]["visual_ids"] = unique(internal[unit_id].get("visual_ids", []) + [visual["visual_id"]])
            if visual.get("table_id"):
                internal[unit_id]["table_ids"] = unique(internal[unit_id].get("table_ids", []) + [visual["table_id"]])
    for node in internal.values():
        parent_id = node.get("parent_id")
        if parent_id in internal:
            internal[parent_id]["child_ids"] = unique(internal[parent_id].get("child_ids", []) + [node["unit_id"]])
    for node in internal.values():
        if node.get("level") == "part":
            node["chapter_ids"] = [child for child in node.get("child_ids", []) if internal.get(child, {}).get("level") == "chapter"]
    parts = [node for node in internal.values() if node.get("level") == "part"]
    parts.sort(key=lambda node: (node.get("part_number") or 999, node["unit_id"]))
    nodes = [node for node in internal.values() if node.get("level") != "part"]
    nodes.sort(key=lambda node: (node.get("pdf_page_start") or 99999, len(node.get("section_path", [])), node["unit_id"]))
    public_parts = [public_node(node, node.get("concept_ids", [])) for node in parts]
    public_nodes = [public_node(node, node.get("concept_ids", [])) for node in nodes]
    counts = {
        "parts": len(parts),
        "chapters": sum(node.get("level") == "chapter" for node in internal.values()),
        "major_sections": sum(node.get("level") == "major_section" for node in internal.values()),
        "subsections": sum(node.get("level") == "subsection" for node in internal.values()),
        "nodes": len(internal),
    }
    result = {
        "schema_version": "vtc-stroke-rehabilitation-5e.retrieval-structure.v1",
        "record_type": "retrieval_structure_lookup",
        "source_id": SOURCE_ID,
        "course_code": COURSE_CODE,
        "course_title": COURSE_TITLE,
        "source_role": "additional_source",
        "book_id": BOOK_ID,
        "title": SOURCE_TITLE,
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "processing_order": ["subsection", "major_section", "chapter", "part"],
        "parts": public_parts,
        "nodes": public_nodes,
        "counts": counts,
        "status": STATUS,
        "verification_status": STATUS,
    }
    return result, internal


def build_visuals(
    visual_manifest: dict[str, Any],
    visual_analysis: dict[str, Any],
    page_map: dict[str, dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    analysis_by_id = {item.get("visual_id"): item for item in visual_analysis.get("visual_extractions", [])}
    table_by_id = {table.get("table_id"): table for table in visual_manifest.get("tables", []) if table.get("table_id")}
    table_to_visual: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for visual in visual_manifest.get("visual_locations", []):
        visual_id = clean(visual.get("visual_id"))
        if not visual_id:
            continue
        analysis = analysis_by_id.get(visual_id, {})
        page_id = clean(visual.get("source_page_id"))
        page = dict(page_map.get(page_id, {}))
        table_id = clean(visual.get("table_id")) or clean(analysis.get("table_id")) or None
        table = table_by_id.get(table_id or "", {})
        unit_id = analysis.get("unit_id")
        section_ids = ancestor_ids(unit_id, node_by_id)
        section_paths = [node_by_id[unit_id].get("section_path", [])] if unit_id in node_by_id else []
        name = clean(visual.get("name")) or clean(analysis.get("name")) or clean(analysis.get("table_name")) or clean(table.get("name")) or None
        caption = visual.get("caption") or table.get("caption") or None
        record = {
            "visual_id": visual_id,
            "table_id": table_id,
            "source_layout_id": visual.get("source_layout_id"),
            "pdf_page": page.get("pdf_page", visual.get("pdf_page")),
            "page_number": page.get("page_number", visual.get("printed_page")),
            "printed_page": page.get("printed_page", visual.get("printed_page")),
            "page_type": page.get("page_type", visual.get("page_type")),
            "source_page_id": page.get("source_page_id", page_id),
            "part_number": page.get("part_number", visual.get("part_number")),
            "part_title": page.get("part_title"),
            "chapter_number": page.get("chapter_number", visual.get("chapter_number")),
            "chapter_title": page.get("chapter_title", visual.get("chapter_title")),
            "page_reference": page or {
                "source_page_id": page_id,
                "pdf_page": visual.get("pdf_page"),
                "page_number": visual.get("printed_page"),
                "printed_page": visual.get("printed_page"),
            },
            "visual_type": "table" if table_id else visual.get("label"),
            "visual_role": visual.get("visual_role") or analysis.get("visual_role"),
            "label": visual.get("label") or analysis.get("label"),
            "name": name,
            "caption": caption,
            "location": visual.get("location_description") or analysis.get("location_description"),
            "bbox_px": visual.get("bbox_px"),
            "bbox_points": visual.get("bbox_points"),
            "confidence": visual.get("confidence"),
            "section_ids": section_ids,
            "section_paths": section_paths,
            "content_reconstruction": visual.get("content_reconstruction") or analysis.get("content_reconstruction"),
            "table_reconstruction_available": bool(table_id and table_id in table_by_id),
            "table_reconstruction_source": "../../02 Text and Tables/stroke_rehab_visual_locations_and_tables_full_generated.json" if table_id else None,
            "policy": "full reconstructed table record" if table_id else "location/name metadata only; visual contents not OCRed",
            "status": STATUS,
            "verification_status": STATUS,
        }
        records.append(record)
        by_id[visual_id] = record
        if table_id:
            table_to_visual[table_id] = visual_id
    for table_id, table in table_by_id.items():
        if table_id not in table_to_visual:
            # A table record without a surviving visual candidate is retained
            # in the table layer but is not fabricated into the visual index.
            continue
    return records, by_id, table_to_visual


def build_passages(
    extraction: dict[str, Any],
    leaf_extractions: list[dict[str, Any]],
    page_map: dict[str, dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    passage_by_id = {paragraph.get("paragraph_id"): paragraph for paragraph in extraction.get("paragraphs", []) if paragraph.get("paragraph_id")}
    paragraph_to_unit: dict[str, str] = {}
    for leaf in leaf_extractions:
        unit_id = leaf.get("unit_id")
        if not unit_id:
            continue
        for passage_id in leaf.get("source_passage_ids", []):
            paragraph_to_unit.setdefault(passage_id, unit_id)
    passages: list[dict[str, Any]] = []
    for paragraph_id, paragraph in passage_by_id.items():
        text = clean(paragraph.get("text"))
        if not text:
            continue
        unit_id = paragraph_to_unit.get(paragraph_id)
        if not unit_id and paragraph.get("section_id") in node_by_id:
            unit_id = paragraph.get("section_id")
        section_ids = ancestor_ids(unit_id, node_by_id)
        section_path = node_by_id.get(unit_id or "", {}).get("section_path", [])
        if not section_path and paragraph.get("section_title"):
            section_path = [value for value in [paragraph.get("part_title"), paragraph.get("chapter_title"), paragraph.get("section_title")] if value]
        source_page_ids = unique(paragraph.get("source_page_ids", []))
        reference = citation_reference(source_page_ids, list(section_path), {**paragraph, "unit_id": unit_id}, page_map, node_by_id)
        passages.append({
            "source_passage_id": paragraph_id,
            "text": text,
            "source_page_ids": source_page_ids,
            "source_pages": page_refs(source_page_ids, page_map),
            "section_ids": section_ids,
            "section_path": list(section_path),
            "unit_id": unit_id,
            "content_type": paragraph.get("content_type", "logical_text_block"),
            "list_group_id": paragraph.get("list_group_id"),
            "list_item_index": paragraph.get("list_item_index"),
            "cross_page_merged": bool(paragraph.get("cross_page_merged")),
            "cross_page_part_count": paragraph.get("cross_page_part_count", 1),
            "source_line_ids": unique(paragraph.get("source_line_ids", [])),
            "source_line_keys": unique(paragraph.get("source_line_keys", [])),
            "reference": reference,
            "status": STATUS,
            "verification_status": STATUS,
        })
    return passages, {item["source_passage_id"]: item for item in passages}, paragraph_to_unit


def build_keyword_indexes(
    keyword_data: dict[str, Any],
    passages_by_id: dict[str, dict[str, Any]],
    visual_by_id: dict[str, dict[str, Any]],
    table_to_visual: dict[str, str],
    page_map: dict[str, dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[str]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in keyword_data.get("records", []):
        preferred = clean(record.get("canonical_candidate")) or clean(record.get("source_form")) or clean(record.get("small_area"))
        term_key = normalize(preferred)
        if not term_key:
            continue
        unit_id = record.get("unit_id")
        element_ids = unique(record.get("source_element_ids", []))
        source_passage_ids = unique(record.get("source_passage_ids", []))
        source_page_ids = unique(record.get("source_page_ids", []))
        section_ids = ancestor_ids(unit_id, node_by_id)
        if not section_ids:
            section_ids = unique(
                section_id
                for passage_id in source_passage_ids
                for section_id in passages_by_id.get(passage_id, {}).get("section_ids", [])
            )
        excerpt = ""
        for passage_id in source_passage_ids:
            passage = passages_by_id.get(passage_id)
            if passage:
                excerpt = sentence_excerpt(passage.get("text", ""), preferred)
                if excerpt:
                    break
        if not excerpt:
            for element_id in element_ids:
                visual = visual_by_id.get(element_id)
                if visual:
                    excerpt = clean(visual.get("name")) or clean(visual.get("caption"))
                    break
                if element_id in table_to_visual:
                    visual = visual_by_id.get(table_to_visual[element_id], {})
                    excerpt = clean(visual.get("name")) or clean(visual.get("caption"))
                    break
        grouped[(clean(record.get("category")) or "clinical_concept", term_key)].append({
            "keyword_record_id": record.get("record_id"),
            "unit_id": unit_id,
            "level": record.get("level"),
            "broad_area": clean(record.get("broad_area")) or clean(record.get("category")),
            "small_area": clean(record.get("small_area")) or preferred,
            "keyword_path": list(record.get("keyword_path", [])),
            "source_form": clean(record.get("source_form")) or preferred,
            "source_passage_ids": source_passage_ids,
            "source_element_ids": element_ids,
            "source_page_ids": source_page_ids,
            "section_ids": section_ids,
            "source_excerpt": excerpt,
            "retrieval_terms": unique(record.get("retrieval_terms", [])),
        })

    concepts: list[dict[str, Any]] = []
    occurrences: list[dict[str, Any]] = []
    node_concepts: dict[str, list[str]] = defaultdict(list)
    for concept_number, ((category, term_key), records) in enumerate(sorted(grouped.items()), 1):
        concept_id = f"{BOOK_ID}-C-{concept_number:07d}"
        preferred = max(
            unique(record.get("source_form") for record in records),
            key=lambda value: (len(clean(value)), clean(value).casefold()),
            default=term_key,
        )
        source_forms = unique(record.get("source_form") for record in records)
        keyword_paths: list[list[str]] = []
        retrieval_terms: list[str] = []
        section_ids: list[str] = []
        occurrence_ids: list[str] = []
        for record in records:
            path = record.get("keyword_path") or [record.get("broad_area"), record.get("small_area")]
            path = [clean(value) for value in path if clean(value)]
            if path and path not in keyword_paths:
                keyword_paths.append(path)
            retrieval_terms.extend(record.get("retrieval_terms", []))
            retrieval_terms.extend(alias_variants(record.get("source_form", "")))
            occurrence_id = f"{BOOK_ID}-O-{len(occurrences) + 1:08d}"
            occurrence_ids.append(occurrence_id)
            section_ids.extend(record.get("section_ids", []))
            related_visual_ids = []
            for element_id in record.get("source_element_ids", []):
                if element_id in visual_by_id:
                    related_visual_ids.append(element_id)
                elif element_id in table_to_visual:
                    related_visual_ids.append(table_to_visual[element_id])
            occurrence = {
                "occurrence_id": occurrence_id,
                "concept_id": concept_id,
                "keyword_record_id": record.get("keyword_record_id"),
                "category": category,
                "broad_area": record.get("broad_area"),
                "small_area": record.get("small_area"),
                "keyword_path": path,
                "source_form": record.get("source_form"),
                "unit_id": record.get("unit_id"),
                "level": record.get("level"),
                "source_passage_ids": record.get("source_passage_ids", []),
                "source_element_ids": record.get("source_element_ids", []),
                "source_page_ids": record.get("source_page_ids", []),
                "source_pages": page_refs(record.get("source_page_ids", []), page_map),
                "section_ids": unique(record.get("section_ids", [])),
                "section_path": node_by_id.get(record.get("unit_id") or "", {}).get("section_path", []),
                "source_excerpt": record.get("source_excerpt", ""),
                "related_visual_ids": unique(related_visual_ids),
                "retrieval_terms": unique(record.get("retrieval_terms", [])),
                "status": STATUS,
                "verification_status": STATUS,
            }
            occurrences.append(occurrence)
        final_terms = unique(
            term
            for value in [preferred] + source_forms + retrieval_terms
            for term in alias_variants(value)
        )
        concept = {
            "concept_id": concept_id,
            "category": category,
            "broad_area": unique(record.get("broad_area") for record in records),
            "small_area": unique(record.get("small_area") for record in records),
            "preferred_label": preferred,
            "canonical_candidate": preferred,
            "keyword_paths": keyword_paths,
            "source_forms": source_forms,
            "retrieval_terms": final_terms,
            "occurrence_ids": occurrence_ids,
            "occurrence_count": len(occurrence_ids),
            "section_ids": unique(section_ids),
            "status": STATUS,
            "verification_status": STATUS,
        }
        concepts.append(concept)
        for section_id in unique(section_ids):
            node_concepts[section_id].append(concept_id)

    term_map: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"display_forms": set(), "concept_ids": set(), "occurrence_ids": set(), "categories": set()})
    concept_by_id = {concept["concept_id"]: concept for concept in concepts}
    for concept in concepts:
        for term in concept["retrieval_terms"]:
            term_key = normalize(term)
            if not term_key:
                continue
            entry = term_map[term_key]
            entry["display_forms"].add(term)
            entry["concept_ids"].add(concept["concept_id"])
            entry["occurrence_ids"].update(concept["occurrence_ids"])
            entry["categories"].add(concept["category"])
    term_lookup = {
        term: {
            "display_forms": sorted(entry["display_forms"]),
            "concept_ids": sorted(entry["concept_ids"]),
            "occurrence_ids": sorted(entry["occurrence_ids"]),
            "categories": sorted(entry["categories"]),
        }
        for term, entry in sorted(term_map.items())
    }
    return concepts, occurrences, term_lookup, {key: unique(value) for key, value in node_concepts.items()}


def build_indexes(inputs: dict[str, Any]) -> dict[str, Any]:
    page_map = build_page_map(inputs["page_rows"])
    visual_records, visual_by_id, table_to_visual = build_visuals(
        inputs["visual_manifest"], inputs["multi_level"], page_map, {}
    )
    # Visual unit IDs are needed before constructing hierarchy links.
    provisional_nodes = {node["unit_id"]: dict(node) for node in inputs["structure"].get("nodes", []) if node.get("unit_id")}
    visual_by_id_for_structure: dict[str, dict[str, Any]] = {}
    for visual in visual_records:
        unit_id = inputs["visual_by_id"].get(visual["visual_id"], {}).get("unit_id")
        if unit_id and unit_id in provisional_nodes:
            visual["section_ids"] = ancestor_ids(unit_id, provisional_nodes)
            visual["section_paths"] = [provisional_nodes[unit_id].get("section_path", [])]
        visual_by_id_for_structure[visual["visual_id"]] = visual
    structure, node_by_id = build_structure(inputs["structure"], visual_by_id_for_structure)
    # Recompute visual section IDs against the complete parent map.
    for visual in visual_records:
        analysis = inputs["visual_by_id"].get(visual["visual_id"], {})
        unit_id = analysis.get("unit_id")
        visual["section_ids"] = ancestor_ids(unit_id, node_by_id)
        visual["section_paths"] = [node_by_id[unit_id].get("section_path", [])] if unit_id in node_by_id else []
    passages, passages_by_id, paragraph_to_unit = build_passages(
        inputs["extraction"], inputs["multi_level"].get("leaf_extractions", []), page_map, node_by_id
    )
    concepts, occurrences, term_lookup, node_concepts = build_keyword_indexes(
        inputs["keywords"], passages_by_id, visual_by_id, table_to_visual, page_map, node_by_id
    )
    # Add concept links after keyword grouping, then rebuild the public
    # structure copy so all hierarchy levels are navigable by concept.
    structure, node_by_id = build_structure(inputs["structure"], visual_by_id, node_concepts)
    for visual in visual_records:
        analysis = inputs["visual_by_id"].get(visual["visual_id"], {})
        unit_id = analysis.get("unit_id")
        visual["section_ids"] = ancestor_ids(unit_id, node_by_id)
        visual["section_paths"] = [node_by_id[unit_id].get("section_path", [])] if unit_id in node_by_id else []

    concept_by_id = {concept["concept_id"]: concept for concept in concepts}
    table_by_id = {table.get("table_id"): table for table in inputs["visual_manifest"].get("tables", []) if table.get("table_id")}
    structure_lookup = {node.get("section_id"): node for node in structure.get("nodes", [])}
    for part in structure.get("parts", []):
        structure_lookup[part.get("section_id")] = part

    concept_index = {
        "schema_version": "llm-wiki.concept-index.v1-medical",
        "record_type": "concept_index",
        "source_id": SOURCE_ID,
        "course_code": COURSE_CODE,
        "book_id": BOOK_ID,
        "index_rule": "Group corrected broad-area/small-area keyword candidates by category and normalized candidate; retain source forms, keyword paths, aliases, and source occurrence IDs.",
        "concepts": concepts,
        "counts": {
            "concepts": len(concepts),
            "occurrences": len(occurrences),
            "categories": len({concept["category"] for concept in concepts}),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    occurrence_index = {
        "schema_version": "llm-wiki.occurrence-index.v1-medical",
        "record_type": "occurrence_index",
        "source_id": SOURCE_ID,
        "course_code": COURSE_CODE,
        "book_id": BOOK_ID,
        "index_rule": "Each keyword occurrence points to a source passage or visual/table element and an explicit hierarchy path; no clinical relationship is inferred.",
        "occurrences": occurrences,
        "counts": {
            "occurrences": len(occurrences),
            "passage_occurrences": sum(bool(item.get("source_passage_ids")) for item in occurrences),
            "visual_occurrences": sum(bool(item.get("source_element_ids")) for item in occurrences),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    term_lookup_index = {
        "schema_version": "llm-wiki.term-lookup-index.v1-medical",
        "record_type": "term_lookup_index",
        "source_id": SOURCE_ID,
        "course_code": COURSE_CODE,
        "book_id": BOOK_ID,
        "normalization": "Unicode NFKC + casefold + letters/digits only; aliases retain source forms, selected UK/US spellings, and simple singular variants.",
        "lookup_rule": "Exact normalized terms and query substrings return candidate concepts and occurrences; an AI must read the linked source passages before answering.",
        "terms": term_lookup,
        "counts": {
            "terms": len(term_lookup),
            "concepts_referenced": len(concept_by_id),
            "occurrences_referenced": len(occurrences),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    visual_index = {
        "schema_version": "vtc-stroke-rehabilitation-5e.visual-retrieval-index.v1",
        "record_type": "visual_retrieval_index",
        "source_id": SOURCE_ID,
        "course_code": COURSE_CODE,
        "book_id": BOOK_ID,
        "policy": {
            "tables": "Return the linked full reconstructed table record from the Text and Tables layer when a table matches.",
            "non_tables": "Return page, PDF page, bounding box, label, name/caption, and hierarchy location only; visual contents were not OCRed or reconstructed.",
        },
        "visuals": visual_records,
        "counts": {
            "visuals": len(visual_records),
            "tables": sum(bool(item.get("table_id")) for item in visual_records),
            "non_tables": sum(not bool(item.get("table_id")) for item in visual_records),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    formal_schema = {
        "schema_version": "stroke-rehabilitation.formal-answer.v1",
        "record_type": "formal_answer_schema",
        "purpose": "Portable answer format for any AI using this retrieval packet.",
        "required_fields": {
            "record_type": "formal_answer",
            "source_id": SOURCE_ID,
            "book_id": BOOK_ID,
            "query": "The user's question",
            "answer": "A concise synthesis grounded in returned source passages",
            "source_quotations": "Quotation candidates actually used in the answer",
            "references": "Matching human-readable references",
        },
        "source_quotation_fields": ["evidence_id", "quotation", "source_passage_id", "reference", "in_text_citation", "verification_status"],
        "reference_fields": ["source_id", "work_title", "edition", "chapter_number", "chapter_title", "page_number", "page_number_type", "pdf_page", "source_page_id", "section_path", "short_form", "formatted"],
        "citation_rule": "Use the printed textbook page as p. or pp. and support each material factual statement with the matching source quotation and reference.",
        "page_rule": "page_number is the printed textbook page; pdf_page is retained for physical-file navigation.",
        "summary_rule": "Summaries provide orientation only. Source quotations and source passages are the evidence.",
        "visual_rule": "Reference tables, figures, charts, and illustrations by name or label, chapter, printed page, and location. Use full reconstructed contents only for tables.",
        "verification_rule": "Keep status generated_not_verified until the cited source page image has been manually checked.",
        "claims_index": "not_used",
        "status": STATUS,
        "verification_status": STATUS,
    }
    visual_ids = {item["visual_id"] for item in visual_records}
    table_ids = set(table_by_id)
    concept_ids = set(concept_by_id)
    occurrence_ids = {item["occurrence_id"] for item in occurrences}
    passage_ids = set(passages_by_id)
    node_ids = set(structure_lookup)
    validation = {
        "schema_version": "llm-wiki.medical-retrieval-validation.v1",
        "record_type": "retrieval_index_validation_report",
        "source_id": SOURCE_ID,
        "course_code": COURSE_CODE,
        "book_id": BOOK_ID,
        "checks": {
            "no_claims_index_requested": True,
            "concept_ids_unique": len(concept_ids) == len(concepts),
            "occurrence_ids_unique": len(occurrence_ids) == len(occurrences),
            "occurrence_concept_links_resolve": all(item.get("concept_id") in concept_ids for item in occurrences),
            "term_concept_links_resolve": all(set(item.get("concept_ids", [])) <= concept_ids for item in term_lookup.values()),
            "term_occurrence_links_resolve": all(set(item.get("occurrence_ids", [])) <= occurrence_ids for item in term_lookup.values()),
            "passage_ids_unique": len(passage_ids) == len(passages),
            "passage_page_ids_resolve": all(page.get("source_page_id") in page_map for passage in passages for page in passage.get("source_pages", [])),
            "passage_section_links_resolve": all(section_id in node_ids for passage in passages for section_id in passage.get("section_ids", [])),
            "occurrence_passage_links_resolve": all(source_id in passage_ids for item in occurrences for source_id in item.get("source_passage_ids", [])),
            "occurrence_visual_links_resolve": all(source_id in visual_ids or source_id in table_ids or source_id in node_ids for item in occurrences for source_id in item.get("source_element_ids", [])),
            "visual_page_numbers_match_source_map": all(item.get("source_page_id") not in page_map or item.get("pdf_page") == page_map[item["source_page_id"]].get("pdf_page") for item in visual_records),
            "visual_table_links_resolve": all(not item.get("table_id") or item.get("table_id") in table_ids for item in visual_records),
            "non_table_visuals_location_only": all(item.get("table_id") or item.get("content_reconstruction") == "location_only" for item in visual_records),
            "node_concept_links_resolve": all(concept_id in concept_ids for node in structure_lookup.values() for concept_id in node.get("concept_ids", [])),
            "generated_not_verified_preserved": all(item.get("verification_status") == STATUS for item in concepts + occurrences + passages + visual_records),
        },
        "counts": {
            **structure.get("counts", {}),
            "passages": len(passages),
            "concepts": len(concepts),
            "occurrences": len(occurrences),
            "terms": len(term_lookup),
            "visuals": len(visual_records),
            "tables": len(table_by_id),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    retrieval_metadata = {
        "schema_version": "vtc-stroke-rehabilitation-5e.retrieval-index.v1",
        "record_type": "retrieval_index_manifest",
        "source_id": SOURCE_ID,
        "course_code": COURSE_CODE,
        "course_title": COURSE_TITLE,
        "source_role": "additional_source",
        "book_id": BOOK_ID,
        "title": SOURCE_TITLE,
        "retrieval_group": "HHS4185-course-first",
        "priority": 2,
        "course_first_policy": "HHS4185 course materials are searched first; this book supplements or clarifies the course material.",
        "evidence_policy": "Read returned source passages before answering. Use summaries only for orientation and cite printed textbook pages.",
        "claims_index": "not_created",
        "files": {
            "structure": "structure_lookup.json",
            "concepts": "concept_index.json",
            "occurrences": "occurrence_index.json",
            "terms": "term_lookup.json",
            "passages": "passage_index.jsonl",
            "visuals": "visual_index.json",
            "formal_output_schema": "formal_output_schema.json",
            "validation": "retrieval_index_validation_report.json",
        },
        "counts": validation["counts"],
        "status": STATUS,
        "verification_status": STATUS,
    }
    return {
        "retrieval_metadata": retrieval_metadata,
        "structure": structure,
        "concept_index": concept_index,
        "occurrence_index": occurrence_index,
        "term_lookup": term_lookup_index,
        "visual_index": visual_index,
        "formal_schema": formal_schema,
        "validation": validation,
        "passages": passages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    package = args.package_root
    output = args.output_root
    if output.exists() and any(output.iterdir()) and not args.overwrite:
        raise SystemExit(f"Output exists and is non-empty; pass --overwrite: {output}")
    output.mkdir(parents=True, exist_ok=True)
    inputs = {
        "page_rows": load_jsonl(package / "01 OCR and Layout/stroke_rehab_page_structure_generated.jsonl"),
        "extraction": load_json(package / "02 Text and Tables/stroke_rehab_sections_paragraphs_full_generated.json"),
        "visual_manifest": load_json(package / "02 Text and Tables/stroke_rehab_visual_locations_and_tables_full_generated.json"),
        "structure": load_json(package / "03 Analysis/stroke_rehab_hierarchical_structure_generated.json"),
        "multi_level": load_json(package / "03 Analysis/stroke_rehab_multi_level_extractions_generated.json"),
        "keywords": load_json(package / "03 Analysis/stroke_rehab_keyword_extraction_generated.json"),
    }
    inputs["visual_by_id"] = {item.get("visual_id"): item for item in inputs["multi_level"].get("visual_extractions", [])}
    result = build_indexes(inputs)
    files = {
        "stroke_rehab_retrieval_structure_generated.json": result["structure"],
        "structure_lookup.json": result["structure"],
        "retrieval_index_manifest.json": result["retrieval_metadata"],
        "concept_index.json": result["concept_index"],
        "occurrence_index.json": result["occurrence_index"],
        "term_lookup.json": result["term_lookup"],
        "visual_index.json": result["visual_index"],
        "formal_output_schema.json": result["formal_schema"],
        "retrieval_index_validation_report.json": result["validation"],
    }
    for filename, value in files.items():
        (output / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "passage_index.jsonl").open("w", encoding="utf-8") as handle:
        for passage in result["passages"]:
            handle.write(json.dumps(passage, ensure_ascii=False) + "\n")
    print(json.dumps({"output_root": str(output), "counts": result["validation"]["counts"], "checks": result["validation"]["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

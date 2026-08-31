#!/usr/bin/env python3
"""Build portable retrieval files for the orthopedic-test source package."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


BOOK_ID = "ORTHO3"
SOURCE_ID = "HHS4185-REF-ORTHO-SPECIAL-TESTS"
STATUS = "generated_not_verified"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def reference_for(paragraph: dict[str, Any]) -> dict[str, Any]:
    page_id = next(iter(paragraph.get("source_page_ids", [])), "")
    match = re.search(r"(\d+)$", page_id)
    pdf_page = int(match.group(1)) if match else None
    printed_page = pdf_page - 24 if pdf_page is not None and pdf_page >= 25 else None
    chapter_number = paragraph.get("chapter_number")
    chapter_title = paragraph.get("chapter_title")
    test_title = paragraph.get("test_title")
    formatted = "Konin et al., Special Tests for Orthopedic Examination, 3rd ed."
    if chapter_number is not None:
        formatted += f", Section {chapter_number}: {chapter_title}"
    if test_title:
        formatted += f", {test_title}"
    if printed_page is not None:
        formatted += f", p. {printed_page} [PDF p. {pdf_page}]"
    return {
        "source_id": SOURCE_ID,
        "source_title": "Special Tests for Orthopedic Examination",
        "edition": "3rd",
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "test_title": test_title,
        "component_title": paragraph.get("component_kind"),
        "page_number": printed_page,
        "page_number_type": "printed_book_page" if printed_page is not None else "unumbered_pdf_page",
        "pdf_page": pdf_page,
        "source_page_ids": paragraph.get("source_page_ids", []),
        "section_path": paragraph.get("section_path", []),
        "formatted": formatted,
        "status": STATUS,
        "verification_status": STATUS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--summaries", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--paragraphs", type=Path, required=True)
    parser.add_argument("--visual-manifest", type=Path, required=True)
    parser.add_argument("--tables", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    analysis = load(args.analysis.expanduser().resolve())
    summaries = load(args.summaries.expanduser().resolve())
    structure = load(args.structure.expanduser().resolve())
    paragraph_data = load(args.paragraphs.expanduser().resolve())
    visual_manifest = load(args.visual_manifest.expanduser().resolve())
    tables = load(args.tables.expanduser().resolve())
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    keyword_records = analysis.get("keyword_records", []) + analysis.get("visual_extractions", [])
    concepts: dict[tuple[str, str], dict[str, Any]] = {}
    occurrences: list[dict[str, Any]] = []
    term_lookup: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"concept_ids": [], "occurrence_ids": []})
    for keyword in keyword_records:
        key = (keyword.get("broad_area", ""), norm(keyword.get("canonical_candidate", "")))
        if not key[1]:
            continue
        concept = concepts.setdefault(key, {
            "concept_id": f"{BOOK_ID}-C-{len(concepts) + 1:07d}",
            "broad_area": keyword.get("broad_area"),
            "preferred_label": keyword.get("canonical_candidate"),
            "canonical_candidate": keyword.get("canonical_candidate"),
            "keyword_path": keyword.get("keyword_path", []),
            "source_forms": [],
            "retrieval_terms": [],
            "occurrence_ids": [],
            "source_passage_ids": [],
            "source_page_ids": [],
            "section_ids": [],
            "status": STATUS,
            "verification_status": STATUS,
        })
        occurrence_id = keyword["record_id"].replace("-KW-", "-OCC-")
        source_passage_ids = keyword.get("source_passage_ids", [])
        source_page_ids = keyword.get("source_page_ids", [])
        section_ids = [value for value in [keyword.get("component_id"), keyword.get("test_id")] if value]
        section_ids.extend(
            value
            for value in keyword.get("source_element_ids", [])
            if isinstance(value, str) and value.startswith(f"{BOOK_ID}-CH")
        )
        occurrence = {
            "occurrence_id": occurrence_id,
            "concept_id": concept["concept_id"],
            "source_passage_ids": source_passage_ids,
            "source_page_ids": source_page_ids,
            "section_ids": unique(section_ids),
            "source_element_ids": [keyword["source_element_id"]] if keyword.get("source_element_id") else [],
            "broad_area": keyword.get("broad_area"),
            "small_area": keyword.get("small_area"),
            "source_form": keyword.get("source_form"),
            "keyword_path": keyword.get("keyword_path", []),
            "status": STATUS,
            "verification_status": STATUS,
        }
        occurrences.append(occurrence)
        concept["source_forms"].extend(keyword.get("source_form", "").split())
        concept["retrieval_terms"].extend(keyword.get("retrieval_terms", []))
        concept["occurrence_ids"].append(occurrence_id)
        concept["source_passage_ids"].extend(source_passage_ids)
        concept["source_page_ids"].extend(source_page_ids)
        concept["section_ids"].extend(occurrence["section_ids"])
        for term in keyword.get("retrieval_terms", []) + [keyword.get("source_form", "")]:
            key_term = norm(term)
            if key_term:
                term_lookup[key_term]["concept_ids"].append(concept["concept_id"])
                term_lookup[key_term]["occurrence_ids"].append(occurrence_id)

    concept_list = list(concepts.values())
    for concept in concept_list:
        for field in ("source_forms", "retrieval_terms", "occurrence_ids", "source_passage_ids", "source_page_ids", "section_ids"):
            concept[field] = unique(concept[field])
        concept["occurrence_count"] = len(concept["occurrence_ids"])
    occurrence_list = occurrences
    term_list = {term: {key: unique(value) for key, value in mapping.items()} for term, mapping in sorted(term_lookup.items())}

    passage_path = output_dir / "passage_index.jsonl"
    passages = []
    for paragraph in paragraph_data.get("paragraphs", []):
        if paragraph.get("content_type") not in {"paragraph", "list_item", "component_heading", "test_title", "chapter_title"}:
            continue
        test_id = paragraph.get("major_section_id")
        passage = {
            "passage_id": paragraph["paragraph_id"],
            "source_id": SOURCE_ID,
            "book_id": BOOK_ID,
            "text": paragraph.get("text", ""),
            "content_type": paragraph.get("content_type"),
            "is_synthetic": paragraph.get("is_synthetic", False),
            "section_id": paragraph.get("section_id"),
            "test_id": test_id,
            "chapter_number": paragraph.get("chapter_number"),
            "chapter_title": paragraph.get("chapter_title"),
            "test_title": paragraph.get("test_title"),
            "component_kind": paragraph.get("component_kind"),
            "section_path": paragraph.get("section_path", []),
            "source_page_ids": paragraph.get("source_page_ids", []),
            "page_parts": paragraph.get("page_parts", []),
            "reference": reference_for(paragraph),
            "status": STATUS,
            "verification_status": STATUS,
        }
        passages.append(passage)
    passage_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in passages), encoding="utf-8")

    structure_lookup = {
        "schema_version": "vtc-ortho3.structure-lookup.v1",
        "record_type": "structure_lookup",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "nodes": structure.get("nodes", []),
        "parts": structure.get("parts", []),
        "status": STATUS,
        "verification_status": STATUS,
    }
    visual_records = []
    for visual in analysis.get("visual_records", visual_manifest.get("visuals", [])):
        visual_records.append(visual)
    visual_index = {
        "schema_version": "vtc-ortho3.visual-index.v1",
        "record_type": "visual_index",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "visual_policy": {"tables": "full reconstruction when detected", "non_tables": "location/name/type metadata only", "table_count": len(tables.get("tables", []))},
        "visuals": visual_records,
        "tables": tables.get("tables", []),
        "counts": {"visuals": len(visual_records), "tables": len(tables.get("tables", []))},
        "status": STATUS,
        "verification_status": STATUS,
    }
    formal_schema = {
        "schema_version": "vtc-ortho3.formal-answer.v1",
        "record_type": "formal_answer_contract",
        "required_sections": ["answer", "source_quotations", "references"],
        "answer": {"type": "string", "description": "Concise source-grounded synthesis."},
        "source_quotations": {"type": "array", "description": "Only returned source-extracted quotation candidates actually used."},
        "references": {"type": "array", "description": "Matching reference.formatted values; use printed book page as p. and PDF page only for navigation."},
        "visual_rule": "Cite visual name/type/location; reconstruct contents only for returned tables.",
        "verification_rule": "Every generated quotation, summary, visual mapping, and reference requires manual source-page verification.",
        "medical_scope": "Study aid only; not a substitute for clinical judgement or professional advice.",
        "status": STATUS,
        "verification_status": STATUS,
    }
    manifest = {
        "schema_version": "vtc-ortho3.retrieval-index-manifest.v1",
        "record_type": "retrieval_index_manifest",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "package_path": "sources/HHS4185/HHS4185-REF-ORTHO-SPECIAL-TESTS",
        "index_files": {"concepts": "concept_index.json", "occurrences": "occurrence_index.json", "terms": "term_lookup.json", "passages": "passage_index.jsonl", "visuals": "visual_index.json", "structure": "structure_lookup.json", "summaries": "hierarchical_summaries.json", "formal_output": "formal_output_schema.json", "validation": "retrieval_index_validation_report.json"},
        "source_separation": "This package remains separate from HHS4185 course materials, Davidson, and Stroke Rehabilitation.",
        "retrieval_policy": {"course_priority": "Search HHS4185 course materials first; this source is supplemental priority 2.", "source_passages_primary": True, "summaries_context_only": True, "non_table_visuals_metadata_only": True, "tables_full_reconstruction_when_detected": True, "exact_quotes_require_manual_verification": True, "claims_index": "not_created"},
        "counts": {"concepts": len(concept_list), "occurrences": len(occurrence_list), "terms": len(term_list), "passages": len(passages), "visuals": len(visual_records), "tables": len(tables.get("tables", [])), "quotation_candidates": len(analysis.get("quotation_candidates", []))},
        "status": STATUS,
        "verification_status": STATUS,
    }
    summary_copy = {**summaries, "status": STATUS, "verification_status": STATUS}
    for name, value in [("concept_index.json", {"schema_version": "vtc-ortho3.concept-index.v1", "record_type": "concept_index", "book_id": BOOK_ID, "source_id": SOURCE_ID, "concepts": concept_list, "counts": {"concepts": len(concept_list)}, "status": STATUS, "verification_status": STATUS}), ("occurrence_index.json", {"schema_version": "vtc-ortho3.occurrence-index.v1", "record_type": "occurrence_index", "book_id": BOOK_ID, "source_id": SOURCE_ID, "occurrences": occurrence_list, "counts": {"occurrences": len(occurrence_list)}, "status": STATUS, "verification_status": STATUS}), ("term_lookup.json", {"schema_version": "vtc-ortho3.term-lookup.v1", "record_type": "term_lookup", "book_id": BOOK_ID, "source_id": SOURCE_ID, "terms": term_list, "counts": {"terms": len(term_list)}, "status": STATUS, "verification_status": STATUS}), ("structure_lookup.json", structure_lookup), ("visual_index.json", visual_index), ("hierarchical_summaries.json", summary_copy), ("formal_output_schema.json", formal_schema), ("retrieval_index_manifest.json", manifest)]:
        (output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    validation = {
        "schema_version": "vtc-ortho3.retrieval-validation.v1",
        "record_type": "retrieval_index_validation_report",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "checks": {
            "concept_occurrence_links": all(occ["concept_id"] in {concept["concept_id"] for concept in concept_list} for occ in occurrence_list),
            "term_concept_links": all(concept_id in {concept["concept_id"] for concept in concept_list} for mapping in term_list.values() for concept_id in mapping["concept_ids"]),
            "passage_jsonl_records": len(passages),
            "structure_nodes": len(structure.get("nodes", [])),
            "visual_records": len(visual_records),
            "tables": len(tables.get("tables", [])),
            "all_status_generated_not_verified": all(item.get("status") == STATUS for item in concept_list + occurrence_list + visual_records),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    validation["valid"] = all(value is True or isinstance(value, int) for value in validation["checks"].values())
    (output_dir / "retrieval_index_validation_report.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), **manifest["counts"], "valid": validation["valid"], "status": STATUS}, ensure_ascii=False))


if __name__ == "__main__":
    main()

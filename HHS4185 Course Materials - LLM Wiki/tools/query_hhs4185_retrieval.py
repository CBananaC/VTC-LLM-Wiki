#!/usr/bin/env python3
"""Return a course-first, agent-neutral HHS4185 retrieval packet.

The packet searches the HHS4185 course materials first and Davidson's
Principles and Practice of Medicine, 25th edition second as a supplement.
It returns source passages, bottom-up summaries, visual metadata, table
reconstructions when available, and formal quotation/reference candidates.
All generated evidence still requires source-page verification.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


COURSE_WIKI = Path(__file__).resolve().parents[1]
COURSE_INDEX = COURSE_WIKI / "(5) Retrieval Index"
DAVIDSON_WIKI = COURSE_WIKI.parent / "Davidson 25th Edition - LLM Wiki"
DAVIDSON_INDEX = DAVIDSON_WIKI / "(6) Retrieval Index"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'/-]{2,}|[\u3400-\u9fff]{2,}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            key = value.get("source_passage_id")
            if not key:
                raise SystemExit(f"Missing source_passage_id at {path}:{line_number}")
            records[key] = value
    return records


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", value.casefold())


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def matched_terms(query: str, explicit_terms: list[str], terms: dict[str, Any], limit: int) -> list[str]:
    query_key = normalize(query)
    query_tokens = {normalize(token) for token in TOKEN_RE.findall(query)}
    candidates: dict[str, str] = {}
    for term in explicit_terms:
        if normalize(term):
            candidates[normalize(term)] = term
    for display_term in terms:
        key = normalize(display_term)
        if len(key) >= 4 and (key in query_tokens or key in query_key):
            candidates.setdefault(key, display_term)
    return [candidates[key] for key in sorted(candidates, key=lambda item: (-len(item), item))[:limit]]


def reference_for(source_kind: str, page: dict[str, Any], section_path: list[str]) -> dict[str, Any]:
    if source_kind == "course_materials":
        file_name = page.get("source_file") or "course material"
        slide = page.get("slide_number", page.get("page_number"))
        formatted = f"HHS4185 course materials, {file_name}, slide {slide} (PDF p. {page.get('pdf_page', slide)})"
        short_form = f"HHS4185, {file_name}, slide {slide}"
        page_type = "slide_number"
    else:
        formatted = page.get("formatted") or f"Davidson's Principles and Practice of Medicine, 25th ed., PDF p. {page.get('pdf_page')}"
        short_form = f"Davidson, 25th ed., Ch. {page.get('chapter_number')}, p. {page.get('page_number')}"
        page_type = "printed_book_page"
    return {
        "source_page_id": page.get("source_page_id"),
        "source_file": page.get("source_file"),
        "chapter_number": page.get("chapter_number"),
        "chapter_title": page.get("chapter_title"),
        "page_number": page.get("page_number", page.get("slide_number")),
        "page_number_type": page_type,
        "slide_number": page.get("slide_number"),
        "pdf_page": page.get("pdf_page"),
        "section_path": section_path,
        "short_form": short_form,
        "formatted": formatted,
    }


def formal_quotation(source_kind: str, passage: dict[str, Any]) -> dict[str, Any]:
    pages = passage.get("source_pages", [])
    page = pages[0] if pages else {}
    reference = reference_for(source_kind, page, passage.get("section_path", []))
    return {
        "evidence_id": f"{source_kind.upper()}-EVID-{passage.get('source_passage_id', '')}",
        "quotation": passage.get("text", ""),
        "quotation_source": "passage_index.jsonl",
        "source_passage_id": passage.get("source_passage_id"),
        "source_page_ids": passage.get("source_page_ids", []),
        "reference": reference,
        "in_text_citation": f"({reference['short_form']})",
        "quotation_status": "source_extracted_candidate",
        "verification_status": passage.get("verification_status", "generated_not_verified"),
        "manual_source_image_check_required": True,
    }


def formal_visual_reference(source_kind: str, hit: dict[str, Any]) -> dict[str, Any]:
    visual = hit.get("visual", {})
    page = visual.get("page_reference") or {
        "source_page_id": visual.get("source_page_id"),
        "source_file": visual.get("source_file"),
        "page_number": visual.get("page_number", visual.get("slide_number")),
        "page_number_type": "slide_number" if source_kind == "course_materials" else "printed_book_page",
        "slide_number": visual.get("slide_number"),
        "pdf_page": visual.get("pdf_page"),
        "formatted": visual.get("formatted"),
    }
    reference = reference_for(source_kind, page, (visual.get("section_paths") or [[]])[0])
    result = {
        "visual_id": hit.get("visual_id"),
        "visual_type": visual.get("visual_type"),
        "name": visual.get("name"),
        "location": visual.get("location"),
        "policy": visual.get("policy"),
        "reference": reference,
        "table_reconstruction_included": "table_reconstruction" in hit,
        "verification_status": visual.get("verification_status", "generated_not_verified"),
    }
    if "table_reconstruction" in hit:
        result["table_reconstruction"] = hit["table_reconstruction"]
    return result


def is_bibliography_source(source: dict[str, Any]) -> bool:
    path_keys = {normalize(value) for value in source.get("section_path", [])}
    source_text = source.get("text", "").strip().casefold()
    numbered_reference = any(re.match(r"^\d+\.\s", value.strip()) for value in source.get("section_path", []))
    bibliography_slide = bool(re.match(r"^\d+\.\s+.*\b(?:department|doi|http|journal|association)\b", source_text)) or numbered_reference
    return bool(path_keys & {"reference", "referencelist"}) or bibliography_slide


def search_source(source_kind: str, index_root: Path, summaries_path: Path, query: str, explicit_terms: list[str], limit: int, max_terms: int) -> dict[str, Any]:
    term_index = load_json(index_root / "term_lookup.json")
    concept_index = load_json(index_root / "concept_index.json")
    occurrence_index = load_json(index_root / "occurrence_index.json")
    structure = load_json(index_root / "structure_lookup.json")
    visual_index = load_json(index_root / "visual_index.json")
    tables_path = (COURSE_WIKI / "(3) Text and Tables/hhs4185_tables_generated.json") if source_kind == "course_materials" else (DAVIDSON_WIKI / "05 Visual Inventory/davidson25_tables_reconstructed_generated.json")
    tables = load_json(tables_path) if tables_path.exists() else {"tables": []}
    summaries = load_json(summaries_path) if summaries_path.exists() else {"units": []}
    passages = load_jsonl(index_root / "passage_index.jsonl")

    terms = term_index.get("terms", {})
    selected_terms = matched_terms(query, explicit_terms, terms, max_terms)
    concept_ids = unique(
        concept_id
        for term in selected_terms
        for concept_id in terms.get(term, {}).get("concept_ids", [])
    )
    concept_by_id = {item.get("concept_id"): item for item in concept_index.get("concepts", [])}
    occurrence_by_id = {item.get("occurrence_id"): item for item in occurrence_index.get("occurrences", [])}
    node_by_id = {item.get("section_id"): item for item in structure.get("nodes", [])}
    visual_by_id = {item.get("visual_id"): item for item in visual_index.get("visuals", [])}
    table_by_id = {item.get("table_id"): item for item in tables.get("tables", [])}
    summary_by_id = {item.get("unit_id"): item for item in summaries.get("units", [])}

    passage_hits: dict[str, dict[str, Any]] = {}
    visual_hits: dict[str, dict[str, Any]] = {}
    section_ids: set[str] = set()
    section_matches: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"terms": set(), "concepts": set()})
    for concept_id in concept_ids:
        concept = concept_by_id.get(concept_id, {})
        for occurrence_id in concept.get("occurrence_ids", []):
            occurrence = occurrence_by_id.get(occurrence_id)
            if not occurrence:
                continue
            matched_for_occurrence = [
                term for term in selected_terms
                if concept_id in terms.get(term, {}).get("concept_ids", [])
            ]
            for section_id in occurrence.get("section_ids", []):
                section_ids.add(section_id)
                section_matches[section_id]["terms"].update(matched_for_occurrence)
                section_matches[section_id]["concepts"].add(concept_id)
            for passage_id in occurrence.get("source_passage_ids", []):
                if passage_id not in passages:
                    continue
                hit = passage_hits.setdefault(passage_id, {
                    "source_passage_id": passage_id,
                    "matched_terms": [],
                    "concept_ids": [],
                    "occurrence_ids": [],
                    "source": passages[passage_id],
                })
                hit["matched_terms"] = unique(hit["matched_terms"] + matched_for_occurrence)
                hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
                hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
            for element_id in occurrence.get("source_element_ids", []):
                table = table_by_id.get(element_id)
                visual_id = element_id if element_id in visual_by_id else (table or {}).get("visual_id")
                if not visual_id or visual_id not in visual_by_id:
                    continue
                hit = visual_hits.setdefault(visual_id, {
                    "visual_id": visual_id,
                    "matched_terms": [],
                    "concept_ids": [],
                    "occurrence_ids": [],
                    "visual": visual_by_id[visual_id],
                })
                hit["matched_terms"] = unique(hit["matched_terms"] + matched_for_occurrence)
                hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
                hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])

    # Some course PDFs expose visual objects but do not link those objects to
    # keyword occurrences.  Resolve them through the matched source page so a
    # query can still return the visual's location/name without pretending its
    # contents were OCR-reconstructed.
    page_context: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"terms": set(), "concepts": set()})
    for hit in passage_hits.values():
        if is_bibliography_source(hit["source"]):
            continue
        for page_id in hit["source"].get("source_page_ids", []):
            page_context[page_id]["terms"].update(hit["matched_terms"])
            page_context[page_id]["concepts"].update(hit["concept_ids"])
    for visual_id, visual in visual_by_id.items():
        page_id = visual.get("source_page_id")
        if page_id not in page_context:
            continue
        hit = visual_hits.setdefault(visual_id, {
            "visual_id": visual_id,
            "matched_terms": [],
            "concept_ids": [],
            "occurrence_ids": [],
            "visual": visual,
        })
        hit["matched_terms"] = unique(hit["matched_terms"] + sorted(page_context[page_id]["terms"]))
        hit["concept_ids"] = unique(hit["concept_ids"] + sorted(page_context[page_id]["concepts"]))

    # Table OCR can contain terms that are not present in the surrounding
    # embedded slide text (for example age bands or blood-pressure thresholds).
    # Match query tokens directly against reconstructed table contents so the
    # table remains discoverable even without inventing concept IDs for it.
    query_table_tokens = [normalize(token) for token in TOKEN_RE.findall(query) if len(normalize(token)) >= 4]
    for table_id, table in table_by_id.items():
        table_text = normalize((table.get("content") or {}).get("text", ""))
        matched_table_terms = [token for token in query_table_tokens if token in table_text]
        if not matched_table_terms:
            continue
        visual_id = table.get("visual_id")
        if not visual_id or visual_id not in visual_by_id:
            continue
        hit = visual_hits.setdefault(visual_id, {
            "visual_id": visual_id,
            "matched_terms": [],
            "concept_ids": [],
            "occurrence_ids": [],
            "visual": visual_by_id[visual_id],
        })
        hit["matched_terms"] = unique(hit["matched_terms"] + matched_table_terms)
        hit["table_reconstruction"] = table

    for hit in passage_hits.values():
        searchable_context = " ".join([
            hit["source"].get("text", ""),
            " ".join(hit["source"].get("section_path", [])),
            hit["source"].get("document_title", ""),
        ])
        context_key = normalize(searchable_context)
        hit["relevance_score"] = sum(context_key.count(normalize(term)) for term in selected_terms if normalize(term))
        bibliography_slide = is_bibliography_source(hit["source"])
        hit["bibliography_slide"] = bibliography_slide
        if bibliography_slide:
            hit["relevance_score"] -= 100
    passage_candidates = sorted(
        passage_hits.values(),
        key=lambda hit: (-(len(hit["matched_terms"]) if not hit.get("bibliography_slide") else 0), -hit.get("relevance_score", 0), -len(hit["concept_ids"]), hit["source_passage_id"]),
    )[:limit]
    visual_candidates = sorted(
        visual_hits.values(),
        key=lambda hit: (-len(hit["matched_terms"]), -len(hit["concept_ids"]), hit["visual_id"]),
    )[:limit]
    for hit in visual_candidates:
        table_id = hit["visual"].get("table_id")
        if table_id and table_id in table_by_id:
            hit["table_reconstruction"] = table_by_id[table_id]

    summary_matches: list[dict[str, Any]] = []
    for section_id in section_ids:
        summary = summary_by_id.get(section_id)
        if not summary or not summary.get("summary"):
            continue
        summary_matches.append({
            **summary,
            "_match_score": len(section_matches[section_id]["terms"]),
            "_concept_score": len(section_matches[section_id]["concepts"]),
        })
    level_order = ["slide", "subsection", "major_section", "chapter", "part", "document", "course"]
    summary_matches.sort(key=lambda item: (-item["_match_score"], -item["_concept_score"], level_order.index(item.get("level", "course")) if item.get("level") in level_order else 99, item.get("unit_id", "")))
    summary_candidates = [{key: value for key, value in item.items() if not key.startswith("_")} for item in summary_matches[:limit]]
    section_candidates = sorted(
        [node_by_id[section_id] for section_id in section_ids if section_id in node_by_id],
        key=lambda node: (-len(section_matches[node["section_id"]]["terms"]), -len(section_matches[node["section_id"]]["concepts"]), node.get("section_id", "")),
    )[:limit]

    quotation_candidates = [formal_quotation(source_kind, hit["source"]) for hit in passage_candidates]
    visual_reference_candidates = [formal_visual_reference(source_kind, hit) for hit in visual_candidates]
    return {
        "source_tier": "primary_course_materials" if source_kind == "course_materials" else "supplemental_reference",
        "source_priority": 1 if source_kind == "course_materials" else 2,
        "book_id": term_index.get("book_id"),
        "matched_terms": selected_terms,
        "concept_candidates": [concept_by_id[concept_id] for concept_id in concept_ids if concept_id in concept_by_id][:limit],
        "section_candidates": section_candidates,
        "summary_candidates": summary_candidates,
        "source_passage_candidates": passage_candidates,
        "quotation_candidates": quotation_candidates,
        "visual_candidates": visual_candidates,
        "visual_reference_candidates": visual_reference_candidates,
        "counts": {
            "matched_terms": len(selected_terms),
            "concept_candidates": len(concept_ids),
            "passage_candidates": len(passage_candidates),
            "visual_candidates": len(visual_candidates),
            "summary_candidates": len(summary_candidates),
        },
        "status": "generated",
        "verification_status": "generated_not_verified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-terms", type=int, default=30)
    parser.add_argument("--course-index-root", type=Path, default=COURSE_INDEX)
    parser.add_argument("--davidson-index-root", type=Path, default=DAVIDSON_INDEX)
    args = parser.parse_args()

    course = search_source(
        "course_materials",
        args.course_index_root,
        COURSE_WIKI / "(4) Analysis/hhs4185_course_summaries_generated.json",
        args.query,
        args.term,
        args.limit,
        args.max_terms,
    )
    davidson = search_source(
        "davidson_supplement",
        args.davidson_index_root,
        DAVIDSON_INDEX / "davidson25_hierarchical_summaries_generated.json",
        args.query,
        args.term,
        args.limit,
        args.max_terms,
    )
    result = {
        "schema_version": "llm-wiki.combined-retrieval-packet.v1-hhs4185",
        "record_type": "combined_course_first_retrieval_packet",
        "query": args.query,
        "course_code": "HHS4185",
        "search_order": [
            {"source_tier": "primary_course_materials", "priority": 1, "instruction": "Use HHS4185 lectures, workshops and tutorials as the first source of course-specific evidence."},
            {"source_tier": "supplemental_reference", "priority": 2, "instruction": "Use Davidson's Principles and Practice of Medicine, 25th ed. only to supplement or clarify the course materials."},
        ],
        "course_materials": course,
        "supplemental_davidson": davidson,
        "formal_output_contract": {
            "schema_version": "hhs4185.formal-answer.v1",
            "required_sections": ["answer", "source_quotations", "references"],
            "answer_rule": "Answer from course_materials first; identify when Davidson is being used as supplementation.",
            "language_rule": "Use English-only derived course-material records. Preserve English bullet, arrow, line-break and indentation structure; use the raw bilingual layer only for provenance or when the user explicitly requests Chinese.",
            "quotation_rule": "Use returned quotation_candidates as source-extracted candidates and preserve their wording until manual source-image verification.",
            "reference_rule": "Course references use PDF filename and slide number; Davidson references use chapter and printed book page, retaining PDF page only for file navigation.",
            "summary_rule": "Use summaries for orientation; treat source passages and reconstructed tables as evidence candidates.",
            "visual_rule": "Use visual_reference_candidates for named/location metadata; use full table reconstructions only when returned; non-table visuals are metadata-only.",
            "verification_rule": "All generated text, visual interpretation, table reconstruction and quotations require manual checking against the source PDF page.",
        },
        "retrieval_policy": {
            "course_first": True,
            "supplemental_davidson": True,
            "course_language": "English-only derived records; raw bilingual extraction is retained for provenance only.",
            "point_form_structure": "Preserve English bullets, dots, arrows, line breaks and indentation metadata.",
            "summaries_are_context_only": True,
            "tables_return_full_reconstruction_when_available": True,
            "non_table_visuals_return_metadata_only": True,
            "claims_index": "not_created",
            "exact_quotation_requires_manual_verification": True,
        },
        "status": "generated",
        "verification_status": "generated_not_verified",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

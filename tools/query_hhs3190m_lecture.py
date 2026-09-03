#!/usr/bin/env python3
"""Return an agent-neutral retrieval packet for any HHS3190M deck."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


COURSE_CODE = "HHS3190M"
SOURCE_ID = "HHS3190M-L01-PHYSIOLOGY-2026-07"
STATUS = "generated_not_verified"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "sources/HHS3190M" / SOURCE_ID / "04 Retrieval Index"
DEFAULT_TEXT = ROOT / "sources/HHS3190M" / SOURCE_ID / "02 Text and Tables"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'/-]*")
QUERY_STOPWORDS = {
    "a", "an", "and", "are", "be", "by", "for", "from", "how", "in",
    "is", "of", "on", "or", "the", "to", "what", "when", "where", "which",
}
QUERY_GENERIC_TERMS = {"human", "body", "organ"}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def load_passages(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.expanduser().resolve().open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            passage_id = value.get("source_passage_id")
            if not passage_id:
                raise ValueError(f"missing source_passage_id at {path}:{line_number}")
            result[passage_id] = value
    return result


def choose_terms(query: str, explicit: list[str], available: dict[str, Any], maximum: int) -> list[str]:
    query_key = norm(query)
    query_tokens = {norm(token) for token in TOKEN_RE.findall(query) if len(norm(token)) >= 3 and norm(token) not in QUERY_STOPWORDS}
    specific_query_tokens = query_tokens - QUERY_GENERIC_TERMS
    candidates: list[tuple[int, int, str]] = []
    selected = {norm(term) for term in explicit if norm(term)}
    for key, info in available.items():
        forms = [key] + [norm(str(form)) for form in info.get("display_forms", [])]
        form_token_sets = [set(norm(token) for token in TOKEN_RE.findall(str(form))) for form in info.get("display_forms", [])]
        exact_query = key in query_tokens or key == query_key or any(form == query_key for form in forms)
        phrase_match = key in query_key or query_key in key
        overlap = max((len(query_tokens & form_tokens) for form_tokens in form_token_sets), default=0)
        minimum_overlap = 2 if len(query_tokens) >= 2 else 1
        if len(query_tokens) >= 2 and key in QUERY_GENERIC_TERMS:
            continue
        if len(query_tokens) >= 2 and overlap >= minimum_overlap and specific_query_tokens and not any(specific in form_tokens for form_tokens in form_token_sets for specific in specific_query_tokens):
            continue
        if exact_query or phrase_match or overlap >= minimum_overlap:
            specificity = max((len(form) for form in forms if form and (form in query_key or query_key in form)), default=0)
            candidates.append((2 if exact_query else (1 if phrase_match else 0), max(specificity, overlap * 10), key))
    for _, _, key in sorted(candidates, key=lambda item: (-item[0], -item[1], item[2]))[:maximum]:
        selected.add(key)
    return sorted(selected, key=lambda value: (-len(value), value))[:maximum]


def hit_score(hit: dict[str, Any]) -> tuple[int, int, int, str]:
    terms = hit.get("matched_terms", [])
    specificity = sum(min(len(term), 60) for term in terms)
    source = hit.get("source", {})
    source_text = norm(source.get("text", "")) if isinstance(source, dict) else norm(str(hit.get("visual", {}).get("name", "")))
    frequency = sum(source_text.count(term) for term in terms if term)
    longest = max((len(term) for term in terms), default=0)
    return specificity, frequency, longest, hit.get("source_passage_id", hit.get("visual_id", ""))


def formal_quote(passage: dict[str, Any]) -> dict[str, Any]:
    reference = (passage.get("source_pages") or [{}])[0]
    return {
        "evidence_id": f"{passage.get('source_passage_id')}-EVIDENCE",
        "quotation": passage.get("text", ""),
        "source_passage_id": passage.get("source_passage_id"),
        "source_page_ids": passage.get("source_page_ids", []),
        "reference": reference,
        "in_text_citation": f"({reference.get('formatted', 'HHS3190M Lecture 1')})",
        "quotation_status": "source_extracted_candidate",
        "verification_status": STATUS,
        "exact_quote_eligible": False,
        "manual_source_slide_check_required": True,
    }


def formal_visual(visual: dict[str, Any]) -> dict[str, Any]:
    reference = visual.get("page_reference", {})
    return {
        "visual_id": visual.get("visual_id"),
        "visual_type": visual.get("visual_type"),
        "name": visual.get("name"),
        "location": visual.get("location"),
        "reference": reference,
        "table_reconstruction_included": bool(visual.get("table_id")),
        "verification_status": STATUS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--source-id", default=SOURCE_ID, help="Registered HHS3190M source ID; defaults to Lecture 1.")
    parser.add_argument("--index-root", type=Path, help="Override the selected package's retrieval-index directory.")
    parser.add_argument("--text-root", type=Path, help="Override the selected package's text/table directory.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-terms", type=int, default=20)
    args = parser.parse_args()

    package_root = ROOT / "sources" / COURSE_CODE / args.source_id
    index = (args.index_root or package_root / "04 Retrieval Index").expanduser().resolve()
    text_root = (args.text_root or package_root / "02 Text and Tables").expanduser().resolve()
    term_index = load(index / "term_lookup.json")
    concept_index = load(index / "concept_index.json")
    occurrence_index = load(index / "occurrence_index.json")
    structure = load(index / "structure_lookup.json")
    visual_index = load(index / "visual_index.json")
    summaries = load(index / "hierarchical_summaries.json")
    formal_schema = load(index / "formal_output_schema.json")
    table_files = sorted(text_root.glob("*_tables_generated.json"))
    tables = {
        item["table_id"]: item
        for table_file in table_files
        for item in load(table_file).get("tables", [])
    }
    passages = load_passages(index / "passage_index.jsonl")

    terms = term_index.get("terms", {})
    selected_terms = choose_terms(args.query, args.term, terms, args.max_terms)
    concepts = {item.get("concept_id"): item for item in concept_index.get("concepts", [])}
    occurrences = {item.get("occurrence_id"): item for item in occurrence_index.get("occurrences", [])}
    nodes = {item.get("section_id"): item for item in structure.get("nodes", [])}
    visuals = {item.get("visual_id"): item for item in visual_index.get("visuals", [])}
    visual_id_by_table_id = {item.get("table_id"): item.get("visual_id") for item in visuals.values() if item.get("table_id")}
    summary_by_id = {item.get("unit_id"): item for item in summaries.get("units", [])}

    concept_ids = unique(concept_id for term in selected_terms for concept_id in terms.get(term, {}).get("concept_ids", []))
    occurrence_ids = unique(occurrence_id for concept_id in concept_ids for occurrence_id in concepts.get(concept_id, {}).get("occurrence_ids", []))
    passage_hits: dict[str, dict[str, Any]] = {}
    visual_hits: dict[str, dict[str, Any]] = {}
    section_matches: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"terms": set(), "concepts": set()})
    for occurrence_id in occurrence_ids:
        occurrence = occurrences.get(occurrence_id)
        if not occurrence:
            continue
        concept_id = occurrence.get("concept_id")
        matched = [term for term in selected_terms if concept_id in terms.get(term, {}).get("concept_ids", [])]
        for section_id in occurrence.get("section_ids", []):
            section_matches[section_id]["terms"].update(matched)
            section_matches[section_id]["concepts"].add(concept_id)
        for passage_id in occurrence.get("source_passage_ids", []):
            if passage_id not in passages:
                continue
            if "References" in passages[passage_id].get("section_path", []):
                continue
            hit = passage_hits.setdefault(passage_id, {"source_passage_id": passage_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "source": passages[passage_id]})
            hit["matched_terms"] = unique(hit["matched_terms"] + matched)
            hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
            hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
        for visual_id in occurrence.get("source_element_ids", []):
            visual_id = visual_id if visual_id in visuals else visual_id_by_table_id.get(visual_id)
            if visual_id not in visuals:
                continue
            hit = visual_hits.setdefault(visual_id, {"visual_id": visual_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "visual": visuals[visual_id]})
            hit["matched_terms"] = unique(hit["matched_terms"] + matched)
            hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
            hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])

    ranked_section_ids = sorted(
        section_matches,
        key=lambda key: (
            -sum(min(len(term), 60) for term in section_matches[key]["terms"]),
            -max((len(term) for term in section_matches[key]["terms"]), default=0),
            -len(section_matches[key]["concepts"]),
            key,
        ),
    )
    source_hits = sorted(passage_hits.values(), key=hit_score, reverse=True)[: args.limit]
    visual_hits_sorted = sorted(visual_hits.values(), key=hit_score, reverse=True)[: args.limit]
    summary_candidates = [summary_by_id[sid] for sid in ranked_section_ids if sid in summary_by_id and summary_by_id[sid].get("summary")][: args.limit]
    table_candidates = []
    seen_tables: set[str] = set()
    for hit in visual_hits_sorted:
        table_id = hit["visual"].get("table_id")
        if table_id and table_id in tables and table_id not in seen_tables:
            table_candidates.append(tables[table_id])
            seen_tables.add(table_id)

    result = {
        "schema_version": "llm-wiki.retrieval-packet.v1-lecture",
        "record_type": "retrieval_packet",
        "course_code": COURSE_CODE,
        "book_id": COURSE_CODE,
        "source_id": args.source_id,
        "query": args.query,
        "matched_terms": selected_terms,
        "concept_candidates": [concepts[concept_id] for concept_id in concept_ids if concept_id in concepts][: args.limit],
        "section_candidates": [nodes[section_id] for section_id in ranked_section_ids if section_id in nodes][: args.limit],
        "summary_candidates": summary_candidates,
        "source_passage_candidates": source_hits,
        "quotation_candidates": [formal_quote(hit["source"]) for hit in source_hits],
        "visual_candidates": visual_hits_sorted,
        "visual_reference_candidates": [formal_visual(hit["visual"]) for hit in visual_hits_sorted],
        "table_candidates": table_candidates,
        "formal_output_contract": formal_schema,
        "retrieval_policy": {
            "course_materials_priority": "This HHS3190M lecture is course evidence; consult supplemental sources only after course materials.",
            "term_matches_are_candidates": True,
            "source_passages_are_primary_evidence": True,
            "summaries_are_context_only": True,
            "tables_return_full_reconstruction_when_matched": True,
            "non_table_visuals_return_metadata_only": True,
            "exact_quotation_requires_manual_verification": True,
            "claims_index": "not_created",
        },
        "counts": {
            "matched_terms": len(selected_terms),
            "concept_candidates": len(concept_ids),
            "source_passage_candidates": len(source_hits),
            "visual_candidates": len(visual_hits_sorted),
            "table_candidates": len(table_candidates),
        },
        "status": "generated",
        "verification_status": STATUS,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

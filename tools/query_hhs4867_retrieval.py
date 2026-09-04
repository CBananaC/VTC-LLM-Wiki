#!/usr/bin/env python3
"""Query one or all processed HHS4867 presentation packages."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
COURSE_CODE = "HHS4867"
STATUS = "generated_not_verified"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'/-]*")
STOPWORDS = {"a", "an", "and", "are", "be", "by", "for", "from", "how", "in", "is", "of", "on", "or", "the", "to", "what", "when", "where", "which"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_passages(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            key = value.get("source_passage_id")
            if not key:
                raise ValueError(f"missing source_passage_id at {path}:{line_number}")
            result[key] = value
    return result


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def choose_terms(query: str, explicit: list[str], available: dict[str, Any], maximum: int) -> list[str]:
    query_key = norm(query)
    query_tokens = {norm(token) for token in TOKEN_RE.findall(query) if len(norm(token)) >= 3 and norm(token) not in STOPWORDS}
    selected = {norm(term) for term in explicit if norm(term)}
    candidates: list[tuple[int, int, str]] = []
    for key, info in available.items():
        forms = [key] + [norm(str(form)) for form in info.get("display_forms", [])]
        form_token_sets = [set(norm(token) for token in TOKEN_RE.findall(str(form))) for form in info.get("display_forms", [])]
        exact = key in query_tokens or key == query_key or query_key in forms
        phrase = key in query_key or query_key in key
        overlap = max((len(query_tokens & form_tokens) for form_tokens in form_token_sets), default=0)
        if exact or phrase or overlap >= (2 if len(query_tokens) >= 2 else 1):
            candidates.append((2 if exact else (1 if phrase else 0), max(len(key), overlap * 10), key))
    for _, _, key in sorted(candidates, key=lambda item: (-item[0], -item[1], item[2]))[:maximum]:
        selected.add(key)
    return sorted(selected, key=lambda value: (-len(value), value))[:maximum]


def hit_score(hit: dict[str, Any]) -> tuple[int, int, int, str]:
    terms = hit.get("matched_terms", [])
    source = hit.get("source") or hit.get("visual") or {}
    text = norm(str(source.get("text", "") if isinstance(source, dict) else source))
    return (
        sum(min(len(term), 60) for term in terms),
        sum(text.count(term) for term in terms if term),
        max((len(term) for term in terms), default=0),
        str(hit.get("source_passage_id", hit.get("visual_id", ""))),
    )


def formal_quote(passage: dict[str, Any]) -> dict[str, Any]:
    reference = (passage.get("source_pages") or [{}])[0]
    return {
        "evidence_id": f"{passage.get('source_passage_id')}-EVIDENCE",
        "quotation": passage.get("text", ""),
        "source_passage_id": passage.get("source_passage_id"),
        "source_page_ids": passage.get("source_page_ids", []),
        "reference": reference,
        "quotation_status": "source_extracted_candidate",
        "verification_status": STATUS,
        "exact_quote_eligible": False,
        "manual_source_slide_check_required": True,
    }


def formal_visual(visual: dict[str, Any]) -> dict[str, Any]:
    return {
        "visual_id": visual.get("visual_id"),
        "visual_type": visual.get("visual_type"),
        "name": visual.get("name"),
        "location": visual.get("location"),
        "reference": visual.get("page_reference"),
        "table_reconstruction_included": bool(visual.get("table_id")),
        "verification_status": STATUS,
    }


def package_from_registry(item: dict[str, Any]) -> Path:
    return ROOT / str(item["package_path"])


def query_package(item: dict[str, Any], query: str, explicit_terms: list[str], limit: int, max_terms: int) -> dict[str, Any]:
    package = package_from_registry(item)
    index = package / "04 Retrieval Index"
    text_root = package / "02 Text and Tables"
    term_index = load_json(index / "term_lookup.json")
    concept_index = load_json(index / "concept_index.json")
    occurrence_index = load_json(index / "occurrence_index.json")
    structure = load_json(index / "structure_lookup.json")
    visual_index = load_json(index / "visual_index.json")
    summaries = load_json(index / "hierarchical_summaries.json")
    formal_schema = load_json(index / "formal_output_schema.json")
    table_files = sorted(text_root.glob("*_tables_generated.json"))
    tables = {}
    for table_file in table_files:
        tables.update({value["table_id"]: value for value in load_json(table_file).get("tables", [])})
    passages = load_passages(index / "passage_index.jsonl")
    terms = term_index.get("terms", {})
    selected_terms = choose_terms(query, explicit_terms, terms, max_terms)
    concepts = {value.get("concept_id"): value for value in concept_index.get("concepts", [])}
    occurrences = {value.get("occurrence_id"): value for value in occurrence_index.get("occurrences", [])}
    nodes = {value.get("section_id"): value for value in structure.get("nodes", [])}
    visuals = {value.get("visual_id"): value for value in visual_index.get("visuals", [])}
    summary_by_id = {value.get("unit_id"): value for value in summaries.get("units", [])}
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
            hit = passage_hits.setdefault(passage_id, {"source_passage_id": passage_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "source": passages[passage_id]})
            hit["matched_terms"] = unique(hit["matched_terms"] + matched)
            hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
            hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
        for visual_id in occurrence.get("source_element_ids", []):
            if visual_id not in visuals:
                continue
            hit = visual_hits.setdefault(visual_id, {"visual_id": visual_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "visual": visuals[visual_id]})
            hit["matched_terms"] = unique(hit["matched_terms"] + matched)
            hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
            hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
    if not passage_hits:
        query_tokens = [norm(token) for token in TOKEN_RE.findall(query) if norm(token) not in STOPWORDS]
        for passage_id, passage in passages.items():
            passage_text = norm(str(passage.get("text", "")))
            matched = [token for token in query_tokens if token and token in passage_text]
            if matched:
                passage_hits[passage_id] = {"source_passage_id": passage_id, "matched_terms": matched, "concept_ids": [], "occurrence_ids": [], "source": passage, "match_method": "direct_passage_token_fallback"}
    ranked_section_ids = sorted(section_matches, key=lambda key: (-sum(min(len(term), 60) for term in section_matches[key]["terms"]), -len(section_matches[key]["concepts"]), key))
    source_hits = sorted(passage_hits.values(), key=hit_score, reverse=True)[:limit]
    visual_hits_sorted = sorted(visual_hits.values(), key=hit_score, reverse=True)[:limit]
    summary_candidates = [summary_by_id[sid] for sid in ranked_section_ids if sid in summary_by_id and summary_by_id[sid].get("summary")][:limit]
    table_candidates = []
    seen_tables: set[str] = set()
    for hit in visual_hits_sorted:
        table_id = hit["visual"].get("table_id")
        if table_id and table_id in tables and table_id not in seen_tables:
            table_candidates.append(tables[table_id])
            seen_tables.add(table_id)
    return {
        "schema_version": "llm-wiki.retrieval-packet.v1-hhs4867",
        "record_type": "retrieval_packet",
        "course_code": COURSE_CODE,
        "source_id": item.get("source_id"),
        "title": item.get("title"),
        "query": query,
        "matched_terms": selected_terms,
        "concept_candidates": [concepts[key] for key in concept_ids if key in concepts][:limit],
        "section_candidates": [nodes[key] for key in ranked_section_ids if key in nodes][:limit],
        "summary_candidates": summary_candidates,
        "source_passage_candidates": source_hits,
        "quotation_candidates": [formal_quote(hit["source"]) for hit in source_hits],
        "visual_candidates": visual_hits_sorted,
        "visual_reference_candidates": [formal_visual(hit["visual"]) for hit in visual_hits_sorted],
        "table_candidates": table_candidates,
        "formal_output_contract": formal_schema,
        "retrieval_policy": {"course_materials_priority": "This HHS4867 package is primary course evidence.", "term_matches_are_candidates": True, "source_passages_are_primary_evidence": True, "summaries_are_context_only": True, "tables_return_full_reconstruction_when_matched": True, "non_table_visuals_return_metadata_only": True, "exact_quotation_requires_manual_verification": True, "claims_index": "not_created"},
        "counts": {"matched_terms": len(selected_terms), "concept_candidates": len(concept_ids), "source_passage_candidates": len(source_hits), "visual_candidates": len(visual_hits_sorted), "table_candidates": len(table_candidates)},
        "status": "generated",
        "verification_status": STATUS,
    }


def main(default_source_id: str | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--source-id", default=default_source_id)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-terms", type=int, default=20)
    args = parser.parse_args()
    registry = load_json(ROOT / "source_registry.json")
    selected = [item for item in registry.get("sources", []) if item.get("course_code") == COURSE_CODE and item.get("retrieval_index_path")]
    if args.source_id:
        selected = [item for item in selected if item.get("source_id") == args.source_id]
    if not selected:
        raise SystemExit(f"No processed HHS4867 source package found for {args.source_id or 'course'}")
    packets = [query_package(item, args.query, args.term, args.limit, args.max_terms) for item in selected]
    if len(packets) == 1:
        print(json.dumps(packets[0], ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"schema_version": "vtc-hhs4867.course-retrieval-packet.v1", "record_type": "course_retrieval_packet", "course_code": COURSE_CODE, "query": args.query, "packets": packets, "status": "generated", "verification_status": STATUS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

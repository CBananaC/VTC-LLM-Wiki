#!/usr/bin/env python3
"""Return an agent-neutral retrieval packet for HHS4867 Lecture 1."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import query_hhs3190m_lecture as shared


COURSE_CODE = "HHS4867"
SOURCE_ID = "HHS4867-L01-MUSCULOSKELETAL-BASIS"
STATUS = "generated_not_verified"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "sources/HHS4867" / SOURCE_ID / "04 Retrieval Index"
DEFAULT_TEXT = ROOT / "sources/HHS4867" / SOURCE_ID / "02 Text and Tables"
TABLE_FILE = "hhs4867_l01_tables_generated.json"


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--index-root", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--text-root", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-terms", type=int, default=20)
    args = parser.parse_args()

    index = args.index_root.expanduser().resolve()
    text_root = args.text_root.expanduser().resolve()
    term_index = shared.load(index / "term_lookup.json")
    concept_index = shared.load(index / "concept_index.json")
    occurrence_index = shared.load(index / "occurrence_index.json")
    structure = shared.load(index / "structure_lookup.json")
    visual_index = shared.load(index / "visual_index.json")
    summaries = shared.load(index / "hierarchical_summaries.json")
    formal_schema = shared.load(index / "formal_output_schema.json")
    tables = {item["table_id"]: item for item in shared.load(text_root / TABLE_FILE).get("tables", [])}
    passages = shared.load_passages(index / "passage_index.jsonl")

    terms = term_index.get("terms", {})
    selected_terms = shared.choose_terms(args.query, args.term, terms, args.max_terms)
    concepts = {item.get("concept_id"): item for item in concept_index.get("concepts", [])}
    occurrences = {item.get("occurrence_id"): item for item in occurrence_index.get("occurrences", [])}
    nodes = {item.get("section_id"): item for item in structure.get("nodes", [])}
    visuals = {item.get("visual_id"): item for item in visual_index.get("visuals", [])}
    summary_by_id = {item.get("unit_id"): item for item in summaries.get("units", [])}

    concept_ids = unique([concept_id for term in selected_terms for concept_id in terms.get(term, {}).get("concept_ids", [])])
    occurrence_ids = unique([occurrence_id for concept_id in concept_ids for occurrence_id in concepts.get(concept_id, {}).get("occurrence_ids", [])])
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

    ranked_section_ids = sorted(section_matches, key=lambda key: (-sum(min(len(term), 60) for term in section_matches[key]["terms"]), -max((len(term) for term in section_matches[key]["terms"]), default=0), -len(section_matches[key]["concepts"]), key))
    source_hits = sorted(passage_hits.values(), key=shared.hit_score, reverse=True)[: args.limit]
    visual_hits_sorted = sorted(visual_hits.values(), key=shared.hit_score, reverse=True)[: args.limit]
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
        "source_id": SOURCE_ID,
        "query": args.query,
        "matched_terms": selected_terms,
        "concept_candidates": [concepts[concept_id] for concept_id in concept_ids if concept_id in concepts][: args.limit],
        "section_candidates": [nodes[section_id] for section_id in ranked_section_ids if section_id in nodes][: args.limit],
        "summary_candidates": summary_candidates,
        "source_passage_candidates": source_hits,
        "quotation_candidates": [shared.formal_quote(hit["source"]) for hit in source_hits],
        "visual_candidates": visual_hits_sorted,
        "visual_reference_candidates": [shared.formal_visual(hit["visual"]) for hit in visual_hits_sorted],
        "table_candidates": table_candidates,
        "formal_output_contract": formal_schema,
        "retrieval_policy": {
            "course_materials_priority": "This HHS4867 lecture is course evidence; consult supplemental sources only after course materials.",
            "term_matches_are_candidates": True,
            "source_passages_are_primary_evidence": True,
            "summaries_are_context_only": True,
            "tables_return_full_reconstruction_when_matched": True,
            "non_table_visuals_return_metadata_only": True,
            "exact_quotation_requires_manual_verification": True,
            "claims_index": "not_created",
        },
        "counts": {"matched_terms": len(selected_terms), "concept_candidates": len(concept_ids), "source_passage_candidates": len(source_hits), "visual_candidates": len(visual_hits_sorted), "table_candidates": len(table_candidates)},
        "status": "generated",
        "verification_status": STATUS,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

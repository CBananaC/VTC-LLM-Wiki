#!/usr/bin/env python3
"""Return an agent-neutral retrieval packet for the orthopedic-test book."""

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
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "sources/HHS4185/HHS4185-REF-ORTHO-SPECIAL-TESTS/04 Retrieval Index"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'/-]*")


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
            passage_id = value.get("passage_id")
            if not passage_id:
                raise ValueError(f"missing passage_id at {path}:{line_number}")
            result[passage_id] = value
    return result


def choose_terms(query: str, explicit: list[str], available: dict[str, Any], maximum: int) -> list[str]:
    query_key = norm(query)
    query_tokens = {norm(token) for token in TOKEN_RE.findall(query)}
    selected = {norm(term) for term in explicit if norm(term)}
    for term in available:
        if len(term) >= 4 and (term in query_key or term in query_tokens):
            selected.add(term)
    return sorted(selected, key=lambda value: (-len(value), value))[:maximum]


def prune_nested_terms(selected: list[str]) -> list[str]:
    """Drop generic nested tokens when a longer exact phrase is available."""
    result = []
    for term in selected:
        nested_in_longer = any(
            term != other and len(other) >= len(term) + 2 and term in other
            for other in selected
        )
        if not nested_in_longer:
            result.append(term)
    return result


def formal_quote(passage: dict[str, Any]) -> dict[str, Any]:
    reference = passage.get("reference", {})
    return {
        "evidence_id": f"{passage.get('passage_id')}-EVIDENCE",
        "quotation": passage.get("text", ""),
        "source_passage_id": passage.get("passage_id"),
        "source_page_ids": passage.get("source_page_ids", []),
        "reference": reference,
        "in_text_citation": f"({reference.get('formatted', 'Konin et al., Special Tests for Orthopedic Examination, 3rd ed.')})",
        "quotation_status": "source_extracted_candidate",
        "verification_status": STATUS,
        "exact_quote_eligible": False,
        "manual_source_image_check_required": True,
    }


def formal_visual(visual: dict[str, Any]) -> dict[str, Any]:
    printed_page = visual.get("printed_page")
    pdf_page = visual.get("pdf_page")
    chapter_number = visual.get("chapter_number")
    chapter_title = visual.get("chapter_title")
    reference = f"Konin et al., Special Tests for Orthopedic Examination, 3rd ed."
    if chapter_number is not None:
        reference += f", Section {chapter_number}: {chapter_title}"
    if printed_page is not None:
        reference += f", p. {printed_page} [PDF p. {pdf_page}]"
    return {"visual_id": visual.get("visual_id"), "visual_type": visual.get("visual_type"), "name": visual.get("name"), "test_title": visual.get("test_title"), "reference": {"formatted": reference, "page_number": printed_page, "pdf_page": pdf_page, "source_id": SOURCE_ID}, "table_reconstruction_included": bool(visual.get("table_id")), "verification_status": STATUS}


def hit_score(hit: dict[str, Any]) -> tuple[int, int, int, str]:
    """Prefer specific phrase/term matches over generic words such as 'test'."""
    terms = hit.get("matched_terms", [])
    specificity = sum(min(len(term), 40) for term in terms)
    longest = max((len(term) for term in terms), default=0)
    return (specificity, longest, len(terms), hit.get("source_passage_id", ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--index-root", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-terms", type=int, default=30)
    args = parser.parse_args()
    index = args.index_root.expanduser().resolve()
    term_index = load(index / "term_lookup.json")
    concept_index = load(index / "concept_index.json")
    occurrence_index = load(index / "occurrence_index.json")
    structure = load(index / "structure_lookup.json")
    visual_index = load(index / "visual_index.json")
    summaries = load(index / "hierarchical_summaries.json")
    passages = load_passages(index / "passage_index.jsonl")
    terms = term_index.get("terms", {})
    selected_terms = prune_nested_terms(choose_terms(args.query, args.term, terms, args.max_terms))
    concepts = {item.get("concept_id"): item for item in concept_index.get("concepts", [])}
    occurrences = {item.get("occurrence_id"): item for item in occurrence_index.get("occurrences", [])}
    nodes = {item.get("section_id"): item for item in structure.get("nodes", [])}
    visuals = {item.get("visual_id"): item for item in visual_index.get("visuals", [])}
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
            hit = passage_hits.setdefault(passage_id, {"source_passage_id": passage_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "source": passages[passage_id]})
            hit["matched_terms"] = unique(hit["matched_terms"] + matched)
            hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
            hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
        for element_id in occurrence.get("source_element_ids", []):
            if element_id not in visuals:
                continue
            hit = visual_hits.setdefault(element_id, {"visual_id": element_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "visual": visuals[element_id]})
            hit["matched_terms"] = unique(hit["matched_terms"] + matched)
            hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
            hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])

    # A named test is often indexed as a title-only occurrence. Expand that
    # matched major section to its actual text passages so an exact test-name
    # query returns evidence, not only the heading node.
    matched_test_sections = {
        section_id: sorted(values["terms"], key=lambda value: (-len(value), value))
        for section_id, values in section_matches.items()
        if nodes.get(section_id, {}).get("level") == "major_section"
    }
    for passage_id, passage in passages.items():
        test_id = passage.get("test_id")
        if test_id not in matched_test_sections:
            continue
        hit = passage_hits.setdefault(
            passage_id,
            {"source_passage_id": passage_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "source": passage},
        )
        hit["matched_terms"] = unique(hit["matched_terms"] + matched_test_sections[test_id])

    source_hits = sorted(passage_hits.values(), key=hit_score, reverse=True)[: args.limit]
    visual_hits_sorted = sorted(visual_hits.values(), key=lambda hit: (hit_score({**hit, "source_passage_id": hit["visual_id"]})), reverse=True)[: args.limit]
    ranked_section_ids = sorted(
        section_matches,
        key=lambda key: (
            -sum(min(len(term), 40) for term in section_matches[key]["terms"]),
            -max((len(term) for term in section_matches[key]["terms"]), default=0),
            -len(section_matches[key]["terms"]),
            -len(section_matches[key]["concepts"]),
            key,
        ),
    )
    section_candidates = [nodes[section_id] for section_id in ranked_section_ids if section_id in nodes][: args.limit]
    summary_candidates = []
    for level in ("subsection", "major_section", "chapter", "part"):
        matching = [summary_by_id[sid] for sid in ranked_section_ids if sid in summary_by_id and summary_by_id[sid].get("level") == level and summary_by_id[sid].get("summary")]
        summary_candidates.extend(matching[: max(1, args.limit // 4)])
    summary_candidates = summary_candidates[: args.limit]
    result = {
        "schema_version": "llm-wiki.retrieval-packet.v1-medical",
        "record_type": "retrieval_packet",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "query": args.query,
        "matched_terms": selected_terms,
        "concept_candidates": [concepts[concept_id] for concept_id in concept_ids if concept_id in concepts][: args.limit],
        "section_candidates": section_candidates,
        "summary_candidates": summary_candidates,
        "source_passage_candidates": source_hits,
        "quotation_candidates": [formal_quote(hit["source"]) for hit in source_hits if not hit["source"].get("is_synthetic") and hit["source"].get("component_kind") != "references"],
        "visual_candidates": visual_hits_sorted,
        "visual_reference_candidates": [formal_visual(hit["visual"]) for hit in visual_hits_sorted],
        "formal_output_contract": {"schema_version": "vtc-ortho3.formal-answer.v1", "required_sections": ["answer", "source_quotations", "references"], "citation_rule": "Support each material factual statement with returned source quotations and references.", "page_rule": "Use printed book page as p.; retain PDF p. for navigation.", "summary_rule": "Summaries are orientation only; source passages are the evidence.", "visual_rule": "Cite visual name/type/location; reconstruct contents only for returned tables.", "verification_rule": "Treat generated records as candidates until manual source-page review."},
        "retrieval_policy": {"course_materials_priority": "Search HHS4185 course materials first; this is a supplemental source.", "term_matches_are_candidates": True, "source_passages_are_primary_evidence": True, "summaries_are_context_only": True, "tables_return_full_reconstruction_when_matched": True, "non_table_visuals_return_metadata_only": True, "exact_quotation_requires_manual_verification": True, "claims_index": "not_created"},
        "status": "generated",
        "verification_status": STATUS,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

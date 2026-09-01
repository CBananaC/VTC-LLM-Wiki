#!/usr/bin/env python3
"""Return an agent-neutral Davidson retrieval packet as JSON.

The helper performs term lookup and source-link resolution only. Any AI can
consume the JSON packet; it must read the returned source passages and use the
section/visual metadata as context. No claims index or precomputed relationship
index is used.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from build_davidson_retrieval_index import TOKEN_RE, normalize


DEFAULT_WIKI_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX_ROOT = DEFAULT_WIKI_ROOT / "(6) Retrieval Index"
DEFAULT_TABLES = DEFAULT_WIKI_ROOT / "05 Visual Inventory/davidson25_tables_reconstructed_generated.json"
DEFAULT_SUMMARIES = DEFAULT_INDEX_ROOT / "davidson25_hierarchical_summaries_generated.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


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


def citation_for_page(page: dict[str, Any], section_path: list[str] | None = None) -> dict[str, Any]:
    """Create a human-readable citation with printed page as the main locator."""
    section_path = section_path or []
    chapter_number = page.get("chapter_number")
    chapter_title = page.get("chapter_title")
    if chapter_number is None and len(section_path) >= 2:
        chapter_title = chapter_title or section_path[1]
    if chapter_number is not None and chapter_title:
        chapter_label = f"Chapter {chapter_number}: {chapter_title}"
    elif chapter_title:
        chapter_label = str(chapter_title)
    elif chapter_number is not None:
        chapter_label = f"Chapter {chapter_number}"
    else:
        chapter_label = None
    printed_page = page.get("page_number", page.get("printed_page"))
    pdf_page = page.get("pdf_page")
    citation_parts = ["Davidson's Principles and Practice of Medicine, 25th ed."]
    if chapter_label:
        citation_parts.append(chapter_label)
    if printed_page is not None:
        citation_parts.append(f"p. {printed_page}")
    elif pdf_page is not None:
        citation_parts.append(f"PDF p. {pdf_page}")
    citation = ", ".join(citation_parts)
    if printed_page is not None and pdf_page is not None:
        citation += f" [PDF p. {pdf_page}]"
    short_parts = ["Davidson, 25th ed."]
    if chapter_number is not None:
        short_parts.append(f"Ch. {chapter_number}")
    if printed_page is not None:
        short_parts.append(f"p. {printed_page}")
    elif pdf_page is not None:
        short_parts.append(f"PDF p. {pdf_page}")
    return {
        "work_title": "Davidson's Principles and Practice of Medicine",
        "edition": "25th",
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "chapter_label": chapter_label,
        "page_number": printed_page,
        "page_number_type": "printed_book_page",
        "pdf_page": pdf_page,
        "source_page_id": page.get("source_page_id"),
        "section_path": section_path,
        "short_form": ", ".join(short_parts),
        "formatted": citation,
    }


def formal_quotation(source: dict[str, Any]) -> dict[str, Any]:
    pages = source.get("source_pages", [])
    page = pages[0] if pages else {}
    reference = citation_for_page(page, source.get("section_path", []))
    return {
        "evidence_id": f"DAV25-EVID-{source.get('source_passage_id', '')}",
        "quotation": source.get("text", ""),
        "quotation_source": "passage_index.jsonl",
        "source_passage_id": source.get("source_passage_id"),
        "source_page_ids": source.get("source_page_ids", []),
        "reference": reference,
        "in_text_citation": f"({reference['short_form']})",
        "quotation_status": "source_extracted_candidate",
        "verification_status": source.get("verification_status", "not_verified"),
        "manual_source_image_check_required": True,
    }


def formal_visual_reference(hit: dict[str, Any]) -> dict[str, Any]:
    visual = hit.get("visual", {})
    page = visual.get("page_reference", {
        "source_page_id": visual.get("source_page_id"),
        "pdf_page": visual.get("pdf_page"),
        "page_number": visual.get("page_number", visual.get("printed_page")),
        "printed_page": visual.get("printed_page"),
        "chapter_number": visual.get("chapter_number"),
        "chapter_title": visual.get("chapter_title"),
    })
    section_paths = visual.get("section_paths", [])
    reference = citation_for_page(page, section_paths[0] if section_paths else [])
    return {
        "visual_id": hit.get("visual_id"),
        "visual_type": visual.get("visual_type"),
        "name": visual.get("name"),
        "reference": reference,
        "table_reconstruction_included": "table_reconstruction" in hit,
        "verification_status": visual.get("verification_status", "not_verified"),
    }


def matched_terms(query: str, explicit_terms: list[str], available: dict[str, Any], limit: int) -> list[str]:
    query_key = normalize(query)
    query_tokens = {normalize(token) for token in TOKEN_RE.findall(query)}
    candidates = {normalize(term) for term in explicit_terms if normalize(term)}
    for term in available:
        # Avoid accidental cross-word matches (for example "sofa" inside a
        # normalized phrase) and ignore very short generic fragments. Exact
        # query tokens and longer phrases remain eligible for substring
        # matching so "amyloid" can still find "amyloidosis".
        if len(term) >= 5 and (term in query_tokens or term in query_key):
            candidates.add(term)
    return sorted(candidates, key=lambda term: (-len(term), term))[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--index-root", type=Path, default=DEFAULT_INDEX_ROOT)
    parser.add_argument("--tables", type=Path, default=DEFAULT_TABLES)
    parser.add_argument("--summaries", type=Path, default=DEFAULT_SUMMARIES)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-terms", type=int, default=30)
    args = parser.parse_args()

    root = args.index_root
    term_index = load_json(root / "term_lookup.json")
    concept_index = load_json(root / "concept_index.json")
    occurrence_index = load_json(root / "occurrence_index.json")
    structure = load_json(root / "structure_lookup.json")
    visual_index = load_json(root / "visual_index.json")
    summaries = load_json(args.summaries) if args.summaries.exists() else {"units": []}
    tables = load_json(args.tables) if args.tables.exists() else {"tables": []}
    passages = load_jsonl(root / "passage_index.jsonl")

    terms = term_index.get("terms", {})
    selected_terms = matched_terms(args.query, args.term, terms, args.max_terms)
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

    matched_occurrence_ids = unique(
        occurrence_id
        for concept_id in concept_ids
        for occurrence_id in concept_by_id.get(concept_id, {}).get("occurrence_ids", [])
    )
    selected_set = set(selected_terms)
    passage_hits: dict[str, dict[str, Any]] = {}
    visual_hits: dict[str, dict[str, Any]] = {}
    section_ids: set[str] = set()
    section_matches: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"terms": set(), "concepts": set()})
    for occurrence_id in matched_occurrence_ids:
        occurrence = occurrence_by_id.get(occurrence_id)
        if not occurrence:
            continue
        concept_id = occurrence.get("concept_id", "")
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
            if element_id in visual_by_id:
                visual = visual_by_id[element_id]
                hit = visual_hits.setdefault(element_id, {
                    "visual_id": element_id,
                    "matched_terms": [],
                    "concept_ids": [],
                    "occurrence_ids": [],
                    "visual": visual,
                })
                hit["matched_terms"] = unique(hit["matched_terms"] + matched_for_occurrence)
                hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
                hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
            elif element_id in table_by_id:
                visual_id = table_by_id[element_id].get("visual_id", element_id)
                visual = visual_by_id.get(visual_id, {"visual_id": visual_id, "table_id": element_id})
                hit = visual_hits.setdefault(visual_id, {
                    "visual_id": visual_id,
                    "matched_terms": [],
                    "concept_ids": [],
                    "occurrence_ids": [],
                    "visual": visual,
                })
                hit["matched_terms"] = unique(hit["matched_terms"] + matched_for_occurrence)
                hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
                hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])

    source_passage_candidates = sorted(
        passage_hits.values(),
        key=lambda hit: (-len(hit["matched_terms"]), -len(hit["concept_ids"]), hit["source_passage_id"]),
    )[: args.limit]
    visual_candidates = sorted(
        visual_hits.values(),
        key=lambda hit: (-len(hit["matched_terms"]), -len(hit["concept_ids"]), hit["visual_id"]),
    )[: args.limit]
    summary_candidates_all = [
        {
            **summary_by_id[section_id],
            "_match_score": len(section_matches[section_id]["terms"]),
            "_concept_score": len(section_matches[section_id]["concepts"]),
        }
        for section_id in sorted(section_ids)
        if section_id in summary_by_id and summary_by_id[section_id].get("summary")
    ]
    # Preserve the requested bottom-up context: return the most specific
    # summaries first, but reserve room for major-section, chapter, and Part
    # context instead of filling the whole limit with unrelated subsections.
    summary_by_level: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summary_candidates_all:
        summary_by_level[summary.get("level", "")].append(summary)
    for values in summary_by_level.values():
        values.sort(key=lambda item: (-item.get("_match_score", 0), -item.get("_concept_score", 0), item.get("unit_id", "")))
    level_order = ["subsection", "major_section", "chapter", "part"]
    per_level = max(1, args.limit // len(level_order))
    summary_candidates = [
        {key: value for key, value in summary.items() if not key.startswith("_")}
        for level in level_order
        for summary in summary_by_level.get(level, [])[:per_level]
    ][: args.limit]
    section_candidates = [
        node_by_id[section_id]
        for section_id in sorted(
            section_ids,
            key=lambda section_id: (
                -len(section_matches[section_id]["terms"]),
                -len(section_matches[section_id]["concepts"]),
                -len(node_by_id.get(section_id, {}).get("section_path", [])),
                section_id,
            ),
        )
        if section_id in node_by_id
    ]

    # Return full reconstructed table records only for matched table visuals;
    # non-table visuals remain metadata-only by policy.
    for hit in visual_candidates:
        table_id = hit["visual"].get("table_id")
        if table_id and table_id in table_by_id:
            hit["table_reconstruction"] = table_by_id[table_id]

    quotation_candidates = [formal_quotation(hit["source"]) for hit in source_passage_candidates]
    visual_reference_candidates = [formal_visual_reference(hit) for hit in visual_candidates]

    result = {
        "schema_version": "llm-wiki.retrieval-packet.v1-medical",
        "record_type": "retrieval_packet",
        "book_id": term_index.get("book_id"),
        "query": args.query,
        "matched_terms": selected_terms,
        "concept_candidates": [concept_by_id[concept_id] for concept_id in concept_ids if concept_id in concept_by_id][: args.limit],
        "section_candidates": section_candidates[: args.limit],
        "summary_candidates": summary_candidates,
        "source_passage_candidates": source_passage_candidates,
        "quotation_candidates": quotation_candidates,
        "visual_candidates": visual_candidates,
        "visual_reference_candidates": visual_reference_candidates,
        "formal_output_contract": {
            "schema_version": "davidson.formal-answer.v1",
            "required_sections": ["answer", "source_quotations", "references"],
            "citation_rule": "Support each material factual statement with one or more returned source quotations and its reference.",
            "page_rule": "Use the printed textbook page as p.; retain PDF p. only as a file-navigation cross-check.",
            "summary_rule": "Use summaries for orientation only; quotations and source passages are the evidence.",
            "visual_rule": "Cite visual names with chapter and printed page; use reconstructed table contents only when returned.",
            "verification_rule": "Treat quotations and references as generated candidates until the source page image is manually checked.",
        },
        "retrieval_policy": {
            "term_matches_are_candidates": True,
            "source_passages_are_primary_evidence": True,
            "summaries_are_context_only": True,
            "tables_return_full_reconstruction_when_matched": True,
            "non_table_visuals_return_metadata_only": True,
            "formal_quotations_returned": True,
            "printed_book_page_is_canonical_citation_page": True,
            "relationship_index": "not_created; judge relationships from the returned source context",
            "exact_quotation_requires_manual_verification": True,
        },
        "status": "generated",
        "verification_status": "not_verified",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

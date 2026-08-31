#!/usr/bin/env python3
"""Return an agent-neutral, source-first Stroke Rehabilitation retrieval packet."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX_ROOT = PROJECT_ROOT / "sources/HHS4185/HHS4185-REF-STROKE-REHAB-5E/04 Retrieval Index"
DEFAULT_TABLES = PROJECT_ROOT / "sources/HHS4185/HHS4185-REF-STROKE-REHAB-5E/02 Text and Tables/stroke_rehab_visual_locations_and_tables_full_generated.json"
DEFAULT_SUMMARIES = PROJECT_ROOT / "sources/HHS4185/HHS4185-REF-STROKE-REHAB-5E/03 Analysis/stroke_rehab_hierarchical_summaries_generated.json"
STATUS = "generated_not_verified"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[’'/-][A-Za-z0-9]+)*")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"Expected a JSON object: {path}")
    return value


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict) and row.get("source_passage_id"):
                rows[row["source_passage_id"]] = row
    return rows


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in text if character.isalnum())


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def unique(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(value for value in values if value not in (None, "")))


def matched_terms(query: str, explicit_terms: list[str], available: dict[str, Any], limit: int) -> list[str]:
    query_key = normalize(query)
    query_tokens = {normalize(token) for token in TOKEN_RE.findall(query)}
    meaningful_tokens = {token for token in query_tokens if len(token) >= 5}
    candidates = {normalize(term) for term in explicit_terms if normalize(term)}
    for term in available:
        # Exact query tokens are preferred.  Longer normalized phrases may
        # also match the compact query string; short substrings such as
        # ``past`` inside ``spasticity`` are deliberately excluded.
        phrase_match = len(meaningful_tokens) >= 2 and all(token in term for token in meaningful_tokens)
        if term in query_tokens or (len(term) >= 8 and term in query_key) or phrase_match:
            candidates.add(term)
    return sorted(candidates, key=lambda term: (-len(term), term))[:limit]


def reference_for_visual(visual: dict[str, Any]) -> dict[str, Any]:
    page = visual.get("page_reference") or {
        "source_page_id": visual.get("source_page_id"),
        "pdf_page": visual.get("pdf_page"),
        "page_number": visual.get("page_number", visual.get("printed_page")),
        "printed_page": visual.get("printed_page"),
        "chapter_number": visual.get("chapter_number"),
        "chapter_title": visual.get("chapter_title"),
        "part_title": visual.get("part_title"),
    }
    page_number = page.get("page_number")
    page_label = f"p. {page_number}" if page_number is not None else f"PDF p. {page.get('pdf_page')}"
    chapter_number = visual.get("chapter_number") or page.get("chapter_number")
    chapter_title = clean(visual.get("chapter_title")) or clean(page.get("chapter_title"))
    chapter_label = f"Chapter {chapter_number}" if chapter_number is not None else "Book visual"
    if chapter_title:
        chapter_label += f": {chapter_title}"
    unit_path = visual.get("section_paths") or []
    unit_label = f", {unit_path[0][-1]}" if unit_path and unit_path[0] else ""
    return {
        "source_id": "HHS4185-REF-STROKE-REHAB-5E",
        "work_title": "Stroke Rehabilitation: A Function-Based Approach",
        "edition": "5th",
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "page_number": page_number,
        "page_number_type": "printed_textbook_page" if page_number is not None else "pdf_navigation_page",
        "pdf_page": page.get("pdf_page", visual.get("pdf_page")),
        "source_page_id": page.get("source_page_id", visual.get("source_page_id")),
        "section_path": unit_path[0] if unit_path else [],
        "short_form": f"Gillen, Stroke Rehabilitation, 5th ed., {chapter_label}, {page_label}",
        "formatted": f"Gillen, Stroke Rehabilitation: A Function-Based Approach, Fifth Edition (2021), {chapter_label}{unit_label}, {page_label}",
        "location": visual.get("location"),
        "status": STATUS,
        "verification_status": STATUS,
    }


def formal_quotation(passage: dict[str, Any]) -> dict[str, Any]:
    reference = dict(passage.get("reference", {}))
    return {
        "evidence_id": f"{passage.get('source_passage_id')}-EVIDENCE",
        "quotation": passage.get("text", ""),
        "source_passage_id": passage.get("source_passage_id"),
        "reference": reference,
        "in_text_citation": f"({reference.get('short_form', 'Stroke Rehabilitation source')})",
        "quotation_status": "source_extracted_candidate",
        "verification_status": passage.get("verification_status", STATUS),
        "manual_source_image_check_required": True,
    }


def lexical_fallback(
    query: str,
    passages: dict[str, dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    limit: int,
) -> dict[str, dict[str, Any]]:
    tokens = [normalize(token) for token in TOKEN_RE.findall(query) if len(normalize(token)) >= 4]
    if not tokens:
        return existing
    for passage_id, passage in passages.items():
        if passage_id in existing:
            continue
        text_key = normalize(passage.get("text", ""))
        matched = [token for token in tokens if token in text_key]
        if matched:
            existing[passage_id] = {
                "source_passage_id": passage_id,
                "matched_terms": matched,
                "concept_ids": [],
                "occurrence_ids": [],
                "source": passage,
                "_lexical_score": len(matched),
            }
        if len(existing) >= limit * 8:
            break
    return existing


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
    concept_by_id = {item.get("concept_id"): item for item in concept_index.get("concepts", [])}
    occurrence_by_id = {item.get("occurrence_id"): item for item in occurrence_index.get("occurrences", [])}
    node_by_id = {item.get("section_id"): item for item in structure.get("nodes", [])}
    node_by_id.update({item.get("section_id"): item for item in structure.get("parts", [])})
    visual_by_id = {item.get("visual_id"): item for item in visual_index.get("visuals", [])}
    visual_by_table_id = {item.get("table_id"): item for item in visual_index.get("visuals", []) if item.get("table_id")}
    table_by_id = {item.get("table_id"): item for item in tables.get("tables", []) if item.get("table_id")}
    summary_by_id = {item.get("unit_id"): item for item in summaries.get("units", [])}

    concept_ids = unique(concept_id for term in selected_terms for concept_id in terms.get(term, {}).get("concept_ids", []))
    matched_occurrence_ids = unique(
        occurrence_id
        for concept_id in concept_ids
        for occurrence_id in concept_by_id.get(concept_id, {}).get("occurrence_ids", [])
    )
    passage_hits: dict[str, dict[str, Any]] = {}
    visual_hits: dict[str, dict[str, Any]] = {}
    section_ids: set[str] = set()
    section_matches: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"terms": set(), "concepts": set()})
    for occurrence_id in matched_occurrence_ids:
        occurrence = occurrence_by_id.get(occurrence_id)
        if not occurrence:
            continue
        concept_id = occurrence.get("concept_id", "")
        matched_for_occurrence = [term for term in selected_terms if concept_id in terms.get(term, {}).get("concept_ids", [])]
        for section_id in occurrence.get("section_ids", []):
            section_ids.add(section_id)
            section_matches[section_id]["terms"].update(matched_for_occurrence)
            section_matches[section_id]["concepts"].add(concept_id)
        for passage_id in occurrence.get("source_passage_ids", []):
            if passage_id not in passages:
                continue
            hit = passage_hits.setdefault(passage_id, {"source_passage_id": passage_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "source": passages[passage_id]})
            hit["matched_terms"] = unique(hit["matched_terms"] + matched_for_occurrence)
            hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
            hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
            for section_id in passages[passage_id].get("section_ids", []):
                section_ids.add(section_id)
                section_matches[section_id]["terms"].update(matched_for_occurrence)
                section_matches[section_id]["concepts"].add(concept_id)
        for element_id in occurrence.get("source_element_ids", []):
            visual = visual_by_id.get(element_id) or visual_by_table_id.get(element_id)
            if not visual:
                continue
            visual_id = visual.get("visual_id")
            hit = visual_hits.setdefault(visual_id, {"visual_id": visual_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "visual": visual})
            hit["matched_terms"] = unique(hit["matched_terms"] + matched_for_occurrence)
            hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
            hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
            for section_id in visual.get("section_ids", []):
                section_ids.add(section_id)
                section_matches[section_id]["terms"].update(matched_for_occurrence)
                section_matches[section_id]["concepts"].add(concept_id)

    passage_hits = lexical_fallback(args.query, passages, passage_hits, args.limit)
    source_passage_candidates = sorted(
        passage_hits.values(),
        key=lambda hit: (-len(hit.get("matched_terms", [])), -len(hit.get("concept_ids", [])), hit["source_passage_id"]),
    )[: args.limit]
    for hit in source_passage_candidates:
        for section_id in hit["source"].get("section_ids", []):
            section_ids.add(section_id)
            section_matches[section_id]["terms"].update(hit.get("matched_terms", []))

    # Visual names and captions are indexed separately from source passages.
    # This fallback makes a query such as "Modifiable and Nonmodifiable Risks"
    # find the named table even when the table title was indexed as one phrase.
    query_visual_tokens = [normalize(token) for token in TOKEN_RE.findall(args.query) if len(normalize(token)) >= 5]
    for visual_id, visual in visual_by_id.items():
        if visual_id in visual_hits:
            continue
        visual_text = normalize(" ".join(str(value or "") for value in (visual.get("name"), visual.get("caption"))))
        matched_visual_tokens = [token for token in query_visual_tokens if token in visual_text]
        if len(matched_visual_tokens) >= 2 or (len(query_visual_tokens) == 1 and matched_visual_tokens):
            visual_hits[visual_id] = {
                "visual_id": visual_id,
                "matched_terms": matched_visual_tokens,
                "concept_ids": [],
                "occurrence_ids": [],
                "visual": visual,
            }
            for section_id in visual.get("section_ids", []):
                section_ids.add(section_id)
                section_matches[section_id]["terms"].update(matched_visual_tokens)

    visual_candidates = sorted(
        visual_hits.values(),
        key=lambda hit: (-len(hit["matched_terms"]), -len(hit["concept_ids"]), hit["visual_id"]),
    )[: args.limit]
    for hit in visual_candidates:
        table_id = hit["visual"].get("table_id")
        if table_id and table_id in table_by_id:
            hit["table_reconstruction"] = table_by_id[table_id]

    summary_candidates_all = []
    for section_id in section_ids:
        summary = summary_by_id.get(section_id)
        if not summary or not summary.get("summary"):
            continue
        summary_candidates_all.append({
            **summary,
            "_match_score": len(section_matches[section_id]["terms"]),
            "_concept_score": len(section_matches[section_id]["concepts"]),
        })
    by_level: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summary_candidates_all:
        by_level[summary.get("level", "")].append(summary)
    for values in by_level.values():
        values.sort(key=lambda item: (-item.get("_match_score", 0), -item.get("_concept_score", 0), item.get("unit_id", "")))
    per_level = max(1, args.limit // 4)
    summary_candidates = [
        {key: value for key, value in summary.items() if not key.startswith("_")}
        for level in ["subsection", "major_section", "chapter", "part"]
        for summary in by_level.get(level, [])[:per_level]
    ][: args.limit]
    section_candidates = [
        node_by_id[section_id]
        for section_id in sorted(
            section_ids,
            key=lambda section_id: (-len(section_matches[section_id]["terms"]), -len(section_matches[section_id]["concepts"]), -len(node_by_id.get(section_id, {}).get("section_path", [])), section_id),
        )
        if section_id in node_by_id
    ][: args.limit]

    result = {
        "schema_version": "llm-wiki.retrieval-packet.v1-medical",
        "record_type": "retrieval_packet",
        "source_id": "HHS4185-REF-STROKE-REHAB-5E",
        "course_code": "HHS4185",
        "course_title": "Common Rehabilitation Conditions",
        "source_role": "additional_source",
        "book_id": term_index.get("book_id"),
        "query": args.query,
        "matched_terms": selected_terms,
        "concept_candidates": [concept_by_id[concept_id] for concept_id in concept_ids if concept_id in concept_by_id][: args.limit],
        "section_candidates": section_candidates,
        "summary_candidates": summary_candidates,
        "source_passage_candidates": source_passage_candidates,
        "quotation_candidates": [formal_quotation(hit["source"]) for hit in source_passage_candidates],
        "visual_candidates": visual_candidates,
        "visual_reference_candidates": [
            {
                "visual_id": hit["visual_id"],
                "visual_type": hit["visual"].get("visual_type"),
                "name": hit["visual"].get("name"),
                "reference": reference_for_visual(hit["visual"]),
                "table_reconstruction_included": "table_reconstruction" in hit,
                "verification_status": hit["visual"].get("verification_status", STATUS),
            }
            for hit in visual_candidates
        ],
        "formal_output_contract": {
            "schema_version": "stroke-rehabilitation.formal-answer.v1",
            "required_sections": ["answer", "source_quotations", "references"],
            "citation_rule": "Support each material factual statement with one or more returned source quotations and its reference.",
            "page_rule": "Use the printed textbook page as p.; retain PDF p. only as a file-navigation cross-check.",
            "summary_rule": "Use summaries for orientation only; quotations and source passages are the evidence.",
            "visual_rule": "Cite visual names or labels with chapter, printed page, and location; use reconstructed contents only for tables.",
            "verification_rule": "Treat quotations and references as generated candidates until the source page image is manually checked.",
        },
        "retrieval_policy": {
            "course_materials_priority": "This is an HHS4185 additional source. Search HHS4185 course materials first and use this book to supplement or clarify.",
            "term_matches_are_candidates": True,
            "source_passages_are_primary_evidence": True,
            "summaries_are_context_only": True,
            "tables_return_full_reconstruction_when_matched": True,
            "non_table_visuals_return_metadata_only": True,
            "formal_quotations_returned": True,
            "printed_book_page_is_canonical_citation_page": True,
            "relationship_index": "not_created; judge relationships from returned source context",
            "exact_quotation_requires_manual_verification": True,
        },
        "status": "generated",
        "verification_status": STATUS,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

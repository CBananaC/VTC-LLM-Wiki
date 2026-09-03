#!/usr/bin/env python3
"""Query one standalone HHS4185 PDF source package.

The helper is intentionally source-local: it returns only the selected
package's English-derived passages, visual locations, reconstructed tables,
summaries, and formal citation candidates. The project router can combine
this packet with the aggregate course package and supplemental sources while
keeping each source's provenance separate.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'/-]{2,}|[\u3400-\u9fff]{2,}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        passage_id = record.get("source_passage_id")
        if not passage_id:
            raise SystemExit(f"missing source_passage_id at {path}:{line_number}")
        records[passage_id] = record
    return records


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", value.casefold())


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def select_terms(query: str, explicit_terms: list[str], terms: dict[str, Any], limit: int) -> list[str]:
    query_key = normalize(query)
    query_tokens = {normalize(token) for token in TOKEN_RE.findall(query)}
    selected: dict[str, str] = {}
    for term in explicit_terms:
        key = normalize(term)
        if key:
            selected[key] = term
    for key, value in terms.items():
        if not key or not (key in query_key or key in query_tokens or any(token in key for token in query_tokens if len(token) >= 4)):
            continue
        display = (value.get("display_forms") or [key])[0]
        selected.setdefault(key, display)
    return [selected[key] for key in sorted(selected, key=lambda item: (-len(item), item))[:limit]]


def formal_reference(passage: dict[str, Any]) -> dict[str, Any]:
    pages = passage.get("source_pages") or []
    page = pages[0] if pages else {}
    source_file = page.get("source_file") or passage.get("source_file")
    slide = page.get("slide_number", page.get("page_number"))
    pdf_page = page.get("pdf_page", slide)
    return {
        "source_page_id": page.get("source_page_id") or (passage.get("source_page_ids") or [None])[0],
        "source_file": source_file,
        "document_id": passage.get("document_id"),
        "document_title": passage.get("document_title"),
        "page_number": page.get("page_number", slide),
        "page_number_type": "slide_number",
        "slide_number": slide,
        "pdf_page": pdf_page,
        "section_path": passage.get("section_path", []),
        "short_form": f"HHS4185, {source_file}, slide {slide}",
        "formatted": f"HHS4185, {source_file}, slide {slide} (PDF p. {pdf_page})",
    }


def quotation_candidate(passage: dict[str, Any]) -> dict[str, Any]:
    reference = formal_reference(passage)
    return {
        "evidence_id": f"HHS4185-SOURCE-EVID-{passage.get('source_passage_id')}",
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


def visual_reference(hit: dict[str, Any], table_by_id: dict[str, Any]) -> dict[str, Any]:
    visual = hit["visual"]
    result = {
        "visual_id": hit["visual_id"],
        "visual_type": visual.get("visual_type"),
        "name": visual.get("name"),
        "location": visual.get("location"),
        "policy": visual.get("policy"),
        "matched_terms": hit.get("matched_terms", []),
        "reference": {
            "source_page_id": visual.get("source_page_id"),
            "source_file": visual.get("source_file"),
            "slide_number": visual.get("slide_number"),
            "pdf_page": visual.get("pdf_page"),
            "page_number_type": "slide_number",
            "formatted": f"HHS4185, {visual.get('source_file')}, slide {visual.get('slide_number')} (PDF p. {visual.get('pdf_page')})",
        },
        "table_reconstruction_included": bool(visual.get("table_id") and visual.get("table_id") in table_by_id and visual.get("table_reconstruction_available")),
        "table_reconstruction_status": visual.get("table_reconstruction_status"),
        "verification_status": visual.get("verification_status", "generated_not_verified"),
    }
    table_id = visual.get("table_id")
    if table_id and table_id in table_by_id and visual.get("table_reconstruction_available"):
        result["table_reconstruction"] = table_by_id[table_id]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-terms", type=int, default=30)
    args = parser.parse_args()
    package_root = args.package_root.resolve()
    index_root = package_root / "04 Retrieval Index"
    term_index = load_json(index_root / "term_lookup.json")
    concept_index = load_json(index_root / "concept_index.json")
    occurrence_index = load_json(index_root / "occurrence_index.json")
    structure = load_json(index_root / "structure_lookup.json")
    visual_index = load_json(index_root / "visual_index.json")
    summaries = load_json(package_root / "03 Analysis/hierarchical_summaries_generated.json")
    tables = load_json(package_root / "02 Text and Tables/tables_reconstructed_generated.json")
    passages = load_jsonl(index_root / "passage_index.jsonl")

    source_id = term_index.get("source_id") or package_root.name
    terms = term_index.get("terms", {})
    selected_terms = select_terms(args.query, args.term, terms, args.max_terms)
    selected_keys = {normalize(term) for term in selected_terms}
    concept_by_id = {item.get("concept_id"): item for item in concept_index.get("concepts", [])}
    occurrence_by_id = {item.get("occurrence_id"): item for item in occurrence_index.get("occurrences", [])}
    visual_by_id = {item.get("visual_id"): item for item in visual_index.get("visuals", [])}
    table_by_id = {item.get("table_id"): item for item in tables.get("tables", [])}
    node_by_id = {item.get("section_id"): item for item in structure.get("nodes", [])}
    summary_by_id = {item.get("unit_id"): item for item in summaries.get("units", [])}

    concept_ids: list[str] = []
    for key in selected_keys:
        concept_ids.extend(terms.get(key, {}).get("concept_ids", []))
    concept_ids = unique(concept_ids)
    passage_hits: dict[str, dict[str, Any]] = {}
    visual_hits: dict[str, dict[str, Any]] = {}
    section_ids: set[str] = set()
    page_context: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"terms": set(), "concepts": set()})

    for concept_id in concept_ids:
        concept = concept_by_id.get(concept_id, {})
        for occurrence_id in concept.get("occurrence_ids", []):
            occurrence = occurrence_by_id.get(occurrence_id, {})
            matched = [term for term in selected_terms if concept_id in terms.get(normalize(term), {}).get("concept_ids", [])]
            section_ids.update(occurrence.get("section_ids", []))
            for passage_id in occurrence.get("source_passage_ids", []):
                if passage_id not in passages:
                    continue
                hit = passage_hits.setdefault(passage_id, {"source_passage_id": passage_id, "matched_terms": [], "concept_ids": [], "occurrence_ids": [], "source": passages[passage_id]})
                hit["matched_terms"] = unique(hit["matched_terms"] + matched)
                hit["concept_ids"] = unique(hit["concept_ids"] + [concept_id])
                hit["occurrence_ids"] = unique(hit["occurrence_ids"] + [occurrence_id])
                for page_id in passages[passage_id].get("source_page_ids", []):
                    page_context[page_id]["terms"].update(matched)
                    page_context[page_id]["concepts"].add(concept_id)

    # Return all visual locations on matched pages, even when the visual has
    # no searchable text of its own. Table contents are additionally searched
    # directly because a table may contain the query term but no page text.
    for visual_id, visual in visual_by_id.items():
        page_id = visual.get("source_page_id")
        if page_id not in page_context:
            continue
        visual_hits[visual_id] = {"visual_id": visual_id, "matched_terms": sorted(page_context[page_id]["terms"]), "concept_ids": sorted(page_context[page_id]["concepts"]), "visual": visual}
    query_tokens = [normalize(token) for token in TOKEN_RE.findall(args.query) if len(normalize(token)) >= 4]
    for table_id, table in table_by_id.items():
        table_text = normalize((table.get("content") or {}).get("text", ""))
        matches = [token for token in query_tokens if token in table_text]
        visual_id = table.get("visual_id")
        if matches and visual_id in visual_by_id:
            visual_hits.setdefault(visual_id, {"visual_id": visual_id, "matched_terms": [], "concept_ids": [], "visual": visual_by_id[visual_id]})
            visual_hits[visual_id]["matched_terms"] = unique(visual_hits[visual_id]["matched_terms"] + matches)
            visual_hits[visual_id]["table_reconstruction"] = table

    for hit in passage_hits.values():
        text = hit["source"].get("text", "")
        context = normalize(" ".join([text, " ".join(hit["source"].get("section_path", [])), hit["source"].get("document_title", "")]))
        hit["relevance_score"] = sum(context.count(normalize(term)) for term in selected_terms if normalize(term))
    passage_candidates = sorted(passage_hits.values(), key=lambda hit: (-len(hit["matched_terms"]), -hit.get("relevance_score", 0), hit["source_passage_id"]))[: args.limit]
    visual_candidates = sorted(visual_hits.values(), key=lambda hit: (-len(hit.get("matched_terms", [])), hit["visual_id"]))[: args.limit]
    summary_candidates = [summary_by_id[section_id] for section_id in section_ids if section_id in summary_by_id and summary_by_id[section_id].get("summary")]
    summary_candidates.sort(key=lambda item: (-(len(item.get("source_page_ids", []))), item.get("unit_id", "")))
    section_candidates = [node_by_id[section_id] for section_id in section_ids if section_id in node_by_id]
    section_candidates.sort(key=lambda item: item.get("section_id", ""))

    result = {
        "schema_version": "vtc-llm-wiki.source-retrieval-packet.v1",
        "record_type": "source_retrieval_packet",
        "source_id": source_id,
        "source_tier": "primary_course_materials",
        "source_priority": 1,
        "query": args.query,
        "matched_terms": selected_terms,
        "concept_candidates": [concept_by_id[concept_id] for concept_id in concept_ids if concept_id in concept_by_id][: args.limit],
        "section_candidates": section_candidates[: args.limit],
        "summary_candidates": summary_candidates[: args.limit],
        "source_passage_candidates": [{**hit, "source": hit["source"]} for hit in passage_candidates],
        "quotation_candidates": [quotation_candidate(hit["source"]) for hit in passage_candidates],
        "visual_candidates": visual_candidates,
        "visual_reference_candidates": [visual_reference(hit, table_by_id) for hit in visual_candidates],
        "counts": {
            "matched_terms": len(selected_terms),
            "concept_candidates": len(concept_ids),
            "passage_candidates": len(passage_candidates),
            "visual_candidates": len(visual_candidates),
            "summary_candidates": len(summary_candidates),
        },
        "status": "generated",
        "verification_status": "generated_not_verified",
        "consumer_instruction": "Read returned source passages and inspect referenced visual/table records before answering. Cite the formal reference and manually verify exact quotations against the original PDF page.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

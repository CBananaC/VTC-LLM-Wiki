#!/usr/bin/env python3
"""Generate Davidson's source-linked keyword extraction and summaries.

This is the analysis stage that must precede retrieval-index construction.
It deliberately follows the requested direction:

    Subsection -> Major section -> Chapter -> Part

Keywords are extracted only at the lowest available textual unit (each
subsection, or a major section without subsections). Parent units aggregate
the lower-level keyword record IDs. Summaries are extractive, source-grounded
candidates assembled from the lowest unit upward; they are not presented as
verified medical advice or as a substitute for reading the source passage.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from build_davidson_retrieval_index import (
    CATEGORY_LABELS,
    STATUS,
    TOKEN_RE,
    all_texts,
    alias_variants,
    build_hierarchy,
    build_page_map,
    clean_text,
    display_form,
    load_json,
    sentence_excerpt,
    token_candidates,
    visual_records,
    normalize,
)


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def split_sentences(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    pieces = re.split(r"(?<=[.!?])\s+", cleaned)
    return [piece.strip() for piece in pieces if len(piece.strip()) >= 45]


def extractive_summary(title: str, texts: list[str], max_sentences: int) -> tuple[str, list[str]]:
    sentences: list[str] = []
    for text in texts:
        for sentence in split_sentences(text):
            if sentence not in sentences:
                sentences.append(sentence)
            if len(sentences) >= max_sentences:
                break
        if len(sentences) >= max_sentences:
            break
    if not sentences:
        return "", []
    return " ".join(sentences), sentences


def source_page_ids(paragraph_ids: list[str], paragraph_by_id: dict[str, dict[str, Any]]) -> list[str]:
    return unique(
        page_id
        for paragraph_id in paragraph_ids
        for page_id in paragraph_by_id.get(paragraph_id, {}).get("source_page_ids", [])
    )


def make_keyword_records(
    extraction: dict[str, Any],
    visual_manifest: dict[str, Any],
    tables: dict[str, Any],
    all_nodes: dict[str, dict[str, Any]],
    paragraph_to_ancestors: dict[str, list[str]],
    visual_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]], dict[str, list[str]]]:
    global_counts = Counter()
    for text in all_texts(extraction, visual_manifest, tables):
        for token in TOKEN_RE.findall(text):
            value = normalize(token)
            if value:
                global_counts[value] += 1

    paragraph_by_id = {paragraph.get("paragraph_id"): paragraph for paragraph in extraction.get("paragraphs", [])}
    paragraph_extractions: list[dict[str, Any]] = []
    section_keyword_records: list[dict[str, Any]] = []
    visual_extractions: list[dict[str, Any]] = []
    keyword_ids_by_node: dict[str, list[str]] = defaultdict(list)
    visual_keyword_ids_by_visual: dict[str, list[str]] = defaultdict(list)

    for paragraph in extraction.get("paragraphs", []):
        paragraph_id = paragraph.get("paragraph_id")
        if not paragraph_id:
            continue
        local = token_candidates(paragraph.get("text", ""), global_counts, source_kind="paragraph")
        records: list[dict[str, Any]] = []
        for local_index, ((category, term_key), forms) in enumerate(sorted(local.items()), 1):
            source_form = display_form(forms, term_key)
            record_id = f"DAV25-KW-{paragraph_id}-{local_index:03d}"
            retrieval_terms = unique(alias for value in [source_form] for alias in alias_variants(value))
            record = {
                "record_id": record_id,
                "category": category,
                "broad_area": CATEGORY_LABELS.get(category, category),
                "small_area": source_form,
                "keyword_path": [CATEGORY_LABELS.get(category, category), source_form],
                "source_form": source_form,
                "canonical_candidate": source_form,
                "retrieval_terms": retrieval_terms,
                "status": STATUS,
                "verification_status": STATUS,
            }
            records.append(record)
            for node_id in paragraph_to_ancestors.get(paragraph_id, []):
                keyword_ids_by_node[node_id].append(record_id)
        paragraph_extractions.append({
            "source_passage_ids": [paragraph_id],
            "source_page_ids": paragraph.get("source_page_ids", []),
            "section_ids": paragraph_to_ancestors.get(paragraph_id, []),
            "keyword_records": records,
            "keyword_record_count": len(records),
            "status": STATUS,
            "verification_status": STATUS,
        })

    # Headings are retrieval anchors, but they are kept separate from
    # paragraph-level keyword extraction so parent summaries never re-extract
    # their child prose.
    for node in all_nodes.values():
        title = clean_text(node.get("title", ""))
        if not title:
            continue
        node_id = node["section_id"]
        ancestors: list[str] = []
        cursor: dict[str, Any] | None = node
        while cursor:
            ancestors.append(cursor["section_id"])
            cursor = all_nodes.get(cursor.get("parent_id"))
        record_id = f"DAV25-KW-{node_id}-TITLE"
        section_keyword_records.append({
            "record_id": record_id,
            "category": "section_topics",
            "broad_area": CATEGORY_LABELS["section_topics"],
            "small_area": title,
            "keyword_path": [CATEGORY_LABELS["section_topics"], title],
            "source_form": title,
            "canonical_candidate": title,
            "retrieval_terms": alias_variants(title),
            "source_element_ids": [node_id],
            "section_ids": ancestors,
            "status": STATUS,
            "verification_status": STATUS,
        })
        for ancestor_id in ancestors:
            keyword_ids_by_node[ancestor_id].append(record_id)

    table_by_id = {table.get("table_id"): table for table in tables.get("tables", [])}
    for visual in visual_by_id.values():
        table = table_by_id.get(visual.get("table_id"))
        content = table.get("content", {}) if table else {}
        visual_text = clean_text(" ".join(value for value in (visual.get("name"), visual.get("caption"), content.get("text")) if value))
        local = token_candidates(visual_text, global_counts, source_kind="visual")
        for local_index, ((category, term_key), forms) in enumerate(sorted(local.items()), 1):
            source_form = display_form(forms, term_key)
            record_id = f"DAV25-KW-{visual['visual_id']}-{local_index:03d}"
            visual_record = {
                "record_id": record_id,
                "source_element_id": visual["visual_id"],
                "table_id": visual.get("table_id"),
                "category": category,
                "broad_area": CATEGORY_LABELS["visuals"],
                "small_area": source_form,
                "keyword_path": [CATEGORY_LABELS["visuals"], source_form],
                "source_form": source_form,
                "canonical_candidate": source_form,
                "retrieval_terms": unique(alias for value in [source_form] for alias in alias_variants(value)),
                "status": STATUS,
                "verification_status": STATUS,
            }
            visual_extractions.append(visual_record)
            visual_keyword_ids_by_visual[visual["visual_id"]].append(record_id)
            for node_id in visual.get("section_ids", []):
                keyword_ids_by_node[node_id].append(record_id)

    for node_id in keyword_ids_by_node:
        keyword_ids_by_node[node_id] = unique(keyword_ids_by_node[node_id])
    return paragraph_extractions, visual_extractions, keyword_ids_by_node, visual_keyword_ids_by_visual


def build_summaries(
    structure: dict[str, Any],
    all_nodes: dict[str, dict[str, Any]],
    paragraph_by_id: dict[str, dict[str, Any]],
    keyword_ids_by_node: dict[str, list[str]],
) -> dict[str, Any]:
    node_by_id = all_nodes
    summaries: dict[str, dict[str, Any]] = {}
    # Leaf units are processed from source paragraphs. Parent units only use
    # already-created child summaries, which implements the requested merge.
    leaves = [
        node for node in all_nodes.values()
        if node.get("level") == "subsection"
        or (node.get("level") == "major_section" and not node.get("subsection_ids"))
    ]
    for node in sorted(leaves, key=lambda item: (len(item.get("section_path", [])), item["section_id"])):
        paragraphs = [paragraph_by_id[pid].get("text", "") for pid in node.get("paragraph_ids", []) if pid in paragraph_by_id]
        text, sentences = extractive_summary(node.get("title", ""), paragraphs, 4)
        summaries[node["section_id"]] = {
            "unit_id": node["section_id"],
            "level": node["level"],
            "title": node.get("title", ""),
            "parent_id": node.get("parent_id"),
            "section_path": node.get("section_path", []),
            "pdf_page_start": node.get("pdf_page_start"),
            "pdf_page_end": node.get("pdf_page_end"),
            "page_number_start": node.get("printed_page_start"),
            "page_number_end": node.get("printed_page_end"),
            "printed_page_start": node.get("printed_page_start"),
            "printed_page_end": node.get("printed_page_end"),
            "source_passage_ids": node.get("paragraph_ids", []),
            "keyword_record_count": len(keyword_ids_by_node.get(node["section_id"], [])),
            "summary": text,
            "summary_sentences": sentences,
            "summary_method": "extractive_source_sentences_at_leaf_unit",
            "child_summary_ids": [],
            "status": STATUS,
            "verification_status": STATUS,
        }

    remaining = [node for node in all_nodes.values() if node["section_id"] not in summaries]
    for level in ("major_section", "chapter", "part"):
        for node in sorted((item for item in remaining if item.get("level") == level), key=lambda item: (-len(item.get("section_path", [])), item["section_id"])):
            child_ids = node.get("children", [])
            child_summaries = [summaries[child_id] for child_id in child_ids if child_id in summaries]
            child_texts = [child.get("summary", "") for child in child_summaries if child.get("summary")]
            text, sentences = extractive_summary(node.get("title", ""), child_texts, 6 if level == "part" else 5)
            summaries[node["section_id"]] = {
                "unit_id": node["section_id"],
                "level": level,
                "title": node.get("title", ""),
                "parent_id": node.get("parent_id"),
                "section_path": node.get("section_path", []),
                "pdf_page_start": node.get("pdf_page_start"),
                "pdf_page_end": node.get("pdf_page_end"),
                "page_number_start": node.get("printed_page_start"),
                "page_number_end": node.get("printed_page_end"),
                "printed_page_start": node.get("printed_page_start"),
                "printed_page_end": node.get("printed_page_end"),
                "source_passage_count": len(node.get("paragraph_ids", [])),
                "keyword_record_count": len(keyword_ids_by_node.get(node["section_id"], [])),
                "summary": text,
                "summary_sentences": sentences,
                "summary_method": "extractive_child_summary_merge",
                "child_summary_ids": [child["unit_id"] for child in child_summaries],
                "status": STATUS,
                "verification_status": STATUS,
            }
    units = [summaries[node_id] for node_id in sorted(summaries)]
    return {
        "schema_version": "vtc-davidson25.hierarchical-summaries.v1",
        "record_type": "hierarchical_summaries",
        "book_id": structure.get("book_id"),
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "processing_order": ["subsection", "major_section", "chapter", "part"],
        "summary_policy": "Leaf summaries use source sentences. Parent summaries use child summaries only; no paragraph-by-paragraph upper-level re-extraction.",
        "units": units,
        "counts": {
            "parts": sum(unit["level"] == "part" for unit in units),
            "chapters": sum(unit["level"] == "chapter" for unit in units),
            "major_sections": sum(unit["level"] == "major_section" for unit in units),
            "subsections": sum(unit["level"] == "subsection" for unit in units),
            "nonempty_summaries": sum(bool(unit["summary"]) for unit in units),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction", required=True, type=Path)
    parser.add_argument("--structure", required=True, type=Path)
    parser.add_argument("--visual-manifest", required=True, type=Path)
    parser.add_argument("--tables", required=True, type=Path)
    parser.add_argument("--output-analysis", required=True, type=Path)
    parser.add_argument("--output-summaries", required=True, type=Path)
    parser.add_argument("--output-structure", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    outputs = [args.output_analysis, args.output_summaries, args.output_structure]
    if not args.overwrite:
        existing = [str(path) for path in outputs if path.exists()]
        if existing:
            raise SystemExit(f"Outputs exist; pass --overwrite: {existing}")
    extraction = load_json(args.extraction)
    chapter_structure = load_json(args.structure)
    visual_manifest = load_json(args.visual_manifest)
    tables = load_json(args.tables)
    structure, _paragraph_to_leaf, paragraph_to_ancestors, all_nodes = build_hierarchy(extraction, chapter_structure)
    visual_entries, visual_by_id = visual_records(
        visual_manifest, tables, all_nodes, build_page_map(chapter_structure)
    )
    paragraph_by_id = {paragraph.get("paragraph_id"): paragraph for paragraph in extraction.get("paragraphs", [])}
    paragraph_extractions, visual_extractions, keyword_ids_by_node, visual_keyword_ids_by_visual = make_keyword_records(
        extraction, visual_manifest, tables, all_nodes, paragraph_to_ancestors, visual_by_id
    )
    summaries = build_summaries(structure, all_nodes, paragraph_by_id, keyword_ids_by_node)

    # Attach the extracted keyword record IDs to every structure node so an
    # agent can navigate the hierarchy without reconstructing the merge.
    for node in structure["nodes"]:
        node["keyword_record_count"] = len(keyword_ids_by_node.get(node["section_id"], []))
        node["visual_keyword_record_count"] = len(unique(
            record_id
            for visual_id in node.get("visual_ids", [])
            for record_id in visual_keyword_ids_by_visual.get(visual_id, [])
        ))

    analysis = {
        "schema_version": "vtc-davidson25.paragraph-first-analysis.v1",
        "record_type": "paragraph_first_analysis",
        "book_id": extraction.get("book_id"),
        "source": extraction.get("source", {}),
        "derived_from": {
            "clean_sections_paragraphs": str(args.extraction),
            "chapter_structure": str(args.structure),
            "visual_manifest": str(args.visual_manifest),
            "tables": str(args.tables),
        },
        "keyword_policy": {
            "leaf_extraction": "Keywords are extracted from each paragraph at the smallest available section unit; parent units merge record IDs only.",
            "broad_and_small": "Each record keeps broad_area/category and small_area/source_form plus a broad-to-small keyword_path.",
            "visuals": "Tables use reconstructed table text; non-table visuals use name/caption metadata only.",
            "no_claims_index": True,
        },
        "paragraph_extractions": paragraph_extractions,
        "section_keyword_records": [],
        "visual_extractions": visual_extractions,
        "counts": {
            "paragraphs": len(paragraph_extractions),
            "keyword_records": sum(item["keyword_record_count"] for item in paragraph_extractions),
            "section_keyword_records": 0,
            "visual_keyword_records": len(visual_extractions),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    # Keep section records in a dedicated top-level list; the builder consumes
    # it directly and this avoids pretending headings came from paragraphs.
    section_records = []
    for node in all_nodes.values():
        title = clean_text(node.get("title", ""))
        if not title:
            continue
        ancestors = []
        cursor: dict[str, Any] | None = node
        while cursor:
            ancestors.append(cursor["section_id"])
            cursor = all_nodes.get(cursor.get("parent_id"))
        section_records.append({
            "record_id": f"DAV25-KW-{node['section_id']}-TITLE",
            "category": "section_topics",
            "source_form": title,
            "canonical_candidate": title,
            "keyword_path": [CATEGORY_LABELS["section_topics"], title],
            "retrieval_terms": alias_variants(title),
            "source_element_ids": [node["section_id"]],
            "section_ids": ancestors,
            "status": STATUS,
            "verification_status": STATUS,
        })
    analysis["section_keyword_records"] = section_records
    analysis["counts"]["section_keyword_records"] = len(section_records)

    args.output_analysis.parent.mkdir(parents=True, exist_ok=True)
    args.output_summaries.parent.mkdir(parents=True, exist_ok=True)
    args.output_structure.parent.mkdir(parents=True, exist_ok=True)
    args.output_analysis.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_summaries.write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_structure.write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"analysis": str(args.output_analysis), "summaries": str(args.output_summaries), "structure": str(args.output_structure), "counts": {"analysis": analysis["counts"], "summaries": summaries["counts"], "structure": structure["counts"]}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

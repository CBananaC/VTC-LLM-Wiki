#!/usr/bin/env python3
"""Build bottom-up orthopedic-test analysis, quotations, and keywords."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


BOOK_ID = "ORTHO3"
SOURCE_ID = "HHS4185-REF-ORTHO-SPECIAL-TESTS"
STATUS = "generated_not_verified"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'/-]*")
STOPWORDS = {
    "the", "and", "that", "with", "from", "this", "test", "subject", "examiner", "may", "can", "will", "are", "was", "were", "for", "into", "while", "when", "then", "than", "which", "their", "there", "these", "those", "should", "being", "have", "has", "had", "not", "but", "also", "such", "any", "one", "two", "both", "more", "most", "very", "during", "after", "before", "over", "under", "along", "side", "same", "opposite", "using", "used", "use", "performed", "perform", "indicates", "indicative", "positive", "finding", "findings", "figure", "figures", "page", "section", "references", "special", "considerations", "comments", "action", "positioning", "sign", "signs", "would", "could", "should", "likely", "often", "usually", "first", "next", "following", "while", "without", "within", "through", "toward", "because", "about", "against", "between", "each", "other", "given", "reported", "reporting", "pain", "possible", "related", "region", "involved", "involvement", "joint", "muscle", "muscles", "patient", "patients", "clinical", "examination", "orthopedic", "orthopaedic",
}
ALIASES = {
    "orthopaedic": ["orthopedic"], "orthopedic": ["orthopaedic"],
    "haemorrhage": ["hemorrhage"], "hemorrhage": ["haemorrhage"],
    "oedema": ["edema"], "edema": ["oedema"],
    "tumour": ["tumor"], "tumor": ["tumour"],
}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def aliases(value: str) -> list[str]:
    value = value.strip()
    result = [value]
    result.extend(ALIASES.get(value.casefold(), []))
    if value.casefold().endswith("s") and len(value) > 4:
        result.append(value[:-1])
    return unique(result)


def broad_area(kind: str | None, content_type: str) -> str:
    if content_type == "test_title":
        return "Orthopedic tests"
    return {
        "test_positioning": "Examination positioning",
        "action": "Test procedure",
        "positive_finding": "Positive findings and interpretation",
        "special_considerations_comments": "Precautions and clinical considerations",
        "references": "Evidence and references",
    }.get(kind or "", "Orthopedic examination concepts")


def small_area(term: str, kind: str | None, content_type: str) -> str:
    if content_type == "test_title":
        return term
    if kind == "test_positioning":
        return f"positioning: {term}"
    if kind == "action":
        return f"procedure: {term}"
    if kind == "positive_finding":
        return f"finding: {term}"
    if kind == "special_considerations_comments":
        return f"consideration: {term}"
    if kind == "references":
        return f"reference: {term}"
    return term


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip()) if len(part.strip()) >= 30]


def merge_text(parts: list[str]) -> str:
    result = ""
    for part in parts:
        if not part:
            continue
        if not result:
            result = part
        elif result.endswith("-"):
            result += part
        else:
            result += " " + part
    return re.sub(r"\s+", " ", result).strip()


def format_reference(structure: dict[str, Any], paragraph: dict[str, Any], test: dict[str, Any] | None, component: dict[str, Any] | None) -> dict[str, Any]:
    chapter_title = paragraph.get("chapter_title") or ""
    chapter_number = paragraph.get("chapter_number")
    printed_page = next(iter(paragraph.get("source_page_ids", [])), "").split("PDF")[-1]
    try:
        pdf_page = int(printed_page)
        printed = pdf_page - 24 if pdf_page >= 25 else None
    except ValueError:
        pdf_page, printed = None, None
    if paragraph.get("source_page_ids"):
        page_id = paragraph["source_page_ids"][0]
        match = re.search(r"(\d+)$", page_id)
        if match:
            pdf_page = int(match.group(1))
            printed = pdf_page - 24 if pdf_page >= 25 else None
    path = ["Special Tests for Orthopedic Examination"]
    if chapter_number is not None:
        path.append(f"Section {chapter_number}: {chapter_title}")
    if test:
        path.append(test["title"])
    if component:
        path.append(component["title"])
    formatted = f"Konin et al., Special Tests for Orthopedic Examination, 3rd ed."
    if chapter_number is not None:
        formatted += f", Section {chapter_number}: {chapter_title}"
    if test:
        formatted += f", {test['title']}"
    if printed is not None:
        formatted += f", p. {printed} [PDF p. {pdf_page}]"
    return {
        "source_id": SOURCE_ID,
        "source_title": "Special Tests for Orthopedic Examination",
        "edition": "3rd",
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "test_title": test.get("title") if test else None,
        "component_title": component.get("title") if component else None,
        "page_number": printed,
        "page_number_type": "printed_book_page" if printed is not None else "unumbered_pdf_page",
        "pdf_page": pdf_page,
        "source_page_ids": paragraph.get("source_page_ids", []),
        "section_path": path,
        "formatted": formatted,
        "status": STATUS,
        "verification_status": STATUS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paragraphs", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--visual-manifest", type=Path, required=True)
    parser.add_argument("--tables", type=Path, required=True)
    parser.add_argument("--output-analysis", type=Path, required=True)
    parser.add_argument("--output-summaries", type=Path, required=True)
    parser.add_argument("--output-structure", type=Path, required=True)
    args = parser.parse_args()
    paragraph_data = load(args.paragraphs.expanduser().resolve())
    structure = load(args.structure.expanduser().resolve())
    visual_manifest = load(args.visual_manifest.expanduser().resolve())
    tables = load(args.tables.expanduser().resolve())
    paragraphs = paragraph_data["paragraphs"]
    nodes = {node["section_id"]: dict(node) for node in structure["nodes"]}
    tests = {node["section_id"]: node for node in nodes.values() if node.get("level") == "major_section"}
    chapters = {node["section_id"]: node for node in nodes.values() if node.get("level") == "chapter"}
    components = {node["section_id"]: node for node in nodes.values() if node.get("level") == "subsection"}
    paragraph_by_id = {paragraph["paragraph_id"]: paragraph for paragraph in paragraphs}

    # Attach every paragraph to its component, test, chapter, and part path.
    for paragraph in paragraphs:
        component = components.get(paragraph.get("section_id"))
        test = tests.get(paragraph.get("major_section_id"))
        chapter = chapters.get(test.get("parent_id")) if test else None
        paragraph["section_path"] = ["Special Tests for Orthopedic Examination"]
        if chapter:
            paragraph["section_path"].append(f"Section {chapter['chapter_number']}: {chapter['title']}")
        if test:
            paragraph["section_path"].append(test["title"])
        if component:
            paragraph["section_path"].append(component["title"])
        paragraph["status"] = STATUS
        paragraph["verification_status"] = STATUS

    global_counts = Counter()
    for paragraph in paragraphs:
        for token in TOKEN_RE.findall(paragraph.get("text", "")):
            key = normalize(token)
            if key and len(key) >= 3 and key not in STOPWORDS:
                global_counts[key] += 1
    keyword_records: list[dict[str, Any]] = []
    paragraph_extractions: list[dict[str, Any]] = []
    keyword_ids_by_node: dict[str, list[str]] = defaultdict(list)
    for paragraph in paragraphs:
        test = tests.get(paragraph.get("major_section_id"))
        component = components.get(paragraph.get("section_id"))
        kind = component.get("title_kind") if component else None
        local_tokens: dict[str, list[str]] = defaultdict(list)
        for token in TOKEN_RE.findall(paragraph.get("text", "")):
            key = normalize(token)
            if key and len(key) >= 3 and key not in STOPWORDS and (global_counts[key] >= 2 or len(key) >= 7):
                local_tokens[key].append(token)
        records: list[dict[str, Any]] = []
        for index, (key, forms) in enumerate(sorted(local_tokens.items()), 1):
            source_form = max(forms, key=lambda value: (len(value), value.casefold()))
            record = {
                "record_id": f"{BOOK_ID}-KW-{paragraph['paragraph_id']}-{index:03d}",
                "source_passage_ids": [paragraph["paragraph_id"]],
                "source_page_ids": paragraph.get("source_page_ids", []),
                "broad_area": broad_area(kind, paragraph.get("content_type", "")),
                "small_area": small_area(source_form, kind, paragraph.get("content_type", "")),
                "keyword_path": [broad_area(kind, paragraph.get("content_type", "")), small_area(source_form, kind, paragraph.get("content_type", ""))],
                "source_form": source_form,
                "canonical_candidate": source_form,
                "retrieval_terms": aliases(source_form),
                "test_id": test["section_id"] if test else None,
                "component_id": component["section_id"] if component else None,
                "status": STATUS,
                "verification_status": STATUS,
            }
            records.append(record)
            keyword_records.append(record)
            ancestry = [paragraph.get("section_id"), paragraph.get("major_section_id"), test.get("parent_id") if test else None, "ORTHO3-PART01"]
            for node_id in ancestry:
                if node_id:
                    keyword_ids_by_node[node_id].append(record["record_id"])
        paragraph_extractions.append({
            "source_passage_ids": [paragraph["paragraph_id"]],
            "source_page_ids": paragraph.get("source_page_ids", []),
            "section_ids": [node_id for node_id in [paragraph.get("section_id"), paragraph.get("major_section_id")] if node_id],
            "keyword_records": records,
            "keyword_record_count": len(records),
            "status": STATUS,
            "verification_status": STATUS,
        })

    # Titles are independent retrieval anchors and are kept separate from
    # paragraph prose extraction.
    for node in nodes.values():
        if node.get("level") not in {"chapter", "major_section", "subsection"}:
            continue
        broad = "Orthopedic tests" if node["level"] == "major_section" else ("Body-region sections" if node["level"] == "chapter" else "Test components")
        record = {
            "record_id": f"{BOOK_ID}-KW-{node['section_id']}-TITLE",
            "source_element_ids": [node["section_id"]],
            "source_page_ids": [f"{BOOK_ID}-PDF{int(node['pdf_page_start']):04d}"],
            "broad_area": broad,
            "small_area": node["title"],
            "keyword_path": [broad, node["title"]],
            "source_form": node["title"],
            "canonical_candidate": node["title"],
            "retrieval_terms": aliases(node["title"]),
            "status": STATUS,
            "verification_status": STATUS,
        }
        keyword_records.append(record)
        cursor: str | None = node["section_id"]
        while cursor:
            keyword_ids_by_node[cursor].append(record["record_id"])
            cursor = nodes.get(cursor, {}).get("parent_id")

    visual_extractions: list[dict[str, Any]] = []
    visual_records = []
    for visual in visual_manifest.get("visuals", []):
        pdf_page = int(visual["pdf_page"])
        test = next((test for test in tests.values() if int(test["pdf_page_start"]) <= pdf_page <= int(test["pdf_page_end"])), None)
        chapter = chapters.get(test.get("parent_id")) if test else None
        visual_copy = dict(visual)
        visual_copy["test_id"] = test.get("section_id") if test else None
        visual_copy["test_title"] = test.get("title") if test else None
        visual_copy["chapter_number"] = chapter.get("chapter_number") if chapter else None
        visual_copy["chapter_title"] = chapter.get("title") if chapter else None
        visual_copy["status"] = STATUS
        visual_copy["verification_status"] = STATUS
        visual_records.append(visual_copy)
        text = " ".join(str(value) for value in [visual.get("name"), visual.get("caption") or ""] if value)
        if text:
            visual_extractions.append({
                "record_id": f"{BOOK_ID}-KW-{visual['visual_id']}",
                "source_element_id": visual["visual_id"],
                "test_id": test.get("section_id") if test else None,
                "broad_area": "Visual aids",
                "small_area": text,
                "keyword_path": ["Visual aids", text],
                "source_form": text,
                "canonical_candidate": text,
                "retrieval_terms": aliases(text),
                "status": STATUS,
                "verification_status": STATUS,
            })

    for key in keyword_ids_by_node:
        keyword_ids_by_node[key] = unique(keyword_ids_by_node[key])
    for node in nodes.values():
        node["keyword_record_ids"] = keyword_ids_by_node.get(node["section_id"], [])
        node["paragraph_ids"] = [p["paragraph_id"] for p in paragraphs if p.get("section_id") == node["section_id"] or p.get("major_section_id") == node["section_id"]]
        node["source_page_ids"] = unique(page_id for p in paragraphs if p.get("section_id") == node["section_id"] or p.get("major_section_id") == node["section_id"] for page_id in p.get("source_page_ids", []))
        node["status"] = STATUS
        node["verification_status"] = STATUS

    # Formal quotation candidates point to reconstructed prose only.
    quotations: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        if paragraph.get("content_type") not in {"paragraph", "list_item"} or paragraph.get("is_synthetic"):
            continue
        test = tests.get(paragraph.get("major_section_id"))
        component = components.get(paragraph.get("section_id"))
        reference = format_reference(structure, paragraph, test, component)
        quotations.append({
            "evidence_id": f"{paragraph['paragraph_id']}-EVIDENCE",
            "quotation": paragraph["text"],
            "source_passage_id": paragraph["paragraph_id"],
            "reference": reference,
            "in_text_citation": f"(Konin et al., Special Tests for Orthopedic Examination, 3rd ed., Section {paragraph.get('chapter_number')}, p. {reference.get('page_number')})" if reference.get("page_number") else "(Konin et al., Special Tests for Orthopedic Examination, 3rd ed.)",
            "quotation_status": "source_extracted_candidate",
            "verification_status": STATUS,
            "exact_quote_eligible": False,
            "manual_source_image_check_required": True,
        })

    analysis = {
        "schema_version": "vtc-ortho3.paragraph-first-analysis.v1",
        "record_type": "paragraph_first_analysis",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "source": paragraph_data.get("source", {}),
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "processing_order": ["subsection", "major_section", "chapter", "part"],
        "keyword_policy": {"leaf_extraction": "keywords are extracted at paragraph/component level", "parent_merge": "parent units aggregate keyword IDs only", "broad_area_and_small_area": True},
        "paragraph_extractions": paragraph_extractions,
        "keyword_records": keyword_records,
        "visual_extractions": visual_extractions,
        "quotation_candidates": quotations,
        "visual_records": visual_records,
        "table_records": tables.get("tables", []),
        "counts": {"paragraphs": len(paragraphs), "keyword_records": len(keyword_records), "visual_keyword_records": len(visual_extractions), "quotation_candidates": len(quotations), "visual_records": len(visual_records), "tables": len(tables.get("tables", [])), "nodes": len(nodes)},
        "status": STATUS,
        "verification_status": STATUS,
    }

    summaries: dict[str, dict[str, Any]] = {}
    component_nodes = [node for node in nodes.values() if node.get("level") == "subsection"]
    for node in sorted(component_nodes, key=lambda item: (item["pdf_page_start"], item["section_id"])):
        texts = [p["text"] for p in paragraphs if p.get("section_id") == node["section_id"] and p.get("content_type") == "paragraph"]
        summary_sentences: list[str] = []
        for text in texts:
            for sentence in sentences(text):
                if sentence not in summary_sentences:
                    summary_sentences.append(sentence)
                if len(summary_sentences) >= 3:
                    break
            if len(summary_sentences) >= 3:
                break
        summaries[node["section_id"]] = {"unit_id": node["section_id"], "level": "subsection", "title": node["title"], "parent_id": node.get("parent_id"), "section_path": node.get("section_path", []), "pdf_page_start": node.get("pdf_page_start"), "pdf_page_end": node.get("pdf_page_end"), "printed_page_start": node.get("printed_page_start"), "printed_page_end": node.get("printed_page_end"), "source_passage_ids": [p["paragraph_id"] for p in paragraphs if p.get("section_id") == node["section_id"]], "keyword_record_ids": node.get("keyword_record_ids", []), "summary": " ".join(summary_sentences), "summary_sentences": summary_sentences, "summary_method": "extractive_source_sentences_at_leaf_unit", "child_summary_ids": [], "status": STATUS, "verification_status": STATUS}
    for level in ("major_section", "chapter", "part"):
        for node in sorted((item for item in nodes.values() if item.get("level") == level), key=lambda item: (item["pdf_page_start"], item["section_id"])):
            child_ids = node.get("children", [])
            children = [summaries[child_id] for child_id in child_ids if child_id in summaries]
            texts = [child["summary"] for child in children if child.get("summary")]
            merged_sentences: list[str] = []
            for text in texts:
                for sentence in sentences(text):
                    if sentence not in merged_sentences:
                        merged_sentences.append(sentence)
                    if len(merged_sentences) >= (5 if level == "part" else 4):
                        break
                if len(merged_sentences) >= (5 if level == "part" else 4):
                    break
            summaries[node["section_id"]] = {"unit_id": node["section_id"], "level": level, "title": node["title"], "parent_id": node.get("parent_id"), "section_path": node.get("section_path", []), "pdf_page_start": node.get("pdf_page_start"), "pdf_page_end": node.get("pdf_page_end"), "printed_page_start": node.get("printed_page_start"), "printed_page_end": node.get("printed_page_end"), "source_passage_ids": node.get("paragraph_ids", []), "keyword_record_ids": node.get("keyword_record_ids", []), "summary": " ".join(merged_sentences), "summary_sentences": merged_sentences, "summary_method": "extractive_child_summary_merge", "child_summary_ids": [child["unit_id"] for child in children], "status": STATUS, "verification_status": STATUS}
    summary_output = {"schema_version": "vtc-ortho3.hierarchical-summaries.v1", "record_type": "hierarchical_summaries", "book_id": BOOK_ID, "source_id": SOURCE_ID, "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"], "processing_order": ["subsection", "major_section", "chapter", "part"], "summary_policy": "leaf component summaries use source sentences; parent summaries merge child summaries only", "units": list(summaries.values()), "counts": {"parts": sum(x["level"] == "part" for x in summaries.values()), "chapters": sum(x["level"] == "chapter" for x in summaries.values()), "major_sections": sum(x["level"] == "major_section" for x in summaries.values()), "subsections": sum(x["level"] == "subsection" for x in summaries.values()), "nonempty_summaries": sum(bool(x["summary"]) for x in summaries.values())}, "status": STATUS, "verification_status": STATUS}
    structure_output = {**structure, "nodes": list(nodes.values()), "status": STATUS, "verification_status": STATUS, "analysis_links": {"analysis": str(args.output_analysis), "summaries": str(args.output_summaries)}}
    for output_path, value in [(args.output_analysis, analysis), (args.output_summaries, summary_output), (args.output_structure, structure_output)]:
        path = output_path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"analysis": str(args.output_analysis), "summaries": str(args.output_summaries), "structure": str(args.output_structure), **analysis["counts"], "summary_units": len(summaries), "status": STATUS}, ensure_ascii=False))


if __name__ == "__main__":
    main()

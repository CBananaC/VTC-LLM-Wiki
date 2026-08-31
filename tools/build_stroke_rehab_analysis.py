#!/usr/bin/env python3
"""Build source-linked multi-level extraction and summaries for Stroke Rehabilitation.

The structural order is deliberately bottom-up:

    Subsection -> Major section -> Chapter -> Part

Major sections come from the PDF outline inventory. Subsections come from
PaddleOCR paragraph_title boxes matched to the clean reading-order line layer.
The source paragraph layer remains immutable; this script only creates derived
analysis files and labels all results generated_not_verified.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


STATUS = "generated_not_verified"
BOOK_ID = "STROKE5"
TITLE = "Stroke Rehabilitation: A Function-Based Approach, Fifth Edition"

STOPWORDS = {
    "about", "after", "again", "also", "although", "among", "because", "before",
    "being", "between", "could", "during", "each", "from", "have", "into", "more",
    "most", "other", "over", "patient", "patients", "should", "some", "such", "than",
    "that", "their", "there", "these", "they", "this", "those", "through", "under",
    "using", "were", "which", "while", "with", "would", "your", "chapter", "figure",
    "table", "box", "page", "section", "summary", "references", "review", "questions",
    "stroke", "following", "after", "during", "include", "including", "used", "use",
    "often", "many", "may", "can", "one", "two", "three", "first", "second", "within",
    "without", "when", "where", "what", "been", "does", "both", "very", "only", "per",
}

MEDICATION_WORDS = {
    "baclofen", "dantrolene", "diazepam", "tizanidine", "botulinum", "carbamazepine",
    "clonazepam", "gabapentin", "lamotrigine", "levetiracetam", "phenobarbital", "phenytoin",
    "primidone", "valproic", "aspirin", "heparin", "warfarin", "anticoagulation", "antiplatelet",
    "thrombolytic", "mannitol", "nimodipine", "labetalol", "lisinopril", "enoxaparin",
}
ASSESSMENT_WORDS = {
    "assessment", "assessments", "evaluation", "evaluations", "diagnosis", "diagnostic", "imaging",
    "computed", "tomography", "magnetic", "resonance", "doppler", "screening", "screen", "scale",
    "test", "tests", "measure", "measurement", "monitor", "monitoring", "score", "questionnaire",
}
INTERVENTION_WORDS = {
    "management", "treatment", "therapy", "intervention", "rehabilitation", "training", "exercise",
    "positioning", "splinting", "mobility", "gait", "adaptation", "prevention", "caregiving", "education",
    "facilitation", "practice", "prescription", "modification", "discharge", "occupation",
}
ANATOMY_WORDS = {
    "brain", "cerebral", "artery", "arterial", "vascular", "muscle", "shoulder", "upper", "extremity",
    "limb", "hand", "arm", "leg", "foot", "trunk", "spine", "heart", "lung", "swallowing", "speech",
    "language", "vestibular", "visual", "cognitive", "perceptual", "skin", "bone", "joint",
}
IMPAIRMENT_WORDS = {
    "weakness", "spasticity", "pain", "dysphagia", "aphasia", "apraxia", "neglect", "agnosia", "ataxia",
    "seizure", "hydrocephalus", "edema", "contracture", "deconditioning", "depression", "anxiety",
    "impairment", "deficit", "disability", "fatigue", "dizziness", "balance", "postural",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def clean(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\x00", " ").replace("\xad", "")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:?!%\)])", r"\1", value)
    value = re.sub(r"([(/])\s+", r"\1", value)
    return value.strip()


def normalized(value: str | None) -> str:
    return "".join(ch.lower() for ch in clean(value) if ch.isalnum())


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def numeric_id(value: str) -> int:
    match = re.search(r"(\d+)$", value or "")
    return int(match.group(1)) if match else 0


def split_sentences(text: str) -> list[str]:
    text = clean(text)
    if not text:
        return []
    pieces = re.split(r"(?<=[.!?])\s+", text)
    return [piece.strip() for piece in pieces if len(piece.strip()) >= 45]


def extractive_summary(texts: list[str], max_sentences: int) -> tuple[str, list[str]]:
    sentences: list[str] = []
    for text in texts:
        for sentence in split_sentences(text):
            if sentence not in sentences:
                sentences.append(sentence)
            if len(sentences) >= max_sentences:
                break
        if len(sentences) >= max_sentences:
            break
    return " ".join(sentences), sentences


def token_list(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9’'/-]{2,}", clean(text))]


def broad_area(term: str, title: str = "") -> str:
    value = term.lower()
    words = set(token_list(value))
    if words & MEDICATION_WORDS or any(value.endswith(suffix) for suffix in ("therapy", "medication", "anticoagulation")):
        return "medication_and_pharmacology"
    if words & ASSESSMENT_WORDS:
        return "assessment_and_diagnosis"
    if words & INTERVENTION_WORDS:
        return "rehabilitation_and_intervention"
    if words & IMPAIRMENT_WORDS:
        return "impairment_and_symptom"
    if words & ANATOMY_WORDS:
        return "anatomy_and_body_system"
    if title and normalized(term) == normalized(title):
        return "section_topic"
    return "clinical_concept"


def page_reference(
    source: dict[str, Any], chapter: dict[str, Any], title: str, pdf_start: int | None, pdf_end: int | None,
    printed_start: str | None, printed_end: str | None, passage_ids: list[str], page_ids: list[str],
    level: str | None = None, part_number: int | None = None, part_title: str | None = None,
) -> dict[str, Any]:
    page_text = str(printed_start) if printed_start else (f"PDF p. {pdf_start}" if pdf_start else "")
    if printed_end and printed_end != printed_start:
        page_text += f"–{printed_end}"
    elif pdf_end and pdf_end != pdf_start and not printed_start:
        page_text += f"–{pdf_end}"
    chapter_number = chapter.get("chapter_number") if level != "part" else None
    chapter_title = chapter.get("title") or chapter.get("chapter_title") or ""
    if level == "part":
        citation = f"Gillen, {TITLE} (2021), Part {part_number}: {part_title or title}"
    else:
        citation = f"Gillen, {TITLE} (2021), Chapter {chapter_number}: {chapter_title}"
        if title and normalized(title) != normalized(chapter_title):
            citation += f", {title}"
    if page_text:
        citation += f", p. {page_text}"
    short_form = (
        f"Gillen, Stroke Rehabilitation, 5th ed., Part {part_number}, p. {page_text}"
        if level == "part"
        else f"Gillen, Stroke Rehabilitation, 5th ed., Ch. {chapter_number}, p. {page_text}"
    )
    return {
        "source_id": source.get("source_id", "HHS4185-REF-STROKE-REHAB-5E"),
        "source_title": TITLE,
        "work_title": "Stroke Rehabilitation: A Function-Based Approach",
        "edition": "5th",
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "unit_title": title,
        "page_number": printed_start if printed_start else pdf_start,
        "page_number_type": "printed_textbook_page" if printed_start else "pdf_page",
        "pdf_page": pdf_start,
        "source_page_id": page_ids[0] if page_ids else None,
        "pdf_page_start": pdf_start,
        "pdf_page_end": pdf_end,
        "printed_page_start": printed_start,
        "printed_page_end": printed_end,
        "source_page_ids": page_ids,
        "source_passage_ids": passage_ids,
        "citation_text": citation,
        "short_form": short_form,
        "formatted": citation,
        "status": STATUS,
        "verification_status": STATUS,
        "exact_quote_eligible": False,
    }


def overlap(a: list[float], b: list[float]) -> bool:
    if len(a) != 4 or len(b) != 4:
        return False
    x = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    y = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = x * y
    line_area = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
    return area / line_area >= 0.25 or (
        b[0] >= a[0] - 2 and b[2] <= a[2] + 2 and b[1] >= a[1] - 2 and b[3] <= a[3] + 2
    )


def build_title_anchors(layout: dict[str, Any], clean_pages: dict[int, dict[str, Any]], paragraphs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    line_to_paragraphs: dict[str, list[str]] = defaultdict(list)
    for paragraph in paragraphs:
        for line_id in paragraph.get("source_line_ids", []):
            line_to_paragraphs[line_id].append(paragraph["paragraph_id"])

    anchors: list[dict[str, Any]] = []
    anchor_index = 0
    for page in layout.get("pages", []):
        pdf_page = page.get("pdf_page")
        clean_page = clean_pages.get(pdf_page)
        if not clean_page:
            continue
        render = page.get("render") or {}
        sx = 612.0 / float(render.get("width", 1020))
        sy = 781.92 / float(render.get("height", 1305))
        lines = clean_page.get("reading_order_lines", [])
        for box in page.get("layout_boxes", []):
            if box.get("label") != "paragraph_title":
                continue
            raw_bbox = box.get("bbox") or []
            if len(raw_bbox) != 4:
                continue
            box_points = [raw_bbox[0] * sx, raw_bbox[1] * sy, raw_bbox[2] * sx, raw_bbox[3] * sy]
            matched = []
            for line_index, line in enumerate(lines):
                bbox = line.get("bbox_points") or []
                if overlap(box_points, bbox):
                    matched.append((line_index, line))
            if not matched:
                continue
            matched.sort(key=lambda item: (item[1].get("bbox_points", [0, 0])[1], item[1].get("bbox_points", [0, 0])[0]))
            title = clean(" ".join(line.get("text", "") for _, line in matched))
            paragraph_ids = unique(
                paragraph_id
                for _, line in matched
                for line_id in ([line.get("line_id")] + line.get("source_line_ids", []))
                if line_id
                for paragraph_id in line_to_paragraphs.get(line_id, [])
            )
            if not title or not paragraph_ids:
                continue
            anchor_index += 1
            anchors.append({
                "anchor_id": f"{BOOK_ID}-H-{anchor_index:04d}",
                "title": title,
                "normalized_title": normalized(title),
                "pdf_page": pdf_page,
                "printed_page": clean_page.get("printed_page"),
                "paragraph_ids": paragraph_ids,
                "source_line_ids": unique(
                    line_id for _, line in matched for line_id in line.get("source_line_ids", [])
                ),
                "line_indices": [line_index for line_index, _ in matched],
                "bbox_points": box_points,
                "layout_confidence": box.get("confidence"),
                "status": STATUS,
                "verification_status": STATUS,
            })
    # PaddleOCR sometimes emits several paragraph_title boxes for one wrapped
    # heading. Remove obvious bullet/number false positives, keep the longest
    # complete heading when it contains shorter fragments, and join fragments
    # only when the first fragment is visibly incomplete.
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        title = anchor["title"].strip()
        if re.match(r"^(?:\(?\d+[.)]|[ivxlcdm]+[.)])\s*", title, re.I):
            continue
        grouped[(anchor["pdf_page"], anchor["paragraph_ids"][0])].append(anchor)
    cleaned: list[dict[str, Any]] = []
    incomplete_endings = ("and", "or", "of", "with", "for", "to", "before", "after", "in", "on", ",")
    for group in grouped.values():
        group.sort(key=lambda item: (min(item.get("line_indices") or [10**9]), item["anchor_id"]))
        kept: list[dict[str, Any]] = []
        for anchor in group:
            key = anchor["normalized_title"]
            if any(key != other["normalized_title"] and key in other["normalized_title"] for other in group):
                continue
            kept.append(anchor)
        merged: list[dict[str, Any]] = []
        index = 0
        while index < len(kept):
            current = kept[index]
            if index + 1 < len(kept):
                following = kept[index + 1]
                current_title = current["title"].rstrip()
                following_title = following["title"].lstrip()
                last_word = current_title.rstrip(".,:;)").split()[-1].lower() if current_title.rstrip(".,:;)").split() else ""
                if current_title.endswith(",") or last_word in incomplete_endings or following_title[:1].islower():
                    current = dict(current)
                    current["title"] = clean(f"{current_title} {following_title}")
                    current["normalized_title"] = normalized(current["title"])
                    current["paragraph_ids"] = unique(current["paragraph_ids"] + following["paragraph_ids"])
                    current["source_line_ids"] = unique(current["source_line_ids"] + following["source_line_ids"])
                    current["line_indices"] = sorted(
                        list(dict.fromkeys(current.get("line_indices", []) + following.get("line_indices", [])))
                    )
                    current["bbox_points"] = [
                        min(current["bbox_points"][0], following["bbox_points"][0]), min(current["bbox_points"][1], following["bbox_points"][1]),
                        max(current["bbox_points"][2], following["bbox_points"][2]), max(current["bbox_points"][3], following["bbox_points"][3]),
                    ]
                    merged.append(current)
                    index += 2
                    continue
            merged.append(current)
            index += 1
        cleaned.extend(merged)
    cleaned.sort(key=lambda item: (item["pdf_page"], min(item.get("line_indices") or [10**9]), item["anchor_id"]))
    return cleaned


def chapter_catalog(structure: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    part_for: dict[str, int] = {}
    part_title_for: dict[str, str] = {}
    for part in structure.get("parts", []):
        for chapter in part.get("chapters", []):
            number = str(chapter.get("chapter_number"))
            part_for[number] = part.get("part_number")
            part_title_for[number] = part.get("title", "")
    chapters: list[dict[str, Any]] = []
    for chapter in structure.get("chapters", []):
        number = str(chapter.get("chapter_number"))
        item = dict(chapter)
        item.update({"chapter_number": number, "part_number": part_for.get(number), "part_title": part_title_for.get(number, "")})
        chapters.append(item)
    for electronic in structure.get("electronic_only_chapters", []):
        item = dict(electronic)
        item.update({"chapter_number": str(electronic.get("chapter_number")), "part_number": 3, "part_title": part_title_for.get("30", "")})
        item["sections"] = []
        chapters.append(item)
    chapters.sort(key=lambda item: (item.get("pdf_page_start") or 0, str(item.get("chapter_number"))))
    return chapters, {str(item["chapter_number"]): item for item in chapters}


def paragraph_pages(paragraph: dict[str, Any]) -> list[int]:
    start = paragraph.get("pdf_page_start")
    end = paragraph.get("pdf_page_end") or start
    if start is None:
        return []
    return list(range(int(start), int(end) + 1))


def build_hierarchy(
    structure: dict[str, Any], extraction: dict[str, Any], anchors: list[dict[str, Any]],
    visual_manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    paragraphs = extraction.get("paragraphs", [])
    paragraph_by_id = {item["paragraph_id"]: item for item in paragraphs}
    paragraph_order = {item["paragraph_id"]: index for index, item in enumerate(paragraphs)}
    chapters, chapter_by_number = chapter_catalog(structure)
    anchors_by_paragraph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        for paragraph_id in anchor["paragraph_ids"]:
            anchors_by_paragraph[paragraph_id].append(anchor)
    for values in anchors_by_paragraph.values():
        values.sort(key=lambda item: (item["pdf_page"], item["anchor_id"]))

    nodes: dict[str, dict[str, Any]] = {}
    children: dict[str, list[str]] = defaultdict(list)
    leaf_nodes: list[str] = []
    paragraph_to_leaf: dict[str, str] = {}
    chapter_node_ids: dict[str, str] = {}

    def add_node(node: dict[str, Any]) -> None:
        nodes[node["unit_id"]] = node
        if node.get("parent_id"):
            children[node["parent_id"]].append(node["unit_id"])

    # Part and chapter containers are source-of-structure records.
    part_info = {part.get("part_number"): part for part in structure.get("parts", [])}
    part_node_ids: dict[int, str] = {}
    for part_number, part in sorted(part_info.items()):
        unit_id = f"{BOOK_ID}-PART-{int(part_number):02d}"
        part_node_ids[int(part_number)] = unit_id
        add_node({
            "unit_id": unit_id, "level": "part", "title": part.get("title", ""),
            "part_number": int(part_number), "parent_id": None, "chapter_ids": [], "section_path": [part.get("title", "")],
            "pdf_page_start": part.get("pdf_page_start"), "pdf_page_end": part.get("pdf_page_end"),
            "printed_page_start": part.get("printed_page_start"), "printed_page_end": part.get("printed_page_end"),
            "paragraph_ids": [], "source_page_ids": [], "status": STATUS, "verification_status": STATUS,
        })

    for chapter in chapters:
        number = str(chapter["chapter_number"])
        part_number = int(chapter.get("part_number") or 3)
        unit_id = f"{BOOK_ID}-CH-{number}"
        chapter_node_ids[number] = unit_id
        add_node({
            "unit_id": unit_id, "level": "chapter", "title": chapter.get("title", ""),
            "chapter_number": number, "part_number": part_number, "part_title": chapter.get("part_title", ""),
            "parent_id": part_node_ids.get(part_number), "section_path": [chapter.get("part_title", ""), chapter.get("title", "")],
            "pdf_page_start": chapter.get("pdf_page_start"), "pdf_page_end": chapter.get("pdf_page_end"),
            "printed_page_start": chapter.get("printed_page_start"), "printed_page_end": chapter.get("printed_page_end"),
            "paragraph_ids": [], "source_page_ids": [], "status": STATUS, "verification_status": STATUS,
        })

    # Assign paragraphs to chapters from their captured source metadata.
    chapter_paragraphs: dict[str, list[str]] = defaultdict(list)
    for paragraph in paragraphs:
        number = paragraph.get("chapter_number")
        if number is not None and str(number) in chapter_node_ids:
            chapter_paragraphs[str(number)].append(paragraph["paragraph_id"])
    for number, ids in chapter_paragraphs.items():
        ids.sort(key=lambda pid: paragraph_order[pid])
        nodes[chapter_node_ids[number]]["paragraph_ids"] = ids
        nodes[chapter_node_ids[number]]["source_page_ids"] = unique(
            page_id for pid in ids for page_id in paragraph_by_id[pid].get("source_page_ids", [])
        )

    # Major section records from the PDF outline. Anchors are matched by page
    # and title, which resolves multiple outline entries starting on one page.
    major_by_chapter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    section_counter_by_chapter: dict[str, int] = defaultdict(int)
    for chapter in chapters:
        number = str(chapter["chapter_number"])
        chapter_ids = chapter_paragraphs.get(number, [])
        chapter_set = set(chapter_ids)
        chapter_anchor_values = [anchor for anchor in anchors if chapter_set.intersection(anchor["paragraph_ids"])]
        chapter_anchor_values.sort(key=lambda anchor: (min(paragraph_order.get(pid, 10**9) for pid in anchor["paragraph_ids"]), anchor["anchor_id"]))
        used_anchor_ids: set[str] = set()
        section_specs: list[dict[str, Any]] = []
        for index, section in enumerate(chapter.get("sections", []), 1):
            title = section.get("title", "")
            target = normalized(title)
            candidates = []
            for anchor in chapter_anchor_values:
                if anchor["anchor_id"] in used_anchor_ids or anchor["pdf_page"] < (section.get("pdf_page_start") or 0):
                    continue
                anchor_title = anchor["normalized_title"]
                if target and (target == anchor_title or target in anchor_title or anchor_title in target):
                    candidates.append(anchor)
            candidates.sort(key=lambda anchor: (anchor["pdf_page"], min(paragraph_order.get(pid, 10**9) for pid in anchor["paragraph_ids"])))
            anchor = candidates[0] if candidates else None
            if anchor:
                used_anchor_ids.add(anchor["anchor_id"])
                start_index = min(paragraph_order.get(pid, 10**9) for pid in anchor["paragraph_ids"])
            else:
                start_index = next(
                    (paragraph_order[pid] for pid in chapter_ids if (paragraph_by_id[pid].get("pdf_page_start") or 0) >= (section.get("pdf_page_start") or 0)),
                    len(paragraphs),
                )
            section_counter_by_chapter[number] += 1
            unit_id = f"{BOOK_ID}-CH-{number}-MAJOR-{index:03d}"
            section_specs.append({
                "unit_id": unit_id, "title": title, "outline_index": section.get("outline_index"),
                "pdf_page_start": section.get("pdf_page_start"), "printed_page_start": section.get("printed_page_start"),
                "start_index": start_index, "anchor": anchor,
            })
        section_specs.sort(key=lambda item: (item["start_index"], item["unit_id"]))
        major_by_chapter[number] = section_specs

        # Build an explicit synthetic container for text before the first PDF
        # outline section. This keeps key terms/objectives navigable without
        # pretending that the PDF calls them a major section.
        first_start = section_specs[0]["start_index"] if section_specs else len(paragraphs)
        if chapter_ids:
            prefix_ids = [pid for pid in chapter_ids if paragraph_order[pid] < first_start]
            if prefix_ids:
                unit_id = f"{BOOK_ID}-CH-{number}-FRONT-MATTER"
                add_node({
                    "unit_id": unit_id, "level": "major_section", "title": "Chapter front matter",
                    "synthetic": True, "parent_id": chapter_node_ids[number], "chapter_number": number,
                    "part_number": chapter.get("part_number"), "part_title": chapter.get("part_title", ""),
                    "section_path": [chapter.get("part_title", ""), chapter.get("title", ""), "Chapter front matter"],
                    "pdf_page_start": min(paragraph_by_id[pid].get("pdf_page_start") or 0 for pid in prefix_ids),
                    "pdf_page_end": max(paragraph_by_id[pid].get("pdf_page_end") or 0 for pid in prefix_ids),
                    "printed_page_start": paragraph_by_id[prefix_ids[0]].get("printed_page_start"),
                    "printed_page_end": paragraph_by_id[prefix_ids[-1]].get("printed_page_end"),
                    "paragraph_ids": prefix_ids, "source_page_ids": unique(page_id for pid in prefix_ids for page_id in paragraph_by_id[pid].get("source_page_ids", [])),
                    "status": STATUS, "verification_status": STATUS,
                })

        for spec_index, spec in enumerate(section_specs):
            next_start = section_specs[spec_index + 1]["start_index"] if spec_index + 1 < len(section_specs) else 10**9
            ids = [pid for pid in chapter_ids if spec["start_index"] <= paragraph_order[pid] < next_start]
            # If the page-based fallback created an empty major section, keep
            # the structure node but let the following section own the text.
            if not ids and spec_index + 1 < len(section_specs):
                continue
            chapter = chapter_by_number[number]
            add_node({
                "unit_id": spec["unit_id"], "level": "major_section", "title": spec["title"],
                "synthetic": False, "outline_index": spec.get("outline_index"), "parent_id": chapter_node_ids[number],
                "chapter_number": number, "part_number": chapter.get("part_number"), "part_title": chapter.get("part_title", ""),
                "section_path": [chapter.get("part_title", ""), chapter.get("title", ""), spec["title"]],
                "pdf_page_start": spec.get("pdf_page_start"), "pdf_page_end": chapter.get("pdf_page_end"),
                "printed_page_start": spec.get("printed_page_start"), "printed_page_end": chapter.get("printed_page_end"),
                "paragraph_ids": ids, "source_page_ids": unique(page_id for pid in ids for page_id in paragraph_by_id[pid].get("source_page_ids", [])),
                "outline_anchor": spec.get("anchor"), "status": STATUS, "verification_status": STATUS,
            })

    # Recalculate major ranges so their page end and printed end are accurate.
    for number, specs in major_by_chapter.items():
        majors = [nodes[spec["unit_id"]] for spec in specs if spec["unit_id"] in nodes]
        front_id = f"{BOOK_ID}-CH-{number}-FRONT-MATTER"
        if front_id in nodes:
            majors = [nodes[front_id]] + majors
        majors.sort(key=lambda node: min((paragraph_order.get(pid, 10**9) for pid in node.get("paragraph_ids", [])), default=10**9))
        for index, node in enumerate(majors):
            ids = node.get("paragraph_ids", [])
            if ids:
                node["pdf_page_start"] = min(paragraph_by_id[pid].get("pdf_page_start") or node.get("pdf_page_start") or 0 for pid in ids)
                node["pdf_page_end"] = max(paragraph_by_id[pid].get("pdf_page_end") or node.get("pdf_page_end") or 0 for pid in ids)
                node["printed_page_start"] = paragraph_by_id[ids[0]].get("printed_page_start") or node.get("printed_page_start")
                node["printed_page_end"] = paragraph_by_id[ids[-1]].get("printed_page_end") or node.get("printed_page_end")

    # Subsections are anchored by paragraph_title layout detections. Each
    # heading starts a new source block. Identical headings already represented
    # by the PDF outline stay at major-section level.
    for number, chapter_node_id in chapter_node_ids.items():
        chapter_node = nodes[chapter_node_id]
        major_ids = [child for child in children[chapter_node_id] if nodes[child]["level"] == "major_section"]
        major_ids.sort(key=lambda node_id: min((paragraph_order.get(pid, 10**9) for pid in nodes[node_id].get("paragraph_ids", [])), default=10**9))
        chapter_pids = set(chapter_paragraphs.get(number, []))
        chapter_anchors = [anchor for anchor in anchors if chapter_pids.intersection(anchor["paragraph_ids"])]
        chapter_anchors.sort(key=lambda anchor: (min(paragraph_order.get(pid, 10**9) for pid in anchor["paragraph_ids"]), anchor["anchor_id"]))
        for major_id in major_ids:
            major = nodes[major_id]
            major_pids = major.get("paragraph_ids", [])
            if not major_pids:
                continue
            lo = min(paragraph_order[pid] for pid in major_pids)
            hi = max(paragraph_order[pid] for pid in major_pids)
            outline_title = normalized(major.get("title"))
            candidates = []
            seen: set[tuple[str, str]] = set()
            for anchor in chapter_anchors:
                anchor_order = min(paragraph_order.get(pid, 10**9) for pid in anchor["paragraph_ids"])
                key = (anchor["normalized_title"], anchor["paragraph_ids"][0])
                if not (lo <= anchor_order <= hi) or key in seen:
                    continue
                # The outline heading itself is not also a subsection.
                if outline_title and (anchor["normalized_title"] == outline_title or outline_title in anchor["normalized_title"]):
                    continue
                seen.add(key)
                candidates.append(anchor)
            candidates.sort(key=lambda anchor: (min(paragraph_order.get(pid, 10**9) for pid in anchor["paragraph_ids"]), anchor["anchor_id"]))
            if not candidates:
                continue
            for sub_index, anchor in enumerate(candidates, 1):
                start = min(paragraph_order.get(pid, 10**9) for pid in anchor["paragraph_ids"])
                same_start = any(
                    min(paragraph_order.get(pid, 10**9) for pid in previous_anchor["paragraph_ids"]) == start
                    for previous_anchor in candidates[:sub_index - 1]
                )
                next_starts = [
                    min(paragraph_order.get(pid, 10**9) for pid in next_anchor["paragraph_ids"])
                    for next_anchor in candidates[sub_index:]
                    if min(paragraph_order.get(pid, 10**9) for pid in next_anchor["paragraph_ids"]) > start
                ]
                end = min(next_starts, default=hi + 1) - 1
                # When multiple title boxes are in one source paragraph, the
                # first heading owns the block and later headings are retained
                # as heading-only anchors instead of duplicating the paragraph.
                ids = [] if same_start else [pid for pid in major_pids if start <= paragraph_order[pid] <= end]
                unit_id = f"{major_id}-SUB-{sub_index:03d}"
                chapter = chapter_by_number[number]
                add_node({
                    "unit_id": unit_id, "level": "subsection", "title": anchor["title"],
                    "synthetic": False, "parent_id": major_id, "chapter_number": number,
                    "part_number": chapter.get("part_number"), "part_title": chapter.get("part_title", ""),
                    "section_path": major.get("section_path", []) + [anchor["title"]],
                    "pdf_page_start": min((paragraph_by_id[pid].get("pdf_page_start") or 0 for pid in ids), default=anchor["pdf_page"]),
                    "pdf_page_end": max((paragraph_by_id[pid].get("pdf_page_end") or 0 for pid in ids), default=anchor["pdf_page"]),
                    "printed_page_start": (paragraph_by_id[ids[0]].get("printed_page_start") if ids else anchor.get("printed_page")),
                    "printed_page_end": (paragraph_by_id[ids[-1]].get("printed_page_end") if ids else anchor.get("printed_page")),
                    "paragraph_ids": ids, "source_page_ids": unique(page_id for pid in ids for page_id in paragraph_by_id[pid].get("source_page_ids", [])),
                    "heading_anchor": anchor, "status": STATUS, "verification_status": STATUS,
                })
            # A paragraph block can precede the first detected lower-level
            # heading (or sit between two heading boxes). Keep that content in
            # a clearly labelled synthetic subsection rather than silently
            # dropping it from the leaf extraction layer.
            covered = {pid for child_id in children[major_id] for pid in nodes[child_id].get("paragraph_ids", [])}
            residual = [pid for pid in major_pids if pid not in covered]
            if residual:
                unit_id = f"{major_id}-SUB-UNHEADED"
                chapter = chapter_by_number[number]
                add_node({
                    "unit_id": unit_id, "level": "subsection", "title": "Unheaded source content",
                    "synthetic": True, "parent_id": major_id, "chapter_number": number,
                    "part_number": chapter.get("part_number"), "part_title": chapter.get("part_title", ""),
                    "section_path": major.get("section_path", []) + ["Unheaded source content"],
                    "pdf_page_start": min((paragraph_by_id[pid].get("pdf_page_start") or 0 for pid in residual), default=major.get("pdf_page_start")),
                    "pdf_page_end": max((paragraph_by_id[pid].get("pdf_page_end") or 0 for pid in residual), default=major.get("pdf_page_end")),
                    "printed_page_start": paragraph_by_id[residual[0]].get("printed_page_start"),
                    "printed_page_end": paragraph_by_id[residual[-1]].get("printed_page_end"),
                    "paragraph_ids": residual, "source_page_ids": unique(page_id for pid in residual for page_id in paragraph_by_id[pid].get("source_page_ids", [])),
                    "status": STATUS, "verification_status": STATUS,
                })
            child_subs = children[major_id]
            leaf_nodes.extend(child_subs)
            # The major section acts as a leaf only where no lower heading is
            # available. Its paragraphs remain the authoritative extraction.
            if not child_subs:
                leaf_nodes.append(major_id)

    # Front matter and electronic-only chapter content can be leaf majors.
    for node_id, node in nodes.items():
        if node.get("level") == "major_section" and node_id not in leaf_nodes and not children.get(node_id):
            leaf_nodes.append(node_id)

    # A paragraph belongs to its narrowest assigned leaf. Preserve a fallback
    # to the major section if a heading-only subsection did not receive a block.
    for leaf_id in leaf_nodes:
        for pid in nodes[leaf_id].get("paragraph_ids", []):
            paragraph_to_leaf.setdefault(pid, leaf_id)
    for number, ids in chapter_paragraphs.items():
        for pid in ids:
            if pid not in paragraph_to_leaf:
                chapter_node_id = chapter_node_ids[number]
                major_ids = [child for child in children[chapter_node_id] if nodes[child]["level"] == "major_section"]
                target = next((mid for mid in major_ids if pid in nodes[mid].get("paragraph_ids", [])), chapter_node_id)
                paragraph_to_leaf[pid] = target

    # Propagate paragraph/source page membership to all parents.
    for node in nodes.values():
        descendants = [node["unit_id"]]
        stack = list(children.get(node["unit_id"], []))
        while stack:
            current = stack.pop()
            descendants.append(current)
            stack.extend(children.get(current, []))
        if node.get("level") in {"part", "chapter"}:
            node["paragraph_ids"] = unique(pid for child_id in descendants for pid in nodes[child_id].get("paragraph_ids", []))
            node["paragraph_ids"].sort(key=lambda pid: paragraph_order.get(pid, 10**9))
            node["source_page_ids"] = unique(page_id for pid in node["paragraph_ids"] for page_id in paragraph_by_id.get(pid, {}).get("source_page_ids", []))

    # Attach visuals to the narrowest leaf whose page range contains the visual.
    leaf_by_chapter: dict[str, list[str]] = defaultdict(list)
    for leaf_id in leaf_nodes:
        node = nodes[leaf_id]
        leaf_by_chapter[str(node.get("chapter_number"))].append(leaf_id)
    for values in leaf_by_chapter.values():
        values.sort(key=lambda node_id: (nodes[node_id].get("pdf_page_end", 10**9) - nodes[node_id].get("pdf_page_start", 0), node_id))
    visual_to_leaf: dict[str, str] = {}
    table_to_leaf: dict[str, str] = {}
    for visual in visual_manifest.get("visual_locations", []):
        chapter_number = visual.get("chapter_number")
        if chapter_number is None:
            continue
        page = visual.get("pdf_page")
        candidates = [node_id for node_id in leaf_by_chapter.get(str(chapter_number), []) if nodes[node_id].get("pdf_page_start", 10**9) <= page <= nodes[node_id].get("pdf_page_end", -1)]
        if not candidates:
            continue
        target = candidates[0]
        visual_to_leaf[visual["visual_id"]] = target
        nodes[target].setdefault("visual_ids", []).append(visual["visual_id"])
        if visual.get("table_id"):
            table_to_leaf[visual["table_id"]] = target
            nodes[target].setdefault("table_ids", []).append(visual["table_id"])
    for node in nodes.values():
        node["visual_ids"] = unique(node.get("visual_ids", []))
        node["table_ids"] = unique(node.get("table_ids", []))

    # Child IDs are emitted in source order, not object insertion order.
    for node_id, child_ids in children.items():
        children[node_id] = sorted(child_ids, key=lambda cid: (nodes[cid].get("pdf_page_start", 10**9), cid))
    for node in nodes.values():
        node["child_ids"] = children.get(node["unit_id"], [])
        node["keyword_record_ids"] = []
        node["visual_keyword_record_ids"] = []

    structure_output = {
        "schema_version": "vtc-stroke-rehabilitation-5e.hierarchical-structure.v1",
        "record_type": "hierarchical_extraction_structure",
        "book_id": BOOK_ID,
        "title": TITLE,
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "processing_order": ["subsection", "major_section", "chapter", "part"],
        "structure_policy": {
            "major_sections": "PDF outline entries, with synthetic Chapter front matter only where chapter text precedes the first outline entry.",
            "subsections": "PaddleOCR paragraph_title boxes matched to clean reading-order lines; headings are retained as source-linked anchors.",
            "paragraphs": "Reconstructed clean paragraphs and list items from the existing visual-excluded text layer.",
            "page_mapping": "Paragraph source-page ranges are used; same-page outline entries are resolved by matched heading anchors.",
        },
        "derived_from": {
            "clean_sections_paragraphs": "02 Text and Tables/stroke_rehab_sections_paragraphs_full_generated.json",
            "clean_reading_order": "02 Text and Tables/stroke_rehab_clean_reading_order_full_generated.jsonl",
            "book_structure": "03 Analysis/stroke_rehab_book_structure_generated.json",
            "layout_inventory": "01 OCR and Layout/stroke_rehab_layout_inventory_generated.json",
            "visual_manifest": "02 Text and Tables/stroke_rehab_visual_locations_and_tables_full_generated.json",
        },
        "nodes": list(nodes.values()),
        "counts": {
            "parts": sum(node.get("level") == "part" for node in nodes.values()),
            "chapters": sum(node.get("level") == "chapter" for node in nodes.values()),
            "major_sections": sum(node.get("level") == "major_section" for node in nodes.values()),
            "subsections": sum(node.get("level") == "subsection" for node in nodes.values()),
            "leaf_units": len(unique(leaf_nodes)),
            "paragraphs_assigned_to_leaf": len(paragraph_to_leaf),
            "visuals_assigned_to_leaf": len(visual_to_leaf),
            "tables_assigned_to_leaf": len(table_to_leaf),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    return structure_output, nodes, paragraph_by_id, {
        "paragraph_to_leaf": paragraph_to_leaf,
        "leaf_nodes": unique(leaf_nodes),
        "children": children,
        "chapter_by_number": chapter_by_number,
        "visual_to_leaf": visual_to_leaf,
        "table_to_leaf": table_to_leaf,
    }


def build_keywords(
    nodes: dict[str, dict[str, Any]], metadata: dict[str, Any], paragraph_by_id: dict[str, dict[str, Any]],
    visual_manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    leaf_ids = metadata["leaf_nodes"]
    table_by_id = {table.get("table_id"): table for table in visual_manifest.get("tables", [])}
    visual_by_id = {visual.get("visual_id"): visual for visual in visual_manifest.get("visual_locations", [])}
    all_text = " ".join(clean(paragraph_by_id[pid].get("text", "")) for pid in paragraph_by_id)
    global_counts = Counter(token_list(all_text))
    records: list[dict[str, Any]] = []
    keyword_ids_by_node: dict[str, list[str]] = defaultdict(list)

    for leaf_id in leaf_ids:
        node = nodes[leaf_id]
        paragraph_text = " ".join(paragraph_by_id[pid].get("text", "") for pid in node.get("paragraph_ids", []) if pid in paragraph_by_id)
        table_texts = []
        for table_id in node.get("table_ids", []):
            table = table_by_id.get(table_id, {})
            table_texts.append(table.get("content", {}).get("text", ""))
        source_text = clean(paragraph_text + " " + " ".join(table_texts))
        title = clean(node.get("title", ""))
        candidates: list[tuple[str, str, str]] = []
        if title:
            candidates.append(("section_topic", title, title))
        local = Counter(token_list(source_text))
        for term, count in local.most_common():
            if len(candidates) >= 16:
                break
            if len(term) < 4 or term in STOPWORDS or count < 1:
                continue
            if global_counts[term] < 2 and term not in set(token_list(title)):
                continue
            candidates.append((broad_area(term, title), term, term))
        # Add a small number of stable multiword terms from the subsection
        # heading; these are particularly useful for other AI systems.
        title_tokens = [token for token in token_list(title) if token not in STOPWORDS]
        if len(title_tokens) >= 2:
            for index in range(len(title_tokens) - 1):
                phrase = " ".join(title_tokens[index:index + 2])
                candidates.append((broad_area(phrase, title), phrase, phrase))
        seen_terms: set[str] = set()
        for index, (category, small_area, source_form) in enumerate(candidates, 1):
            key = normalized(small_area)
            if not key or key in seen_terms:
                continue
            seen_terms.add(key)
            record_id = f"{BOOK_ID}-KW-{leaf_id}-{index:03d}"
            record = {
                "record_id": record_id,
                "unit_id": leaf_id,
                "level": node.get("level"),
                "category": category,
                "broad_area": category,
                "small_area": small_area,
                "keyword_path": [category, small_area],
                "source_form": source_form,
                "canonical_candidate": small_area,
                "retrieval_terms": unique([small_area, small_area.lower()]),
                "source_passage_ids": node.get("paragraph_ids", []),
                "source_page_ids": node.get("source_page_ids", []),
                "status": STATUS,
                "verification_status": STATUS,
            }
            records.append(record)
            keyword_ids_by_node[leaf_id].append(record_id)

        for visual_id in node.get("visual_ids", []):
            visual = visual_by_id.get(visual_id, {})
            if visual.get("table_id"):
                table = table_by_id.get(visual["table_id"], {})
                table_title = clean(table.get("name") or (table.get("caption") or {}).get("text") or "")
                if table_title:
                    record_id = f"{BOOK_ID}-KW-{visual_id}-TABLE"
                    records.append({
                        "record_id": record_id, "unit_id": leaf_id, "level": node.get("level"),
                        "category": "visual_table", "broad_area": "visual_table", "small_area": table_title,
                        "keyword_path": ["visual_table", table_title], "source_form": table_title,
                        "canonical_candidate": table_title, "retrieval_terms": unique([table_title, table_title.lower()]),
                        "source_element_ids": [visual_id, visual["table_id"]], "source_page_ids": [visual.get("source_page_id")],
                        "status": STATUS, "verification_status": STATUS,
                    })
                    keyword_ids_by_node[leaf_id].append(record_id)

    # Merge leaf IDs upward without re-extracting parent prose.
    for node in sorted(nodes.values(), key=lambda item: {"subsection": 4, "major_section": 3, "chapter": 2, "part": 1}.get(item.get("level"), 0), reverse=True):
        child_ids = node.get("child_ids", [])
        if child_ids:
            keyword_ids_by_node[node["unit_id"]] = unique(
                record_id for child_id in child_ids for record_id in keyword_ids_by_node.get(child_id, [])
            )
    for node_id, values in keyword_ids_by_node.items():
        nodes[node_id]["keyword_record_ids"] = unique(values)
    return records, keyword_ids_by_node


def list_groups_for(paragraph_ids: list[str], paragraph_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pid in paragraph_ids:
        paragraph = paragraph_by_id.get(pid, {})
        group_id = paragraph.get("list_group_id")
        if group_id:
            groups[group_id].append(paragraph)
    result = []
    for group_id, items in groups.items():
        items.sort(key=lambda item: (item.get("list_item_index") or 0, item.get("paragraph_id", "")))
        result.append({
            "list_group_id": group_id,
            "item_count": len(items),
            "items": [{
                "source_passage_id": item.get("paragraph_id"), "item_index": item.get("list_item_index"),
                "text": item.get("text", ""), "source_page_ids": item.get("source_page_ids", []),
            } for item in items],
            "status": STATUS, "verification_status": STATUS,
        })
    return result


def build_extractions_and_summaries(
    structure_output: dict[str, Any], nodes: dict[str, dict[str, Any]], metadata: dict[str, Any],
    paragraph_by_id: dict[str, dict[str, Any]], visual_manifest: dict[str, Any], source: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    chapter_by_number = metadata["chapter_by_number"]
    children = metadata["children"]
    leaf_ids = metadata["leaf_nodes"]
    table_by_id = {table.get("table_id"): table for table in visual_manifest.get("tables", [])}
    visual_by_id = {visual.get("visual_id"): visual for visual in visual_manifest.get("visual_locations", [])}

    leaf_extractions: list[dict[str, Any]] = []
    summaries_by_id: dict[str, dict[str, Any]] = {}
    unit_order = {node["unit_id"]: index for index, node in enumerate(structure_output["nodes"])}

    def node_pages(node: dict[str, Any]) -> list[int]:
        pages = [paragraph_by_id[pid].get("pdf_page_start") for pid in node.get("paragraph_ids", []) if pid in paragraph_by_id]
        return [int(page) for page in pages if page is not None]

    def node_reference(node: dict[str, Any]) -> dict[str, Any]:
        number = str(node.get("chapter_number"))
        chapter = chapter_by_number.get(number, node)
        pids = node.get("paragraph_ids", [])
        pages = node_pages(node)
        page_ids = unique(page_id for pid in pids for page_id in paragraph_by_id.get(pid, {}).get("source_page_ids", []))
        printed = [paragraph_by_id[pid].get("printed_page_start") for pid in pids if pid in paragraph_by_id]
        printed_end = [paragraph_by_id[pid].get("printed_page_end") for pid in pids if pid in paragraph_by_id]
        reference = page_reference(
            source, chapter, node.get("title", ""),
            min(pages) if pages else node.get("pdf_page_start"), max(pages) if pages else node.get("pdf_page_end"),
            next((value for value in printed if value), node.get("printed_page_start")),
            next((value for value in reversed(printed_end) if value), node.get("printed_page_end")),
            pids, page_ids, level=node.get("level"), part_number=node.get("part_number"), part_title=node.get("title"),
        )
        reference["section_path"] = node.get("section_path", [])
        return reference

    for leaf_id in leaf_ids:
        node = nodes[leaf_id]
        pids = node.get("paragraph_ids", [])
        quote_candidates = []
        for pid in pids:
            paragraph = paragraph_by_id.get(pid, {})
            if paragraph.get("content_type") == "list_item":
                continue
            text = clean(paragraph.get("text", ""))
            if len(text) < 50:
                continue
            quote_candidates.append({
                "source_passage_id": pid, "text": text[:700], "quote_type": "quotation_candidate",
                "exact_quote_eligible": False, "status": STATUS, "verification_status": STATUS,
            })
            if len(quote_candidates) >= 2:
                break
        references = [node_reference(node)]
        for quote_index, quote in enumerate(quote_candidates, 1):
            quote["evidence_id"] = f"{leaf_id}-QUOTE-{quote_index:03d}"
            quote["quotation"] = quote.pop("text")
            quote["reference"] = references[0]["formatted"]
            quote["in_text_citation"] = references[0]["short_form"]
        extraction_record = {
            "unit_id": leaf_id, "level": node.get("level"), "title": node.get("title", ""),
            "section_path": node.get("section_path", []), "parent_id": node.get("parent_id"),
            "source_passage_ids": pids, "source_page_ids": references[0]["source_page_ids"],
            "pdf_page_start": references[0]["pdf_page_start"], "pdf_page_end": references[0]["pdf_page_end"],
            "printed_page_start": references[0]["printed_page_start"], "printed_page_end": references[0]["printed_page_end"],
            "list_groups": list_groups_for(pids, paragraph_by_id),
            "visual_element_ids": node.get("visual_ids", []), "table_ids": node.get("table_ids", []),
            "visual_policy": "Tables are referenced as reconstructed table records; non-table visuals retain location/name only.",
            "quotation_candidates": quote_candidates, "references": references,
            "keyword_record_ids": node.get("keyword_record_ids", []),
            "status": STATUS, "verification_status": STATUS,
        }
        leaf_extractions.append(extraction_record)
        prose = [paragraph_by_id[pid].get("text", "") for pid in pids if paragraph_by_id.get(pid, {}).get("content_type") != "list_item"]
        summary, sentences = extractive_summary(prose, 4)
        summaries_by_id[leaf_id] = {
            "unit_id": leaf_id, "level": node.get("level"), "title": node.get("title", ""),
            "parent_id": node.get("parent_id"), "section_path": node.get("section_path", []),
            "pdf_page_start": references[0]["pdf_page_start"], "pdf_page_end": references[0]["pdf_page_end"],
            "printed_page_start": references[0]["printed_page_start"], "printed_page_end": references[0]["printed_page_end"],
            "source_passage_ids": pids, "source_passage_count": len(pids),
            "source_page_ids": references[0]["source_page_ids"], "summary": summary,
            "summary_sentences": sentences, "summary_method": "extractive_source_sentences_at_leaf_unit",
            "child_summary_ids": [], "keyword_record_ids": node.get("keyword_record_ids", []),
            "visual_element_ids": node.get("visual_ids", []), "table_ids": node.get("table_ids", []),
            "references": references, "status": STATUS, "verification_status": STATUS,
        }

    # Parent summaries merge only completed child summaries.
    level_rank = {"subsection": 4, "major_section": 3, "chapter": 2, "part": 1}
    for node in sorted(nodes.values(), key=lambda item: (level_rank.get(item.get("level"), 0), unit_order.get(item["unit_id"], 0)), reverse=True):
        if node["unit_id"] in summaries_by_id:
            continue
        child_ids = [child_id for child_id in children.get(node["unit_id"], []) if child_id in summaries_by_id]
        child_summaries = [summaries_by_id[child_id] for child_id in child_ids]
        summary, sentences = extractive_summary([item.get("summary", "") for item in child_summaries], 6 if node.get("level") == "part" else 5)
        pids = node.get("paragraph_ids", [])
        reference = node_reference(node)
        summaries_by_id[node["unit_id"]] = {
            "unit_id": node["unit_id"], "level": node.get("level"), "title": node.get("title", ""),
            "parent_id": node.get("parent_id"), "section_path": node.get("section_path", []),
            "pdf_page_start": reference["pdf_page_start"], "pdf_page_end": reference["pdf_page_end"],
            "printed_page_start": reference["printed_page_start"], "printed_page_end": reference["printed_page_end"],
            "source_passage_ids": pids, "source_passage_count": len(pids), "source_page_ids": reference["source_page_ids"],
            "summary": summary, "summary_sentences": sentences,
            "summary_method": "extractive_child_summary_merge", "child_summary_ids": child_ids,
            "keyword_record_ids": node.get("keyword_record_ids", []),
            "visual_element_ids": node.get("visual_ids", []), "table_ids": node.get("table_ids", []),
            "references": [reference], "status": STATUS, "verification_status": STATUS,
        }

    visual_extractions = []
    for visual in visual_manifest.get("visual_locations", []):
        target = metadata["visual_to_leaf"].get(visual.get("visual_id"))
        record = {
            "visual_id": visual.get("visual_id"), "unit_id": target, "table_id": visual.get("table_id"),
            "visual_role": visual.get("visual_role"), "label": visual.get("label"), "name": visual.get("name"),
            "caption": visual.get("caption"), "pdf_page": visual.get("pdf_page"), "printed_page": visual.get("printed_page"),
            "source_page_id": visual.get("source_page_id"), "location_description": visual.get("location_description"),
            "content_reconstruction": visual.get("content_reconstruction"),
            "table_record_path": visual.get("table_id"),
            "status": STATUS, "verification_status": STATUS,
        }
        if visual.get("table_id") and visual.get("table_id") in table_by_id:
            table = table_by_id[visual["table_id"]]
            record["table_name"] = table.get("name")
            record["table_row_count"] = table.get("content", {}).get("row_count")
            record["table_column_count"] = table.get("content", {}).get("max_column_count")
            record["table_content_source"] = "02 Text and Tables/stroke_rehab_visual_locations_and_tables_full_generated.json"
        visual_extractions.append(record)

    analysis = {
        "schema_version": "vtc-stroke-rehabilitation-5e.multi-level-extraction.v1",
        "record_type": "multi_level_source_extraction",
        "book_id": BOOK_ID, "title": TITLE, "source": source,
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "processing_order": ["subsection", "major_section", "chapter", "part"],
        "extraction_policy": {
            "text": "Use reconstructed clean reading-order paragraphs with visual contents excluded.",
            "point_form": "List groups and item order are copied into leaf extraction records and are not flattened into prose summaries.",
            "tables": "Use reconstructed table records, preserving table IDs, row/column counts, and source page references.",
            "non_table_visuals": "Keep page, location, label, and available name/caption only; no visual-content OCR or reconstruction.",
            "quotation": "Quotation candidates are source excerpts only; exact_quote_eligible remains false until manual review.",
            "verification": "All derived extraction, summaries, keywords, and visual interpretations are generated_not_verified.",
        },
        "derived_from": structure_output.get("derived_from", {}),
        "leaf_extractions": leaf_extractions,
        "visual_extractions": visual_extractions,
        "counts": {
            "leaf_extractions": len(leaf_extractions), "quotation_candidates": sum(len(item["quotation_candidates"]) for item in leaf_extractions),
            "list_groups": sum(len(item["list_groups"]) for item in leaf_extractions), "visual_extractions": len(visual_extractions),
            "table_extractions": sum(1 for item in visual_extractions if item.get("table_id")),
        },
        "status": STATUS, "verification_status": STATUS,
    }
    summary_output = {
        "schema_version": "vtc-stroke-rehabilitation-5e.hierarchical-summaries.v1",
        "record_type": "hierarchical_summaries",
        "book_id": BOOK_ID, "title": TITLE,
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "processing_order": ["subsection", "major_section", "chapter", "part"],
        "summary_policy": "Leaf units use extractive source sentences. Parent units merge child summaries only; they do not perform paragraph-by-paragraph re-extraction.",
        "units": sorted(summaries_by_id.values(), key=lambda item: (level_rank.get(item.get("level"), 0), item.get("pdf_page_start") or 0, item.get("unit_id", ""))),
        "counts": {
            "parts": sum(item.get("level") == "part" for item in summaries_by_id.values()),
            "chapters": sum(item.get("level") == "chapter" for item in summaries_by_id.values()),
            "major_sections": sum(item.get("level") == "major_section" for item in summaries_by_id.values()),
            "subsections": sum(item.get("level") == "subsection" for item in summaries_by_id.values()),
            "nonempty_summaries": sum(bool(item.get("summary")) for item in summaries_by_id.values()),
        },
        "status": STATUS, "verification_status": STATUS,
    }
    return analysis, summary_output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--clean-pages", type=Path, required=True)
    parser.add_argument("--visual-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    extraction = load_json(args.extraction)
    book_structure = load_json(args.structure)
    layout = load_json(args.layout)
    visual_manifest = load_json(args.visual_manifest)
    clean_pages = {}
    with args.clean_pages.open(encoding="utf-8") as stream:
        for line in stream:
            page = json.loads(line)
            clean_pages[int(page["pdf_page"])] = page
    paragraphs = extraction.get("paragraphs", [])
    anchors = build_title_anchors(layout, clean_pages, paragraphs)
    source = extraction.get("source", {})
    structure_output, nodes, paragraph_by_id, metadata = build_hierarchy(book_structure, extraction, anchors, visual_manifest)
    keyword_records, _ = build_keywords(nodes, metadata, paragraph_by_id, visual_manifest)
    analysis, summaries = build_extractions_and_summaries(structure_output, nodes, metadata, paragraph_by_id, visual_manifest, source)
    analysis["anchors"] = anchors
    analysis["counts"]["paragraph_title_anchors"] = len(anchors)
    analysis["keyword_record_count"] = len(keyword_records)
    keyword_output = {
        "schema_version": "vtc-stroke-rehabilitation-5e.keyword-extraction.v1",
        "record_type": "hierarchical_keyword_extraction",
        "book_id": BOOK_ID, "title": TITLE,
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "processing_order": ["subsection", "major_section", "chapter", "part"],
        "keyword_policy": {
            "leaf_extraction": "Candidate keywords are extracted at the narrowest available structured unit; parent units merge record IDs only.",
            "broad_and_small": "Each record contains broad_area/category and small_area/source_form with a broad-to-small keyword_path.",
            "visuals": "Reconstructed tables contribute table-title candidates; non-table visuals contribute metadata only.",
            "status": "Candidates are not verified against the page image.",
        },
        "records": keyword_records,
        "node_keyword_record_ids": {node_id: node.get("keyword_record_ids", []) for node_id, node in nodes.items()},
        "counts": {"records": len(keyword_records), "nodes_with_keywords": sum(bool(node.get("keyword_record_ids")) for node in nodes.values())},
        "status": STATUS, "verification_status": STATUS,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "structure": args.output_dir / "stroke_rehab_hierarchical_structure_generated.json",
        "extractions": args.output_dir / "stroke_rehab_multi_level_extractions_generated.json",
        "summaries": args.output_dir / "stroke_rehab_hierarchical_summaries_generated.json",
        "keywords": args.output_dir / "stroke_rehab_keyword_extraction_generated.json",
    }
    if not args.overwrite:
        existing = [str(path) for path in outputs.values() if path.exists()]
        if existing:
            raise SystemExit(f"Outputs exist; pass --overwrite: {existing}")
    outputs["structure"].write_text(json.dumps(structure_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs["extractions"].write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs["summaries"].write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs["keywords"].write_text(json.dumps(keyword_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outputs": {key: str(path) for key, path in outputs.items()}, "counts": {"structure": structure_output["counts"], "extractions": analysis["counts"], "summaries": summaries["counts"], "keywords": keyword_output["counts"]}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

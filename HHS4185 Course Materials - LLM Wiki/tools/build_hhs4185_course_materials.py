#!/usr/bin/env python3
"""Build the course-first HHS4185 slide-material LLM Wiki package.

The source PDFs are never modified.  This pipeline keeps embedded PDF text,
PaddleOCR output, layout candidates, reconstructed tables, non-table visual
locations, page keywords, document parts, summaries, and portable retrieval
indexes as separate generated layers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


TOOLS_DIR = Path(__file__).resolve().parents[2] / "Davidson 25th Edition - LLM Wiki" / "tools"
sys.path.insert(0, str(TOOLS_DIR))
from build_davidson_retrieval_index import (  # noqa: E402
    CATEGORY_LABELS,
    STATUS,
    TOKEN_RE,
    alias_variants,
    category_for,
    clean_text,
    display_form,
    normalize,
    token_candidates,
)


COURSE_CODE = "HHS4185"
SCHEMA_VERSION = "vtc-hhs4185-course-materials.v1"
PAGE_NS = {"x": "http://www.w3.org/1999/xhtml"}
PAGE_TAG = "{http://www.w3.org/1999/xhtml}page"
TEXT_LABELS = {
    "text", "title", "doc_title", "header", "footer", "paragraph", "list",
    "reference", "footnote", "page_number", "caption", "formula",
}
NON_TABLE_LABELS = {
    "image", "figure", "chart", "graph", "diagram", "illustration", "seal",
    "algorithm", "flowchart", "equation", "formula", "table", "infographic",
}
CJK_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_OR_DIGIT_RE = re.compile(r"[A-Za-z0-9]")
LIST_MARKER_RE = re.compile(r"^\s*(?P<marker>[•●▪◦◉➢➤→⇒↔]+|[-–—])(?:\s+|$)")
LIST_MARKER_CHARS = "•●▪◦◉➢➤→⇒↔"


DOCUMENTS = [
    {
        "document_id": "HHS4185-L1",
        "file_name": "HHS4185_L1.pdf",
        "source_type": "lecture",
        "lecture_number": 1,
        "title": "Lecture 1 - Joint problems: osteoarthritis, rheumatology, ankylosing spondylitis and joint replacement",
    },
    {
        "document_id": "HHS4185-L2",
        "file_name": "HHS4185_L2.pdf",
        "source_type": "lecture",
        "lecture_number": 2,
        "title": "Lecture 2 - Bone problems: osteoporosis, fracture and amputation",
    },
    {
        "document_id": "HHS4185J-L2",
        "file_name": "HHS4185J_L2.pdf",
        "source_type": "lecture_bilingual",
        "lecture_number": 2,
        "title": "Lecture 2 bilingual deck - Bone problems: osteoporosis, fracture and amputation",
    },
    {
        "document_id": "HHS4185-WS1",
        "file_name": "HHS4185_WS1_Equipment.pdf",
        "source_type": "workshop",
        "workshop_number": 1,
        "title": "Workshop 1 - Introduction to rehabilitation equipment",
    },
    {
        "document_id": "HHS4185-T1-ICF",
        "file_name": "HHS4185_T1_ICF.pdf",
        "source_type": "tutorial",
        "tutorial_number": 1,
        "title": "Tutorial 1 - ICF",
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def run_text_command(command: list[str]) -> str:
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode("utf-8", errors="replace")


def pdf_page_count(path: Path) -> int:
    text = run_text_command(["pdfinfo", str(path)])
    match = re.search(r"^Pages:\s+(\d+)", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Unable to read page count: {path}")
    return int(match.group(1))


def trace_image_pages(path: Path) -> dict[int, list[dict[str, Any]]]:
    """Return fast, page-level image locations from MuPDF's trace output.

    This is the non-Paddle fallback for slide PDFs.  It preserves embedded
    image objects and their page coordinates, but deliberately does not claim
    that an image is a table or reconstruct its contents.  Such candidates
    can be sent to targeted PaddleOCR later.
    """
    trace_xml = subprocess.run(
        ["mutool", "draw", "-F", "trace", "-o", "-", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.decode("utf-8", errors="replace")
    page_images: dict[int, list[dict[str, Any]]] = {}
    # Use a small tag parser rather than parsing the whole trace as XML: the
    # trace format can contain raw < or & in accessibility text attributes.
    page_pattern = re.compile(r'<page\s+number="(\d+)"\s+mediabox="([^"]+)">(.*?)</page>', re.DOTALL)
    attr_pattern = re.compile(r'(\w+)="([^"]*)"')
    for page_match in page_pattern.finditer(trace_xml):
        page_number = int(page_match.group(1))
        mediabox = [float(value) for value in page_match.group(2).split()]
        page_width = mediabox[2] - mediabox[0]
        page_height = mediabox[3] - mediabox[1]
        images: list[dict[str, Any]] = []
        for image_index, image_match in enumerate(re.finditer(r"<fill_image\b([^>]*)/>", page_match.group(3))):
            attributes = dict(attr_pattern.findall(image_match.group(1)))
            transform = [float(value) for value in attributes.get("transform", "0 0 0 0 0 0").split()]
            if len(transform) != 6:
                continue
            x, y = transform[4], transform[5]
            width, height = abs(transform[0]), abs(transform[3])
            if width <= 0 or height <= 0:
                continue
            # Skip recurring tiny logos and image masks; retain page-sized
            # images when they are the only visual object on a slide.
            if width <= 130 and height <= 40:
                continue
            images.append({
                "image_index": image_index,
                "bbox_points": [round(x, 3), round(y, 3), round(x + width, 3), round(y + height, 3)],
                "width_points": round(width, 3),
                "height_points": round(height, 3),
                "pixel_width": attributes.get("width"),
                "pixel_height": attributes.get("height"),
                "full_page": width >= page_width * 0.95 and height >= page_height * 0.95,
                "source": "mutool-trace-embedded-image-object",
            })
        page_images[page_number] = images
    return page_images


def strip_xml_controls(value: str) -> str:
    return "".join(ch for ch in value if ch in "\t\n\r" or ord(ch) >= 32)


def parse_bbox_pages(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(strip_xml_controls(xml_text))
    pages: list[dict[str, Any]] = []
    for pdf_page, page_element in enumerate(root.findall(".//x:page", PAGE_NS), 1):
        width = float(page_element.attrib.get("width", 0))
        height = float(page_element.attrib.get("height", 0))
        lines: list[dict[str, Any]] = []
        for line_index, line in enumerate(page_element.findall(".//x:line", PAGE_NS)):
            words: list[dict[str, Any]] = []
            for word in line.findall("x:word", PAGE_NS):
                text = word.text or ""
                words.append({
                    "text": text,
                    "bbox_points": [
                        float(word.attrib.get("xMin", 0)),
                        float(word.attrib.get("yMin", 0)),
                        float(word.attrib.get("xMax", 0)),
                        float(word.attrib.get("yMax", 0)),
                    ],
                })
            if not words:
                continue
            bbox = [
                min(word["bbox_points"][0] for word in words),
                min(word["bbox_points"][1] for word in words),
                max(word["bbox_points"][2] for word in words),
                max(word["bbox_points"][3] for word in words),
            ]
            lines.append({
                "line_index": line_index,
                "bbox_points": [round(value, 3) for value in bbox],
                "text": " ".join(word["text"] for word in words).strip(),
                "words": words,
            })
        pages.append({"pdf_page": pdf_page, "width_points": width, "height_points": height, "lines": lines})
    return pages


def reading_order_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(lines, key=lambda line: (line["bbox_points"][1], line["bbox_points"][0]))
    return [line for line in ordered if clean_text(line.get("text"))]


def line_height(line: dict[str, Any]) -> float:
    bbox = line.get("bbox_points", [0, 0, 0, 0])
    return float(bbox[3] - bbox[1])


def split_list_marker(text: str) -> tuple[str, str]:
    match = LIST_MARKER_RE.match(text)
    if not match:
        return "", text
    return match.group("marker"), text[match.end():].strip()


def english_text_from_line(text: str) -> tuple[str, str]:
    """Keep the English layer while preserving a leading list marker.

    The slide exports frequently place the Chinese and English versions on
    adjacent text runs.  We retain source lines that have useful English
    content, discard Chinese-only runs, and keep a marker separately so a
    standalone duplicated bullet can be attached to the next English line.
    """
    text = clean_text(text)
    marker, body = split_list_marker(text)
    if not body:
        return "", marker
    pieces = [piece.strip() for piece in CJK_RE.split(body)]
    english_pieces = [piece for piece in pieces if LATIN_OR_DIGIT_RE.search(piece)]
    if not english_pieces:
        return "", marker
    candidate = clean_text(" ".join(english_pieces))
    candidate = re.sub(r"\s+([,.;:!?%)\]])", r"\1", candidate)
    candidate = re.sub(r"([([])\s+", r"\1", candidate)
    candidate = re.sub(r"\s+([/])\s+", r"\1", candidate)
    if not candidate:
        return "", marker
    if CJK_RE.search(text):
        alpha_numeric = re.sub(r"[^A-Za-z0-9]", "", candidate)
        long_tokens = re.findall(r"[A-Za-z]{4,}", candidate)
        # Avoid retaining isolated English abbreviations/units from a
        # Chinese run such as `T分數` or `BMD (以 g/cm2...)`.  Standalone
        # bilingual headings such as `Arthritis 關節炎` remain useful.
        if len(alpha_numeric) < 3 or (not long_tokens and len(alpha_numeric) < 8):
            return "", marker
        # A marker-bearing mixed run is normally the Chinese copy of a
        # separate English bullet.  The marker is carried forward below.
        if marker:
            return "", marker
    return (f"{marker} {candidate}" if marker else candidate).strip(), marker


def english_line_records(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    pending_markers: list[str] = []
    for line in reading_order_lines(lines):
        raw_text = clean_text(line.get("text", ""))
        text, marker = english_text_from_line(raw_text)
        if not text:
            if marker:
                pending_markers.append(marker)
            continue
        if marker:
            pending_markers.clear()
        elif pending_markers:
            text = f"{pending_markers[0]} {text}".strip()
            marker = pending_markers[0]
            pending_markers.clear()
        records.append({
            "source_line_index": line.get("line_index"),
            "bbox_points": line.get("bbox_points", [0, 0, 0, 0]),
            "text": text,
            "language": "en",
            "marker": marker or None,
        })
    if pending_markers:
        # Preserve an unmatched marker rather than silently losing a point
        # form glyph at the end of a slide.
        records.append({
            "source_line_index": None,
            "bbox_points": [0, 0, 0, 0],
            "text": pending_markers[0],
            "language": "en",
            "marker": pending_markers[0],
        })
    if records:
        base_x = min(float(item.get("bbox_points", [0, 0, 0, 0])[0]) for item in records if item.get("bbox_points"))
        for item in records:
            bbox = item.get("bbox_points", [base_x, 0, base_x, 0])
            indent_points = max(0.0, float(bbox[0]) - base_x)
            item["indent_points"] = round(indent_points, 3)
            item["indent_level"] = int(round(indent_points / 24.0))
    return records


def derived_page_text(page: dict[str, Any]) -> str:
    """Return only the English derived layer, never the raw bilingual layer."""
    return page.get("reading_order_text") or page.get("ocr_text_english") or ""


def useful_slide_lines(page: dict[str, Any]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for line in reading_order_lines(page.get("lines", [])):
        text = clean_text(line.get("text", ""))
        lowered = normalize(text)
        if not text or lowered in {"ive", "healthandlifesciences", "allrightsreserved"}:
            continue
        if re.fullmatch(r"\d{1,3}", text):
            continue
        if "higherdiplomainrehabilitationservices" in lowered:
            continue
        if "復康服務高級文憑" in lowered:
            continue
        if "commonrehabilitationconditions" in lowered and len(text) < 90:
            continue
        if re.match(r"(?i)^(?:lecturer|講師|m\s*s\.?|ms\.?)\b", text):
            continue
        filtered.append({**line, "text": text})
    return english_line_records(filtered)


def slide_title(page: dict[str, Any]) -> str:
    lines = useful_slide_lines(page)
    if not lines:
        return ""
    candidates = [line for line in lines if len(line["text"]) <= 140]
    if not candidates:
        return lines[0]["text"][:140]
    chosen = max(candidates, key=lambda line: (line_height(line), -line["bbox_points"][1]))
    return chosen["text"]


def unwrap_paddle(result: Any) -> dict[str, Any]:
    value = result.json
    if callable(value):
        value = value()
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and isinstance(value.get("res"), dict):
        value = value["res"]
    return value if isinstance(value, dict) else {}


def ocr_page(ocr: Any, image_path: Path) -> dict[str, Any]:
    value = unwrap_paddle(next(iter(ocr.predict(str(image_path)))))
    texts = value.get("rec_texts", []) or []
    scores = value.get("rec_scores", []) or []
    boxes = value.get("rec_boxes", []) or []
    regions: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        box = boxes[index] if index < len(boxes) else None
        score = scores[index] if index < len(scores) else None
        regions.append({"text": text, "score": score, "bbox_px": box})
    regions.sort(key=lambda item: ((item.get("bbox_px") or [0, 0])[1], (item.get("bbox_px") or [0, 0])[0]))
    english_regions = []
    pending_marker = ""
    for item in regions:
        text, marker = english_text_from_line(str(item.get("text", "")))
        if not text:
            pending_marker = marker or pending_marker
            continue
        if pending_marker and not marker:
            text = f"{pending_marker} {text}".strip()
            pending_marker = ""
        elif marker:
            pending_marker = ""
        english_regions.append(text)
    return {
        "text": "\n".join(str(item["text"]) for item in regions if item.get("text")),
        "english_text": "\n".join(english_regions),
        "regions": regions,
        "mean_score": (sum(float(item["score"]) for item in regions if item.get("score") is not None) / len([item for item in regions if item.get("score") is not None])) if any(item.get("score") is not None for item in regions) else None,
    }


def layout_page(layout: Any, image_path: Path, dpi: int) -> list[dict[str, Any]]:
    value = unwrap_paddle(next(iter(layout.predict(str(image_path)))))
    boxes: list[dict[str, Any]] = []
    scale = 72.0 / dpi
    for index, box in enumerate(value.get("boxes", []) or []):
        coordinate = box.get("coordinate", [0, 0, 0, 0])
        boxes.append({
            "layout_id": index,
            "label": box.get("label"),
            "class_id": box.get("cls_id"),
            "confidence": box.get("score"),
            "bbox_px": coordinate,
            "bbox_points": [round(float(value) * scale, 3) for value in coordinate],
            "is_visual_candidate": str(box.get("label", "")).casefold() not in TEXT_LABELS,
        })
    return boxes


def overlap_ratio(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    area = max(0.0, right - left) * max(0.0, bottom - top)
    base = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    return area / base if base else 0.0


def words_in_bbox(lines: list[dict[str, Any]], bbox: list[float]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for line in lines:
        for word in line.get("words", []):
            wb = word["bbox_points"]
            center = ((wb[0] + wb[2]) / 2, (wb[1] + wb[3]) / 2)
            if bbox[0] <= center[0] <= bbox[2] and bbox[1] <= center[1] <= bbox[3]:
                words.append(word)
    return words


def reconstruct_table(table_id: str, visual_id: str, page: dict[str, Any], bbox: list[float], name: str) -> dict[str, Any]:
    words = words_in_bbox(page.get("lines", []), bbox)
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda item: (item["bbox_points"][1], item["bbox_points"][0])):
        y = word["bbox_points"][1]
        target = next((row for row in rows if abs(row[0]["bbox_points"][1] - y) <= 5), None)
        if target is None:
            rows.append([word])
        else:
            target.append(word)
    row_records = []
    for row_index, row in enumerate(rows):
        row.sort(key=lambda item: item["bbox_points"][0])
        row_records.append({
            "source_row_index": row_index,
            "text": " ".join(item["text"] for item in row),
            "cells": [
                {"text": item["text"], "bbox_points": item["bbox_points"]}
                for item in row
            ],
        })
    return {
        "table_id": table_id,
        "visual_id": visual_id,
        "name": name,
        "source_page_id": page["source_page_id"],
        "pdf_page": page["pdf_page"],
        "slide_number": page["pdf_page"],
        "bbox_points": bbox,
        "coordinate_rows": row_records,
        "content": {
            "text": "\n".join(row["text"] for row in row_records),
            "rows": row_records,
        },
        "reconstruction_method": "embedded-PDF-word-coordinates-with-layout-bbox",
        "status": STATUS,
        "verification_status": STATUS,
    }


def caption_near(page: dict[str, Any], bbox: list[float]) -> str | None:
    candidates = []
    for line in useful_slide_lines(page):
        text = line["text"]
        if re.match(r"(?i)^(fig(?:ure)?|table|box|chart|diagram)\b", text):
            line_bbox = line["bbox_points"]
            distance = abs(line_bbox[1] - bbox[3]) if line_bbox[1] >= bbox[3] else abs(bbox[1] - line_bbox[3])
            candidates.append((distance, text))
    if candidates:
        return sorted(candidates)[0][1]
    return None


def source_page_reference(document: dict[str, Any], page: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_page_id": page["source_page_id"],
        "document_id": document["document_id"],
        "document_title": document["title"],
        "source_file": document["file_name"],
        "page_number": page["pdf_page"],
        "page_number_type": "slide_number",
        "slide_number": page["pdf_page"],
        "pdf_page": page["pdf_page"],
        "formatted": f"{document['file_name']}, slide {page['pdf_page']} (PDF p. {page['pdf_page']})",
    }


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean_text(text)) if len(part.strip()) >= 35]


def extractive_summary(texts: list[str], max_sentences: int = 5) -> tuple[str, list[str]]:
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
        fallback = [clean_text(text) for text in texts if clean_text(text)]
        sentences = fallback[:max_sentences]
    return " ".join(sentences), sentences


def document_source_path(course_root: Path, document: dict[str, Any]) -> Path:
    for folder in ("(2) Lecture Materials", "(3) Workshop and Practice Materials"):
        path = course_root / folder / document["file_name"]
        if path.exists():
            return path
    raise FileNotFoundError(f"Canonical course PDF not found: {document['file_name']}")


def collect_pages(course_root: Path, dpi: int, paddle_cache: Path, skip_paddle: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_pages: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    ocr = layout = None
    if not skip_paddle:
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(paddle_cache)
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        from paddleocr import PaddleOCR, LayoutDetection
        ocr = PaddleOCR(lang="en", device="cpu", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
        layout = LayoutDetection(model_name="PP-DocLayout_plus-L", device="cpu")

    for document in DOCUMENTS:
        source = document_source_path(course_root, document)
        count = pdf_page_count(source)
        document_manifest = {
            **document,
            "source_path": str(source),
            "source_sha256": sha256_file(source),
            "pdf_page_count": count,
            "status": STATUS,
            "verification_status": STATUS,
        }
        manifest.append(document_manifest)
        bbox_xml = run_text_command(["pdftotext", "-bbox-layout", "-enc", "UTF-8", str(source), "-"])
        bbox_pages = parse_bbox_pages(bbox_xml)
        if len(bbox_pages) != count:
            raise RuntimeError(f"BBox page count mismatch for {source}: {len(bbox_pages)} != {count}")
        trace_pages = trace_image_pages(source)
        with tempfile.TemporaryDirectory(prefix=f"{document['document_id']}-") as temp_dir:
            temp_path = Path(temp_dir)
            prefix = temp_path / "slide"
            subprocess.run(["pdftoppm", "-png", "-r", str(dpi), str(source), str(prefix)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            images = sorted(temp_path.glob("slide-*.png"))
            if len(images) != count:
                raise RuntimeError(f"Rendered page count mismatch for {source}: {len(images)} != {count}")
            for page_number, bbox_page in enumerate(bbox_pages, 1):
                page_id = f"{document['document_id']}-P{page_number:04d}"
                page = {
                    "source_page_id": page_id,
                    "document_id": document["document_id"],
                    "document_title": document["title"],
                    "source_file": document["file_name"],
                    "source_type": document["source_type"],
                    "pdf_page": page_number,
                    "slide_number": page_number,
                    "width_points": bbox_page["width_points"],
                    "height_points": bbox_page["height_points"],
                    "lines": bbox_page["lines"],
                    "embedded_text": "\n".join(line["text"] for line in reading_order_lines(bbox_page["lines"])),
                    "reading_order_lines": useful_slide_lines({"lines": bbox_page["lines"]}),
                    "title_candidate": slide_title(bbox_page),
                    "embedded_image_objects": trace_pages.get(page_number, []),
                    "status": STATUS,
                    "verification_status": STATUS,
                }
                if ocr and layout:
                    ocr_result = ocr_page(ocr, images[page_number - 1])
                    page["ocr_text"] = ocr_result["text"]
                    page["ocr_text_english"] = ocr_result["english_text"]
                    page["ocr_regions"] = ocr_result["regions"]
                    page["ocr_mean_score"] = ocr_result["mean_score"]
                    page["ocr_status"] = "completed"
                    page["layout_boxes"] = layout_page(layout, images[page_number - 1], dpi)
                    page["layout_status"] = "completed"
                else:
                    page["ocr_text"] = None
                    page["ocr_text_english"] = None
                    page["ocr_regions"] = []
                    page["ocr_mean_score"] = None
                    page["ocr_status"] = "skipped"
                    page["layout_boxes"] = []
                    page["layout_status"] = "skipped"
                page["reading_order_text"] = "\n".join(line["text"] for line in page["reading_order_lines"])
                all_pages.append(page)
    return manifest, all_pages


def build_parts(documents: list[dict[str, Any]], pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    parts: list[dict[str, Any]] = []
    page_to_part: dict[str, str] = {}
    for document in documents:
        doc_pages = [page for page in pages if page["document_id"] == document["document_id"]]
        candidates = []
        for page in doc_pages:
            lines = useful_slide_lines(page)
            title = page.get("title_candidate", "")
            lowered = clean_text(title).casefold()
            compact_title = normalize(title)
            is_reference_or_footer = (
                not title
                or lowered in {"reference", "reference list", "american heart association, 2022"}
                or re.fullmatch(r"(?:\d{1,2}/){2}\d{2,4}", clean_text(title))
                or lowered.startswith(("m s ", "ms ", "mr ", "mrs ", "lecturer", "protection,"))
                or compact_title.startswith("preparedby")
                or (lowered.startswith("(naso et al") and len(title) < 80)
                or (re.search(r"\bet al\.?\b", lowered) and len(title) < 80)
            )
            if is_reference_or_footer or len(lines) > 8:
                continue
            if len(title) >= 4:
                candidates.append(page)
        if not candidates or candidates[0]["pdf_page"] != 1:
            candidates.insert(0, doc_pages[0])
        starts = []
        for page in candidates:
            if not starts or page["pdf_page"] != starts[-1]["pdf_page"]:
                starts.append(page)
        for index, start in enumerate(starts, 1):
            end_page = starts[index]["pdf_page"] - 1 if index < len(starts) else doc_pages[-1]["pdf_page"]
            part_id = f"{document['document_id']}-PART{index:02d}"
            part_pages = [page for page in doc_pages if start["pdf_page"] <= page["pdf_page"] <= end_page]
            part = {
                "unit_id": part_id,
                "level": "part",
                "document_id": document["document_id"],
                "document_title": document["title"],
                "title": start.get("title_candidate") or f"Part {index}",
                "slide_start": start["pdf_page"],
                "slide_end": end_page,
                "pdf_page_start": start["pdf_page"],
                "pdf_page_end": end_page,
                "source_page_ids": [page["source_page_id"] for page in part_pages],
                "status": STATUS,
                "verification_status": STATUS,
            }
            parts.append(part)
            for page in part_pages:
                page_to_part[page["source_page_id"]] = part_id
    return parts, page_to_part


def page_visuals(pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    visuals: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    for page in pages:
        visual_boxes = [box for box in page.get("layout_boxes", []) if box.get("is_visual_candidate")]
        if not visual_boxes:
            # Slide PDFs commonly contain embedded images even when the
            # heavyweight layout model is skipped.  Use their MuPDF trace
            # coordinates as page-level visual candidates.
            visual_boxes = [
                {
                    "layout_id": image["image_index"],
                    "label": "image",
                    "confidence": None,
                    "bbox_px": None,
                    "bbox_points": image["bbox_points"],
                    "is_visual_candidate": True,
                    "fallback_source": image["source"],
                    "full_page": image.get("full_page", False),
                }
                for image in page.get("embedded_image_objects", [])
            ]
        table_index = 0
        for box in visual_boxes:
            label = str(box.get("label") or "non_table_visual").casefold()
            if label not in NON_TABLE_LABELS and label not in {"table", "image"}:
                continue
            bbox = box["bbox_points"]
            caption = caption_near(page, bbox)
            visual_id = f"{page['document_id']}-VIS-P{page['pdf_page']:04d}-C{box['layout_id']:04d}"
            is_table = label == "table" or bool(caption and re.match(r"(?i)^table\b", caption))
            page_title = page.get("title_candidate") or f"Slide {page['pdf_page']}"
            name = caption or ("Table on slide %d" % page["pdf_page"] if is_table else f"Visual associated with: {page_title}")
            table_id = None
            if is_table:
                table_index += 1
                table_id = f"{page['document_id']}-TBL-P{page['pdf_page']:04d}-C{table_index:02d}"
                tables.append(reconstruct_table(table_id, visual_id, page, bbox, name))
            visuals.append({
                "visual_id": visual_id,
                "table_id": table_id,
                "document_id": page["document_id"],
                "source_page_id": page["source_page_id"],
                "source_file": page["source_file"],
                "pdf_page": page["pdf_page"],
                "slide_number": page["pdf_page"],
                "visual_type": "table" if is_table else label,
                "name": name,
                "caption": caption,
                "location": {
                    "bbox_points": bbox,
                    "bbox_px": box.get("bbox_px"),
                    "coordinate_origin": "top-left",
                    "location_source": box.get("fallback_source", "paddle-layout-detection"),
                },
                "policy": "full_table_reconstruction" if is_table else "metadata_only",
                "status": STATUS,
                "verification_status": STATUS,
            })
    return visuals, tables


def build_structure(documents: list[dict[str, Any]], pages: list[dict[str, Any]], parts: list[dict[str, Any]], page_to_part: dict[str, str], visuals: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    node_by_id: dict[str, dict[str, Any]] = {}
    course_id = "HHS4185-COURSE"
    course_node = {
        "section_id": course_id,
        "level": "course",
        "course_code": COURSE_CODE,
        "title": "HHS4185 - Common Rehabilitation Conditions",
        "children": [],
        "status": STATUS,
        "verification_status": STATUS,
    }
    nodes.append(course_node)
    node_by_id[course_id] = course_node
    for document in documents:
        doc_id = document["document_id"]
        doc_pages = [page for page in pages if page["document_id"] == doc_id]
        doc_node = {
            "section_id": doc_id,
            "level": "document",
            "course_code": COURSE_CODE,
            "document_id": doc_id,
            "title": document["title"],
            "source_file": document["file_name"],
            "parent_id": course_id,
            "children": [],
            "slide_start": 1,
            "slide_end": len(doc_pages),
            "pdf_page_start": 1,
            "pdf_page_end": len(doc_pages),
            "status": STATUS,
            "verification_status": STATUS,
        }
        nodes.append(doc_node)
        node_by_id[doc_id] = doc_node
        course_node["children"].append(doc_id)
        doc_parts = [part for part in parts if part["document_id"] == doc_id]
        for part in doc_parts:
            part_node = {
                "section_id": part["unit_id"],
                "level": "part",
                "course_code": COURSE_CODE,
                "document_id": doc_id,
                "title": part["title"],
                "parent_id": doc_id,
                "children": [],
                "slide_start": part["slide_start"],
                "slide_end": part["slide_end"],
                "pdf_page_start": part["pdf_page_start"],
                "pdf_page_end": part["pdf_page_end"],
                "source_page_ids": part["source_page_ids"],
                "visual_ids": [],
                "status": STATUS,
                "verification_status": STATUS,
            }
            nodes.append(part_node)
            node_by_id[part["unit_id"]] = part_node
            doc_node["children"].append(part["unit_id"])
            for page in doc_pages:
                if page_to_part.get(page["source_page_id"]) != part["unit_id"]:
                    continue
                slide_id = page["source_page_id"]
                slide_node = {
                    "section_id": slide_id,
                    "level": "slide",
                    "course_code": COURSE_CODE,
                    "document_id": doc_id,
                    "title": page.get("title_candidate") or f"Slide {page['pdf_page']}",
                    "parent_id": part["unit_id"],
                    "children": [],
                    "slide_number": page["pdf_page"],
                    "pdf_page": page["pdf_page"],
                    "source_page_id": slide_id,
                    "visual_ids": [visual["visual_id"] for visual in visuals if visual["source_page_id"] == slide_id],
                    "status": STATUS,
                    "verification_status": STATUS,
                }
                nodes.append(slide_node)
                node_by_id[slide_id] = slide_node
                part_node["children"].append(slide_id)
                part_node["visual_ids"].extend(slide_node["visual_ids"])
    for node in nodes:
        node["visual_ids"] = list(dict.fromkeys(node.get("visual_ids", [])))
    structure = {
        "schema_version": "vtc-hhs4185.course-structure.v1",
        "record_type": "course_material_structure_lookup",
        "book_id": COURSE_CODE,
        "hierarchy_order": ["course", "document", "part", "slide"],
        "processing_order": ["slide", "part", "document", "course"],
        "course": course_node,
        "nodes": nodes,
        "counts": {
            "documents": len(documents),
            "parts": sum(node["level"] == "part" for node in nodes),
            "slides": sum(node["level"] == "slide" for node in nodes),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    return structure, node_by_id


def build_analysis(documents: list[dict[str, Any]], pages: list[dict[str, Any]], parts: list[dict[str, Any]], page_to_part: dict[str, str], visuals: list[dict[str, Any]], tables: list[dict[str, Any]], node_by_id: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    all_text = [derived_page_text(page) for page in pages]
    all_text.extend(visual.get("name", "") or "" for visual in visuals)
    all_text.extend(table.get("content", {}).get("text", "") for table in tables)
    global_counts = Counter(normalize(token) for text in all_text for token in TOKEN_RE.findall(text) if normalize(token))
    page_records: list[dict[str, Any]] = []
    keyword_records: list[dict[str, Any]] = []
    occurrence_source: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        page_id = page["source_page_id"]
        ancestors = [page_id, page_to_part.get(page_id, ""), page["document_id"], "HHS4185-COURSE"]
        local = token_candidates(derived_page_text(page), global_counts, source_kind="paragraph")
        records = []
        for index, ((category, term_key), forms) in enumerate(sorted(local.items()), 1):
            source_form = display_form(forms, term_key)
            record_id = f"HHS4185-KW-{page_id}-{index:03d}"
            record = {
                "record_id": record_id,
                "category": category,
                "broad_area": CATEGORY_LABELS.get(category, category),
                "small_area": source_form,
                "keyword_path": [CATEGORY_LABELS.get(category, category), source_form],
                "source_form": source_form,
                "canonical_candidate": source_form,
                "retrieval_terms": alias_variants(source_form),
                "source_passage_ids": [f"{page_id}-PASSAGE"],
                "source_page_ids": [page_id],
                "section_ids": [value for value in ancestors if value],
                "source_excerpt": clean_text(derived_page_text(page))[:500],
                "status": STATUS,
                "verification_status": STATUS,
            }
            records.append(record)
            keyword_records.append(record)
            occurrence_source[record_id].append(page_id)
        page_records.append({
            "source_page_id": page_id,
            "document_id": page["document_id"],
            "slide_number": page["pdf_page"],
            "section_ids": [value for value in ancestors if value],
            "keyword_records": records,
            "keyword_record_count": len(records),
            "status": STATUS,
            "verification_status": STATUS,
        })

    summary_units: list[dict[str, Any]] = []
    for part in parts:
        part_pages = [page for page in pages if page_to_part.get(page["source_page_id"]) == part["unit_id"]]
        summary, sentences = extractive_summary([derived_page_text(page) for page in part_pages])
        summary_units.append({
            "unit_id": part["unit_id"],
            "level": "part",
            "document_id": part["document_id"],
            "title": part["title"],
            "parent_id": part["document_id"],
            "slide_start": part["slide_start"],
            "slide_end": part["slide_end"],
            "source_page_ids": part["source_page_ids"],
            "summary": summary,
            "summary_sentences": sentences,
            "summary_method": "extractive_source_sentences_at_part_candidate",
            "status": STATUS,
            "verification_status": STATUS,
        })
    for document in documents:
        doc_pages = [page for page in pages if page["document_id"] == document["document_id"]]
        summary, sentences = extractive_summary([derived_page_text(page) for page in doc_pages], 8)
        summary_units.append({
            "unit_id": document["document_id"],
            "level": "document",
            "title": document["title"],
            "parent_id": "HHS4185-COURSE",
            "slide_start": 1,
            "slide_end": len(doc_pages),
            "source_page_ids": [page["source_page_id"] for page in doc_pages],
            "summary": summary,
            "summary_sentences": sentences,
            "summary_method": "extractive_child_part_summary_merge",
            "child_summary_ids": [part["unit_id"] for part in parts if part["document_id"] == document["document_id"]],
            "status": STATUS,
            "verification_status": STATUS,
        })
    course_summary, course_sentences = extractive_summary([unit["summary"] for unit in summary_units if unit["level"] == "document"], 10)
    summary_units.append({
        "unit_id": "HHS4185-COURSE",
        "level": "course",
        "title": "HHS4185 - Common Rehabilitation Conditions",
        "parent_id": None,
        "source_page_ids": [page["source_page_id"] for page in pages],
        "summary": course_summary,
        "summary_sentences": course_sentences,
        "summary_method": "extractive_child_document_summary_merge",
        "child_summary_ids": [document["document_id"] for document in documents],
        "status": STATUS,
        "verification_status": STATUS,
    })
    analysis = {
        "schema_version": "vtc-hhs4185.course-analysis.v1",
        "record_type": "course_material_analysis",
        "book_id": COURSE_CODE,
        "processing_order": ["page", "part", "document", "course"],
        "page_keyword_extractions": page_records,
        "keyword_records": keyword_records,
        "summary_units": summary_units,
        "counts": {
            "pages": len(pages),
            "keyword_records": len(keyword_records),
            "parts": len(parts),
            "documents": len(documents),
            "summary_units": len(summary_units),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    return analysis, {record["record_id"]: record for record in keyword_records}


def build_retrieval_indexes(documents: list[dict[str, Any]], pages: list[dict[str, Any]], parts: list[dict[str, Any]], page_to_part: dict[str, str], visuals: list[dict[str, Any]], tables: list[dict[str, Any]], analysis: dict[str, Any], structure: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    page_by_id = {page["source_page_id"]: page for page in pages}
    visual_by_id = {visual["visual_id"]: visual for visual in visuals}
    table_by_id = {table["table_id"]: table for table in tables}
    summary_by_id = {unit["unit_id"]: unit for unit in analysis["summary_units"]}
    concepts: list[dict[str, Any]] = []
    occurrences: list[dict[str, Any]] = []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in analysis["keyword_records"]:
        groups[(record["category"], normalize(record["canonical_candidate"]))].append(record)
    for concept_index, ((category, term_key), records) in enumerate(sorted(groups.items()), 1):
        concept_id = f"HHS4185-C-{concept_index:07d}"
        source_forms = list(dict.fromkeys(record["source_form"] for record in records))
        preferred = display_form(source_forms, term_key)
        retrieval_terms = list(dict.fromkeys(alias for form in [preferred] + source_forms for alias in alias_variants(form)))
        occurrence_ids = []
        section_ids = []
        for record in records:
            occurrence_id = f"HHS4185-O-{len(occurrences) + 1:08d}"
            occurrence_ids.append(occurrence_id)
            section_ids.extend(record.get("section_ids", []))
            pages_ref = [source_page_reference(next(doc for doc in documents if doc["document_id"] == page_by_id[page_id]["document_id"]), page_by_id[page_id]) for page_id in record.get("source_page_ids", []) if page_id in page_by_id]
            occurrences.append({
                "occurrence_id": occurrence_id,
                "concept_id": concept_id,
                "category": category,
                "broad_area": CATEGORY_LABELS.get(category, category),
                "small_area": preferred,
                "keyword_path": [CATEGORY_LABELS.get(category, category), preferred],
                "source_form": record["source_form"],
                "source_passage_ids": record.get("source_passage_ids", []),
                "source_element_ids": record.get("source_element_ids", []),
                "source_page_ids": record.get("source_page_ids", []),
                "source_pages": pages_ref,
                "section_ids": list(dict.fromkeys(record.get("section_ids", []))),
                "source_excerpt": record.get("source_excerpt", ""),
                "retrieval_terms": retrieval_terms,
                "status": STATUS,
                "verification_status": STATUS,
            })
        concepts.append({
            "concept_id": concept_id,
            "category": category,
            "broad_area": CATEGORY_LABELS.get(category, category),
            "preferred_label": preferred,
            "canonical_candidate": preferred,
            "keyword_path": [CATEGORY_LABELS.get(category, category), preferred],
            "source_forms": source_forms,
            "retrieval_terms": retrieval_terms,
            "occurrence_ids": occurrence_ids,
            "occurrence_count": len(occurrence_ids),
            "section_ids": list(dict.fromkeys(section_ids)),
            "status": STATUS,
            "verification_status": STATUS,
        })
    concept_by_id = {concept["concept_id"]: concept for concept in concepts}
    term_map: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"display_forms": set(), "concept_ids": set(), "occurrence_ids": set(), "categories": set()})
    for concept in concepts:
        for term in concept["retrieval_terms"]:
            key = normalize(term)
            if not key:
                continue
            term_map[key]["display_forms"].add(term)
            term_map[key]["concept_ids"].add(concept["concept_id"])
            term_map[key]["occurrence_ids"].update(concept["occurrence_ids"])
            term_map[key]["categories"].add(concept["category"])
    term_lookup = {
        "schema_version": "llm-wiki.term-lookup-index.v1-course",
        "record_type": "term_lookup_index",
        "book_id": COURSE_CODE,
        "source_priority": "course_materials",
        "terms": {
            key: {
                "display_forms": sorted(value["display_forms"]),
                "concept_ids": sorted(value["concept_ids"]),
                "occurrence_ids": sorted(value["occurrence_ids"]),
                "categories": sorted(value["categories"]),
            }
            for key, value in sorted(term_map.items())
        },
        "counts": {"terms": len(term_map), "concepts_referenced": len(concepts), "occurrences_referenced": len(occurrences)},
        "status": STATUS,
        "verification_status": STATUS,
    }
    passage_lines = []
    for page in pages:
        document = next(doc for doc in documents if doc["document_id"] == page["document_id"])
        page_id = page["source_page_id"]
        part_id = page_to_part.get(page_id)
        path = ["HHS4185 - Common Rehabilitation Conditions", document["title"], summary_by_id.get(part_id, {}).get("title", ""), page.get("title_candidate") or f"Slide {page['pdf_page']}"]
        passage_lines.append({
            "source_passage_id": f"{page_id}-PASSAGE",
            "text": derived_page_text(page),
            "document_id": document["document_id"],
            "document_title": document["title"],
            "source_file": document["file_name"],
            "source_page_ids": [page_id],
            "source_pages": [source_page_reference(document, page)],
            "slide_number": page["pdf_page"],
            "section_ids": [value for value in [page_id, part_id, document["document_id"], "HHS4185-COURSE"] if value],
            "section_path": [value for value in path if value],
            "content_type": "slide_text",
            "ocr_text": page.get("ocr_text"),
            "status": STATUS,
            "verification_status": STATUS,
        })
    visual_entries = []
    for visual in visuals:
        document = next(doc for doc in documents if doc["document_id"] == visual["document_id"])
        page = page_by_id[visual["source_page_id"]]
        part_id = page_to_part.get(page["source_page_id"])
        entry = {
            **visual,
            "page_reference": source_page_reference(document, page),
            "section_ids": [value for value in [page["source_page_id"], part_id, document["document_id"], "HHS4185-COURSE"] if value],
            "section_paths": [["HHS4185 - Common Rehabilitation Conditions", document["title"], summary_by_id.get(part_id, {}).get("title", ""), page.get("title_candidate") or f"Slide {page['pdf_page']}"]],
            "table_reconstruction_available": bool(visual.get("table_id")),
            "table_reconstruction_source": "../(3) Text and Tables/hhs4185_tables_generated.json" if visual.get("table_id") else None,
        }
        visual_entries.append(entry)
    structure_nodes = {node["section_id"]: node for node in structure["nodes"]}
    for node in structure_nodes.values():
        node["concept_ids"] = list(dict.fromkeys(concept["concept_id"] for concept in concepts if node["section_id"] in concept.get("section_ids", [])))
    structure["nodes"] = list(structure_nodes.values())
    structure["course"] = structure_nodes["HHS4185-COURSE"]
    validation = {
        "schema_version": "llm-wiki.course-retrieval-validation.v1",
        "record_type": "course_retrieval_validation_report",
        "book_id": COURSE_CODE,
        "checks": {
            "documents_present": len(documents) == len(DOCUMENTS),
            "canonical_sha256_unique": len({document["source_sha256"] for document in documents}) == len(documents),
            "all_pages_have_ocr": all(page.get("ocr_status") == "completed" for page in pages),
            "all_pages_have_layout": all(page.get("layout_status") == "completed" for page in pages),
            "concept_ids_unique": len({concept["concept_id"] for concept in concepts}) == len(concepts),
            "occurrence_ids_unique": len({item["occurrence_id"] for item in occurrences}) == len(occurrences),
            "occurrence_concept_links_resolve": all(item["concept_id"] in concept_by_id for item in occurrences),
            "term_concept_links_resolve": all(set(item["concept_ids"]) <= set(concept_by_id) for item in term_lookup["terms"].values()),
            "passage_count_matches_pages": len(passage_lines) == len(pages),
            "passage_page_references_present": all(item.get("source_pages") and item["source_pages"][0].get("page_number") is not None for item in passage_lines),
            "visual_page_references_present": all(item.get("page_reference", {}).get("page_number") is not None for item in visual_entries),
            "generated_not_verified_preserved": all(item.get("verification_status") == STATUS for item in concepts + occurrences + passage_lines + visual_entries),
        },
        "counts": {
            "documents": len(documents),
            "pages": len(pages),
            "passages": len(passage_lines),
            "parts": len(parts),
            "concepts": len(concepts),
            "occurrences": len(occurrences),
            "terms": len(term_map),
            "visuals": len(visual_entries),
            "tables": len(tables),
        },
        "status": STATUS,
        "verification_status": STATUS,
    }
    return {
        "concept_index": {
            "schema_version": "llm-wiki.concept-index.v1-course",
            "record_type": "concept_index",
            "book_id": COURSE_CODE,
            "source_priority": "course_materials",
            "keyword_taxonomy": CATEGORY_LABELS,
            "concepts": concepts,
            "counts": {"concepts": len(concepts), "occurrences": len(occurrences)},
            "status": STATUS,
            "verification_status": STATUS,
        },
        "occurrence_index": {
            "schema_version": "llm-wiki.occurrence-index.v1-course",
            "record_type": "occurrence_index",
            "book_id": COURSE_CODE,
            "occurrences": occurrences,
            "counts": {"occurrences": len(occurrences)},
            "status": STATUS,
            "verification_status": STATUS,
        },
        "term_lookup": term_lookup,
        "structure": structure,
        "visual_index": {
            "schema_version": "vtc-hhs4185.visual-retrieval-index.v1",
            "record_type": "visual_retrieval_index",
            "book_id": COURSE_CODE,
            "policy": {"tables": "full reconstructed contents", "non_tables": "metadata, name, location, and page only"},
            "visuals": visual_entries,
            "counts": {"visuals": len(visual_entries), "tables": sum(bool(item.get("table_id")) for item in visual_entries), "non_tables": sum(not bool(item.get("table_id")) for item in visual_entries)},
            "status": STATUS,
            "verification_status": STATUS,
        },
        "passage_lines": passage_lines,
        "validation": validation,
    }


def write_outputs(output_root: Path, manifest: list[dict[str, Any]], pages: list[dict[str, Any]], visuals: list[dict[str, Any]], tables: list[dict[str, Any]], analysis: dict[str, Any], indexes: dict[str, Any]) -> None:
    for path in output_root.parents:
        path.mkdir(exist_ok=True)
    (output_root / "(1) Source Inventory").mkdir(parents=True, exist_ok=True)
    (output_root / "(2) OCR and Layout").mkdir(parents=True, exist_ok=True)
    (output_root / "(3) Text and Tables").mkdir(parents=True, exist_ok=True)
    (output_root / "(4) Analysis").mkdir(parents=True, exist_ok=True)
    (output_root / "(5) Retrieval Index").mkdir(parents=True, exist_ok=True)
    def write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_json(output_root / "(1) Source Inventory/hhs4185_course_source_manifest_generated.json", {"schema_version": SCHEMA_VERSION, "record_type": "course_source_manifest", "book_id": COURSE_CODE, "documents": manifest, "status": STATUS, "verification_status": STATUS})
    with (output_root / "(2) OCR and Layout/hhs4185_pages_ocr_layout_generated.jsonl").open("w", encoding="utf-8") as handle:
        for page in pages:
            handle.write(json.dumps(page, ensure_ascii=False) + "\n")
    write_json(output_root / "(3) Text and Tables/hhs4185_visual_manifest_generated.json", {"schema_version": SCHEMA_VERSION, "record_type": "course_visual_manifest", "book_id": COURSE_CODE, "visuals": visuals, "counts": {"visuals": len(visuals), "tables": sum(bool(item.get("table_id")) for item in visuals)}, "status": STATUS, "verification_status": STATUS})
    write_json(output_root / "(3) Text and Tables/hhs4185_tables_generated.json", {"schema_version": SCHEMA_VERSION, "record_type": "course_table_reconstructions", "book_id": COURSE_CODE, "tables": tables, "counts": {"tables": len(tables)}, "status": STATUS, "verification_status": STATUS})
    write_json(output_root / "(4) Analysis/hhs4185_course_analysis_generated.json", analysis)
    write_json(output_root / "(4) Analysis/hhs4185_course_summaries_generated.json", {"schema_version": SCHEMA_VERSION, "record_type": "course_hierarchical_summaries", "book_id": COURSE_CODE, "processing_order": ["slide", "part", "document", "course"], "units": analysis["summary_units"], "status": STATUS, "verification_status": STATUS})
    index_root = output_root / "(5) Retrieval Index"
    for filename, key in (("concept_index.json", "concept_index"), ("occurrence_index.json", "occurrence_index"), ("term_lookup.json", "term_lookup"), ("structure_lookup.json", "structure"), ("visual_index.json", "visual_index"), ("retrieval_index_validation_report.json", "validation")):
        write_json(index_root / filename, indexes[key])
    with (index_root / "passage_index.jsonl").open("w", encoding="utf-8") as handle:
        for line in indexes["passage_lines"]:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs4185-course"))
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output_root.exists() and not args.overwrite:
        raise SystemExit(f"Output exists; pass --overwrite: {args.output_root}")
    manifest, pages = collect_pages(args.course_root, args.dpi, args.paddle_cache, args.skip_paddle)
    documents = [item for item in manifest]
    parts, page_to_part = build_parts(documents, pages)
    visuals, tables = page_visuals(pages)
    structure, node_by_id = build_structure(documents, pages, parts, page_to_part, visuals)
    analysis, _keyword_by_id = build_analysis(documents, pages, parts, page_to_part, visuals, tables, node_by_id)
    indexes = build_retrieval_indexes(documents, pages, parts, page_to_part, visuals, tables, analysis, structure, node_by_id)
    write_outputs(args.output_root, manifest, pages, visuals, tables, analysis, indexes)
    print(json.dumps({"output_root": str(args.output_root), "counts": indexes["validation"]["counts"], "checks": indexes["validation"]["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

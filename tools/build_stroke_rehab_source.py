#!/usr/bin/env python3
"""Build a source-preserving structure and visual-cue map for a stroke book.

This first pass does not OCR visual contents. It records the PDF outline,
part/chapter/section ranges, printed-page labels, embedded-text statistics,
and caption-like visual cues so a later layout pass can be reviewed against
the source pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PAGE_NS = {"x": "http://www.w3.org/1999/xhtml"}
CUE_PATTERNS = (
    ("table", re.compile(r"(?i)\b(?:table|tbl\.?)\s+\d+(?:[.-]\d+)?")),
    ("figure", re.compile(r"(?i)\b(?:figure|fig\.?)\s+\d+(?:[.-]\d+)?")),
    ("case_study", re.compile(r"(?i)\bcase\s+study\b")),
    ("box", re.compile(r"(?i)^\s*box\s+\d+(?:[.-]\d+)?")),
    ("algorithm", re.compile(r"(?i)\balgorithm\s+\d+(?:[.-]\d+)?")),
)


def run(command: list[str]) -> str:
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode("utf-8", errors="replace")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()


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
                words.append(
                    {
                        "text": text,
                        "bbox_points": [
                            float(word.attrib.get("xMin", 0)),
                            float(word.attrib.get("yMin", 0)),
                            float(word.attrib.get("xMax", 0)),
                            float(word.attrib.get("yMax", 0)),
                        ],
                    }
                )
            if not words:
                continue
            bbox = [
                min(word["bbox_points"][0] for word in words),
                min(word["bbox_points"][1] for word in words),
                max(word["bbox_points"][2] for word in words),
                max(word["bbox_points"][3] for word in words),
            ]
            lines.append(
                {
                    "line_index": line_index,
                    "text": clean_text(" ".join(word["text"] for word in words)),
                    "bbox_points": [round(value, 3) for value in bbox],
                    "words": words,
                }
            )
        pages.append(
            {
                "pdf_page": pdf_page,
                "width_points": width,
                "height_points": height,
                "lines": lines,
            }
        )
    return pages


def parse_printed_page(page: dict[str, Any]) -> str | None:
    candidates: list[tuple[float, str]] = []
    for line in page["lines"]:
        for word in line.get("words", []):
            text = clean_text(word["text"])
            x_min, y_min, x_max, y_max = word["bbox_points"]
            # Running headers/footers in this PDF sit at roughly y=26 or
            # y=742 points. A looser threshold catches table/caption numbers
            # near the page edge, so keep the margin deliberately narrow.
            near_edge = y_min <= 45 or y_max >= page["height_points"] - 40
            near_outer_margin = x_min <= 80 or x_max >= page["width_points"] - 77
            if not near_edge or not near_outer_margin:
                continue
            if page["pdf_page"] <= 12 and re.fullmatch(r"\d{1,4}", text):
                continue
            if re.fullmatch(r"\d{1,4}(?:\.e\d{1,3})?", text) or (
                page["pdf_page"] <= 12 and re.fullmatch(r"(?i)[ivxlcdm]{1,12}", text)
            ):
                candidates.append((y_min, text))
    return sorted(candidates)[-1][1] if candidates else None


def infer_contiguous_printed_pages(pages: list[dict[str, Any]], printed: dict[int, str | None]) -> dict[int, str | None]:
    """Fill only gaps bracketed by page labels that advance one-for-one.

    Chapter/part opener pages often suppress the running page number. Inference
    is deliberately conservative: a gap is filled only when the nearest known
    labels on both sides are the same numeric/electronic sequence and the
    difference exactly matches the PDF-page gap.
    """
    result = dict(printed)
    known = sorted(page for page, label in result.items() if label)
    for left_page, right_page in zip(known, known[1:]):
        left = result[left_page]
        right = result[right_page]
        if not left or not right or left_page + 1 >= right_page:
            continue
        numeric = re.fullmatch(r"(\d+)", left)
        right_numeric = re.fullmatch(r"(\d+)", right)
        electronic = re.fullmatch(r"(\d+)\.e(\d+)", left)
        right_electronic = re.fullmatch(r"(\d+)\.e(\d+)", right)
        if numeric and right_numeric:
            left_value, right_value = int(numeric.group(1)), int(right_numeric.group(1))
            if right_value - left_value != right_page - left_page:
                continue
            for pdf_page in range(left_page + 1, right_page):
                result[pdf_page] = str(left_value + pdf_page - left_page)
        elif electronic and right_electronic and electronic.group(1) == right_electronic.group(1):
            left_value, right_value = int(electronic.group(2)), int(right_electronic.group(2))
            if right_value - left_value != right_page - left_page:
                continue
            for pdf_page in range(left_page + 1, right_page):
                result[pdf_page] = f"{electronic.group(1)}.e{left_value + pdf_page - left_page}"
    return result


def parse_outline(source: Path) -> list[dict[str, Any]]:
    raw = run(["mutool", "show", str(source), "outline"])
    rows: list[dict[str, Any]] = []
    pattern = re.compile(r'(?P<kind>[|+-])(?P<tabs>\t*)"(?P<title>.*?)"\s+#page=(?P<page>\d+)')
    for index, line in enumerate(raw.splitlines(), 1):
        match = pattern.match(line)
        if not match:
            continue
        title = clean_text(match.group("title").replace("\\r", ""))
        rows.append(
            {
                "outline_index": index,
                "outline_level": len(match.group("tabs")) - 1,
                "marker": match.group("kind"),
                "title": title,
                "pdf_page": int(match.group("page")),
            }
        )
    return rows


def numbered_title(title: str) -> tuple[str | None, str]:
    match = re.match(r"(?i)^\s*(?P<number>e?\d+)\s*(?:[-–—:]\s*|\s+)(?P<title>.+?)\s*$", title)
    if not match:
        return None, title.strip()
    return match.group("number"), match.group("title").strip()


def structure_from_outline(outline: list[dict[str, Any]], pages: list[dict[str, Any]]) -> dict[str, Any]:
    page_lookup = {page["pdf_page"]: page for page in pages}
    printed = infer_contiguous_printed_pages(
        pages,
        {page["pdf_page"]: parse_printed_page(page) for page in pages},
    )
    parts: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    electronic_chapters: list[dict[str, Any]] = []
    front_matter: list[dict[str, Any]] = []
    back_matter: list[dict[str, Any]] = []
    current_part: dict[str, Any] | None = None
    current_chapter: dict[str, Any] | None = None
    for row in outline:
        number, title = numbered_title(row["title"])
        if number == "e31":
            electronic_chapters.append(
                {
                    "chapter_number": number,
                    "title": title,
                    "pdf_page_start": row["pdf_page"],
                    "printed_page_start": printed.get(row["pdf_page"]),
                    "outline_index": row["outline_index"],
                    "content_status": "included_in_pdf_but_listed_as_electronic_only_in_contents",
                }
            )
            current_chapter = None
            continue
        if row["outline_level"] == 0:
            if row["marker"] == "-" and number in {"1", "2", "3"}:
                current_part = {
                    "part_number": int(number),
                    "title": title,
                    "pdf_page_start": row["pdf_page"],
                    "printed_page_start": printed.get(row["pdf_page"]),
                    "outline_index": row["outline_index"],
                    "chapters": [],
                }
                parts.append(current_part)
                current_chapter = None
            else:
                item = {
                    "title": row["title"],
                    "pdf_page_start": row["pdf_page"],
                    "printed_page_start": printed.get(row["pdf_page"]),
                    "outline_index": row["outline_index"],
                }
                target = front_matter if not parts else back_matter
                target.append(item)

        elif row["outline_level"] == 1 and current_part and row["marker"] == "-":
            chapter = {
                "chapter_number": number,
                "title": title,
                "pdf_page_start": row["pdf_page"],
                "printed_page_start": printed.get(row["pdf_page"]),
                "outline_index": row["outline_index"],
                "sections": [],
            }
            current_part["chapters"].append(chapter)
            chapters.append(chapter)
            current_chapter = chapter
        elif row["outline_level"] == 2 and current_chapter:
            current_chapter["sections"].append(
                {
                    "title": row["title"],
                    "pdf_page_start": row["pdf_page"],
                    "printed_page_start": printed.get(row["pdf_page"]),
                    "outline_index": row["outline_index"],
                }
            )

    def set_ranges(items: list[dict[str, Any]], final_end: int) -> None:
        items.sort(key=lambda item: item["pdf_page_start"])
        for index, item in enumerate(items):
            end = items[index + 1]["pdf_page_start"] - 1 if index + 1 < len(items) else final_end
            item["pdf_page_end"] = end
            item["printed_page_end"] = printed.get(end)
            item["pdf_page_count"] = end - item["pdf_page_start"] + 1

    # Top-level boundaries define Part ranges. Chapter starts must not shorten
    # their parent Part; the electronic chapter and appendices are boundaries.
    top_level_boundaries = sorted(
        [item["pdf_page_start"] for item in parts[1:]]
        + [item["pdf_page_start"] for item in electronic_chapters]
        + [item["pdf_page_start"] for item in back_matter]
    )
    for index, part in enumerate(parts):
        following = [page for page in top_level_boundaries if page > part["pdf_page_start"]]
        end = following[0] - 1 if following else len(pages)
        part["pdf_page_end"] = end
        part["printed_page_end"] = printed.get(end)
        part["pdf_page_count"] = end - part["pdf_page_start"] + 1
        part_chapters = part["chapters"]
        for chapter_index, chapter in enumerate(part_chapters):
            next_start = part_chapters[chapter_index + 1]["pdf_page_start"] if chapter_index + 1 < len(part_chapters) else end + 1
            chapter["pdf_page_end"] = next_start - 1
            chapter["printed_page_end"] = printed.get(next_start - 1)
            chapter["pdf_page_count"] = next_start - chapter["pdf_page_start"]

    set_ranges(front_matter, (parts[0]["pdf_page_start"] - 1) if parts else len(pages))
    set_ranges(back_matter, len(pages))
    if electronic_chapters:
        electronic_end = min((item["pdf_page_start"] for item in back_matter), default=len(pages) + 1) - 1
        set_ranges(electronic_chapters, electronic_end)

    page_nodes: list[dict[str, Any]] = []
    for pdf_page in range(1, len(pages) + 1):
        part = next((item for item in parts if item["pdf_page_start"] <= pdf_page <= item["pdf_page_end"]), None)
        chapter = next((item for item in chapters if item["pdf_page_start"] <= pdf_page <= item["pdf_page_end"]), None)
        electronic = next((item for item in electronic_chapters if item["pdf_page_start"] <= pdf_page <= item["pdf_page_end"]), None)
        if chapter:
            page_type = "chapter_content"
        elif electronic:
            page_type = "electronic_only_chapter_content"
        elif part:
            page_type = "part_front_matter_or_transition"
        elif pdf_page < (parts[0]["pdf_page_start"] if parts else 13):
            page_type = "front_matter"
        else:
            page_type = "back_matter"
        page_nodes.append(
            {
                "source_page_id": f"STROKE5-PDF{pdf_page:04d}",
                "pdf_page": pdf_page,
                "printed_page": printed.get(pdf_page),
                "page_type": page_type,
                "part_number": part["part_number"] if part else None,
                "chapter_number": chapter["chapter_number"] if chapter else (electronic or {}).get("chapter_number"),
                "chapter_title": chapter["title"] if chapter else (electronic or {}).get("title"),
                "line_count": len(page_lookup[pdf_page]["lines"]),
                "word_count": sum(len(line["text"].split()) for line in page_lookup[pdf_page]["lines"]),
            }
        )

    toc_text = "\n".join(line["text"] for line in page_lookup.get(12, {}).get("lines", []))
    document_anomalies: list[dict[str, Any]] = []
    if pages:
        tail_text = " ".join(line["text"] for line in page_lookup[len(pages)]["lines"])
        if "Medications Commonly Used to Treat Stroke and Its Comorbidities" in tail_text and "Index" not in tail_text:
            document_anomalies.append(
                {
                    "pdf_pages": [len(pages)],
                    "description": "The final PDF page is an unnumbered continuation of the medications table, although the PDF outline extends the Index entry through the end of the file.",
                    "status": "generated_not_verified",
                }
            )
    return {
        "schema_version": "vtc-stroke-rehabilitation-5e.book-structure.v1",
        "record_type": "book_structure_inventory",
        "book_id": "STROKE5",
        "title": "Stroke Rehabilitation: A Function-Based Approach, Fifth Edition",
        "source": {
            "pdf_page_count": len(pages),
            "page_size_points": [pages[0]["width_points"], pages[0]["height_points"]] if pages else None,
        },
        "structure_basis": {
            "primary": "PDF outline via MuPDF mutool show outline",
            "secondary": "Contents page and embedded PDF text coordinates",
            "status": "generated_not_verified",
        },
        "toc": {
            "pdf_page": 12,
            "printed_page": printed.get(12),
            "embedded_text_snapshot": toc_text[:12000],
            "status": "generated_not_verified",
        },
        "parts": parts,
        "chapters": chapters,
        "electronic_only_chapters": electronic_chapters,
        "front_matter": front_matter,
        "back_matter": back_matter,
        "document_anomalies": document_anomalies,
        "counts": {
            "parts": len(parts),
            "chapters": len(chapters),
            "chapter_sections": sum(len(chapter["sections"]) for chapter in chapters),
            "electronic_only_chapters": len(electronic_chapters),
            "front_matter_entries": len(front_matter),
            "back_matter_entries": len(back_matter),
            "pages": len(page_nodes),
        },
        "pages": page_nodes,
        "outline_entries": outline,
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
    }


def visual_cues(pages: list[dict[str, Any]], structure: dict[str, Any]) -> dict[str, Any]:
    page_map = {item["pdf_page"]: item for item in structure["pages"]}
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    pages_with_cues: set[int] = set()
    for page in pages:
        context = page_map[page["pdf_page"]]
        for line in page["lines"]:
            text = line["text"]
            for cue_type, pattern in CUE_PATTERNS:
                match = pattern.search(text)
                if not match:
                    continue
                records.append(
                    {
                        "visual_cue_id": f"STROKE5-VIS-CUE-P{page['pdf_page']:04d}-L{line['line_index']:04d}-{cue_type}",
                        "source_page_id": context["source_page_id"],
                        "pdf_page": page["pdf_page"],
                        "printed_page": context["printed_page"],
                        "part_number": context["part_number"],
                        "chapter_number": context["chapter_number"],
                        "cue_type": cue_type,
                        "label_candidate": clean_text(match.group(0)),
                        "line_text": text,
                        "bbox_points": line["bbox_points"],
                        "status": "generated_not_verified",
                        "verification_status": "generated_not_verified",
                    }
                )
                counts[cue_type] += 1
                pages_with_cues.add(page["pdf_page"])
    return {
        "schema_version": "vtc-stroke-rehabilitation-5e.visual-cues.v1",
        "record_type": "embedded_text_visual_cue_inventory",
        "book_id": "STROKE5",
        "scope": "caption-like and named visual cues from embedded text; not a complete visual-layout inventory",
        "cues": records,
        "counts": {"cues": len(records), "pages_with_cues": len(pages_with_cues), "by_type": dict(counts)},
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    package = args.package_root.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    info = run(["pdfinfo", str(source)])
    page_count_match = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
    if not page_count_match:
        raise RuntimeError("pdfinfo did not report a page count")
    page_count = int(page_count_match.group(1))
    bbox_xml = run(["pdftotext", "-bbox-layout", "-enc", "UTF-8", str(source), "-"])
    pages = parse_bbox_pages(bbox_xml)
    if len(pages) != page_count:
        raise RuntimeError(f"bbox page count mismatch: {len(pages)} != {page_count}")
    outline = parse_outline(source)
    structure = structure_from_outline(outline, pages)
    structure["source"].update({"filename": source.name, "sha256": sha256_file(source), "pdfinfo": info})
    cues = visual_cues(pages, structure)
    page_path = package / "01 OCR and Layout/stroke_rehab_page_structure_generated.jsonl"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    with page_path.open("w", encoding="utf-8") as stream:
        for page in structure["pages"]:
            stream.write(json.dumps(page, ensure_ascii=False) + "\n")
    write_json(package / "01 OCR and Layout/stroke_rehab_outline_generated.json", {"outline_entries": outline, "counts": {"entries": len(outline), "max_outline_level": max((row["outline_level"] for row in outline), default=0)}, "status": "generated_not_verified", "verification_status": "generated_not_verified"})
    write_json(package / "02 Text and Tables/stroke_rehab_visual_cues_generated.json", cues)
    write_json(package / "03 Analysis/stroke_rehab_book_structure_generated.json", structure)
    manifest_path = package / "source_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["processing_status"] = "structure_and_visual_inventory_generated"
        manifest["verification_status"] = "generated_not_verified"
        manifest["generated_outputs"] = [
            "01 OCR and Layout/stroke_rehab_page_structure_generated.jsonl",
            "01 OCR and Layout/stroke_rehab_outline_generated.json",
            "01 OCR and Layout/stroke_rehab_layout_inventory_generated.json",
            "02 Text and Tables/stroke_rehab_visual_cues_generated.json",
            "03 Analysis/stroke_rehab_book_structure_generated.json",
            "03 Analysis/stroke_rehab_visual_structure_generated.json",
        ]
        write_json(manifest_path, manifest)
    print(json.dumps({"source": str(source), "pages": page_count, "outline_entries": len(outline), "structure_counts": structure["counts"], "visual_cues": cues["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

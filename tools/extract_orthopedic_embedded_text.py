#!/usr/bin/env python3
"""Extract the complete embedded text layer for the orthopedic-test book."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


BOOK_ID = "ORTHO3"
SOURCE_ID = "HHS4185-REF-ORTHO-SPECIAL-TESTS"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def load_structure(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("book_id") != BOOK_ID or value.get("source_id") != SOURCE_ID:
        raise ValueError("structure map does not belong to the orthopedic source")
    return value


def chapter_for_page(chapters: list[dict[str, Any]], pdf_page: int) -> dict[str, Any] | None:
    for chapter in chapters:
        if int(chapter["pdf_page_start"]) <= pdf_page <= int(chapter["pdf_page_end"]):
            return chapter
    return None


def pdftotext_version(executable: str) -> str | None:
    result = subprocess.run([executable, "-v"], capture_output=True, text=True)
    match = re.search(r"pdftotext version\s+([^\s]+)", f"{result.stdout}\n{result.stderr}", re.I)
    return match.group(1) if match else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    structure_path = args.structure.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    structure = load_structure(structure_path)
    chapters = [chapter for part in structure["parts"] for chapter in part["chapters"]]
    total_pages = int(structure["pdf_page_count"])
    pdftotext = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    command = [pdftotext, "-enc", "UTF-8", "-layout", "-f", "1", "-l", str(total_pages), str(source), "-"]
    result = subprocess.run(command, check=True, capture_output=True)
    raw_bytes = result.stdout
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    page_texts = raw_text.split("\f")
    if page_texts and page_texts[-1] == "":
        page_texts.pop()
    if len(page_texts) != total_pages:
        raise RuntimeError(f"expected {total_pages} layout pages, got {len(page_texts)}")

    linear_command = [pdftotext, "-enc", "UTF-8", "-raw", "-f", "1", "-l", str(total_pages), str(source), "-"]
    linear_result = subprocess.run(linear_command, check=True, capture_output=True)
    linear_bytes = linear_result.stdout
    linear_text = linear_bytes.decode("utf-8", errors="replace")
    linear_page_texts = linear_text.split("\f")
    if linear_page_texts and linear_page_texts[-1] == "":
        linear_page_texts.pop()
    if len(linear_page_texts) != total_pages:
        raise RuntimeError(f"expected {total_pages} linear pages, got {len(linear_page_texts)}")

    pages: list[dict[str, Any]] = []
    for offset, text in enumerate(page_texts):
        pdf_page = offset + 1
        chapter = chapter_for_page(chapters, pdf_page)
        pages.append({
            "record_id": f"{BOOK_ID}-PA{pdf_page:04d}",
            "source_page_id": f"{BOOK_ID}-PDF{pdf_page:04d}",
            "pdf_page": pdf_page,
            "chapter_number": chapter.get("chapter_number") if chapter else None,
            "chapter_title": chapter.get("title") if chapter else None,
            "printed_page": chapter.get("printed_page_start") + pdf_page - chapter.get("pdf_page_start") if chapter else None,
            "text_raw": text,
            "text_raw_linear": linear_page_texts[pdf_page - 1],
            "char_count": len(text),
            "line_count": len(text.splitlines()),
            "is_empty": not text.strip(),
            "status": "generated_not_verified",
            "verification_status": "generated_not_verified",
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / "orthopedic_embedded_text_full_layout.txt"
    linear_text_path = output_dir / "orthopedic_embedded_text_full_linear.txt"
    json_path = output_dir / "orthopedic_embedded_text_full_raw.json"
    text_path.write_bytes(raw_bytes)
    linear_text_path.write_bytes(linear_bytes)
    output = {
        "schema_version": "vtc-ortho3.embedded-text-full.v1",
        "record_type": "embedded_text_extraction_full_book",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "source": {"filename": source.name, "path": str(source), "sha256": sha256_file(source)},
        "structure_map": str(structure_path),
        "extraction": {
            "method": "embedded PDF text layer",
            "tool": "pdftotext",
            "tool_version": pdftotext_version(pdftotext),
            "options": ["-enc", "UTF-8", "-layout"],
            "raw_text_file": str(text_path),
            "linear_text_file": str(linear_text_path),
            "page_separator": "form feed (U+000C)",
            "scope": "complete embedded page text in layout and linear order; no image OCR and no visual-content OCR",
        },
        "counts": {
            "pages": len(pages),
            "empty_pages": sum(page["is_empty"] for page in pages),
            "characters": sum(page["char_count"] for page in pages),
            "lines": sum(page["line_count"] for page in pages),
            "linear_characters": len(linear_text),
            "linear_lines": sum(len(page.splitlines()) for page in linear_page_texts),
        },
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
        "pages": pages,
    }
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "text": str(text_path), **output["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

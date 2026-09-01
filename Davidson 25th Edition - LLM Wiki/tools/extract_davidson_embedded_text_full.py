#!/usr/bin/env python3
"""Extract the complete embedded PDF text layer page by page.

This is a raw source layer. It intentionally preserves the PDF's original
text order, watermark, layout whitespace, and any text that belongs to visual
regions. Later derived layers must not overwrite this file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def pdftotext_version(executable: str) -> str | None:
    result = subprocess.run([executable, "-v"], capture_output=True, text=True)
    version_text = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"pdftotext version\s+([^\s]+)", version_text, re.I)
    return match.group(1) if match else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--chapter-map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def chapter_for_page(chapters: list[dict[str, Any]], pdf_page: int) -> dict[str, Any] | None:
    for chapter in chapters:
        if int(chapter["pdf_page_start"]) <= pdf_page <= int(chapter["pdf_page_end"]):
            return chapter
    return None


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    chapter_map_path = args.chapter_map.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not chapter_map_path.is_file():
        raise FileNotFoundError(chapter_map_path)

    chapter_map = json.loads(chapter_map_path.read_text(encoding="utf-8"))
    chapters = [
        {**chapter, "part": part["title"]}
        for part in chapter_map["parts"]
        for chapter in part["chapters"]
    ]
    total_pages = int(chapter_map["pdf_page_count"])
    pdftotext = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    command = [
        pdftotext,
        "-enc",
        "UTF-8",
        "-layout",
        "-f",
        "1",
        "-l",
        str(total_pages),
        str(source),
        "-",
    ]
    result = subprocess.run(command, check=True, capture_output=True)
    raw_output = result.stdout.decode("utf-8")
    page_texts = raw_output.split("\f")
    if page_texts and page_texts[-1] == "":
        page_texts.pop()
    if len(page_texts) != total_pages:
        raise RuntimeError(
            f"Expected {total_pages} page records, got {len(page_texts)} "
            "from embedded text extraction"
        )

    pages: list[dict[str, Any]] = []
    for offset, text in enumerate(page_texts):
        pdf_page = offset + 1
        chapter = chapter_for_page(chapters, pdf_page)
        chapter_number = chapter["chapter_number"] if chapter else None
        pages.append(
            {
                "record_id": f"DAV25-PA{pdf_page:04d}",
                "source_page_id": f"DAV25-PDF{pdf_page:04d}",
                "pdf_page": pdf_page,
                "chapter_number": chapter_number,
                "chapter_title": chapter["title"] if chapter else None,
                "part": chapter["part"] if chapter else None,
                "chapter_page_index": (
                    pdf_page - int(chapter["pdf_page_start"]) + 1 if chapter else None
                ),
                "printed_page": (
                    int(chapter["printed_page_start"])
                    + pdf_page
                    - int(chapter["pdf_page_start"])
                    if chapter
                    else None
                ),
                "text_raw": text,
                "char_count": len(text),
                "line_count": len(text.splitlines()),
                "is_empty": not text.strip(),
                "status": "generated",
                "verification_status": "not_verified",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / "davidson25_embedded_text_full_layout.txt"
    json_path = output_dir / "davidson25_embedded_text_full_raw.json"
    text_path.write_bytes(result.stdout)
    manifest = {
        "schema_version": "vtc-davidson25.embedded-text-full.v1",
        "record_type": "embedded_text_extraction_full_book",
        "book_id": "DAV25",
        "chapter_count": len(chapters),
        "source": {
            "filename": source.name,
            "path": str(source),
            "sha256": sha256_file(source),
        },
        "chapter_map": str(chapter_map_path),
        "extraction": {
            "method": "embedded PDF text layer",
            "tool": "pdftotext",
            "tool_version": pdftotext_version(pdftotext),
            "options": ["-enc", "UTF-8", "-layout"],
            "raw_text_file": str(text_path),
            "page_separator": "form feed (U+000C)",
            "scope": "complete embedded page text only; no image OCR and no visual-content OCR",
        },
        "counts": {
            "pages": len(pages),
            "empty_pages": sum(page["is_empty"] for page in pages),
            "characters": sum(page["char_count"] for page in pages),
            "lines": sum(page["line_count"] for page in pages),
        },
        "status": "generated",
        "verification_status": "not_verified",
        "pages": pages,
    }
    json_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "json": str(json_path),
                "text": str(text_path),
                "pages": len(pages),
                "empty_pages": manifest["counts"]["empty_pages"],
                "characters": manifest["counts"]["characters"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

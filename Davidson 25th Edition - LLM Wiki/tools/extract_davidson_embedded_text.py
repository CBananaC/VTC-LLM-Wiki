#!/usr/bin/env python3
"""Extract embedded PDF text for one Davidson chapter, page by page."""

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


def load_chapter(chapter_map: Path, chapter_number: int) -> dict[str, Any]:
    data = json.loads(chapter_map.read_text(encoding="utf-8"))
    for part in data["parts"]:
        for chapter in part["chapters"]:
            if chapter["chapter_number"] == chapter_number:
                return {**chapter, "part": part["title"]}
    raise ValueError(f"Chapter {chapter_number} not found in {chapter_map}")


def pdftotext_version(executable: str) -> str | None:
    result = subprocess.run([executable, "-v"], capture_output=True, text=True)
    version_text = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"pdftotext version\s+([^\s]+)", version_text, re.I)
    return match.group(1) if match else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--chapter-map", type=Path, required=True)
    parser.add_argument("--chapter-number", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    chapter_map = args.chapter_map.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not chapter_map.is_file():
        raise FileNotFoundError(chapter_map)

    chapter = load_chapter(chapter_map, args.chapter_number)
    start_page = int(chapter["pdf_page_start"])
    end_page = int(chapter["pdf_page_end"])
    page_count = end_page - start_page + 1
    pdftotext = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    command = [
        pdftotext,
        "-enc",
        "UTF-8",
        "-layout",
        "-f",
        str(start_page),
        "-l",
        str(end_page),
        str(source),
        "-",
    ]
    result = subprocess.run(command, check=True, capture_output=True)
    raw_output = result.stdout.decode("utf-8")
    page_texts = raw_output.split("\f")
    if page_texts and page_texts[-1] == "":
        page_texts.pop()
    if len(page_texts) != page_count:
        raise RuntimeError(
            f"Expected {page_count} page records, got {len(page_texts)} "
            f"from embedded text extraction"
        )

    pages: list[dict[str, Any]] = []
    for offset, text in enumerate(page_texts):
        pdf_page = start_page + offset
        pages.append(
            {
                "record_id": f"DAV25-CH{args.chapter_number:02d}-PA{offset + 1:02d}",
                "source_page_id": f"DAV25-PDF{pdf_page:04d}",
                "pdf_page": pdf_page,
                "chapter_page_index": offset + 1,
                "printed_page": int(chapter["printed_page_start"]) + offset,
                "text_raw": text,
                "char_count": len(text),
                "line_count": len(text.splitlines()),
                "is_empty": not text.strip(),
                "status": "generated",
                "verification_status": "not_verified",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / f"davidson25_ch{args.chapter_number:02d}_embedded_text_layout.txt"
    json_path = output_dir / f"davidson25_ch{args.chapter_number:02d}_embedded_text_raw.json"
    text_path.write_bytes(result.stdout)
    manifest = {
        "schema_version": "vtc-davidson25.embedded-text.v1",
        "record_type": "embedded_text_extraction",
        "book_id": "DAV25",
        "chapter_number": args.chapter_number,
        "chapter_title": chapter["title"],
        "part": chapter["part"],
        "printed_page_start": chapter["printed_page_start"],
        "printed_page_end": int(chapter["printed_page_start"]) + page_count - 1,
        "pdf_page_start": start_page,
        "pdf_page_end": end_page,
        "source": {
            "filename": source.name,
            "path": str(source),
            "sha256": sha256_file(source),
        },
        "chapter_map": str(chapter_map),
        "extraction": {
            "method": "embedded PDF text layer",
            "tool": "pdftotext",
            "tool_version": pdftotext_version(pdftotext),
            "options": ["-enc", "UTF-8", "-layout"],
            "raw_text_file": str(text_path),
            "page_separator": "form feed (U+000C)",
            "scope": "embedded page text only; no image OCR and no visual-content OCR",
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
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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

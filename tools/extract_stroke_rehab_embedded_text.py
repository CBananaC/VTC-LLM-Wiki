#!/usr/bin/env python3
"""Extract the complete embedded PDF text layer for Stroke Rehabilitation.

This is a raw, source-preserving pass. It does not run OCR and does not
modify the source PDF. Text that belongs to a table, figure, diagram, or
other visual may remain in this raw layer; the clean-text pass removes words
inside the visual-location inventory.
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
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    structure_path = args.structure.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not structure_path.is_file():
        raise FileNotFoundError(structure_path)

    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    page_map = {page["pdf_page"]: page for page in structure["pages"]}
    total_pages = int(structure["source"]["pdf_page_count"])
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
    raw_output = result.stdout.decode("utf-8", errors="replace")
    page_texts = raw_output.split("\f")
    if page_texts and page_texts[-1] == "":
        page_texts.pop()
    if len(page_texts) != total_pages:
        raise RuntimeError(
            f"Expected {total_pages} page records, got {len(page_texts)} "
            "from embedded text extraction"
        )

    chapters = structure.get("chapters", []) + structure.get("electronic_only_chapters", [])
    pages: list[dict[str, Any]] = []
    for offset, text in enumerate(page_texts):
        pdf_page = offset + 1
        page_source = page_map[pdf_page]
        chapter = next(
            (
                item
                for item in chapters
                if int(item["pdf_page_start"]) <= pdf_page <= int(item["pdf_page_end"])
            ),
            None,
        )
        pages.append(
            {
                "record_id": f"STROKE5-PA{pdf_page:04d}",
                "source_page_id": page_source["source_page_id"],
                "pdf_page": pdf_page,
                "printed_page": page_source.get("printed_page"),
                "page_type": page_source.get("page_type"),
                "part_number": page_source.get("part_number"),
                "chapter_number": page_source.get("chapter_number"),
                "chapter_title": page_source.get("chapter_title"),
                "chapter_page_index": (
                    pdf_page - int(chapter["pdf_page_start"]) + 1 if chapter else None
                ),
                "text_raw": text,
                "char_count": len(text),
                "line_count": len(text.splitlines()),
                "is_empty": not text.strip(),
                "status": "generated_not_verified",
                "verification_status": "generated_not_verified",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / "stroke_rehab_embedded_text_full_layout.txt"
    json_path = output_dir / "stroke_rehab_embedded_text_full_raw.json"
    text_path.write_bytes(result.stdout)
    manifest = {
        "schema_version": "vtc-stroke-rehabilitation-5e.embedded-text-full.v1",
        "record_type": "embedded_text_extraction_full_book",
        "book_id": "STROKE5",
        "title": structure.get("title"),
        "source": {
            "filename": source.name,
            "path": str(source),
            "sha256": sha256_file(source),
        },
        "structure_input": str(structure_path),
        "extraction": {
            "method": "embedded PDF text layer",
            "tool": "pdftotext",
            "tool_version": pdftotext_version(pdftotext),
            "options": ["-enc", "UTF-8", "-layout"],
            "raw_text_file": str(text_path),
            "page_separator": "form feed (U+000C)",
            "scope": "complete embedded page text only; no OCR and no visual-content OCR",
        },
        "counts": {
            "pages": len(pages),
            "empty_pages": sum(page["is_empty"] for page in pages),
            "characters": sum(page["char_count"] for page in pages),
            "lines": sum(page["line_count"] for page in pages),
        },
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
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
                "lines": manifest["counts"]["lines"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

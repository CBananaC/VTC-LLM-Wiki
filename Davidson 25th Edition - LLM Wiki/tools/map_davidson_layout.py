#!/usr/bin/env python3
"""Create a resumable page-level layout inventory for Davidson's 25th Edition.

This pass locates layout elements only. It does not OCR their contents and does
not replace the source PDF or its embedded text layer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image
from paddleocr import LayoutDetection


VISUAL_LABELS = {
    "table",
    "table_caption",
    "figure",
    "figure_title",
    "figure_caption",
    "image",
    "chart",
    "formula",
    "formula_number",
    "algorithm",
    "header_image",
    "footer_image",
    "seal",
}


def plain(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def payload_from_result(result: Any) -> dict[str, Any]:
    payload = result.json
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload = plain(payload)
    if isinstance(payload, dict) and isinstance(payload.get("res"), dict):
        payload = payload["res"]
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected layout result: {type(payload)!r}")
    return payload


def chapter_for_page(chapters: list[dict[str, Any]], pdf_page: int) -> dict[str, Any] | None:
    for chapter in chapters:
        start = chapter.get("pdf_page_start")
        end = chapter.get("pdf_page_end")
        if isinstance(start, int) and isinstance(end, int) and start <= pdf_page <= end:
            return chapter
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--chapter-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    chapter_map_path = args.chapter_map.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not chapter_map_path.is_file():
        raise FileNotFoundError(chapter_map_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial.jsonl")
    if output.exists() and not args.overwrite and not partial.exists():
        raise FileExistsError(f"Output exists without a resumable checkpoint: {output}")
    if args.overwrite:
        partial.unlink(missing_ok=True)

    chapter_map = json.loads(chapter_map_path.read_text(encoding="utf-8"))
    chapters = [chapter for part in chapter_map["parts"] for chapter in part["chapters"]]
    total_pages = int(chapter_map["pdf_page_count"])
    start_page = max(1, args.start_page)
    end_page = min(total_pages, args.end_page or total_pages)
    if start_page > end_page:
        raise ValueError(f"Invalid page range: {start_page}-{end_page}")

    done_pages: set[int] = set()
    existing_records: list[dict[str, Any]] = []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("record_type") == "page_layout":
                page = record.get("pdf_page")
                if isinstance(page, int):
                    done_pages.add(page)
                    existing_records.append(record)

    layout = LayoutDetection(model_name="PP-DocLayout_plus-L", device="cpu")
    pdfinfo = shutil.which("pdfinfo") or "/opt/homebrew/bin/pdfinfo"
    pdftoppm = shutil.which("pdftoppm") or "/opt/homebrew/bin/pdftoppm"
    source_hash = sha256_file(source)
    errors: list[dict[str, Any]] = []

    with partial.open("a", encoding="utf-8") as stream, tempfile.TemporaryDirectory(prefix="davidson25-layout-") as temp:
        temp_dir = Path(temp)
        for pdf_page in range(start_page, end_page + 1):
            if pdf_page in done_pages:
                continue
            prefix = temp_dir / "page"
            try:
                subprocess.run(
                    [
                        pdftoppm,
                        "-f",
                        str(pdf_page),
                        "-l",
                        str(pdf_page),
                        "-r",
                        str(args.dpi),
                        "-png",
                        "-singlefile",
                        str(source),
                        str(prefix),
                    ],
                    check=True,
                    capture_output=True,
                )
                image_path = prefix.with_suffix(".png")
                with Image.open(image_path) as image:
                    width, height = image.size
                result = next(iter(layout.predict(str(image_path), batch_size=1)))
                payload = payload_from_result(result)
                boxes = payload.get("boxes", [])
                normalized_boxes: list[dict[str, Any]] = []
                for index, box in enumerate(boxes):
                    coordinate = box.get("coordinate", [])
                    normalized_boxes.append(
                        {
                            "layout_id": f"DAV25-PDF{pdf_page:04d}-L{index + 1:04d}",
                            "layout_index": index,
                            "label": box.get("label"),
                            "class_id": box.get("cls_id"),
                            "confidence": box.get("score"),
                            "bbox": [round(float(value), 2) for value in coordinate],
                            "is_visual_candidate": box.get("label") in VISUAL_LABELS,
                        }
                    )
                chapter = chapter_for_page(chapters, pdf_page)
                visuals = [box for box in normalized_boxes if box["is_visual_candidate"]]
                record = {
                    "schema_version": "vtc-davidson25.page-layout.v1",
                    "record_type": "page_layout",
                    "book_id": "DAV25",
                    "source_page_id": f"DAV25-PDF{pdf_page:04d}",
                    "pdf_page": pdf_page,
                    "render": {"dpi": args.dpi, "width": width, "height": height},
                    "chapter_number": chapter.get("chapter_number") if chapter else None,
                    "chapter_title": chapter.get("title") if chapter else None,
                    "chapter_printed_page_start": chapter.get("printed_page_start") if chapter else None,
                    "layout_boxes": normalized_boxes,
                    "visual_candidates": visuals,
                    "label_counts": dict(Counter(box.get("label") for box in normalized_boxes)),
                    "status": "generated_candidate",
                    "verification_status": "not_verified",
                }
            except Exception as error:
                record = {
                    "schema_version": "vtc-davidson25.page-layout.v1",
                    "record_type": "page_layout",
                    "book_id": "DAV25",
                    "source_page_id": f"DAV25-PDF{pdf_page:04d}",
                    "pdf_page": pdf_page,
                    "chapter_number": (chapter_for_page(chapters, pdf_page) or {}).get("chapter_number"),
                    "status": "error",
                    "verification_status": "not_verified",
                    "error": repr(error),
                    "layout_boxes": [],
                    "visual_candidates": [],
                }
                errors.append({"pdf_page": pdf_page, "error": repr(error)})
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    records_by_page = {
        record["pdf_page"]: record
        for record in existing_records
        if isinstance(record.get("pdf_page"), int)
    }
    for line in partial.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("record_type") == "page_layout":
                page = record.get("pdf_page")
                if isinstance(page, int):
                    records_by_page[page] = record
    all_records = list(records_by_page.values())
    all_records.sort(key=lambda record: record["pdf_page"])
    manifest = {
        "schema_version": "vtc-davidson25.layout-inventory.v1",
        "record_type": "layout_inventory",
        "book_id": "DAV25",
        "source": {
            "filename": source.name,
            "path": str(source),
            "sha256": source_hash,
            "pdf_page_count": total_pages,
        },
        "chapter_map": str(chapter_map_path),
        "run": {
            "ocr_engine": "PaddleOCR LayoutDetection",
            "model_name": "PP-DocLayout_plus-L",
            "device": "cpu",
            "dpi": args.dpi,
            "scope": "page layout and visual location only; no visual content OCR",
        },
        "counts": {
            "pages": len(all_records),
            "pages_with_errors": sum(record.get("status") == "error" for record in all_records),
            "visual_candidates": sum(len(record.get("visual_candidates", [])) for record in all_records),
            "label_counts": dict(Counter(box.get("label") for record in all_records for box in record.get("layout_boxes", []))),
        },
        "status": "generated_candidate",
        "verification_status": "not_verified",
        "pages": all_records,
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "pages": len(all_records), "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()

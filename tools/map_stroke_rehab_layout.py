#!/usr/bin/env python3
"""Map page layout and visual locations for Stroke Rehabilitation, 5th ed.

This pass renders each requested PDF page and uses PaddleOCR layout detection
to locate likely tables, figures, charts, diagrams, and related objects. It
does not OCR or reconstruct visual contents. The JSONL checkpoint is retained
so a long run can resume without replacing completed page records.
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
from collections import Counter, defaultdict
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
    "diagram",
    "graph",
    "illustration",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def context_key(page: dict[str, Any]) -> str:
    if page.get("chapter_number"):
        number = page["chapter_number"]
        title = page.get("chapter_title") or ""
        return f"Chapter {number}: {title}".strip()
    if page.get("part_number"):
        return f"Part {page['part_number']}"
    return page.get("page_type") or "unclassified"


def main() -> None:
    args = parse_args()
    source = args.source.expanduser().resolve()
    structure_path = args.structure.expanduser().resolve()
    output = args.output.expanduser().resolve()
    summary_output = args.summary_output.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not structure_path.is_file():
        raise FileNotFoundError(structure_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial.jsonl")
    if output.exists() and not args.overwrite and not partial.exists():
        raise FileExistsError(f"Output exists without a resumable checkpoint: {output}")
    if args.overwrite:
        partial.unlink(missing_ok=True)

    structure = json.loads(structure_path.read_text(encoding="utf-8"))
    page_map = {page["pdf_page"]: page for page in structure["pages"]}
    total_pages = int(structure["source"]["pdf_page_count"])
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

    with partial.open("a", encoding="utf-8") as stream, tempfile.TemporaryDirectory(prefix="stroke5-layout-") as temp:
        temp_dir = Path(temp)
        for pdf_page in range(start_page, end_page + 1):
            if pdf_page in done_pages:
                continue
            prefix = temp_dir / "page"
            context = page_map[pdf_page]
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
                            "layout_id": f"STROKE5-PDF{pdf_page:04d}-L{index + 1:04d}",
                            "layout_index": index,
                            "label": box.get("label"),
                            "class_id": box.get("cls_id"),
                            "confidence": box.get("score"),
                            "bbox": [round(float(value), 2) for value in coordinate],
                            "is_visual_candidate": box.get("label") in VISUAL_LABELS,
                        }
                    )
                visuals = [box for box in normalized_boxes if box["is_visual_candidate"]]
                record = {
                    "schema_version": "vtc-stroke-rehabilitation-5e.page-layout.v1",
                    "record_type": "page_layout",
                    "book_id": "STROKE5",
                    "source_page_id": context["source_page_id"],
                    "pdf_page": pdf_page,
                    "printed_page": context.get("printed_page"),
                    "page_type": context.get("page_type"),
                    "part_number": context.get("part_number"),
                    "chapter_number": context.get("chapter_number"),
                    "chapter_title": context.get("chapter_title"),
                    "render": {"dpi": args.dpi, "width": width, "height": height},
                    "layout_boxes": normalized_boxes,
                    "visual_candidates": visuals,
                    "label_counts": dict(Counter(box.get("label") for box in normalized_boxes)),
                    "status": "generated_not_verified",
                    "verification_status": "generated_not_verified",
                }
            except Exception as error:
                record = {
                    "schema_version": "vtc-stroke-rehabilitation-5e.page-layout.v1",
                    "record_type": "page_layout",
                    "book_id": "STROKE5",
                    "source_page_id": context["source_page_id"],
                    "pdf_page": pdf_page,
                    "printed_page": context.get("printed_page"),
                    "page_type": context.get("page_type"),
                    "part_number": context.get("part_number"),
                    "chapter_number": context.get("chapter_number"),
                    "chapter_title": context.get("chapter_title"),
                    "status": "error",
                    "verification_status": "generated_not_verified",
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
    all_records = [records_by_page[page] for page in sorted(records_by_page)]
    label_counts = Counter(
        box.get("label")
        for record in all_records
        for box in record.get("layout_boxes", [])
    )
    visual_candidates = sum(len(record.get("visual_candidates", [])) for record in all_records)
    manifest = {
        "schema_version": "vtc-stroke-rehabilitation-5e.layout-inventory.v1",
        "record_type": "layout_inventory",
        "book_id": "STROKE5",
        "source": {
            "filename": source.name,
            "path": str(source),
            "sha256": source_hash,
            "pdf_page_count": total_pages,
        },
        "structure_input": str(structure_path),
        "run": {
            "layout_engine": "PaddleOCR LayoutDetection",
            "model_name": "PP-DocLayout_plus-L",
            "device": "cpu",
            "dpi": args.dpi,
            "scope": "page layout and visual location only; no visual content OCR",
        },
        "counts": {
            "pages": len(all_records),
            "pages_with_errors": sum(record.get("status") == "error" for record in all_records),
            "pages_with_visual_candidates": sum(bool(record.get("visual_candidates")) for record in all_records),
            "visual_candidates": visual_candidates,
            "label_counts": dict(label_counts),
        },
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
        "pages": all_records,
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "pages": 0,
            "pages_with_visual_candidates": 0,
            "visual_candidates": 0,
            "label_counts": Counter(),
            "visual_locations": [],
        }
    )
    for record in all_records:
        key = context_key(record)
        group = groups[key]
        group["pages"] += 1
        visuals = record.get("visual_candidates", [])
        if visuals:
            group["pages_with_visual_candidates"] += 1
        group["visual_candidates"] += len(visuals)
        group["label_counts"].update(box.get("label") for box in visuals)
        if visuals:
            group["visual_locations"].append(
                {
                    "source_page_id": record["source_page_id"],
                    "pdf_page": record["pdf_page"],
                    "printed_page": record.get("printed_page"),
                    "visuals": [
                        {
                            "layout_id": box["layout_id"],
                            "label": box.get("label"),
                            "confidence": box.get("confidence"),
                            "bbox": box.get("bbox"),
                        }
                        for box in visuals
                    ],
                    "status": "generated_not_verified",
                }
            )

    summary_groups = []
    for key in sorted(groups):
        group = groups[key]
        summary_groups.append(
            {
                "context": key,
                "pages": group["pages"],
                "pages_with_visual_candidates": group["pages_with_visual_candidates"],
                "visual_candidates": group["visual_candidates"],
                "label_counts": dict(group["label_counts"]),
                "visual_locations": group["visual_locations"],
            }
        )
    summary = {
        "schema_version": "vtc-stroke-rehabilitation-5e.visual-structure.v1",
        "record_type": "visual_structure_inventory",
        "book_id": "STROKE5",
        "scope": "PaddleOCR model-detected visual layout candidates grouped by book context; not a complete semantic visual inventory and not visual-content OCR",
        "source_layout_inventory": str(output),
        "counts": manifest["counts"],
        "groups": summary_groups,
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
    }
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "output": str(output),
                "summary_output": str(summary_output),
                "pages": len(all_records),
                "errors": errors,
                "counts": manifest["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

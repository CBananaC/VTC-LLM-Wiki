#!/usr/bin/env python3
"""Run resumable PaddleOCR over every HHS4185 slide and merge the results."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


WIKI_ROOT = Path(__file__).resolve().parents[1]
from build_hhs4185_course_materials import english_text_from_line  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def paddle_value(result: Any) -> dict[str, Any]:
    value = result.json
    if callable(value):
        value = value()
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and isinstance(value.get("res"), dict):
        value = value["res"]
    return value if isinstance(value, dict) else {}


def english_ocr_text(regions: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    pending_marker = ""
    for region in regions:
        text, marker = english_text_from_line(str(region.get("text", "")))
        if not text:
            pending_marker = marker or pending_marker
            continue
        if pending_marker and not marker:
            text = f"{pending_marker} {text}".strip()
            pending_marker = ""
        elif marker:
            pending_marker = ""
        lines.append(text)
    return "\n".join(lines)


def source_path(course_root: Path, file_name: str) -> Path:
    for folder in ("(2) Lecture Materials", "(3) Workshop and Practice Materials"):
        candidate = course_root / folder / file_name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(file_name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, default=WIKI_ROOT.parent)
    parser.add_argument("--output-root", type=Path, default=WIKI_ROOT)
    parser.add_argument("--dpi", type=int, default=72)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs4185-course"))
    args = parser.parse_args()
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(args.paddle_cache)
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    from paddleocr import PaddleOCR

    page_path = args.output_root / "(2) OCR and Layout/hhs4185_pages_ocr_layout_generated.jsonl"
    checkpoint_path = args.output_root / "(2) OCR and Layout/hhs4185_all_pages_ocr.partial.jsonl"
    final_ocr_path = args.output_root / "(2) OCR and Layout/hhs4185_all_pages_ocr_generated.jsonl"
    pages = read_jsonl(page_path)
    checkpoint = {record["source_page_id"]: record for record in read_jsonl(checkpoint_path)} if checkpoint_path.exists() else {}
    pending = [page for page in pages if page["source_page_id"] not in checkpoint]
    print(json.dumps({"total_pages": len(pages), "already_completed": len(checkpoint), "pending": len(pending)}, ensure_ascii=False), flush=True)
    if pending:
        ocr = PaddleOCR(lang="en", device="cpu", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for page in pending:
            grouped.setdefault(page["source_file"], []).append(page)
        for file_name, file_pages in grouped.items():
            pdf = source_path(args.course_root, file_name)
            with tempfile.TemporaryDirectory(prefix="hhs4185-all-ocr-") as temp_dir:
                prefix = Path(temp_dir) / "slide"
                subprocess.run(["pdftoppm", "-png", "-r", str(args.dpi), str(pdf), str(prefix)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                images = {int(path.stem.rsplit("-", 1)[1]): path for path in Path(temp_dir).glob("slide-*.png")}
                batch_size = 4
                for batch_start in range(0, len(file_pages), batch_size):
                    batch_pages = file_pages[batch_start:batch_start + batch_size]
                    batch_images = [str(images[page["slide_number"]]) for page in batch_pages]
                    batch_results = list(ocr.predict(batch_images))
                    for page, result in zip(batch_pages, batch_results):
                        value = paddle_value(result)
                        texts = value.get("rec_texts", []) or []
                        scores = value.get("rec_scores", []) or []
                        boxes = value.get("rec_boxes", []) or []
                        regions = [{"text": text, "score": scores[index] if index < len(scores) else None, "bbox_px": boxes[index] if index < len(boxes) else None} for index, text in enumerate(texts)]
                        numeric_scores = [float(item["score"]) for item in regions if item.get("score") is not None]
                        checkpoint[page["source_page_id"]] = {
                            "source_page_id": page["source_page_id"],
                            "document_id": page["document_id"],
                            "source_file": page["source_file"],
                            "pdf_page": page["pdf_page"],
                            "slide_number": page["slide_number"],
                            "ocr_text": "\n".join(str(item["text"]) for item in regions if item.get("text")),
                            "ocr_text_english": english_ocr_text(regions),
                            "ocr_regions": regions,
                            "ocr_mean_score": sum(numeric_scores) / len(numeric_scores) if numeric_scores else None,
                            "ocr_status": "completed",
                            "status": "generated_not_verified",
                            "verification_status": "generated_not_verified",
                        }
                    write_jsonl(checkpoint_path, [checkpoint[key] for key in sorted(checkpoint)])
                    print(f"OCR {len(checkpoint)}/{len(pages)} {batch_pages[-1]['source_page_id']}", flush=True)

    ordered_ocr = [checkpoint[page["source_page_id"]] for page in pages if page["source_page_id"] in checkpoint]
    write_jsonl(final_ocr_path, ordered_ocr)
    ocr_by_id = {record["source_page_id"]: record for record in ordered_ocr}
    for page in pages:
        record = ocr_by_id.get(page["source_page_id"])
        if record:
            page.update({key: record[key] for key in ("ocr_text", "ocr_text_english", "ocr_regions", "ocr_mean_score", "ocr_status")})
    merge_path = page_path.with_suffix(".merged.tmp")
    write_jsonl(merge_path, pages)
    merge_path.replace(page_path)

    passage_path = args.output_root / "(5) Retrieval Index/passage_index.jsonl"
    if passage_path.exists():
        passages = read_jsonl(passage_path)
        for passage in passages:
            page_id = passage.get("source_page_ids", [None])[0]
            passage["ocr_text"] = ocr_by_id.get(page_id, {}).get("ocr_text")
            passage["ocr_text_english"] = ocr_by_id.get(page_id, {}).get("ocr_text_english")
        temp_passage_path = passage_path.with_suffix(".merged.tmp")
        write_jsonl(temp_passage_path, passages)
        temp_passage_path.replace(passage_path)

    validation_path = args.output_root / "(5) Retrieval Index/retrieval_index_validation_report.json"
    if validation_path.exists():
        validation = load_json(validation_path)
        validation["checks"]["all_pages_have_ocr"] = len(ordered_ocr) == len(pages) and all(record.get("ocr_status") == "completed" for record in ordered_ocr)
        validation["checks"]["ocr_passage_fields_present"] = all(passage.get("ocr_text") is not None for passage in read_jsonl(passage_path)) if passage_path.exists() else False
        validation["status"] = "generated_not_verified"
        validation["verification_status"] = "generated_not_verified"
        validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"completed_pages": len(ordered_ocr), "output": str(final_ocr_path), "all_pages_have_ocr": len(ordered_ocr) == len(pages)}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Register a new course or supplemental source in the VTC LLM Wiki.

This command creates a source package scaffold and updates the project registry.
It deliberately does not run OCR, build a retrieval index, or mark any source
as verified. Local source files are copied into the raw layer by default so the
project can preserve a hashed input; use --no-copy-source when the canonical
file must remain outside this project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "source_registry.json"
LAYER_NAMES = (
    "00 Source",
    "01 OCR and Layout",
    "02 Text and Tables",
    "03 Analysis",
    "04 Retrieval Index",
)
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def fail(message: str) -> None:
    raise SystemExit(f"register_source.py: {message}")


def safe_component(value: str, label: str) -> str:
    if not SAFE_COMPONENT.fullmatch(value):
        fail(f"{label} must contain only letters, numbers, dots, underscores, and hyphens")
    return value


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def project_relative(path: Path) -> str:
    """Return a portable path without exposing an absolute home directory."""
    return Path(os.path.relpath(path, PROJECT_ROOT)).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        fail(f"missing registry: {REGISTRY_PATH}")
    try:
        value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid registry JSON: {exc}")
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        fail("registry must be an object with a sources list")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--source-id", required=True, help="Stable identifier, for example HHS4185-L3")
    command.add_argument("--title", required=True, help="Human-readable source title")
    command.add_argument("--course-code", default="general", help="Course code, or general for a cross-course source")
    command.add_argument(
        "--source-role",
        required=True,
        choices=("course_materials", "additional_source", "official_document", "assessment", "past_exam", "other"),
    )
    command.add_argument("--source-kind", required=True, help="Specific kind, for example lecture, book, URL, or journal_article")
    source_group = command.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source-path", action="append", type=Path, help="Local source file; repeat for a related source set")
    source_group.add_argument("--source-url", action="append", help="Source URL; repeat for related URLs")
    command.add_argument("--no-copy-source", action="store_true", help="Keep local inputs at their original locations instead of copying them")
    command.add_argument("--notes", default="", help="Short source or processing note")
    command.add_argument("--dry-run", action="store_true", help="Show the planned package and registry entry without writing")
    return command


def main() -> None:
    args = parser().parse_args()
    source_id = safe_component(args.source_id, "--source-id")
    course_code = safe_component(args.course_code, "--course-code")
    package_rel = Path("sources") / course_code / source_id
    package_root = PROJECT_ROOT / package_rel
    if package_root.exists():
        fail(f"refusing to overwrite existing package: {package_root}")

    registry = load_registry()
    if any(item.get("source_id") == source_id for item in registry["sources"]):
        fail(f"source_id already exists in registry: {source_id}")

    now = datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(timespec="seconds")
    source_files: list[dict[str, Any]] = []
    source_urls = list(args.source_url or [])

    if args.source_path:
        seen_names: set[str] = set()
        for raw_path in args.source_path:
            path = raw_path.expanduser().resolve()
            if not path.is_file():
                fail(f"source file does not exist or is not a file: {path}")
            if path.name in seen_names:
                fail(f"source file names must be unique within one package: {path.name}")
            seen_names.add(path.name)
            destination = package_root / "00 Source" / path.name
            source_files.append(
                {
                    "file_name": path.name,
                    "original_path": project_relative(path),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "copied_path": None if args.no_copy_source else project_relative(destination),
                    "copy_status": "not_requested" if args.no_copy_source else "planned",
                }
            )
    else:
        for url in source_urls:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                fail(f"source URL must be an http(s) URL: {url}")

    layers = {name.split(" ", 1)[0]: name for name in LAYER_NAMES}
    manifest: dict[str, Any] = {
        "schema_version": "vtc-llm-wiki.source-manifest.v1",
        "record_type": "source_manifest",
        "source_id": source_id,
        "title": args.title,
        "course_code": course_code,
        "source_role": args.source_role,
        "source_kind": args.source_kind,
        "added_at_hkt": now,
        "package_path": package_rel.as_posix(),
        "source_input": {
            "source_files": source_files,
            "source_urls": source_urls,
            "copy_source": bool(args.source_path) and not args.no_copy_source,
        },
        "layers": layers,
        "processing_status": "pending",
        "verification_status": "not_verified",
        "status": "registered",
        "claims_index": "not_created",
        "notes": args.notes,
        "next_step": "Run the source-type-specific extraction/OCR and layout workflow, then manually check source pages before changing verification status.",
    }
    registry_entry: dict[str, Any] = {
        "source_id": source_id,
        "course_code": course_code,
        "source_role": args.source_role,
        "source_kind": args.source_kind,
        "title": args.title,
        "package_status": "registered",
        "package_path": package_rel.as_posix(),
        "source_manifest_path": (package_rel / "source_manifest.json").as_posix(),
        "query_helper_path": None,
        "priority": 1 if args.source_role in {"course_materials", "official_document", "assessment", "past_exam"} else 2,
        "source_files": source_files,
        "source_urls": source_urls,
        "verification_status": "not_verified",
        "claims_index": "not_created",
    }

    result = {
        "source_id": source_id,
        "package_path": package_rel.as_posix(),
        "source_manifest_path": (package_rel / "source_manifest.json").as_posix(),
        "registry_path": project_relative(REGISTRY_PATH),
        "copy_source": manifest["source_input"]["copy_source"],
        "status": "dry_run" if args.dry_run else "registered",
    }
    if args.dry_run:
        print(json.dumps({"plan": result, "manifest": manifest, "registry_entry": registry_entry}, ensure_ascii=False, indent=2))
        return

    package_root.mkdir(parents=True)
    for layer_name in LAYER_NAMES:
        (package_root / layer_name).mkdir()
    for item, raw_path in zip(source_files, args.source_path or []):
        if args.no_copy_source:
            item["copy_status"] = "not_requested"
            continue
        destination = package_root / "00 Source" / item["file_name"]
        shutil.copy2(raw_path.expanduser().resolve(), destination)
        item["copy_status"] = "copied"
    manifest["source_input"]["source_files"] = source_files
    registry_entry["source_files"] = source_files

    package_readme = f"# {args.title}\n\n"
    package_readme += "This source package was created by `tools/register_source.py`.\n\n"
    package_readme += f"- Source ID: `{source_id}`\n- Course: `{course_code}`\n- Role: `{args.source_role}`\n- Kind: `{args.source_kind}`\n- Added: `{now}`\n- Verification: `not_verified`\n\n"
    package_readme += "Processing layers are `00 Source`, `01 OCR and Layout`, `02 Text and Tables`, `03 Analysis`, and `04 Retrieval Index`. Keep the raw source immutable. Label OCR, summaries, tables, quotations, visual interpretations, and retrieval results `generated_not_verified` until manual source review.\n\n"
    package_readme += "The source manifest is `source_manifest.json`. After processing, add a source-specific query helper to the registry when one exists; otherwise this package remains discoverable through its manifest.\n"
    (package_root / "README.md").write_text(package_readme, encoding="utf-8")
    write_json(package_root / "source_manifest.json", manifest)
    registry["updated_at"] = now[:10]
    registry["sources"].append(registry_entry)
    write_json(REGISTRY_PATH, registry)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

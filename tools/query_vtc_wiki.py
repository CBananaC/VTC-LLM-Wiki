#!/usr/bin/env python3
"""Route a study query to registered source-package query helpers.

Each registered helper must accept --query, --term, --limit, and --max-terms
and return one JSON retrieval packet. The router does not merge or reinterpret
those packets; it preserves each package's source priority and verification
boundary for the consuming AI.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "source_registry.json"


def load_registry() -> dict[str, Any]:
    try:
        value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"query_vtc_wiki.py: missing registry: {REGISTRY_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"query_vtc_wiki.py: invalid registry JSON: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        raise SystemExit("query_vtc_wiki.py: registry must contain a sources list")
    return value


def build_parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--query", required=True)
    command.add_argument("--course-code")
    command.add_argument("--source-id")
    command.add_argument("--term", action="append", default=[])
    command.add_argument("--limit", type=int, default=20)
    command.add_argument("--max-terms", type=int, default=30)
    return command


def main() -> int:
    args = build_parser().parse_args()
    registry = load_registry()
    selected: list[dict[str, Any]] = []
    seen_helpers: set[str] = set()
    for source in registry["sources"]:
        if args.course_code and source.get("course_code") != args.course_code:
            continue
        if args.source_id and source.get("source_id") != args.source_id:
            continue
        helper_rel = source.get("query_helper_path")
        if not helper_rel:
            continue
        helper_key = str(helper_rel)
        if helper_key in seen_helpers:
            continue
        seen_helpers.add(helper_key)
        selected.append(source)

    # Registry order reflects addition history, not evidence priority. Keep
    # primary course materials ahead of supplemental books and other sources
    # for every consuming AI, while retaining deterministic source order.
    selected.sort(key=lambda source: (int(source.get("priority", 99)), str(source.get("source_id", ""))))

    if not selected:
        filter_label = args.source_id or args.course_code or "the registry"
        raise SystemExit(f"query_vtc_wiki.py: no registered query helper for {filter_label}")

    packets: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for source in selected:
        helper_path = PROJECT_ROOT / source["query_helper_path"]
        if not helper_path.is_file():
            failures.append({"source_id": source["source_id"], "error": f"missing helper: {helper_path}"})
            continue
        command = [
            sys.executable,
            str(helper_path),
            "--query",
            args.query,
            "--limit",
            str(args.limit),
            "--max-terms",
            str(args.max_terms),
        ]
        for term in args.term:
            command.extend(("--term", term))
        completed = subprocess.run(
            command,
            cwd=helper_path.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or f"helper exited with status {completed.returncode}"
            failures.append({"source_id": source["source_id"], "error": error[-1000:]})
            continue
        try:
            packet = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            failures.append({"source_id": source["source_id"], "error": f"helper returned invalid JSON: {exc}"})
            continue
        packets.append(
            {
                "source_id": source["source_id"],
                "title": source.get("title"),
                "source_role": source.get("source_role"),
                "priority": source.get("priority"),
                "package_path": source.get("package_path"),
                "packet": packet,
            }
        )

    result = {
        "schema_version": "vtc-llm-wiki.retrieval-router.v1",
        "record_type": "project_retrieval_packet",
        "query": args.query,
        "course_code": args.course_code,
        "source_id": args.source_id,
        "packets": packets,
        "failures": failures,
        "status": "generated" if packets and not failures else "partial" if packets else "failed",
        "verification_status": "generated_not_verified",
        "consumer_instruction": "Read source passages before answering, preserve each packet's source priority, cite returned locators, and manually verify quotations or visual/table interpretations against the original source page.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if packets else 1


if __name__ == "__main__":
    raise SystemExit(main())

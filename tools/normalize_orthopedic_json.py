#!/usr/bin/env python3
"""Normalize an output from a reused Davidson-compatible processing engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def replace_tokens(value: Any, replacements: list[tuple[str, str]]) -> Any:
    if isinstance(value, str):
        for old, new in replacements:
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [replace_tokens(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: replace_tokens(item, replacements) for key, item in value.items()}
    return value


def normalize_status_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_status_fields(item) for item in value]
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if key in {"status", "verification_status"} and item in {"generated_candidate", "not_verified"}:
                normalized[key] = "generated_not_verified"
            else:
                normalized[key] = normalize_status_fields(item)
        return normalized
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.expanduser().resolve().read_text(encoding="utf-8"))
    normalized = replace_tokens(data, [("DAV25", "ORTHO3"), ("davidson25", "orthopedic")])
    normalized = normalize_status_fields(normalized)
    args.output.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.expanduser().resolve().write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"input": str(args.input), "output": str(args.output), "status": "normalized"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

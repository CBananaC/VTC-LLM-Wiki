#!/usr/bin/env python3
"""Registry wrapper for the standalone equipment-workshop query helper."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[2]
HELPER = PROJECT_ROOT / "tools/query_hhs4185_source_package.py"
sys.argv.extend(["--package-root", str(PACKAGE_ROOT)])
runpy.run_path(str(HELPER), run_name="__main__")

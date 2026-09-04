#!/usr/bin/env python3
"""Source-specific HHS4867 retrieval wrapper."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from query_hhs4867_retrieval import main

if __name__ == "__main__":
    raise SystemExit(main(default_source_id="HHS4867-L02-MANUAL-MUSCLE-TESTING"))

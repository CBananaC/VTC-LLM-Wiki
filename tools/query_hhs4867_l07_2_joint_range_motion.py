#!/usr/bin/env python3
from pathlib import Path
import query_hhs4867_lecture as query

SOURCE_ID = "HHS4867-L07-2-JOINT-RANGE-MOTION"
ROOT = Path(__file__).resolve().parents[1]
query.SOURCE_ID = SOURCE_ID
query.DEFAULT_INDEX = ROOT / "sources/HHS4867" / SOURCE_ID / "04 Retrieval Index"
query.DEFAULT_TEXT = ROOT / "sources/HHS4867" / SOURCE_ID / "02 Text and Tables"
query.TABLE_FILE = "hhs4867_l07_2_joint_range_motion_tables_generated.json"
query.main()

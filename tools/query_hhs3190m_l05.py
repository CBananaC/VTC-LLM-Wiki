#!/usr/bin/env python3
"""Retrieve source-grounded evidence from HHS3190M Lecture 5."""
import sys

from query_hhs3190m_lecture import main


if __name__ == "__main__":
    if "--source-id" not in sys.argv:
        sys.argv[1:1] = ["--source-id", "HHS3190M-L05-PHYSIOLOGY-2026-07"]
    main()

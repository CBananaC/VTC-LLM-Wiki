#!/usr/bin/env python3
"""Retrieve source-grounded evidence from HHS3190M Anatomy L1."""
import sys

from query_hhs3190m_lecture import main


if __name__ == "__main__":
    if "--source-id" not in sys.argv:
        sys.argv[1:1] = ["--source-id", "HHS3190M-ANATOMY-L01-TERMINOLOGY-2026-07"]
    main()

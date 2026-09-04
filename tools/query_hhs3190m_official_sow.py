#!/usr/bin/env python3
"""Retrieve source-grounded evidence from the HHS3190M official SOW."""

from __future__ import annotations

import sys

import query_hhs3190m_lecture as query


if "--source-id" not in sys.argv:
    sys.argv[1:1] = ["--source-id", "HHS3190M-OFFICIAL-SOW-2026-27"]

query.main()

#!/usr/bin/env python3
"""Build the HHS3190M Semester 1 Scheme of Module Activity package.

The raw source remains bilingual and immutable. The derived layer keeps
English text and list structure, records the three reviewed table locations,
and reconstructs the tables separately from ordinary page text.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import build_hhs3190m_lecture_pdf as builder


COURSE_TITLE = "HHS3190M - Human Physiology and Functional Anatomy for Rehabilitation Services"
SOURCE_ID = "HHS3190M-OFFICIAL-SOW-2026-27"
SOURCE_FILENAME = "01 - S1 SOW (26-27).pdf"
SOURCE_RELATIVE = "01 Official/01 - S1 SOW (26-27).pdf"
OUTPUT_STEM = "hhs3190m_official_sow_2026_27"
STATUS = "generated_not_verified"


def table(page: int, name: str, bbox: list[float], columns: list[str], rows: list[list[object]]) -> dict[str, object]:
    return {"page": page, "name": name, "bbox": bbox, "columns": columns, "rows": rows}


MANUAL_TABLES = [
    table(
        2,
        "Module Assessment Plan",
        [35.0, 65.0, 570.0, 400.0],
        ["Assessment Part (Proportion)", "Assessment Items (Proportion)", "MILO", "Assessment Schedule"],
        [
            [{"text": "Continuous Assessment (CA) (50%)", "row_span": 5}, "(1) CA Physiology Assignment (10%)", "1, 2", "Semester 2"],
            [{"text": "", "source_cell_note": "Covered by the preceding merged Continuous Assessment cell."}, "(2) CA Anatomy Assignment (10%)", "3, 4", "To be announced"],
            [{"text": "", "source_cell_note": "Covered by the preceding merged Continuous Assessment cell."}, "(3) CA Physiology Tutorial Exercises (15%)", "1, 2", "Semester 1"],
            [{"text": "", "source_cell_note": "Covered by the preceding merged Continuous Assessment cell."}, "(4) CA Anatomy Quiz (5%)", "3, 4", "To be announced"],
            [{"text": "", "source_cell_note": "Covered by the preceding merged Continuous Assessment cell."}, "(5) CA Test (10%)", "1, 2, 3, 4", "Semester 1"],
            [{"text": "End-of-Module Assessment (EA) (50%)", "row_span": 2}, "(6) EA Test (20%)", "1, 2, 3, 4", "Semester 2 (Early May)"],
            [{"text": "", "source_cell_note": "Covered by the preceding merged End-of-Module Assessment cell."}, "(7) EA Case Study (30%)", "1, 2, 3, 4, 5", "Semester 2 (Early May)"],
        ],
    ),
    table(
        4,
        "HHS3190M Lesson Plan",
        [35.0, 80.0, 805.0, 532.0],
        [
            "Week",
            "Lecture",
            "Physiology Tutorial 1A (Rm 352)",
            "Physiology Tutorial 1B (Rm 352)",
            "Physiology Tutorial 1C (Rm352)",
            "Anatomy Workshop 1A (Rm 352)",
            "Anatomy Workshop 1B (Rm 352)",
            "Anatomy Workshop 1C (Rm352)",
            "Content",
        ],
        [
            ["1", "02/09/26; 1530-1730", "---", "---", "---", "---", "---", "---", "Physiology Lecture: L1"],
            ["2", "09/09/26; 1530-1730", "---", "---", "---", "09/09/26; 1030-1230", "09/09/26; 0830-1030", "08/09/26; 1330-1530", "Physiology Lecture: L1 + L2; Anatomy Workshop: L1 Terminology"],
            ["3", "---", "15/09/26; 1030-1230", "16/09/26; 0830-1030", "16/09/26; 1330-1530", "---", "---", "---", "Physiology Tutorial: L2 + Ex 1"],
            ["4", "23/09/26; 1530-1730", "---", "---", "---", "23/09/26; 1030-1230", "23/09/26; 0830-1030", "22/09/26; 1330-1530", "Anatomy Lecture: L3 LL Bones; Anatomy Workshop: L2 Bones & Joints"],
            ["5", "30/09/26; 1530-1730", "30/09/26; 1030-1230", "30/09/26; 0830-1030", "29/09/26; 1330-1530", "---", "---", "---", "Physiology Lecture: L4; Physiology Tutorial: L3"],
            ["6", "07/10/26; 1530-1730", "---", "---", "---", "07/10/26; 1030-1230", "07/10/26; 0830-1030", "06/10/26; 1330-1530", "Anatomy Lecture: L4 UL Bones; Anatomy Workshop: WS1 Terminology"],
            ["7", "14/10/26; 1030-1230", "14/10/26; 1030-1230", "14/10/26; 0830-1030", "13/10/26; 1330-1530", "---", "---", "---", "Physiology Lecture: L4 + L5; Physiology Tutorial: CA Ex 2"],
            ["8", "21/10/26; 1530-1730", "---", "---", "---", "21/10/26; 1030-1230", "21/10/26; 0830-1030", "20/10/26; 1330-1530", "Anatomy Lecture: L5 Introduction of Muscles; Anatomy Workshop: WS2 Movement Analysis"],
            ["9", "28/10/26; 1530-1730", "28/10/26; 1030-1230", "28/10/26; 0830-1030", "27/10/26; 1330-1530", "---", "---", "---", "Physiology Lecture: L5; Physiology Tutorial: L5"],
            ["10", "04/11/26; 1530-1730", "---", "---", "---", "04/11/26; 1030-1230", "04/11/26; 0830-1030", "03/11/26; 1330-1530", "Anatomy Lecture: L6 LL Muscles; Anatomy Workshop: WS3 Muscle contraction"],
            ["11", "11/11/26; 1530-1730", "11/11/26; 1030-1230", "11/11/26; 0830-1030", "10/10/26; 1330-1530", "---", "---", "---", "Physiology Lecture: L6; Physiology Tutorial: CA Ex 3"],
            ["12", "18/11/26; 1530-1730", "---", "---", "---", "18/11/26; 1030-1230", "18/11/26; 0830-1030", "17/11/26; 1330-1530", "Anatomy Lecture: L7 UL Muscles; Anatomy Workshop: WS4 Agonist & Antagonist"],
            ["13", "25/11/26; 1530-1730", "25/11/26; 1030-1230", "25/11/26; 0830-1030", "24/10/26; 1330-1530", "---", "---", "---", "Physiology Lecture: L7; Physiology Tutorial: L6 + CA Ex 4"],
            ["14", "02/12/26; 1530-1730", "---", "---", "---", "02/12/26; 1030-1230", "02/12/26; 0830-1030", "01/12/26; 1330-1530", "Anatomy Lecture: Revision; Anatomy Workshop: WS5 Two Joint Muscle"],
            ["15", "09/12/26; 1530-1730", "(Reserved)", "(Reserved)", "(Reserved)", "---", "---", "---", "Physiology Lecture: L7+ Revision"],
            ["16", "16/12/26; 1530-1730", "---", "---", "---", "(Reserved)", "(Reserved)", "(Reserved)", "Anatomy Lecture: TBC; Anatomy Workshop: TBC"],
        ],
    ),
    table(
        5,
        "HHS3190M Teacher's Information",
        [35.0, 62.0, 550.0, 170.0],
        ["Role", "Teacher", "Contact"],
        [
            ["Physiology Teacher", "Ms. Silvia Tsang (Semester 1)", "Email: stsang@vtc.edu.hk; Direct Line / WhatsApp: 26123545"],
            ["Anatomy Teacher", "Ms. Fion Yeung (Semester 1)", "Email: fionyeung@vtc.edu.hk; Direct Line: 26123592 / WhatsApp: 61878933"],
        ],
    ),
]


PARTS = [
    ("Title, outline, and module intended learning outcomes", 1, 1, "front_matter"),
    ("Module assessment plan and pass requirements", 2, 2, "official_requirements"),
    ("Assessment implementation, attendance, and reassessment rules", 3, 3, "official_requirements"),
    ("HHS3190M lesson plan", 4, 4, "schedule"),
    ("HHS3190M teacher information", 5, 5, "contact_information"),
]


KEYWORDS = [
    ("document_concepts", "Scheme of Module Activity"),
    ("document_concepts", "Module Intended Learning Outcomes"),
    ("document_concepts", "MILO"),
    ("learning_outcomes", "homeostasis"),
    ("learning_outcomes", "physiological disorders"),
    ("learning_outcomes", "musculoskeletal structures"),
    ("learning_outcomes", "functional movements"),
    ("learning_outcomes", "human physiology"),
    ("learning_outcomes", "functional anatomy"),
    ("assessment", "Continuous Assessment"),
    ("assessment", "CA Physiology Assignment"),
    ("assessment", "CA Physiology Tutorial Exercises"),
    ("assessment", "CA Anatomy Assignment"),
    ("assessment", "CA Anatomy Quiz"),
    ("assessment", "CA Test"),
    ("assessment", "End-of-Module Assessment"),
    ("assessment", "EA Test"),
    ("assessment", "EA Case Study"),
    ("assessment", "closed-book written test"),
    ("assessment", "opened-book case study assessment"),
    ("requirements", "70% attendance"),
    ("requirements", "minimum attendance requirement"),
    ("requirements", "40% of overall EA mark"),
    ("requirements", "40% of overall module mark"),
    ("requirements", "re-assessment"),
    ("requirements", "3 working days"),
    ("schedule", "Lesson Plan"),
    ("schedule", "Physiology Lecture"),
    ("schedule", "Physiology Tutorial"),
    ("schedule", "Anatomy Lecture"),
    ("schedule", "Anatomy Workshop"),
    ("schedule", "Moodle"),
    ("schedule", "Reserved"),
    ("schedule", "TBC"),
]


def configure() -> None:
    builder.COURSE_CODE = "HHS3190M"
    builder.COURSE_TITLE = COURSE_TITLE
    builder.SOURCE_ID = SOURCE_ID
    builder.DOCUMENT_ID = SOURCE_ID
    builder.SOURCE_FILENAME = SOURCE_FILENAME
    builder.SOURCE_RELATIVE = SOURCE_RELATIVE
    builder.OUTPUT_STEM = OUTPUT_STEM
    builder.QUERY_HELPER_PATH = "../../../tools/query_hhs3190m_official_sow.py"
    builder.MANUAL_TABLES = MANUAL_TABLES
    builder.DOCUMENT = {
        "document_id": SOURCE_ID,
        "file_name": SOURCE_FILENAME,
        "source_type": "official_document",
        "title": "Semester 1 (26-27) Scheme of Module Activity",
    }
    builder.TOPIC_PARTS = [
        {
            "unit_id": f"{SOURCE_ID}-PART{index:02d}",
            "title": title,
            "slide_start": start,
            "slide_end": end,
            "kind": kind,
        }
        for index, (title, start, end, kind) in enumerate(PARTS)
    ]
    builder.OUTLINE_MAP = [
        {"outline_item": "Module Intended Learning Outcomes (MILO)", "mapped_slides": [1], "mapping_status": STATUS},
        {"outline_item": "Module Assessment Plan", "mapped_slides": [2, 3], "mapping_status": STATUS},
        {"outline_item": "Lesson Plan", "mapped_slides": [4], "mapping_status": STATUS},
        {"outline_item": "Teacher's Information", "mapped_slides": [5], "mapping_status": STATUS},
    ]
    builder.SLIDE_TITLE_OVERRIDES = {
        1: "Semester 1 (26-27) Scheme of Module Activity",
        2: "Module Assessment Plan",
        3: "Physiology and Anatomy Assessments",
        4: "HHS3190M Lesson Plan",
        5: "HHS3190M Teacher's Information",
    }
    builder.LECTURE_KEYWORDS = KEYWORDS
    builder.SCHEMA = "vtc-hhs3190m-official-document.v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs3190m-course"))
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    configure()
    delegated = [
        sys.argv[0],
        "--course-root", str(args.course_root),
        "--output-root", str(args.output_root),
        "--dpi", str(args.dpi),
        "--paddle-cache", str(args.paddle_cache),
    ]
    if args.skip_paddle:
        delegated.append("--skip-paddle")
    if args.overwrite:
        delegated.append("--overwrite")
    sys.argv = delegated
    builder.main()


if __name__ == "__main__":
    main()

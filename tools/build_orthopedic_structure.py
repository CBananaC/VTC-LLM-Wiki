#!/usr/bin/env python3
"""Build the source structure map for Special Tests for Orthopedic Examination.

The scan has no usable PDF outline.  The printed contents pages (PDF pages
9-13) are therefore recorded as the authoritative candidate map for the
book's twelve body sections and their test entries.  Physical PDF pages are
kept alongside printed pages because the PDF begins the numbered body at
physical page 25 (printed page 1).  The map is a generated candidate and must
remain subject to source-page review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


BOOK_ID = "ORTHO3"
SOURCE_ID = "HHS4185-REF-ORTHO-SPECIAL-TESTS"
TITLE = "Special Tests for Orthopedic Examination"
EDITION = "3rd"
PDF_PAGE_COUNT = 380
BODY_PDF_START = 25
BODY_PRINTED_START = 1
PRINTED_PAGE_OFFSET = BODY_PDF_START - BODY_PRINTED_START
TOC_PDF_PAGES = [9, 10, 11, 12, 13]


SECTIONS: list[tuple[str, str, int, list[tuple[str, int]]]] = [
    (
        "1",
        "Temporomandibular",
        1,
        [
            ("Chvostek's Sign", 2),
            ("Loading Test", 4),
            ("Palpation Test", 5),
        ],
    ),
    (
        "2",
        "Cervical Spine",
        9,
        [
            ("Vertebral Artery Test", 10),
            ("Foraminal Compression Test (Spurling)", 12),
            ("Foraminal Distraction Test", 15),
            ("Valsalva's Maneuver", 17),
            ("Swallowing Test", 19),
            ("Tinel's Sign", 20),
        ],
    ),
    (
        "3",
        "Shoulder",
        23,
        [
            ("Empty Can (Supraspinatus) Test", 24),
            ("Yergason Test", 25),
            ("Speed's Test", 27),
            ("Ludington's Sign", 29),
            ("Drop Arm Test", 30),
            ("Lateral Scapular Slide Test (LSST)", 32),
            ("Apley's Scratch Test", 35),
            ("Cross-Over Impingement Test", 39),
            ("Posterior Impingement Test", 40),
            ("Neer Impingement Test", 42),
            ("Hawkins-Kennedy Impingement Test", 44),
            ("Sternoclavicular (SC) Joint Stress Test", 46),
            ("Acromioclavicular (AC) Joint Distraction Test", 47),
            ("Acromioclavicular (AC) Joint Compression Test (Shear)", 48),
            ("Piano Key Sign", 50),
            ("Apprehension Test (Anterior)", 52),
            ("Apprehension Test (Posterior)", 54),
            ("Sulcus Sign", 56),
            ("Anterior Drawer Test", 58),
            ("Posterior Drawer Test", 60),
            ("Jobe Relocation Test", 62),
            ("Surprise Test (Active Release Test)", 64),
            ("Feagin Test", 66),
            ("Load and Shift Test", 67),
            ("Grind Test", 69),
            ("Clunk Test", 70),
            ("Crank Test", 72),
            ("O'Brien Test (Active Compression)", 74),
            ("Brachial Plexus Stretch Test", 76),
            ("Adson's Maneuver", 77),
            ("Allen's Test", 79),
            ("Roos Test", 81),
            ("Military Brace Position", 83),
            ("Pectoralis Major Contracture Test", 84),
        ],
    ),
    (
        "4",
        "Elbow",
        87,
        [
            ("Resistive Tennis Elbow Test (Cozen's Test)", 88),
            ("Resistive Tennis Elbow Test", 90),
            ("Passive Tennis Elbow Test", 92),
            ("Golfer's Elbow Test", 94),
            ("Hyperextension Test", 96),
            ("Elbow Flexion Test", 97),
            ("Varus Stress Test", 99),
            ("Valgus Stress Test", 100),
            ("Tinel's Sign", 102),
            ("Pinch Grip Test", 104),
        ],
    ),
    (
        "5",
        "Wrist and Hand",
        107,
        [
            ("Tap or Percussion Test", 108),
            ("Compression Test", 110),
            ("Long Finger Flexion Test", 111),
            ("Finkelstein Test", 113),
            ("Phalen Test", 115),
            ("Reverse Phalen Test", 117),
            ("Tinel's Sign", 118),
            ("Froment's Sign", 120),
            ("Wrinkle Test", 121),
            ("Digital Allen's Test", 122),
            ("Bunnel Littler Test", 125),
            ("Murphy's Sign", 127),
            ("Watson Test", 128),
            ("Valgus Stress Test", 130),
            ("Varus Stress Test", 132),
        ],
    ),
    (
        "6",
        "Thoracic Spine",
        135,
        [
            ("Kernig/Brudzinski Signs", 136),
            ("Lateral and Anterior/Posterior Rib Compression Tests", 138),
            ("Inspiration/Expiration Breathing Test", 140),
        ],
    ),
    (
        "7",
        "Lumbar Spine",
        143,
        [
            ("Valsalva's Maneuver", 144),
            ("Stoop Test", 146),
            ("Hoover Test", 148),
            ("Kernig/Brudzinski Signs", 150),
            ("90-90 Straight Leg Raise Test", 152),
            ("Bowstring Test (Cram Test)", 154),
            ("Sitting Root Test", 156),
            ("Unilateral Straight Leg Raise Test (Lasegue Test)", 159),
            ("Bilateral Straight Leg Raise Test", 161),
            ("Well Straight Leg Raise Test", 163),
            ("Slump Test", 165),
            ("Thomas Test", 170),
            ("Spring Test", 173),
            ("Trendelenburg's Test", 175),
            ("Stork Standing Test", 178),
        ],
    ),
    (
        "8",
        "Sacral Spine",
        183,
        [
            ("Sacroiliac (SI) Joint Fixation Test", 184),
            ("Gillet Test", 191),
            ("Sacroiliac (SI) Joint Stress Test", 193),
            ("Squish Test", 197),
            ("Yeoman's Test", 198),
            ("Gaenslen's Test", 200),
            ("Patrick or FABER Test", 201),
            ("Long-Sitting Test", 203),
        ],
    ),
    (
        "9",
        "Hip",
        207,
        [
            ("Hip Scouring/Quadrant Test", 208),
            ("Craig's Test", 211),
            ("90-90 Straight Leg Raise Test", 214),
            ("Patrick or FABER Test", 216),
            ("Trendelenburg's Test", 218),
            ("Ober's Test", 221),
            ("Piriformis Test", 224),
            ("Thomas Test", 226),
            ("True Leg-Length Discrepancy Test", 229),
            ("Apparent Leg-Length Discrepancy Test", 230),
            ("Ely's Test", 232),
            ("Femoral Nerve Traction Test", 234),
        ],
    ),
    (
        "10",
        "Knee",
        239,
        [
            ("Patella Tendon/Patella Ligament Length Test", 240),
            ("Patellar Apprehension Test", 242),
            ("Ballotable Patella or Patella Tap Test", 244),
            ("Sweep Test (Wipe, Brush, Bulge, or Stroke Test)", 245),
            ("Q-Angle Test", 247),
            ("Medial-Lateral Grind Test", 249),
            ("Bounce Home Test", 252),
            ("Patellar Grind Test (Clarke's Sign)", 255),
            ("Renne Test", 258),
            ("Noble Test", 261),
            ("Hughston's Plica Test", 264),
            ("Godfrey 90/90 Test", 266),
            ("Posterior Sag Test (Gravity Drawer Test)", 267),
            ("Reverse Pivot Shift (Jakob Test)", 269),
            ("Anterior Lachman's Test", 272),
            ("Anterior Drawer Test", 274),
            ("Slocum Test With Internal Tibial Rotation", 276),
            ("Slocum Test With External Tibial Rotation", 278),
            ("Pivot Shift Test", 280),
            ("Jerk Test", 284),
            ("Posterior Drawer Test", 288),
            ("Hughston Posteromedial Drawer Test", 290),
            ("Hughston Posterolateral Drawer Test", 292),
            ("Posterior Lachman's Test", 294),
            ("External Rotation Recurvatum Test", 296),
            ("Dial Test (Tibial External Rotation Test)", 298),
            ("Valgus Stress Test", 301),
            ("Varus Stress Test", 304),
            ("McMurray Test", 307),
            ("Apley Compression Test", 310),
            ("Steinman's Tenderness Displacement Test", 312),
        ],
    ),
    (
        "11",
        "Ankle and Foot",
        317,
        [
            ("Homans' Sign", 318),
            ("Anterior Drawer Test", 321),
            ("Talar Tilt Test (Inversion)", 324),
            ("Talar Tilt Test (Eversion)", 326),
            ("Thompson Test", 328),
            ("Tap or Percussion Test", 330),
            ("Feiss Line", 331),
            ("Interdigital Neuroma Test", 333),
            ("Compression Test", 335),
            ("Long Bone Compression Test", 336),
            ("Swing Test", 337),
            ("Kleiger's Test", 339),
            ("Tinel's Sign", 342),
        ],
    ),
    (
        "12",
        "Contemporary Special Tests",
        345,
        [
            ("Impingement Reduction Test", 346),
            ("Walking Arm Stress (WAS) Test", 349),
            ("Finger Extension Test", 351),
            ("Flexor Pronator Syndrome Test", 353),
            ("Tarsal Twist Test", 355),
        ],
    ),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def physical_page(printed_page: int) -> int:
    return printed_page + PRINTED_PAGE_OFFSET


def page_reference(pdf_page: int, printed_page: int | None, role: str) -> dict[str, Any]:
    return {
        "source_page_id": f"ORTHO3-PDF{pdf_page:04d}",
        "pdf_page": pdf_page,
        "printed_page": printed_page,
        "page_number_type": "printed_book_page" if printed_page is not None else "unumbered_pdf_page",
        "role": role,
    }


def build_structure(source: Path) -> dict[str, Any]:
    chapters: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    part_id = "ORTHO3-PART01"
    for section_index, (number, title, printed_start, tests) in enumerate(SECTIONS, 1):
        next_printed = SECTIONS[section_index][2] if section_index < len(SECTIONS) else 357
        section_pdf_start = physical_page(printed_start)
        section_pdf_end = physical_page(next_printed) - 1
        chapter_id = f"ORTHO3-CH{int(number):02d}"
        test_nodes: list[dict[str, Any]] = []
        for test_index, (test_title, test_printed_start) in enumerate(tests, 1):
            next_test_printed = tests[test_index][1] if test_index < len(tests) else next_printed
            test_pdf_start = physical_page(test_printed_start)
            test_pdf_end = physical_page(next_test_printed) - 1
            test_id = f"ORTHO3-CH{int(number):02d}-M{test_index:02d}"
            component_ids: list[str] = []
            components = [
                ("TEST POSITIONING", "test_positioning"),
                ("ACTION", "action"),
                ("POSITIVE FINDING", "positive_finding"),
                ("SPECIAL CONSIDERATIONS/COMMENTS", "special_considerations_comments"),
                ("REFERENCES", "references"),
            ]
            for component_index, (component_title, component_kind) in enumerate(components, 1):
                component_id = f"{test_id}-S{component_index:02d}"
                component_ids.append(component_id)
                nodes.append({
                    "section_id": component_id,
                    "level": "subsection",
                    "title": component_title,
                    "title_kind": component_kind,
                    "parent_id": test_id,
                    "chapter_id": chapter_id,
                    "part_id": part_id,
                    "pdf_page_start": test_pdf_start,
                    "pdf_page_end": test_pdf_end,
                    "printed_page_start": test_printed_start,
                    "printed_page_end": next_test_printed - 1,
                    "section_path": ["Special Tests for Orthopedic Examination", f"Section {number}: {title}", test_title, component_title],
                    "children": [],
                    "status": "generated_not_verified",
                    "verification_status": "generated_not_verified",
                })
            test_node = {
                "section_id": test_id,
                "level": "major_section",
                "title": test_title,
                "title_kind": "orthopedic_test",
                "parent_id": chapter_id,
                "chapter_id": chapter_id,
                "part_id": part_id,
                "pdf_page_start": test_pdf_start,
                "pdf_page_end": test_pdf_end,
                "printed_page_start": test_printed_start,
                "printed_page_end": next_test_printed - 1,
                "section_path": ["Special Tests for Orthopedic Examination", f"Section {number}: {title}", test_title],
                "children": component_ids,
                "subsection_ids": component_ids,
                "status": "generated_not_verified",
                "verification_status": "generated_not_verified",
            }
            test_nodes.append(test_node)
            nodes.append(test_node)
        chapter = {
            "section_id": chapter_id,
            "level": "chapter",
            "chapter_number": int(number),
            "title": title,
            "title_kind": "body_section",
            "parent_id": part_id,
            "part_id": part_id,
            "pdf_page_start": section_pdf_start,
            "pdf_page_end": section_pdf_end,
            "printed_page_start": printed_start,
            "printed_page_end": next_printed - 1,
            "section_path": ["Special Tests for Orthopedic Examination", f"Section {number}: {title}"],
            "children": [node["section_id"] for node in test_nodes],
            "major_section_ids": [node["section_id"] for node in test_nodes],
            "test_count": len(test_nodes),
            "status": "generated_not_verified",
            "verification_status": "generated_not_verified",
        }
        chapters.append(chapter)
        nodes.append(chapter)

    part = {
        "section_id": part_id,
        "level": "part",
        "title": TITLE,
        "title_kind": "book",
        "parent_id": None,
        "pdf_page_start": 1,
        "pdf_page_end": PDF_PAGE_COUNT,
        "printed_page_start": None,
        "printed_page_end": 356,
        "section_path": [TITLE],
        "children": [chapter["section_id"] for chapter in chapters],
        "chapter_ids": [chapter["section_id"] for chapter in chapters],
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
    }
    nodes.append(part)

    front_matter = [
        page_reference(1, None, "cover"),
        page_reference(3, None, "title_page"),
        page_reference(4, None, "digitization_notice"),
        page_reference(5, None, "title_and_authors"),
        page_reference(6, None, "copyright_and_cataloguing"),
        page_reference(7, "v", "dedication"),
        *[page_reference(page, None, "contents") for page in TOC_PDF_PAGES],
        page_reference(14, "xii", "acknowledgments_third_edition"),
        page_reference(15, "xiii", "acknowledgments_second_edition"),
        page_reference(16, "xiii", "acknowledgments_first_edition"),
        page_reference(17, "xiv", "foreword_third_edition"),
        page_reference(18, "xv", "foreword_second_edition"),
        page_reference(19, "xvi", "foreword_first_edition"),
        page_reference(20, "xvii", "preface_third_edition"),
        page_reference(21, "xviii", "preface_third_edition_continuation"),
        page_reference(22, "xix", "introduction_third_edition"),
        page_reference(23, "xx", "introduction_third_edition_continuation"),
        page_reference(24, None, "section_divider_or_scan_artifact"),
    ]
    return {
        "schema_version": "vtc-ortho3.book-structure.v1",
        "record_type": "book_structure_candidate",
        "book_id": BOOK_ID,
        "source_id": SOURCE_ID,
        "title": TITLE,
        "edition": EDITION,
        "pdf_page_count": PDF_PAGE_COUNT,
        "source": {
            "filename": source.name,
            "path": str(source),
            "sha256": sha256_file(source),
            "pdf_page_count": PDF_PAGE_COUNT,
            "pdf_page_size_points": [315.2, 569.4],
            "orientation": "portrait",
            "encrypted": False,
            "pdf_outline_status": "no_outline_found",
        },
        "toc": {
            "pdf_pages": TOC_PDF_PAGES,
            "method": "printed_contents_pages plus page-image inspection and embedded-text cross-check",
            "body_sections": len(SECTIONS),
            "test_entries": sum(len(section[3]) for section in SECTIONS),
            "index_status": "contents lists Index at printed page 359, but this 380-page file ends at printed page 356; no index pages are present in the supplied PDF",
        },
        "page_numbering": {
            "body_printed_page_start": BODY_PRINTED_START,
            "body_pdf_page_start": BODY_PDF_START,
            "pdf_to_printed_offset": PRINTED_PAGE_OFFSET,
            "rule": "for printed body pages 1-356, PDF page = printed page + 24; front matter uses Roman labels and PDF navigation pages",
        },
        "hierarchy_order": ["part", "chapter", "major_section", "subsection", "paragraph"],
        "hierarchy_semantics": {
            "part": "the book as a single top-level unit",
            "chapter": "printed Section 1 through Section 12 body divisions",
            "major_section": "one named orthopedic test",
            "subsection": "the recurring test components: TEST POSITIONING, ACTION, POSITIVE FINDING, SPECIAL CONSIDERATIONS/COMMENTS, REFERENCES",
            "paragraph": "reconstructed prose or preserved list item inside a test component",
        },
        "front_matter": front_matter,
        "parts": [
            {
                **part,
                "chapters": chapters,
            }
        ],
        "nodes": nodes,
        "status": "generated_not_verified",
        "verification_status": "generated_not_verified",
        "verification_notes": [
            "Section and test titles were checked against rendered contents pages 9-13.",
            "Physical-to-printed page offset was checked against body headers on representative pages.",
            "OCR spelling and exact component boundaries require page-level review during text reconstruction.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    structure = build_structure(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "chapters": len(SECTIONS),
        "tests": sum(len(section[3]) for section in SECTIONS),
        "subsections": sum(len(section[3]) * 5 for section in SECTIONS),
        "pdf_pages": PDF_PAGE_COUNT,
        "printed_body_pages": 356,
        "status": structure["verification_status"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

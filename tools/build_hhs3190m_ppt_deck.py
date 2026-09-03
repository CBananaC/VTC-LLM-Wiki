#!/usr/bin/env python3
"""Build one deduplicated HHS3190M Physiology & Anatomy presentation package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import build_hhs3190m_lecture_pdf as builder


COURSE_TITLE = "HHS3190M - Human Physiology and Functional Anatomy for Rehabilitation Services"
STATUS = "generated_not_verified"


def part(source_id: str, number: int, title: str, start: int, end: int, kind: str = "topic") -> dict[str, object]:
    return {
        "unit_id": f"{source_id}-PART{number:02d}",
        "title": title,
        "slide_start": start,
        "slide_end": end,
        "kind": kind,
    }


CONFIGS: dict[str, dict[str, object]] = {
    "HHS3190M-L02-PHYSIOLOGY-2026-07": {
        "filename": "03 - HHS3190MJ Physiology L2 (Jul 2026).pdf",
        "relative": "02 Lectures/03 - HHS3190MJ Physiology L2 (Jul 2026).pdf",
        "stem": "hhs3190m_l02",
        "lecture_number": 2,
        "title": "Lecture 2 - Human Cells, Basic Tissues, and Organs (July 2026)",
        "parts": [
            ("Cover and Outline", 1, 2, "front_matter"),
            ("Human cells: structure and basic properties", 3, 5, "topic"),
            ("Cell organelles in a typical human cell", 6, 16, "topic"),
            ("Primary tissues in the human body", 17, 28, "topic"),
            ("L2 Revision Exercise", 29, 29, "revision"),
            ("References", 30, 30, "references"),
        ],
        "keywords": [
            ("definitions_abbreviations", "cell"), ("definitions_abbreviations", "tissue"),
            ("definitions_abbreviations", "organ"), ("section_topics", "cell membrane"),
            ("section_topics", "cytosol"), ("section_topics", "mitochondria"),
            ("section_topics", "endoplasmic reticulum"), ("section_topics", "Golgi apparatus"),
            ("section_topics", "lysosome"), ("section_topics", "nucleus"),
            ("section_topics", "epithelial tissue"), ("section_topics", "connective tissue"),
            ("section_topics", "muscle tissue"), ("section_topics", "nervous tissue"),
        ],
    },
    "HHS3190M-L03-PHYSIOLOGY-2026-07": {
        "filename": "05 - HHS3190MJ Physiology L3 (Jul 2026).pdf",
        "relative": "02 Lectures/05 - HHS3190MJ Physiology L3 (Jul 2026).pdf",
        "stem": "hhs3190m_l03",
        "lecture_number": 3,
        "title": "Lecture 3 - Membrane Transport (July 2026)",
        "parts": [
            ("Cover and Outline", 1, 2, "front_matter"),
            ("Revision: structure and properties of the cell membrane", 3, 5, "revision"),
            ("Passive membrane transport", 6, 12, "topic"),
            ("Active membrane transport", 13, 20, "topic"),
            ("Membrane transport and membrane potential", 21, 22, "topic"),
            ("L3 Revision Exercise", 23, 23, "revision"),
            ("References", 24, 24, "references"),
        ],
        "keywords": [
            ("definitions_abbreviations", "selective permeability"), ("section_topics", "simple diffusion"),
            ("section_topics", "facilitated diffusion"), ("section_topics", "osmosis"),
            ("section_topics", "passive transport"), ("section_topics", "active transport"),
            ("section_topics", "primary active transport"), ("section_topics", "secondary active transport"),
            ("section_topics", "sodium-potassium pump"), ("section_topics", "endocytosis"),
            ("section_topics", "exocytosis"), ("section_topics", "membrane potential"),
            ("section_topics", "resting membrane potential"),
        ],
    },
    "HHS3190M-L04-PHYSIOLOGY-2026-07": {
        "filename": "07 - HHS3190MJ Physiology L4 (Jul 2026).pdf",
        "relative": "02 Lectures/07 - HHS3190MJ Physiology L4 (Jul 2026).pdf",
        "stem": "hhs3190m_l04",
        "lecture_number": 4,
        "title": "Lecture 4 - Cellular Energetics and Homeostasis (July 2026)",
        "parts": [
            ("Cover and Outline", 1, 2, "front_matter"),
            ("Basic concepts of cellular energetics and metabolism", 3, 6, "topic"),
            ("Nature and functions of enzymes", 7, 18, "topic"),
            ("Concepts of homeostasis", 19, 22, "topic"),
            ("Examples of homeostasis", 23, 26, "topic"),
            ("L4 Revision Exercise", 27, 27, "revision"),
            ("References", 28, 28, "references"),
        ],
        "keywords": [
            ("section_topics", "cellular energetics"), ("section_topics", "metabolism"),
            ("section_topics", "exergonic reaction"), ("section_topics", "endergonic reaction"),
            ("section_topics", "anabolism"), ("section_topics", "catabolism"),
            ("definitions_abbreviations", "enzyme"), ("section_topics", "active site"),
            ("section_topics", "substrate"), ("section_topics", "co-enzyme"),
            ("section_topics", "metabolic pathway"), ("section_topics", "homeostasis"),
            ("section_topics", "negative feedback"), ("section_topics", "positive feedback"),
        ],
    },
    "HHS3190M-L05-PHYSIOLOGY-2026-07": {
        "filename": "09 - HHS3190MJ Physiology L5 (Jul 2026).pdf",
        "relative": "02 Lectures/09 - HHS3190MJ Physiology L5 (Jul 2026).pdf",
        "stem": "hhs3190m_l05",
        "lecture_number": 5,
        "title": "Lecture 5 - Digestive System and Digestion (July 2026)",
        "parts": [
            ("Cover and Outline", 1, 2, "front_matter"),
            ("Overview of the digestive system", 3, 10, "topic"),
            ("Basic structure of the alimentary canal", 11, 12, "topic"),
            ("Functional anatomy of the digestive system", 13, 30, "topic"),
            ("Physiology of digestion and absorption", 31, 44, "topic"),
            ("L5 Revision Exercise", 45, 45, "revision"),
            ("References", 46, 46, "references"),
        ],
        "keywords": [
            ("section_topics", "digestive system"), ("section_topics", "gastrointestinal tract"),
            ("section_topics", "alimentary canal"), ("section_topics", "peristalsis"),
            ("section_topics", "mouth"), ("section_topics", "stomach"),
            ("section_topics", "small intestine"), ("section_topics", "large intestine"),
            ("section_topics", "liver"), ("section_topics", "gallbladder"),
            ("section_topics", "pancreas"), ("section_topics", "villi"),
            ("section_topics", "chemical digestion"), ("section_topics", "absorption"),
            ("section_topics", "bile"), ("section_topics", "digestive enzymes"),
        ],
    },
    "HHS3190M-L06-PHYSIOLOGY-2026-07": {
        "filename": "11 - HHS3190MJ Physiology L6 (Jul 2026).pdf",
        "relative": "02 Lectures/11 - HHS3190MJ Physiology L6 (Jul 2026).pdf",
        "stem": "hhs3190m_l06",
        "lecture_number": 6,
        "title": "Lecture 6 - Respiratory System and Gas Exchange (July 2026)",
        "parts": [
            ("Cover and Outline", 1, 2, "front_matter"),
            ("Anatomy of the respiratory system", 3, 15, "topic"),
            ("Mechanics of ventilation", 16, 18, "topic"),
            ("Respiratory volumes, capacities, and ventilation", 19, 27, "topic"),
            ("Gas exchange between the lungs and blood", 28, 37, "topic"),
            ("Control of breathing", 38, 43, "topic"),
            ("L6 Revision Exercise", 44, 44, "revision"),
            ("References", 45, 45, "references"),
        ],
        "keywords": [
            ("section_topics", "respiratory system"), ("section_topics", "nasal cavity"),
            ("section_topics", "trachea"), ("section_topics", "bronchial tree"),
            ("section_topics", "alveoli"), ("section_topics", "pleura"),
            ("section_topics", "inspiration"), ("section_topics", "expiration"),
            ("section_topics", "tidal volume"), ("section_topics", "residual volume"),
            ("section_topics", "vital capacity"), ("section_topics", "alveolar ventilation"),
            ("section_topics", "gas exchange"), ("section_topics", "partial pressure"),
            ("section_topics", "hemoglobin"), ("section_topics", "control of breathing"),
        ],
    },
    "HHS3190M-L07-PHYSIOLOGY-2026-07": {
        "filename": "13 - HHS3190MJ Physiology L7 (Jul 2026).pdf",
        "relative": "02 Lectures/13 - HHS3190MJ Physiology L7 (Jul 2026).pdf",
        "stem": "hhs3190m_l07",
        "lecture_number": 7,
        "title": "Lecture 7 - Endocrine System and Hormone Regulation (July 2026)",
        "parts": [
            ("Cover and Outline", 1, 2, "front_matter"),
            ("Overview of the endocrine system", 3, 8, "topic"),
            ("Hormone chemical structures and mechanisms of action", 9, 16, "topic"),
            ("Regulation of hormone secretion", 17, 20, "topic"),
            ("Examples of endocrine disorders", 21, 22, "topic"),
            ("L7 Revision Exercise", 23, 23, "revision"),
            ("References", 24, 24, "references"),
        ],
        "keywords": [
            ("section_topics", "endocrine system"), ("section_topics", "endocrine gland"),
            ("section_topics", "exocrine gland"), ("definitions_abbreviations", "hormone"),
            ("section_topics", "target cell"), ("section_topics", "water-soluble hormone"),
            ("section_topics", "lipid-soluble hormone"), ("section_topics", "second messenger"),
            ("section_topics", "cAMP"), ("section_topics", "G protein"),
            ("section_topics", "intracellular receptor"), ("section_topics", "negative feedback"),
            ("section_topics", "hypothalamus-pituitary-adrenal axis"),
            ("section_topics", "hypothalamus-pituitary-thyroid axis"),
            ("section_topics", "thyroid hormones"), ("section_topics", "acromegaly"),
        ],
    },
    "HHS3190M-ANATOMY-L01-TERMINOLOGY-2026-07": {
        "filename": "15 - J L1 Terminology for anatomy.pdf",
        "relative": "02 Lectures/15 - J L1 Terminology for anatomy.pdf",
        "stem": "hhs3190m_anatomy_l01",
        "lecture_number": 1,
        "title": "Anatomy L1 - Terminology for Anatomy (July 2026)",
        "parts": [
            ("Cover and Introduction", 1, 2, "front_matter"),
            ("Anatomical position, planes, and positions", 3, 8, "topic"),
            ("Terminology related to movements", 9, 14, "topic"),
            ("Terminologies related to bone markings", 15, 16, "topic"),
            ("References", 17, 17, "references"),
        ],
        "keywords": [
            ("definitions_abbreviations", "anatomical position"), ("section_topics", "sagittal plane"),
            ("section_topics", "coronal plane"), ("section_topics", "transverse plane"),
            ("section_topics", "anterior"), ("section_topics", "posterior"),
            ("section_topics", "medial"), ("section_topics", "lateral"),
            ("section_topics", "proximal"), ("section_topics", "distal"),
            ("section_topics", "flexion"), ("section_topics", "extension"),
            ("section_topics", "abduction"), ("section_topics", "adduction"),
            ("section_topics", "pronation"), ("section_topics", "supination"),
            ("section_topics", "dorsiflexion"), ("section_topics", "plantar flexion"),
            ("section_topics", "bone markings"), ("section_topics", "condyle"),
        ],
    },
}


def configure(source_id: str) -> dict[str, object]:
    config = CONFIGS[source_id]
    parts = [part(source_id, i, title, start, end, kind) for i, (title, start, end, kind) in enumerate(config["parts"])]
    outline = [
        {"outline_item": item[0], "mapped_slides": list(range(int(item[1]), int(item[2]) + 1)), "mapping_status": STATUS}
        for item in config["parts"]
        if item[3] not in {"front_matter", "references"}
    ]
    builder.COURSE_CODE = "HHS3190M"
    builder.COURSE_TITLE = COURSE_TITLE
    builder.SOURCE_ID = source_id
    builder.DOCUMENT_ID = source_id
    builder.SOURCE_FILENAME = str(config["filename"])
    builder.SOURCE_RELATIVE = str(config["relative"])
    builder.OUTPUT_STEM = str(config["stem"])
    builder.QUERY_HELPER_PATH = f"../../../tools/query_{config['stem']}.py"
    builder.DOCUMENT = {
        "document_id": source_id,
        "file_name": str(config["filename"]),
        "source_type": "lecture",
        "lecture_number": int(config["lecture_number"]),
        "title": str(config["title"]),
    }
    builder.TOPIC_PARTS = parts
    builder.OUTLINE_MAP = outline
    builder.SLIDE_TITLE_OVERRIDES = {}
    builder.LECTURE_KEYWORDS = list(config["keywords"])
    builder.SCHEMA = "vtc-hhs3190m-lecture.v1"
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True, choices=sorted(CONFIGS))
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs3190m-course"))
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    configure(args.source_id)
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

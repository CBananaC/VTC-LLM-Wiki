#!/usr/bin/env python3
"""Run the shared HHS4867 bilingual-PPT PDF workflow for one deck.

The deck-specific configuration keeps duplicate copies out of processing,
preserves English point form, and gives each unique PowerPoint export its own
source package and retrieval path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import build_hhs4867_lecture_pdf as builder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COURSE_ROOT_DEFAULT = Path("/Users/creamybanana/Downloads/Movement Science")
COURSE_TITLE = "HHS4867 - Functional Movement Science"


def title_map(values: list[str]) -> dict[int, str]:
    return dict(enumerate(values, 1))


def part_map(source_id: str, values: list[tuple[str, int, int, str]]) -> list[dict[str, object]]:
    return [
        {"unit_id": f"{source_id}-PART{index:02d}", "title": title, "slide_start": start, "slide_end": end, "kind": kind}
        for index, (title, start, end, kind) in enumerate(values)
    ]


DECKS: dict[str, dict[str, object]] = {
    "HHS4867-L02-NEUROMUSCULAR-CONTROL": {
        "filename": "05 - 2. Neuromuscular control of movement 人體運動神經控制.pdf",
        "relative": "02 Lectures/05 - 2. Neuromuscular control of movement 人體運動神經控制.pdf",
        "title": "Lecture 2 - Neuromuscular Control of Human Movement",
        "lecture_number": 2,
        "stem": "hhs4867_l02_neuromuscular_control",
        "helper": "../../tools/query_hhs4867_l02_neuromuscular.py",
        "parts": [("Introduction to neuromuscular control", 1, 3, "topic"), ("Nervous system organization", 4, 7, "topic"), ("Spinal nerves", 8, 11, "topic"), ("Motor units", 12, 13, "topic"), ("Sensory receptors, reflexes, and proprioceptors", 14, 18, "topic")],
        "titles": title_map(["Neuromuscular control of human movement", "Introduction", "Introduction", "Nervous System", "Central Nervous System", "Peripheral Nervous System - Upper Extremity Nerves", "Peripheral Nervous System - Lower Extremity", "Spinal Nerves", "Spinal Nerves", "Spinal Nerves (diagram)", "Spinal Nerves", "Motor Unit", "Motor Unit", "Sensory Receptors", "Sensory Receptors", "Reflex", "Reflex (diagram)", "Proprioceptors"]),
    },
    "HHS4867-L03-ANALYSIS-OF-MOVEMENT": {
        "filename": "07 - 3. Analysis of Movement 運動動作分析.pdf",
        "relative": "02 Lectures/07 - 3. Analysis of Movement 運動動作分析.pdf",
        "title": "Lecture 3 - Analysis of Movement",
        "lecture_number": 3,
        "stem": "hhs4867_l03_analysis_of_movement",
        "helper": "../../tools/query_hhs4867_l03_analysis_of_movement.py",
        "parts": [("Introduction to movement analysis", 1, 2, "topic"), ("Biomechanical aspects of human movement", 3, 13, "topic"), ("Stability and mobility", 14, 17, "topic"), ("Proper body mechanics and force direction", 18, 27, "topic")],
        "titles": title_map(["Analysis of Movement", "The body as an instrument in patient care", "Biomechanical Aspects of Human Movement", "Mass", "Centre of Mass (CM) = Centre of Gravity (CG)", "Effects of adding/removing weights on shifting the CG", "Force", "Gravity", "Friction", "Levers", "Levers (diagram)", "Moments & Moment Arms", "Moment = Force (N) x Distance (m)", "Stability & Mobility", "Base of Support (BoS)", "Stability v.s. Mobility", "Dynamic Trunk Stabilization", "Application: Proper Body Mechanics", "Proper Body Mechanics", "Poor Body Mechanics", "Better Body Mechanics", "Proper Body Mechanics", "Patient position", "Caregiver position", "Positioning for stability", "Directing Forces by Blocking the knees", "Directing Forces by Blocking the knees (diagram)"]),
    },
    "HHS4867-L04-TRANSFER-WHEELCHAIRS": {
        "filename": "12 - 4. Transfer techniques and standard wheelchairs 轉移技巧及輪椅使用.pdf",
        "relative": "02 Lectures/12 - 4. Transfer techniques and standard wheelchairs 轉移技巧及輪椅使用.pdf",
        "title": "Lecture 4 - Transfer Techniques and Standard Wheelchairs",
        "lecture_number": 4,
        "stem": "hhs4867_l04_transfer_wheelchairs",
        "helper": "../../tools/query_hhs4867_l04_transfer_wheelchairs.py",
        "parts": [("Transfer overview and assistance levels", 1, 2, "topic"), ("Bed mobility and pivot transfers", 3, 14, "topic"), ("Conditions with precautions", 15, 19, "topic"), ("Standard wheelchairs and fitting", 20, 27, "topic"), ("Use of the wheelchair", 28, 35, "topic")],
        "titles": title_map(["Transfer Technique", "Level of Assistance", "Bed Mobility", "Supine lying to side lying", "Supine lying to side lying (diagram)", "Lying to sitting", "Lying to sitting (diagram)", "Pivot Transfers", "Setting up the Pivot Transfers", "Setting up the Pivot Transfers", "Pivot Transfer - Squat", "Pivot Transfer - Squat (diagram)", "Pivot Transfer - Standing", "Transfer with 2 Assistance", "Conditions with Precautions", "Conditions with Precautions (video)", "Conditions with Precautions", "Conditions with Precautions", "Conditions with Precautions", "Standard Wheelchairs", "Wheelchair", "How to choose a suitable wheelchair for a patient?", "Standard Wheelchair - Postural Support Options", "Standard Wheelchair - Drive wheels and caster", "Standard Wheelchair (diagram)", "Standard Wheelchair (diagram)", "How to fit a Wheelchair? - Seat width", "Use of Wheelchair", "Use of Wheelchair (diagram)", "Using the wheelchair", "Safety tips for using wheelchair", "Using the wheelchair - Getting into the wheelchair", "Using the wheelchair - Getting down a kerb", "Using the wheelchair - Getting up a kerb", "Using the wheelchair - Getting up slope"]),
    },
    "HHS4867-L05-MOBILITY-WALKING-AIDS": {
        "filename": "17 - 5. Mobility Walking Aids 助行工具.pdf",
        "relative": "02 Lectures/17 - 5. Mobility Walking Aids 助行工具.pdf",
        "title": "Lecture 5 - Mobility and Walking Aids",
        "lecture_number": 5,
        "stem": "hhs4867_l05_mobility_walking_aids",
        "helper": "../../tools/query_hhs4867_l05_mobility_walking_aids.py",
        "parts": [("Aims, selection, and weight-bearing status", 1, 9, "topic"), ("Types of walking aids", 10, 23, "topic"), ("Fitting walking aids", 24, 29, "topic"), ("Gait patterns", 30, 40, "topic"), ("Stairs", 41, 47, "topic")],
        "titles": title_map(["Mobility and Walking Aids", "Aims for Using Walking Aids?", "Walking aids (visual)", "Different Types of Walking Aids", "Selection of Walking Aids", "Selection of Walking Aids", "Weight Bearing Status", "Weight Bearing Status (visual)", "Walking aid selection (visual)", "Walking - Elbow crutches and Stick", "Walking Frame", "Walking Frame", "Limitations of Walking Frame/Rollator", "Axillary Crutches", "Axillary Crutches", "Limitations for Axillary crutches", "Aid - Elbow crutches", "Elbow crutches", "Limitations of Elbow crutches", "Quadripod", "Quadripod", "Limitations for Quadripod", "Stick", "Fitting of Walking aids", "Fitting walking aids (visual)", "Standing upright", "Elbow bend at 20 to 30 degrees", "Stick placing anterolaterally", "For axillary/elbow crutches", "Gait Pattern", "Gait patterns", "Gait patterns (visual)", "Three-point gait pattern (3pt gait)", "Modified 3pt gait pattern", "Gait pattern comparison", "Four-point gait pattern (4pt gait)", "Two-point gait pattern (2pt gait)", "Gait pattern sequence", "Gait pattern comparison (visual)", "Modified 4pt gait", "Stairs", "Stairs with One side aids (Stick or quad)", "Stairs (visual)", "Stairs (visual)", "Stairs with Crutches", "Stairs (visual)", "Stairs (visual)"]),
    },
    "HHS4867-L06-POSTURAL-GAIT": {
        "filename": "19 - 6. Postural and Gait 姿勢及步態評估.pdf",
        "relative": "02 Lectures/19 - 6. Postural and Gait 姿勢及步態評估.pdf",
        "title": "Lecture 6 - Postural Assessment and Gait",
        "lecture_number": 6,
        "stem": "hhs4867_l06_postural_gait",
        "helper": "../../tools/query_hhs4867_l06_postural_gait.py",
        "parts": [("Postural assessment basics", 1, 2, "topic"), ("Postural features and assessment", 3, 16, "topic"), ("Gait fundamentals", 17, 23, "topic"), ("Pathological gait", 24, 32, "topic"), ("Functional mobility tests", 33, 34, "topic")],
        "titles": title_map(["Postural Assessment", "What is Posture?", "Ideal Erect Posture", "Ideal Erect Posture (visual)", "Understanding the Posture", "Poor Posture", "Upper body in different posture", "Effect of Pelvic Tilt on lower body posture", "Elbow - Carrying angle", "Hip / Knee - Q angle", "Hip / Knee - Genu Varum and Genu Valgum", "Foot", "Foot (visual)", "Postural Assessment: Tools", "Postural Assessment: Views", "Postural Assessment: Analysis", "Gait", "Gait cycle", "Stance phase & Swing phase", "Gait cycle subdivision", "Stride length", "Walking base", "Cycle time", "Pathological gait", "Spastic hemiplegia", "Spastic hemiplegia (visual)", "Spastic diplegia", "Spastic diplegia (visual)", "Shuffling gait", "Shuffling gait (visual)", "Trendelenburg Gait", "Trendelenburg Gait (visual)", "Modified Functional Ambulation Categories (MFAC)", "Timed up and Go test"]),
    },
    "HHS4867-L07-MANUAL-MUSCLE-TESTING": {
        "filename": "21 - 7.1 Manual Muscle Testing 手動肌肉測試.pdf",
        "relative": "02 Lectures/21 - 7.1 Manual Muscle Testing 手動肌肉測試.pdf",
        "title": "Lecture 7.1 - Manual Muscle Testing",
        "lecture_number": 7,
        "stem": "hhs4867_l07_manual_muscle_testing",
        "helper": "../../tools/query_hhs4867_l07_manual_muscle_testing.py",
        "parts": [("Manual muscle testing overview", 1, 2, "topic"), ("Oxford muscle-strength grading scale", 3, 4, "topic"), ("MMT procedure and testing positions", 5, 8, "topic"), ("Regional manual muscle testing examples", 9, 18, "topic")],
        "titles": title_map(["Manual Muscle Testing", "Manual Muscle Testing (MMT)", "Muscle Strength Grading Scale (Oxford Scale)", "Muscle Strength Grading Scale (Oxford Scale) - grades", "How to perform MMT", "Testing Position", "Testing Position (visual)", "Testing Position Summary", "Shoulder Flexion & Extension", "Shoulder Abduction", "Shoulder Internal & External Rotation", "Elbow Flexion & Extension", "Hip Flexion & Extension", "Hip Abduction", "Hip Internal & External Rotation", "Knee Flexion & Extension", "Dynamometer", "Measuring Strength with Dynamometer"]),
    },
    "HHS4867-L07-JOINT-RANGE-OF-MOTION": {
        "filename": "23 - 7.2 Joint Range of Motion 關節活動幅度測量.pdf",
        "relative": "02 Lectures/23 - 7.2 Joint Range of Motion 關節活動幅度測量.pdf",
        "title": "Lecture 7.2 - Joint Range of Motion",
        "lecture_number": 7,
        "stem": "hhs4867_l07_joint_range_of_motion",
        "helper": "../../tools/query_hhs4867_l07_joint_range_of_motion.py",
        "parts": [("Joint range-of-motion concepts", 1, 2, "topic"), ("Goniometry and normal ROM", 3, 4, "topic"), ("Joint ROM examples", 5, 12, "topic")],
        "titles": title_map(["Joint Range of Motion", "Joint Range of Motion", "Goniometer", "AROM Summary", "Shoulder Flexion & Extension", "Shoulder Abduction", "Shoulder Internal & External Rotation", "Elbow Flexion & Extension", "Hip Flexion & Extension", "Hip Abduction", "Hip Internal & External Rotation", "Knee Flexion & Extension"]),
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True, choices=sorted(DECKS))
    parser.add_argument("--course-root", type=Path, default=COURSE_ROOT_DEFAULT)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--paddle-cache", type=Path, default=Path("/private/tmp/paddlex-hhs4867-course"))
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    config = DECKS[args.source_id]
    filename = str(config["filename"])
    source_id = args.source_id
    builder.COURSE_CODE = "HHS4867"
    builder.COURSE_TITLE = COURSE_TITLE
    builder.SOURCE_ID = source_id
    builder.DOCUMENT_ID = source_id
    builder.SOURCE_FILENAME = filename
    builder.SOURCE_RELATIVE = str(config["relative"])
    builder.SOURCE_PACKAGE_PDF = PROJECT_ROOT / "sources/HHS4867" / source_id / "00 Source" / filename
    builder.OUTPUT_STEM = str(config["stem"])
    builder.QUERY_HELPER_PATH = str(config["helper"])
    builder.SCHEMA = "vtc-hhs4867-lecture.v1"
    builder.DOCUMENT = {"document_id": source_id, "file_name": filename, "source_type": "lecture", "lecture_number": int(config["lecture_number"]), "title": str(config["title"])}
    builder.TOPIC_PARTS = part_map(source_id, config["parts"])  # type: ignore[arg-type]
    builder.SLIDE_TITLES = config["titles"]  # type: ignore[assignment]
    builder.VISUAL_NAMES = {}
    output_root = PROJECT_ROOT / "sources/HHS4867" / source_id
    forwarded = [
        "build_hhs4867_lecture_pdf.py",
        "--course-root", str(args.course_root.expanduser().resolve()),
        "--output-root", str(output_root),
        "--dpi", str(args.dpi),
        "--paddle-cache", str(args.paddle_cache.expanduser().resolve()),
    ]
    if args.skip_paddle:
        forwarded.append("--skip-paddle")
    if args.overwrite:
        forwarded.append("--overwrite")
    sys.argv = forwarded
    builder.main()


if __name__ == "__main__":
    main()

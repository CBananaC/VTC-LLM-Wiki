# VTC LLM Wiki

This project is a unified, source-preserving LLM Wiki for Hong Kong VTC
rehabilitation study. It is intended for the student owner and for ChatGPT,
OpenCode, local models, and other AI systems that need source-grounded answers.

## Project layout

```text
VTC LLM Wiki/
├── source_registry.json
├── tools/
│   ├── register_source.py
│   └── query_vtc_wiki.py
├── workflows/
│   └── ADD_SOURCE.md
├── HHS4185 Course Materials - LLM Wiki/
├── Davidson 25th Edition - LLM Wiki/
├── sources/HHS4185/HHS4185-REF-ORTHO-SPECIAL-TESTS/
└── sources/HHS3190M/HHS3190M-L01-PHYSIOLOGY-2026-07/
```

The two existing wiki packages were moved here with their original files
intact. Their source PDFs remain in the VTC study folder; the package data
retains the original source provenance. Generated records are not silently
rewritten just because the package location changed.

New source packages use `sources/<course-code>/<source-id>/` and keep these
layers separate:

```text
00 Source/
01 OCR and Layout/
02 Text and Tables/
03 Analysis/
04 Retrieval Index/
```

## Retrieval

Use the project-level router when a registered package provides a query helper:

```bash
python3 tools/query_vtc_wiki.py \
  --course-code HHS4185 \
  --query "rehabilitation principles for osteoporosis"
```

The current HHS4185 route searches course materials first and then exposes
Davidson's *Principles and Practice of Medicine*, 25th edition, and *Stroke
Rehabilitation: A Function-Based Approach*, fifth edition, plus *Special Tests
for Orthopedic Examination* as separately labelled supplemental packets. The
returned packet is evidence for an AI workflow, not a substitute for reading
the returned source passages and checking the original page image. The portable instructions for ChatGPT,
OpenCode, local models, and other AI systems are in [`AI_USAGE_INSTRUCTIONS.md`](Davidson%2025th%20Edition%20-%20LLM%20Wiki/(6)%20Retrieval%20Index/AI_USAGE_INSTRUCTIONS.md).
The Davidson-side federation manifest is
`Davidson 25th Edition - LLM Wiki/(6) Retrieval Index/hhs4185_federated_sources_manifest.json`.

For the HHS3190M physiology lecture, query the project router or the
source-specific helper:

```bash
python3 tools/query_vtc_wiki.py \
  --course-code HHS3190M \
  --query "monosaccharides"
```

The HHS3190M package remains separate from HHS4185 and contains the raw PDF,
English slide blocks with preserved point form, visual locations, the
reconstructed DNA/RNA table, hierarchical summaries, and portable indexes.

## Add a source

Follow [`workflows/ADD_SOURCE.md`](workflows/ADD_SOURCE.md). The short form is:

```bash
python3 tools/register_source.py \
  --source-id HHS4185-L3 \
  --title "Lecture 3 - Source title" \
  --course-code HHS4185 \
  --source-role course_materials \
  --source-kind lecture \
  --source-path "/absolute/path/to/source.pdf"
```

The command creates a source package, records a SHA-256 hash, copies the raw
input into `00 Source/` by default, and updates `source_registry.json`. It does
not run OCR or claim verification; source-specific processing and manual review
come afterward.

## Verification and publication

OCR, layout detection, reconstructed tables, summaries, quotations, visual
interpretations, and retrieval matches are `generated_not_verified` until the
original source is checked. Raw sources are immutable inputs.

GitHub is intended to be public, but no repository has been created or pushed.
Before publication, review copyright, personal data, and redistribution rights;
public visibility is not permission to publish course PDFs, book text, OCR, or
derived extracts. Google Drive is intended to remain restricted, with no folder
creation, upload, or permission change performed by local bootstrap.

# HHS4185 Course Materials — LLM Wiki

This is the course-first retrieval package for `HHS4185 - Common
Rehabilitation Conditions`. It is designed to be readable by ChatGPT,
OpenCode, local models, or another AI that can read JSON/JSONL.

## Source set

The canonical slide PDFs are:

- `HHS4185_L1.pdf` — Lecture 1: joint problems.
- `HHS4185_L2.pdf` — Lecture 2: bone problems.
- `HHS4185J_L2.pdf` — bilingual Lecture 2: bone problems.
- `HHS4185_WS1_Equipment.pdf` — Workshop 1: rehabilitation equipment.
- `HHS4185_T1_ICF.pdf` — Tutorial 1: ICF.

Exact duplicate Downloads copies were moved to `Archive - Duplicate
Downloads`. The active source PDFs were not edited. The SOW and assessment
PDFs remain outside this slide-material extraction set.

## Processing layers

- `(1) Source Inventory` — source manifest, file hashes, and page counts.
- `(2) OCR and Layout` — raw embedded PDF text in reading order, English-only
  derived reading-order lines, preserved bullet/arrow markers and indentation,
  word coordinates, and page-level embedded visual-object locations.
- `(3) Text and Tables` — targeted English table OCR/reconstruction and visual
  policy.
- `(4) Analysis` — page keyword candidates and bottom-up summaries in the
  order `Slide → Part → Document → Course`.
- `(5) Retrieval Index` — structure, concepts, occurrences, terms, passages,
  visual metadata, table links, formal answer schema, and validation report.

All generated layers are marked `generated_not_verified`. Embedded text was
extracted from all 313 slides. The derived study/search layer uses only the
English version of each deck, including the English side of bilingual slides;
the raw embedded layer remains unchanged for provenance. English bullet,
dot, arrow, line-break, and indentation records are retained rather than
flattened into prose. PaddleOCR was applied selectively to five visually
verified English table candidates whose contents were absent from embedded
text: the DXA report table, calcium-intake table, English blood-pressure table,
and walking-aids comparison table (including the bilingual slide's English
cells). The Chinese-only blood-pressure table was excluded. Non-table visuals
are retained as metadata-only records with slide and coordinate locations.

## Query from the terminal

From this `tools` directory:

```bash
python3 query_hhs4185_retrieval.py --query "rehabilitation principles for osteoporosis"
```

The command searches HHS4185 course materials first, then Davidson's
*Principles and Practice of Medicine*, 25th edition, as a supplement. The
project-level router additionally exposes *Stroke Rehabilitation: A
Function-Based Approach*, fifth edition, as a separate supplemental packet;
the book packages are not merged into this course-material package. The
returned packets retain source-specific IDs and citation formats so any AI can
apply the same priority rule.

For a term that automatic matching may miss:

```bash
python3 query_hhs4185_retrieval.py \
  --query "blood pressure categories" \
  --term "blood pressure" \
  --term "systolic"
```

## Required AI response format

The AI should return:

1. `Answer` — answer from `course_materials` first.
2. `Source quotations` — use `course_materials.quotation_candidates` for
   course evidence; use Davidson quotations only when supplementing.
3. `References` — course citations use PDF filename and slide number;
   Davidson citations use chapter and printed textbook page, with PDF page
   retained only for file navigation.

Use summaries for orientation only. Read the returned source passage before
answering. Treat quotation, table, keyword, summary, and visual records as
generated candidates until the original PDF page image is manually checked.
There is intentionally no `claims_index.json`.

The standalone answer contract is `(5) Retrieval Index/hhs4185_formal_output_schema.json`.

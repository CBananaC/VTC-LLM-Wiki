# Stroke Rehabilitation: A Function-Based Approach, Fifth Edition

This source package was created by `tools/register_source.py` and processed with the source-type-specific structural/layout inventory tools.

- Source ID: `HHS4185-REF-STROKE-REHAB-5E`
- Course: `HHS4185`
- Role: `additional_source`
- Kind: `book`
- Added: `2026-08-30T16:53:48+08:00`
- Verification: `generated_not_verified`

Processing layers are `00 Source`, `01 OCR and Layout`, `02 Text and Tables`, `03 Analysis`, and `04 Retrieval Index`. Keep the raw source immutable. Label OCR, summaries, tables, quotations, visual interpretations, and retrieval results `generated_not_verified` until manual source review.

The source manifest is `source_manifest.json`. After processing, add a source-specific query helper to the registry when one exists; otherwise this package remains discoverable through its manifest.

## Current inventory

- The canonical PDF is 784 PDF pages. `pdfinfo` reports *Stroke Rehabilitation: A Function-Based Approach, Fifth Edition* (2021), Glen Gillen, Elsevier.
- The book contains 3 parts, 30 numbered chapters, 235 chapter-level outline sections, one electronic-only-in-Contents chapter (`e31`, printed `709.e1`–`709.e25`), and front/back matter.
- The structural map uses PDF page numbers as the stable identifiers and records printed-page labels where visible or conservatively inferred. It records a PDF-tail anomaly: PDF page 784 is an unnumbered continuation of the medications table after the Index pages, although the outline extends the Index entry to the end of the file.
- Embedded-text cue inventory: 250 table cues, 721 figure cues, 76 box cues, 49 case-study cues, and 1 algorithm cue across 516 pages. These are caption-like cues, not a complete visual inventory.
- PaddleOCR `PP-DocLayout_plus-L` layout inventory at 120 dpi: all 784 pages processed with no errors; 398 pages contain 999 model-detected visual candidates. It records bounding-box locations and labels only; it does not OCR visual contents.

## Generated outputs

- `01 OCR and Layout/stroke_rehab_page_structure_generated.jsonl` — page-level PDF/printed-page and chapter association.
- `01 OCR and Layout/stroke_rehab_outline_generated.json` — raw PDF-outline entries.
- `01 OCR and Layout/stroke_rehab_layout_inventory_generated.json` — page-level PaddleOCR layout boxes and visual candidates.
- `02 Text and Tables/stroke_rehab_visual_cues_generated.json` — embedded-text table/figure/box/case-study/algorithm cues.
- `03 Analysis/stroke_rehab_book_structure_generated.json` — parts, chapters, sections, ranges, page map, and TOC snapshot.
- `03 Analysis/stroke_rehab_visual_structure_generated.json` — visual candidates grouped by book context and chapter.

All outputs are `generated_not_verified`. No text extraction from visual regions, table reconstruction, summary, keyword extraction, or retrieval index has been created yet.

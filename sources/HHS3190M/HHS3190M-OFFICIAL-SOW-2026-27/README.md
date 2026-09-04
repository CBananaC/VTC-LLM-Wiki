# Semester 1 (26-27) Scheme of Module Activity

This is the standalone official-document package for the HHS3190M course.
The source PDF is preserved unchanged; all processing outputs are derived
candidates and remain `generated_not_verified` until manual source-page review.

- Source ID: `HHS3190M-OFFICIAL-SOW-2026-27`
- Course: `HHS3190M`
- Role: `official_document`
- Kind: `scheme_of_module_activity`
- Added: `2026-09-04T08:30:27+08:00`
- Verification: `generated_not_verified`

## Processing result

- 5 PDF pages, A4 portrait pages 1-3 and landscape pages 4-5.
- Raw bilingual embedded text and page coordinates are preserved.
- The clean derived layer is English-only and keeps the source's bullet/dot
  markers and list indentation.
- Three tables are reconstructed separately: the Module Assessment Plan, the
  16-week HHS3190M Lesson Plan, and HHS3190M Teacher's Information.
- Table content is excluded from ordinary page prose and linked through table
  and visual IDs. No non-table visual interiors were separately OCRed.
- PaddleOCR/layout models were unavailable in this run; embedded PDF text and
  MuPDF visual tracing are recorded as the explicit fallback.

Processing layers are `00 Source`, `01 OCR and Layout`, `02 Text and Tables`, `03 Analysis`, and `04 Retrieval Index`. Keep the raw source immutable. Label OCR, summaries, tables, quotations, visual interpretations, and retrieval results `generated_not_verified` until manual source review.

The source manifest is `source_manifest.json`. Query this package with:

```bash
python3 tools/query_hhs3190m_official_sow.py --query "70% attendance"
```

The source-specific helper is registered in `source_registry.json`. Read the
returned page passage first, inspect the table record when relevant, and cite
the PDF page reference. Exact quotations and table values still require manual
checking against the original PDF.

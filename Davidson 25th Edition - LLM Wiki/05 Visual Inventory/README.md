# Davidson 25th Edition visual workflow

This layer applies the medical-book visual policy agreed for the VTC LLM Wiki workflow.

## Policy

- The source PDF and raw embedded-text extraction remain immutable.
- Tables receive a full generated reconstruction from embedded PDF word coordinates, including text, inferred baseline rows, cell fragments, coordinates, and source line IDs.
- Figures, graphs, charts, illustrations, formulas, algorithms, and other non-table visuals receive metadata only: type, name or caption, PDF page, printed page, and location.
- The clean reading-order layer removes visual-region text and exposes visual placeholders in `reading_order_items` and `clean_text_with_visual_placeholders`.
- All full-book visual and table results remain `generated_not_verified` until visual/manual review.

## Outputs

- `davidson25_visual_manifest_generated.json`: all layout candidates, visual metadata, caption candidates, and policy classification.
- `davidson25_tables_reconstructed_generated.json`: full generated table-content and coordinate-preserving reconstruction records.
- `../04 Verified Clean Text/davidson25_clean_reading_order_full_generated.json`: page text plus visual placeholders.
- `../04 Verified Clean Text/davidson25_sections_paragraphs_full_generated.json`: structured paragraphs plus the visual-placeholder index.

## Current run

- 1,412 pages scanned.
- 3,482 layout candidates retained for provenance.
- 716 table records, including 714 chapter-content tables.
- 1,691 non-table visual records.
- 2,354 chapter-content visual placeholders.
- One layout false positive, Figure 32.6 on PDF page 1396, was reclassified as metadata-only after visual inspection.
- Table content was available in the embedded PDF layer; no table candidate required additional visual OCR in this run.

The table layer is generated for review. Merged cells, column spans, and semantic row grouping should be checked against the source page before the table is treated as verified study evidence.

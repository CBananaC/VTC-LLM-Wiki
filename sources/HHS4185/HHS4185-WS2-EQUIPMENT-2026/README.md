# Workshop 2 - Introduction to Rehabilitation Equipment (2)

This source package was created by `tools/register_source.py` and processed by
`tools/build_hhs4185_source_package.py`.

- Source ID: `HHS4185-WS2-EQUIPMENT-2026`
- Course: `HHS4185 - Common Rehabilitation Conditions`
- Source type: `workshop`
- Raw source: `00 Source/AY2627_HHS4185  4185J_ W2_復康器材(二).pdf`
- Verification: `generated_not_verified`

## Processing layers

- `00 Source/`: immutable copied PDF.
- `01 OCR and Layout/`: raw embedded text, page records, OCR regions, and layout candidates.
- `02 Text and Tables/`: visual inventory and full table reconstructions where detected.
- `03 Analysis/`: reconstructed document structure, page keywords, and bottom-up summaries.
- `04 Retrieval Index/`: concepts, occurrences, term lookup, passages, visual references, and validation.

## Reconstructed topic structure

- Workshop overview and content — slides 1–2.
- Ceiling Hoist / Portable Hoist and transfer procedures — slides 3–14.
- Tilt Table / Easy Stand — slides 15–20.
- Hospital Bed / Ripple Bed — slides 21–22.
- Rehab equipment for activities of daily living (ADL) — slides 23–26.
- Reference — slide 27.

Page references preserve both slide number and PDF page number. Point-form markers,
indentation, and the order of the embedded text layer are retained. Visual text
from OCR is kept in raw OCR fields and is not silently merged into the derived
reading-order passage.

The deck contains 13 detected non-table image/video visuals. They are recorded
with page, slide, bounding-box location, and generated uncaptioned names; their
internal visual text is not promoted into the clean passage layer. No table
candidate was detected, so there is no table reconstruction record for this
deck.

## Query

Run the source-local helper:

```bash
python3 "sources/HHS4185/HHS4185-WS2-EQUIPMENT-2026/query_source.py" \
  --query "ripple bed pressure sore" --limit 10
```

Or use the project router so HHS4185 course materials remain ahead of
supplemental sources:

```bash
python3 tools/query_vtc_wiki.py \
  --course-code HHS4185 \
  --query "ripple bed pressure sore" --limit 10
```

Read the returned passage and formal reference before answering. All OCR,
clean text, keywords, summaries, visual records, and retrieval results remain
`generated_not_verified` until manual source-page review.

Validation counts: `{"concepts": 89, "documents": 1, "occurrences": 156, "pages": 27, "parts": 6, "passages": 27, "tables": 0, "terms": 91, "visuals": 13}`


# AGENTS.md - Portable PDF-to-LLM-Wiki Conversion Standard

This document is a self-contained, tool-neutral instruction set for any AI
agent, including non-Codex agents and Codex agents working in another
workspace. Copy it to the root of a new workspace as AGENTS.md when the
workspace needs to convert PDFs into source-grounded JSON/JSONL for an LLM
Wiki.

It is a processing standard, not permission to redistribute copyrighted books,
course files, private documents, or extracted text. Follow the user's source,
privacy, copyright, language, and output instructions first. Do not upload,
publish, or send any source or derived file unless the user explicitly permits
that action.

## 1. Required outcome

Convert each source PDF into a navigable, source-preserving package that lets an
AI:

- find the relevant source passage;
- understand the document hierarchy and page range;
- distinguish raw extraction from cleaned or generated material;
- locate every relevant visual element;
- read a fully reconstructed table when a table is returned;
- identify non-table visuals without pretending that they were reconstructed;
- preserve headings, numbering, bullets, dots, arrows, indentation, and list
  structure;
- quote and reference the source with stable page or slide locators; and
- verify generated records against the original source page before treating
  them as authoritative.

The package is an evidence-retrieval layer, not a replacement for the PDF and
not a medical, legal, or financial authority. For medical study materials,
answers must be educational and source-grounded, not individualized clinical
advice.

## 2. Non-negotiable principles

### 2.1 Preserve the source

- Keep the original PDF unchanged and immutable.
- Record the original absolute path or source URL, access date when relevant,
  filename, byte size, page count, and SHA-256 hash.
- Do not replace a source merely because a new file has a similar name.
- Detect exact duplicates by hash before creating a new source ID or package.
- If a new file is byte-identical to an existing source, upgrade the existing
  source record instead of creating a duplicate.
- Keep raw extraction, OCR, layout detection, cleaned text, analysis, and
  indexes in separate files and folders.

### 2.2 Preserve provenance

Every derived record must be traceable to one or more of:

- source file;
- PDF page number;
- printed page number, when present;
- slide number, when the PDF is a slide deck;
- source page ID;
- source passage ID;
- source visual ID or table ID; and
- bounding box or line/cell coordinates when available.

Never use an untraceable paraphrase as evidence. Never invent a chapter,
caption, page number, table value, or visual name. If a label is not printed in
the source, use a clearly marked generated designation such as Unnamed visual
on PDF p. 12 and keep the status unverified.

### 2.3 Separate status from truth

All OCR, layout detections, cleaned text, paragraph reconstruction, keyword
extraction, summaries, visual interpretations, table reconstructions,
quotations, and retrieval results are generated candidates until a person
checks them against the source page.

Use these fields consistently:

~~~json
{
  "status": "generated_not_verified",
  "verification_status": "generated_not_verified"
}
~~~

Use verified only after an actual source-page review. Use error or blocked when
processing failed. Do not convert a successful program run into verified
automatically.

### 2.4 Preserve language boundaries

- Retain the raw text of all languages present in the PDF for provenance.
- Build the clean retrieval layer in the user's requested language.
- For a bilingual deck where the user requests English, keep only the English
  derived layer for normal retrieval while retaining the raw bilingual layer.
- Do not merge Chinese and English copies into one sentence.
- Do not silently translate source text and present the translation as a quote.
- If a table itself is bilingual, retain the requested-language cells in the
  requested-language reconstruction and, when useful, retain raw bilingual OCR
  separately.

### 2.5 Preserve structure

Do not flatten a structured document into one long text field. Keep:

- title, subtitle, chapter, section, and subsection levels;
- chapter or slide numbering;
- paragraph boundaries;
- bullet, numbered, dot, arrow, and checkbox markers;
- list indentation and nested levels;
- continued paragraphs across page breaks;
- table rows, columns, merged cells, units, footnotes, and notes; and
- visual location and page references.

### 2.6 Visual policy

Use a two-stage visual policy:

1. Locate and classify visual elements first.
2. Reconstruct content only according to the user's policy.

Default policy:

- Tables: reconstruct the complete layout and contents after targeted review.
- Charts and graphs: record page, location, title/caption, axes or legend only
  when clearly available; do not invent data or redraw them by default.
- Illustrations, photographs, diagrams, maps, icons, and decorative images:
  record type, name/caption if present, page, and location only.
- Formulas or equations: preserve extracted formula text if reliable; otherwise
  record the location and mark targeted formula OCR as needed.
- A visual may receive targeted OCR only when the user explicitly requests it
  or when it is necessary to answer a defined question. Keep targeted OCR
  separate from normal page text.

## 3. End-to-end workflow

Perform the following stages in order. Do not build the final retrieval index
before structure, text, visuals, tables, keywords, and summaries are ready.

### Stage 0 - Read instructions and define scope

Before touching the PDF:

1. Read the workspace AGENTS.md, project README, source registry, and any
   source-specific workflow.
2. Identify the user's requested language, course/source priority, visual
   policy, output folder, and verification standard.
3. Decide whether the PDF is a book, article, lecture deck, workshop, official
   document, assessment, form, scan, or mixed source.
4. Decide whether the task covers one PDF or a source set.
5. Write a short processing plan and record it in the project log when a log
   exists.

For a course wiki, use this default retrieval priority:

~~~text
course materials -> course-specific official documents -> supplemental books
-> other references
~~~

Keep separate source packages. A federation manifest may connect them, but do
not merge unrelated raw text, page IDs, tables, or indexes into one source.

### Stage 1 - Register the source and detect duplicates

For every PDF:

1. Preserve the original location and filename.
2. Compute SHA-256 and byte size.
3. Run duplicate detection against existing source manifests.
4. Assign a stable source ID only after duplicate checking.
5. Create a source manifest with generated_not_verified status.
6. Decide whether the original PDF is copied into the package or kept at its
   canonical external location. Record that decision explicitly.

Suggested source IDs are stable and descriptive, for example:

~~~text
HHS4185-L02
HHS4185-REF-STROKE-REHAB-5E
ARTICLE-2026-001
~~~

Do not use a timestamp or random ID when a stable source ID already exists.

### Stage 2 - Inspect the PDF before extracting content

Run read-only inspection first:

~~~bash
pdfinfo "$INPUT_PDF"
pdftotext -f 1 -l 3 -layout "$INPUT_PDF" -
~~~

Record:

- page count;
- page dimensions and orientation;
- PDF title, author, subject, creator, and dates when available;
- whether an embedded text layer exists;
- whether pages are scans or image-only;
- whether the file is a slide export;
- whether an outline/bookmark tree exists;
- whether a table of contents exists;
- printed page numbering conventions;
- recurring headers, footers, watermarks, logos, and page numbers; and
- likely visual-heavy pages.

Render representative pages before committing to an extraction strategy. At
minimum inspect:

- cover/title page;
- table of contents or outline pages;
- one ordinary text page;
- one list-heavy page;
- one table page;
- one chart/graph or illustration page;
- one page with a continuation across a page break; and
- the final page or index page.

Use Poppler when available:

~~~bash
pdftoppm -f 1 -l 3 -png -r 120 "$INPUT_PDF" "$REVIEW_DIR/page"
~~~

Visual inspection is required because text extraction alone cannot prove
reading order, table geometry, image boundaries, or language pairing.

### Stage 3 - Map the document structure

Build the hierarchy before full content analysis.

#### For books and long documents

Use the following default hierarchy when the source supports it:

~~~text
Part -> Chapter -> Major section -> Subsection -> Paragraph or list item
~~~

Use a lower level only when it is present or defensibly reconstructed. Do not
invent a major section merely because a paragraph looks important.

#### For lecture or workshop slide PDFs

Use:

~~~text
Course -> Document/deck -> Part/topic -> Slide
~~~

If the deck has explicit chapters or sections, insert them between document and
slide. If it has no explicit part headings, create a generated topic part only
when the page boundary is supported by title/layout evidence and mark it
synthetic.

#### Structure mapping rules

- Prefer the source's printed TOC and PDF outline over guesses.
- Record both PDF page range and printed page range when both exist.
- Keep a page-to-node map so every page belongs to a document and, where
  possible, a chapter/part.
- Keep heading candidates separate from verified headings.
- Preserve title text exactly in a raw field and use a normalized form only for
  search.
- Never use a page number from a scan as a printed page number without checking
  the page label convention.

### Stage 4 - Extract raw text with coordinates

Prefer embedded PDF text when it exists, but never assume it is already in
reading order.

Useful tools include:

~~~bash
pdftotext -bbox-layout -enc UTF-8 "$INPUT_PDF" "$WORK_DIR/embedded_bbox.html"
pdfinfo "$INPUT_PDF"
~~~

Use pdfplumber, pypdf, or equivalent libraries for programmatic checks.
Retain:

- raw page text exactly as extracted;
- line and word coordinates;
- source line indices;
- font/size/style when available;
- page dimensions; and
- extraction warnings or missing-page errors.

Do not clean away headers, footers, repeated page numbers, or visual text at
this stage. Mark them and decide their treatment later.

### Stage 5 - Render pages and run OCR/layout detection

Render pages at a resolution appropriate to the source. Use a lower DPI for a
first scan and a higher DPI for small text or targeted tables.

Choose OCR by language and source type. PaddleOCR is one possible local
implementation; it is not mandatory. For example:

~~~python
from paddleocr import PaddleOCR

ocr = PaddleOCR(
    lang="en",
    device="cpu",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
~~~

Use the language model that matches the source. Test it on representative pages
before full processing. If the source is bilingual, do not use OCR output as a
replacement for language-aware filtering.

Run layout detection when the source contains columns, tables, figures,
charts, sidebars, or mixed visual/text areas. Store for each layout box:

- label and class ID;
- confidence;
- pixel coordinates;
- normalized or point coordinates;
- coordinate origin and scale; and
- whether it is a visual candidate.

Keep these layers separate:

~~~text
raw embedded text
raw OCR text
language-filtered OCR text
layout boxes
clean reading-order text
~~~

Do not put OCR text from a table, chart, or illustration into the normal page
body unless the visual policy explicitly requires that. Tables belong in the
table layer; non-table visual OCR belongs in a targeted visual layer.

If a model is unavailable:

- continue with embedded extraction and a clearly labeled fallback when it is
  safe to do so;
- record exactly which pages lack OCR/layout;
- do not claim full OCR or full layout coverage; and
- do not mark the source verified.

### Stage 6 - Reconstruct reading order and text structure

Build a clean page layer from raw lines and layout coordinates.

#### Reading order

Use the source layout, not only y-coordinate sorting. Check for:

- one or more columns;
- title/subtitle hierarchy;
- sidebars and callouts;
- footnotes and references;
- headers and footers;
- reading order around tables and figures; and
- text that continues onto the next page.

Keep both the raw line order and the reconstructed order. For each clean line,
retain its source line IDs and bounding box.

#### Headings

Recognize a heading using multiple signals such as source numbering, font size,
font weight, spacing, capitalization, position, and consistency with nearby
headings. A heading candidate must not be promoted solely because it is short.

#### Paragraphs

Merge lines into logical paragraphs when they are part of the same block and
the sentence clearly continues. Preserve paragraph boundaries at:

- a new heading;
- a new list item;
- a new table/figure/callout;
- a footnote or reference block; and
- a clear layout boundary.

For paragraphs spanning pages, create one logical block with a list of source
page IDs and source line IDs. Keep page-local fragments available for audit.

#### Point form and lists

Never flatten a list into prose. Preserve:

- the exact leading marker where readable;
- marker type, such as bullet, dot, arrow, number, letter, or checkbox;
- list nesting/indent level;
- continuation lines;
- item order; and
- source page and line references.

If a bullet glyph is separated from its text by extraction, attach it using
coordinate proximity and layout evidence, and record that it was reconstructed.
If it cannot be assigned confidently, retain it as an unmatched marker rather
than dropping it.

### Stage 7 - Build the complete visual inventory

Scan every page for visual elements, using layout detection, embedded image
objects, vector geometry, captions, and source review.

Record a visual even when it has no caption. A visual record should include:

- stable visual_id;
- source_page_id;
- source file, PDF page, printed page or slide number;
- visual type;
- printed name/caption when present;
- generated name only when no printed name exists;
- bounding box;
- coordinate origin and units;
- detection source and confidence;
- associated heading/section IDs;
- OCR/reconstruction policy; and
- verification status.

Use a visual type vocabulary such as:

~~~text
table, chart, graph, figure, illustration, photograph, diagram, flowchart,
formula, equation, map, callout, icon, seal, infographic, image, unknown
~~~

Do not count a recurring logo, page number, or decorative footer as a study
visual unless the user wants those elements. Record that filtering decision.

### Stage 8 - Reconstruct tables

Table reconstruction is a separate operation from page OCR.

1. Identify every table candidate from the visual inventory.
2. Review the candidate page image and determine whether it is a real table or
   a false layout detection.
3. Prefer the embedded text layer when it contains reliable cell text and
   coordinates.
4. Use targeted OCR on the table crop or page when table text is rasterized or
   absent from embedded text.
5. Reconstruct rows and columns from visible geometry and cell coordinates.
6. Preserve merged cells, spanning headers, units, footnotes, notes, symbols,
   missing-value marks, and ordering.
7. Separate source-language cells from translated or generated cells.
8. Compare the result against the rendered table image.
9. Keep the table contents out of normal page text when the policy is to exclude
   visual content from page prose.

A table record should preserve both a machine-readable grid and a readable
plain-text form. Example:

~~~json
{
  "table_id": "SOURCE-P0025-TBL-01",
  "visual_id": "SOURCE-P0025-VIS-01",
  "source_page_id": "SOURCE-P0025",
  "pdf_page": 25,
  "printed_page": null,
  "slide_number": 25,
  "name": "DXA scan report interpretation table",
  "bbox_points": [175, 78, 545, 255],
  "content": {
    "text": "Region | BMD | BMC | ...",
    "rows": [
      {
        "row_index": 0,
        "cells": [
          {"text": "Region", "column_index": 0, "row_span": 1, "col_span": 1},
          {"text": "BMD", "column_index": 1, "row_span": 1, "col_span": 1}
        ]
      }
    ]
  },
  "language": "en",
  "reconstruction_method": "targeted_ocr_with_coordinate_row_reconstruction",
  "status": "generated_not_verified",
  "verification_status": "generated_not_verified"
}
~~~

If a table is detected but its content cannot be reconstructed reliably, keep
the visual location and record table_reconstruction_available: false. Do not
silently output an empty table as if it were complete.

### Stage 9 - Build leaf extraction and keywords

Extract keywords only after clean reading order and visual separation exist.
Use page, paragraph, subsection, slide, and table units as appropriate.

Use at least two levels of keyword classification:

- broad_area: a high-level topic such as anatomy, clinical condition,
  investigation, treatment, rehabilitation, risk factor, measurement, or
  document concept;
- small_area: the source-grounded term or phrase such as osteoporosis, DXA,
  T-score, amputation, balance training, or blood pressure.

Each keyword candidate should include:

- stable keyword record ID;
- category, broad area, and small area;
- exact source form;
- normalized search form;
- aliases/spelling variants only when defensible;
- source page IDs and passage IDs;
- section IDs;
- source excerpt;
- content type, such as paragraph, list, table, heading, or visual label; and
- generated/verification status.

Do not use an LLM to invent medical keywords that are not present or strongly
supported by the source. Generated synonyms must be labeled as aliases and
must not replace the exact source form.

For reconstructed tables, create separate table keyword records linked to the
table ID. This makes table-only terms searchable without flattening table text
into the page passage.

### Stage 10 - Summarize bottom-up

Complete extraction before writing summaries. Summarize from the smallest
meaningful unit upward:

For books:

~~~text
Subsection -> Major section -> Chapter -> Part -> Book/source
~~~

For slide decks:

~~~text
Slide -> Part/topic -> Document/deck -> Course/source set
~~~

Rules:

- Leaf summaries may use leaf text and source tables/visual metadata.
- Parent summaries should merge and resummarize child units, not repeat a
  paragraph-by-paragraph extraction.
- Keep child summary IDs and source page IDs on every parent summary.
- Preserve uncertainty and conflicting evidence.
- Do not treat a summary as a quotation.
- Do not put table values or visual interpretations in a summary unless the
  corresponding table/visual record is linked.
- Keep summary method and status fields.

Example summary record:

~~~json
{
  "unit_id": "SOURCE-CH01-M01-S01",
  "level": "subsection",
  "title": "Osteoporosis",
  "parent_id": "SOURCE-CH01-M01",
  "source_page_ids": ["SOURCE-P0032"],
  "summary": "Source-grounded summary text.",
  "summary_method": "extractive_child_passage_summary",
  "child_summary_ids": [],
  "keyword_record_ids": ["SOURCE-KW-0001"],
  "status": "generated_not_verified",
  "verification_status": "generated_not_verified"
}
~~~

### Stage 11 - Create formal quotations and references

Retrieval output must support a formal answer rather than returning only
unreferenced text.

For every quotation candidate, preserve:

- evidence ID;
- exact source-extracted wording;
- source passage ID;
- source page ID;
- section path;
- page type and number;
- PDF page for navigation;
- quotation status; and
- manual verification requirement.

Use source-specific citation formats:

- Book: Author, Title (Year), Chapter X, p. Y (PDF p. Z).
- Article: Author, Article title (Year), p. Y (PDF p. Z).
- Slide: SourceFile.pdf, slide N (PDF p. N).
- Course material with printed page labels: retain both printed page and PDF
  page, clearly naming each.

The formal answer contract should contain:

~~~text
Answer
Source quotations
References
~~~

Every material factual statement should be supported by a returned source
passage or a clearly identified table/visual record. Exact quotations require
manual source-page checking even when OCR confidence is high.

### Stage 12 - Build portable retrieval indexes

Build indexes only from the completed source package. Use ordinary JSON and
JSONL so another AI can consume them without a database or proprietary tool.

Recommended files:

~~~text
00 Source/
  original source PDF or source manifest pointing to the immutable source

01 OCR and Layout/
  pages_ocr_layout.jsonl
  layout_inventory.json
  extraction_validation.json

02 Text and Tables/
  clean_reading_order.json or .jsonl
  visual_manifest.json
  tables.json

03 Analysis/
  structure.json
  keywords.json
  summaries.json
  formal_quotations.json

04 Retrieval Index/
  passage_index.jsonl
  concept_index.json
  occurrence_index.json
  term_lookup.json
  structure_lookup.json
  visual_index.json
  formal_output_schema.json
  retrieval_index_validation_report.json
  AI_USAGE_INSTRUCTIONS.md
~~~

A source registry or federation manifest may live above these packages. It
must identify source role, course/source priority, package path, manifest path,
retrieval path, query helper if one exists, and verification status.

#### Passage index

Use one JSON object per line. A passage record should include:

~~~json
{
  "source_passage_id": "SOURCE-P000032-PASSAGE-01",
  "source_id": "SOURCE",
  "source_file": "source.pdf",
  "document_id": "SOURCE-DOC",
  "source_page_ids": ["SOURCE-P000032"],
  "pdf_page": 32,
  "printed_page": 20,
  "slide_number": null,
  "section_ids": ["SOURCE-CH01-M01-S01"],
  "section_path": ["Part 1", "Chapter 1", "Osteoporosis"],
  "text": "Clean, non-visual page or paragraph text.",
  "content_type": "paragraph",
  "status": "generated_not_verified",
  "verification_status": "generated_not_verified"
}
~~~

Do not use a passage record to conceal visual content that was intentionally
excluded. Link a table or visual through its own ID.

#### Concept, occurrence, and term indexes

Use this relationship:

~~~text
term_lookup -> concept_index -> occurrence_index -> passage_index / visual_index / table record
~~~

Required integrity properties:

- concept IDs are unique;
- occurrence IDs are unique;
- every occurrence concept ID resolves;
- every term concept ID resolves;
- every source passage ID resolves or is explicitly marked unavailable;
- every visual/table page reference resolves; and
- every returned source locator points back to the source manifest.

#### Structure index

Each node should include:

- stable section ID;
- level;
- exact title and normalized title;
- parent ID;
- child IDs;
- source page IDs;
- PDF/printed/slide start and end numbers;
- visual IDs and table IDs where applicable; and
- status/verification fields.

#### Visual index

Every visual index entry must contain page and location metadata. For a table,
include a resolvable table_id and table reconstruction path. For all other
visuals, state metadata_only unless targeted content extraction was actually
performed.

### Stage 13 - Validate after every stage

Do not wait until the end to discover dropped pages or broken IDs. Run a gate
after each stage.

#### Source gate

- source exists;
- SHA-256 is recorded;
- duplicate decision is recorded;
- page count is known;
- source manifest parses.

#### Inspection/structure gate

- PDF page count matches rendered page count;
- page dimensions are recorded;
- TOC/outline mapping is plausible;
- page/slide numbering is explicit;
- no chapter or document starts outside the source page range.

#### Extraction gate

- every page has a raw extraction record;
- page IDs are unique and sequential;
- no page disappears because extraction returned empty text;
- raw text and clean text are separate;
- line/word coordinates are inside the page bounds where available.

#### OCR/layout gate

- expected OCR pages have ocr_status: completed;
- expected layout pages have layout_status: completed;
- OCR region counts and confidence ranges are recorded;
- failed or skipped pages are listed explicitly;
- the requested-language layer is not contaminated by unwanted duplicate
  language text;
- representative rendered pages have been inspected.

#### Reading-order gate

- headings remain separate from body text;
- list markers and indentation are preserved;
- paragraphs spanning pages are linked;
- headers/footers are either retained with a role or excluded with a rule;
- visual content excluded by policy is absent from page prose but present in
  the visual/table layer.

#### Visual/table gate

- every visual candidate has a page and location;
- bounding boxes are within page dimensions or have an explicit exception;
- every table candidate is classified as reconstructed, rejected as a false
  positive, or unresolved;
- reconstructed tables have non-empty rows/cells when the source contains
  readable content;
- no table is labeled fully reconstructed when its contents were not checked;
- non-table visuals are not presented as reconstructed diagrams or graphs.

#### Analysis gate

- every leaf content unit is assigned once or listed as unresolved;
- every parent references valid children;
- summaries reference their source pages and child units;
- keyword records reference source units;
- table keyword records reference table IDs;
- no summary is mistaken for an exact quotation.

#### Retrieval gate

- all JSON parses;
- all JSONL lines parse;
- IDs are unique;
- term -> concept -> occurrence -> source link resolution passes;
- passage count matches the intended unit count;
- page references are present;
- visual/table links resolve;
- generated status is preserved;
- a direct query returns the expected source tier; and
- a course query returns course material before supplements.

#### Manual review gate

Review rendered source pages and compare them with generated records. At
minimum review:

- one title/heading page;
- one dense paragraph page;
- one list-heavy page;
- one cross-page paragraph;
- every table type or a representative sample of each table type;
- one page with multiple columns or sidebars;
- one page with a chart/graph/illustration;
- one bilingual page when applicable; and
- one final/index page.

Record what was reviewed, which pages were checked, and what remains
unverified. Only a human source review should change the status to verified.

## 4. AI retrieval and answer protocol

An AI consuming this package must follow this order.

1. Read the source registry or federation manifest.
2. Determine the relevant course/source priority.
3. Search the primary course/source package first.
4. Search supplemental packages only when the primary source is insufficient,
   or when the user asks for comparison.
5. Read the returned source passages, not only keyword hits or summaries.
6. Inspect the returned visual/table record when the question involves a
   visual, measurement, table, chart, or diagram.
7. Separate source evidence from AI inference.
8. Answer in the requested language.
9. Include source quotations and formal references for material claims.
10. State when a supplemental source was used.
11. State when evidence is generated but not manually verified.
12. For medical questions, avoid individualized diagnosis or treatment and
    recommend qualified professional advice where appropriate.

The AI must not:

- cite a keyword as if it were evidence;
- cite a summary as an exact quote;
- fabricate missing table values;
- infer chart trends without a readable source chart or explicit data;
- merge two separate sources into one quotation;
- use a supplemental book to silently override course material;
- present OCR errors as source wording without checking; or
- reveal private source content beyond the user's authorized use.

## 5. Recommended portable implementation

The following tools are common choices, not mandatory dependencies:

- Poppler: pdfinfo, pdftotext, pdftoppm;
- Python: pypdf, pdfplumber, Pillow, json, gzip;
- OCR: PaddleOCR, Tesseract, OCRmyPDF, or another language-appropriate OCR;
- layout detection: a local layout model or geometry-based fallback;
- validation: JSON schema checks, Python assertions, and rendered-page review.

Use a repeatable script or command for every stage. A typical shell sequence
is:

~~~bash
SOURCE_ID="SOURCE-001"
INPUT_PDF="/absolute/path/to/source.pdf"
PACKAGE_ROOT="/absolute/path/to/wiki/sources/$SOURCE_ID"
REVIEW_DIR="/absolute/path/to/work/$SOURCE_ID/review"

pdfinfo "$INPUT_PDF"
pdftotext -bbox-layout -enc UTF-8 "$INPUT_PDF" "$PACKAGE_ROOT/01 OCR and Layout/embedded_bbox.html"
pdftoppm -png -r 120 "$INPUT_PDF" "$REVIEW_DIR/page"
~~~

Never use these commands to overwrite the original PDF. Use a separate output
package and a separate temporary/review directory.

## 6. Failure and recovery rules

If a stage fails:

- keep the last valid layer;
- record the failure and affected pages;
- do not overwrite a good generated layer with an incomplete one;
- retry only the failed stage when possible;
- retain partial output under a clearly named .partial file if it is useful;
- mark downstream layers stale or blocked;
- rerun validation after recovery; and
- never claim complete coverage because a process exited without an error.

Common problems:

### OCR model unavailable

Use the embedded-text/layout fallback only if it is adequate, record skipped
coverage, and leave the source unverified. Do not silently substitute a
different language model.

### Text appears in the wrong order

Return to rendered-page review and coordinates. Keep the original raw text,
then rebuild only the clean reading-order layer.

### Bilingual duplicates appear

Keep the raw bilingual layer, create a requested-language derived layer, and
test the derived layer for unwanted scripts or duplicate blocks.

### Table content is missing from embedded text

Run targeted table OCR on the table region, reconstruct rows/cells, compare with
the source image, and link the table to the visual index. Do not add the OCR
cells to the normal page paragraph unless explicitly requested.

### Layout detection creates false table/figure candidates

Review the source image, mark the candidate as false positive or unresolved,
and preserve the location evidence. Do not generate a fictional table.

### A paragraph crosses a page break

Merge it only when layout and sentence continuity support the merge. Keep both
page-local fragments and the merged logical record.

### A page has no text

Do not drop it. It may be a visual-only page, separator, cover, scan failure, or
image. Create a page record and explain the absence of clean text.

## 7. Minimum source package contract

A package is not complete until it contains, or explicitly records why it lacks,
the following:

~~~text
source_manifest.json
raw page/OCR/layout records
clean reading-order records
document structure
visual manifest
table manifest
keyword records
hierarchical summaries
passage index
concept/occurrence/term indexes
structure index
visual index
formal output schema
validation report
AI usage instructions
processing log entry
~~~

At minimum, every generated JSON/JSONL object should be able to answer:

~~~text
What source did this come from?
What page or slide did it come from?
What section does it belong to?
Is it raw, extracted, reconstructed, summarized, or indexed?
Was visual content included or intentionally excluded?
Can another AI follow the link to the evidence?
Has a human verified it?
~~~

## 8. Final handoff format

When reporting completion, state:

- source path and hash;
- duplicate decision;
- package location;
- page/slide coverage;
- OCR/layout coverage and skipped pages;
- visual and table counts;
- hierarchy and summary counts;
- retrieval index counts;
- manual pages reviewed;
- remaining unverified or blocked items;
- validation/query results; and
- whether anything was uploaded, published, pushed, or externally shared.

Never report a full verified conversion when the actual result is only a
generated candidate or when some pages were processed with a fallback.

## 9. Completion checklist

Before marking a PDF conversion complete, check every item:

- [ ] The original PDF remains unchanged.
- [ ] Filename, path/URL, byte size, page count, and SHA-256 are recorded.
- [ ] Exact duplicate handling is recorded.
- [ ] PDF metadata, outline/TOC, dimensions, and page numbering were inspected.
- [ ] Representative pages were rendered and visually reviewed.
- [ ] Raw embedded text is preserved separately.
- [ ] Raw OCR and layout records are preserved separately when used.
- [ ] Requested-language derived text is separated from raw multilingual text.
- [ ] Reading order, headings, paragraphs, lists, and cross-page continuations
      were reconstructed.
- [ ] Bullet/dot/arrow/number markers and indentation were retained.
- [ ] Every visual candidate has a page and location.
- [ ] Tables were reviewed and reconstructed separately.
- [ ] Non-table visuals are metadata-only unless targeted extraction was
      explicitly performed.
- [ ] Chapter/part/section hierarchy is represented with stable IDs.
- [ ] Keywords were extracted at the leaf level with broad and small areas.
- [ ] Summaries were built bottom-up and cite child/source IDs.
- [ ] Passage, concept, occurrence, term, structure, visual, and table links
      resolve.
- [ ] Formal quotation and reference candidates are present.
- [ ] All generated records are marked generated_not_verified until human
      review.
- [ ] JSON/JSONL parsing and integrity validation passed.
- [ ] At least one direct retrieval query passed.
- [ ] Course-first priority was tested when applicable.
- [ ] The processing log was updated.
- [ ] Only intended local files were changed and committed, if Git is used.
- [ ] No external upload, publication, push, or sharing occurred without
      explicit permission.

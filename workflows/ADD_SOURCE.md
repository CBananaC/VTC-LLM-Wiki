# Add a source to the VTC LLM Wiki

Use this workflow whenever a new lecture, official document, assessment file,
past paper, book, article, or web source is given.

## 1. Preserve the input

Keep the original download unchanged in the VTC study folder. For a local file,
record its exact filename and location. For a web source, record the exact URL
and access date. Do not replace an existing file just because a new download
has a similar name.

## 2. Register the source

From the project root, run:

```bash
python3 tools/register_source.py \
  --source-id HHS4185-L3 \
  --title "Lecture 3 - Source title" \
  --course-code HHS4185 \
  --source-role course_materials \
  --source-kind lecture \
  --source-path "/absolute/path/to/source.pdf"
```

For an additional book or article, use `--source-role additional_source` and a
more specific `--source-kind`:

```bash
python3 tools/register_source.py \
  --source-id HHS4185-REF-STROKE-2026 \
  --title "Reference title" \
  --course-code HHS4185 \
  --source-role additional_source \
  --source-kind book \
  --source-path "/absolute/path/to/reference.pdf"
```

For a source that is only a URL:

```bash
python3 tools/register_source.py \
  --source-id HHS4185-REF-WHO-ICF \
  --title "WHO ICF source" \
  --course-code HHS4185 \
  --source-role additional_source \
  --source-kind web_source \
  --source-url "https://example.org/source"
```

The command creates `sources/<course-code>/<source-id>/`, its five processing
layers, `source_manifest.json`, and a package README. Local files are copied
into `00 Source/` by default and hashed with SHA-256. Use `--no-copy-source`
only when the canonical local file must remain outside this project. The
registry and manifest record `not_verified`; registration is not processing or
verification.

Use `--dry-run` first when the source metadata needs checking. The command
refuses to overwrite an existing package or reuse a registered `source_id`.

## 3. Process by source type

Use the closest existing package workflow:

- PDF with an embedded text layer: extract raw text page by page, preserving
  the original text layer separately from cleaned reading order.
- Image-only PDF or scanned page: render pages, run OCR/layout detection, and
  retain page images or coordinates needed for review.
- Slides: preserve slide number, bullet/arrow/indentation structure, and visual
  locations rather than flattening the deck into prose.
- Tables, charts, formulas, photographs, and illustrations: record locations
  first; reconstruct a table only after targeted visual review.
- Web or article source: save the source metadata and a source-preserving local
  capture only when permitted; do not treat a URL fetch alone as verification.

Write derived records into the relevant numbered layer. Never overwrite the raw
input. Mark OCR, summaries, table reconstructions, quotations, visual
interpretations, and retrieval records `generated_not_verified` until a person
checks the source page.

## 4. Build and validate retrieval

Create a source-specific retrieval index and query helper when the source type
supports it. Add its relative helper path to `source_registry.json`, then test
the project router:

```bash
python3 tools/query_vtc_wiki.py \
  --course-code HHS4185 \
  --query "your study question" \
  --limit 10
```

An AI consuming the result must read the returned source passages before
answering, preserve course-versus-supplement priority, cite source locators,
and manually verify exact quotations and visual/table interpretations.

## 5. Record and review

Record the source addition, processing status, validation evidence, and next
step in `PROJECT_LOG.md`. Commit each changed file separately. Review the
working tree before any remote action.

GitHub is intended to be public, but public visibility does not establish rights
to redistribute VTC course files, book text, OCR, or derived extracts. Review
copyright, personal data, and publication rights before any push. Google Drive
remains restricted; do not create folders, upload, or change permissions without
explicit approval and live verification.

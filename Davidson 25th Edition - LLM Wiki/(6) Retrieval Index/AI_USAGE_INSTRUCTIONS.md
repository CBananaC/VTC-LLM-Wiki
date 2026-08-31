# Instructions for AI Systems Using the HHS4185 Federated LLM Wiki

## Purpose

Use this collection to answer HHS4185 — Common Rehabilitation Conditions
study questions with source-grounded evidence. The collection combines
discovery and retrieval only. The source packages are not merged.

## Source priority

Always apply this order:

1. `hhs4185-course-materials` — primary course evidence, priority 1.
2. `davidson-25th-edition` — supplemental medical reference, priority 2.
3. `HHS4185-REF-STROKE-REHAB-5E` — supplemental stroke-rehabilitation
   reference, priority 2.

Use the course materials first. Use Davidson or Stroke Rehabilitation only to
supplement, clarify, or extend the course evidence. Explicitly label when a
statement comes from a supplement rather than the course materials.

The source-specific indexes remain separate:

- Davidson: `.` in this retrieval directory.
- Stroke Rehabilitation:
  `../../sources/HHS4185/HHS4185-REF-STROKE-REHAB-5E/04 Retrieval Index`.
- HHS4185 course materials:
  `../../HHS4185 Course Materials - LLM Wiki/(5) Retrieval Index`.

The authoritative federation map is
`hhs4185_federated_sources_manifest.json`.

## Preferred executable workflow

From the project root, run:

```bash
python3 tools/query_vtc_wiki.py \
  --course-code HHS4185 \
  --query "your study question" \
  --limit 10 \
  --max-terms 30
```

The command returns one JSON object with `packets`. The course-material packet
is first and contains the existing Davidson supplement field; the Stroke
package is returned as its own supplemental packet. Do not combine their
passage IDs or citation fields.

For a source-specific query, use the relevant helper directly:

```bash
python3 tools/query_stroke_rehab_retrieval.py \
  --query "stroke rehabilitation and spasticity"

python3 "Davidson 25th Edition - LLM Wiki/tools/query_davidson_retrieval.py" \
  --query "causes of amyloidosis"
```

If automatic term matching misses a concept, add explicit terms:

```bash
python3 tools/query_vtc_wiki.py \
  --course-code HHS4185 \
  --query "upper limb recovery" \
  --term "spasticity" \
  --term "motor recovery"
```

## Required retrieval procedure

1. Read the returned `packets` in priority order.
2. Within each packet, use `source_passage_candidates` as the primary textual
   evidence.
3. Read the complete returned passage, not only its keyword or excerpt.
4. Use `section_candidates` and `summary_candidates` to understand hierarchy
   and context. Summaries are orientation only, not independent evidence.
5. Use `quotation_candidates` for candidate quotations and their formal
   references.
6. Use `visual_candidates` for page, name, label, and location information.
7. If a matched visual is a table, read its returned
   `table_reconstruction`. Tables contain reconstructed contents but still
   require source-page checking.
8. Treat non-table visuals — figures, charts, graphs, photographs, and
   illustrations — as location/name metadata only. Do not invent their
   contents.
9. Check the original PDF page image before treating an exact quotation,
   table reconstruction, page number, or visual interpretation as verified.
10. Answer only after evaluating whether the course evidence is sufficient and
    whether supplemental material is actually needed.

## How to interpret the index files

- `term_lookup.json` maps normalized search terms to candidate concepts and
  occurrences.
- `concept_index.json` groups broad-area/small-area keyword candidates. It is
  a locator, not a clinical ontology.
- `occurrence_index.json` links a candidate keyword to source passages,
  visuals/tables, pages, and hierarchy nodes.
- `passage_index.jsonl` is the portable source-passage store. These passages
  preserve logical paragraph order, list metadata, cross-page reconstruction,
  source-line IDs, and formal references.
- `structure_lookup.json` provides the hierarchy
  `Part → Chapter → Major section → Subsection → Paragraph`.
- `visual_index.json` records all visual locations. Tables link to the full
  reconstructed records in the Text and Tables layer; non-table visuals are
  location-only.
- `formal_output_schema.json` defines the required answer, quotation, and
  reference fields.
- `retrieval_index_validation_report.json` records automated integrity checks.

Do not answer from a keyword, concept, occurrence, or summary record alone.
Those records locate evidence; they do not replace reading the source passage.

## Citation and answer format

Return a formal answer with these sections or equivalent JSON fields:

1. `answer` — concise synthesis.
2. `source_quotations` — the source-extracted quotation candidates actually
   used.
3. `references` — the matching formal references.

For book evidence, use the printed textbook page as the main citation page and
retain the PDF page only for file navigation. Cite the chapter and subsection
when available. For course evidence, cite the PDF filename and slide number.

Every quotation candidate currently has
`verification_status: generated_not_verified` and
`exact_quote_eligible: false` or an equivalent manual-check requirement. Do
not silently remove that status or present generated text as verified.

Example prose citation:

> The retrieved passage states that ... (Gillen, Stroke Rehabilitation, 5th
> ed., Ch. 1, p. 3).

Then identify whether the statement is from `course_materials`, Davidson, or
Stroke Rehabilitation. Do not cite one source as if it were another.

## Medical-safety and scope rules

- This is a study aid, not a substitute for clinical judgement, teaching,
  institutional guidance, or professional medical advice.
- Do not infer a treatment recommendation merely because a keyword matches.
- Distinguish source statements, summaries, and your own synthesis.
- If course and supplemental sources differ, report the difference and give
  both source references rather than silently reconciling them.
- Do not create or rely on a `claims_index.json`; this collection intentionally
  has no claims index.

## Source separation rule

Keep these identifiers and files independent:

- Course materials: their own source IDs, slide references, and index files.
- Davidson: `DAV25-*` passage/concept/occurrence/visual IDs and printed-book
  references.
- Stroke Rehabilitation: `STROKE5-*` passage/concept/occurrence/visual/table
  IDs and printed-book references.

The federation layer is a routing and discovery layer only. It must never
copy, flatten, renumber, or merge source records.

## Verification boundary

The retrieval index is structurally validated but generated. Before relying on
an answer, manually verify the relevant source page, especially:

- exact quotations and hyphenation;
- printed-page references;
- reconstructed table cells and layout;
- visual names, labels, and bounding-box locations;
- disagreements between course material and supplemental books.

The original PDFs remain the final source for verification.

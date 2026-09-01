# Davidson 25th Edition Retrieval Index

This is a portable, source-first retrieval package for Davidson's *Principles
and Practice of Medicine*, 25th edition. It is designed for ChatGPT, OpenCode,
local models, or another AI that can read JSON/JSONL.

## Contents

- `davidson25_paragraph_keyword_extraction_generated.json` — paragraph-level
  medical keyword candidates and visual keyword candidates.
- `davidson25_hierarchical_summaries_generated.json` — summaries in the order
  `Subsection → Major section → Chapter → Part`.
- `structure_lookup.json` — explicit `Part → Chapter → Major section →
  Subsection` hierarchy and source mapping.
- `concept_index.json` — canonical candidate concepts, source forms, aliases,
  broad-to-small `keyword_path`, and occurrence IDs.
- `occurrence_index.json` — source-linked keyword occurrences.
- `term_lookup.json` — normalized search term to concept/occurrence lookup.
- `passage_index.jsonl` — portable paragraph source store with printed-page and
  physical-PDF-page provenance.
- `visual_index.json` — visual location/name/type metadata and table links.
- `formal_output_schema.json` — portable answer contract with quotation and
  chapter/printed-page references.
- `retrieval_index_validation_report.json` — automated link and integrity checks.
- `hhs4185_federated_sources_manifest.json` — Davidson-side discovery manifest
  that points to HHS4185 course materials, Davidson, and Stroke Rehabilitation
  as separate source packages.

There is intentionally no `claims_index.json`. The package contains summaries,
but it does not pre-index AI-generated claims separately from the source.

## Query from the terminal

From the `tools` directory:

```bash
python3 query_davidson_retrieval.py --query "causes of amyloidosis"
```

For a term that automatic matching may miss:

```bash
python3 query_davidson_retrieval.py \
  --query "rehabilitation after stroke" \
  --term "stroke" \
  --term "rehabilitation"
```

The command returns a JSON retrieval packet. Give that packet to any AI and
instruct it to read `source_passage_candidates` and `quotation_candidates`
before answering, use `summary_candidates` only as orientation, and cite the
returned printed textbook page in `quotation_candidates[].reference.formatted`.
The packet also retains the physical PDF page as `PDF p.` so a reader can open
the exact file page. The formal response contract requires an answer,
source quotations, and references; it does not generate claims independently
of the returned source passages.

## Formal answer shape

An AI using this package should return:

1. `Answer` — a concise synthesis based on the retrieved passages.
2. `Source quotations` — one or more quotations from
   `quotation_candidates[].quotation`.
3. `References` — the matching `reference.formatted` value, where `p.` is the
   printed textbook page and `[PDF p. ...]` is only the physical-file locator.

Example reference form:

`Davidson's Principles and Practice of Medicine, 25th ed., Chapter 4: Clinical immunology, p. 76 [PDF p. 95]`

## Verification boundary

All extraction, summaries, concepts, occurrences, and visual mappings are
`generated_not_verified`. The original PDF, raw embedded text, and full clean
text layers remain separate and unchanged. Quotation candidates are copied
from the source-derived passage layer, but exact quotations and clinical use
require checking the original page image and appropriate medical judgement.

## HHS4185 course-first retrieval

For HHS4185 study questions, use the combined helper in the course-material
Wiki:

```bash
python3 "../HHS4185 Course Materials - LLM Wiki/tools/query_hhs4185_retrieval.py" \
  --query "rehabilitation principles for osteoporosis"
```

The project-level router searches HHS4185 lectures, workshops, and tutorials
first, then returns Davidson and Stroke Rehabilitation as separately labelled
supplements. The Davidson-side federation manifest is
`hhs4185_federated_sources_manifest.json`; the older
`hhs4185_course_first_manifest.json` remains available for the Davidson-only
course-first route. Course references use the PDF filename and slide number;
book references use the chapter and printed textbook page.

The source packages are combined only through discovery and retrieval routing.
Their raw files, cleaned text, hierarchy, summaries, keywords, passages,
visuals, tables, and IDs are not merged.

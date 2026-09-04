# AI usage instructions

This package contains the official HHS3190M Semester 1 (26-27) Scheme of
Module Activity. Use it as course-level evidence before supplemental books or
other sources.

## Retrieval

From the project root:

```bash
python3 tools/query_hhs3190m_official_sow.py --query "70% attendance"
```

For course-aware retrieval, use:

```bash
python3 tools/query_vtc_wiki.py --course-code HHS3190M --query "EA Case Study"
```

Read `source_passage_candidates` before answering. Search
`table_candidates` when the question concerns assessment weighting, the weekly
lesson plan, or teacher information. Non-table visual records are metadata
only.

## Answer contract

Return:

1. `answer` - a concise answer grounded in the returned page passage or table.
2. `source_quotations` - only exact source wording, marked as requiring manual
   checking.
3. `references` - cite `01 - S1 SOW (26-27).pdf, PDF p. N`.

Keep this official document separate from lecture decks and supplemental books.
Do not silently use a supplemental source to override it. All generated text,
table reconstructions, keywords, summaries, quotations, and retrieval matches
are `generated_not_verified` until the original PDF page has been checked.

The PDF is bilingual, but the normal derived retrieval layer is English-only;
the raw bilingual extraction remains in the OCR/layout layer for provenance.

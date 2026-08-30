# VTC LLM Wiki — project rules

## Purpose and scope

- Project root: `/Users/creamybanana/Downloads/VTC LLM Wiki`
- Type: `hybrid`
- Purpose: A unified, source-preserving LLM Wiki for the user’s Hong Kong VTC rehabilitation studies, combining course materials from every course with carefully identified additional books and other sources.
- Intended users: The student owner, ChatGPT, OpenCode, local language models, and other AI systems that need source-grounded study answers.
- Main outcome: A navigable multi-course study knowledge base with course-aware retrieval, explicit source provenance, generated-versus-verified labels, and a repeatable workflow for adding any new source.

Preserve source material and user-owned edits. Do not expand the scope without discussing it first.

## Required project files

- `PROJECT_DESCRIPTION.md` is the stable project brief.
- `PROJECT_LOG.md` is append-only and records concise action summaries, not full prompts or secrets.
- Update this `AGENTS.md` when project rules, source-of-truth paths, commands, or boundaries change.

## Source organization

- `source_registry.json` is the project-level directory of courses, additional sources, package paths, source manifests, retrieval helpers, and verification status.
- The existing `HHS4185 Course Materials - LLM Wiki/` and `Davidson 25th Edition - LLM Wiki/` packages are preserved at the project root; do not rename, flatten, or rewrite their generated layers without a targeted reason.
- New source packages created by `tools/register_source.py` use `sources/<course-code>/<source-id>/` with `00 Source`, `01 OCR and Layout`, `02 Text and Tables`, `03 Analysis`, and `04 Retrieval Index` layers.
- Original PDFs and other source files are immutable inputs. Keep raw/extracted/analysed/retrieved layers separate, and label OCR, summaries, tables, quotations, visual interpretations, and retrieval results `generated_not_verified` until manual source review.
- Use `workflows/ADD_SOURCE.md` and `tools/register_source.py` for every new source. Do not silently add files to an index or claim that a source has been verified merely because processing succeeded.
- Use `tools/query_vtc_wiki.py` as the project-level retrieval entry point when a registered package has a query helper. Read returned source passages before answering and keep course material ahead of supplemental sources when the registry says so.

## Git and remote boundaries

- Commit after every individual file write when Git is available; stage only the intended file and verify the commit hash.
- GitHub visibility decision: `public`. Ask before creating or connecting a remote repository.
- Google Drive sharing decision: `restricted`. Ask before creating a folder, changing permissions, or uploading files.
- Do not push, publish, upload, or send external messages without explicit approval.

## Safety and validation

- Never print, store, commit, or upload passwords, tokens, API keys, cookies, private keys, credential files, or one-time codes.
- Read before writing; preserve unrelated changes; avoid destructive commands.
- Validate the actual requested surface and record evidence in `PROJECT_LOG.md`.
- Keep the local project folder as the source copy unless the user explicitly requests a move.
- Before a public GitHub commit or push, review source copyright, personal data, and redistribution rights. A public repository decision does not by itself authorize publishing course PDFs, book text, OCR, or derived extracts.

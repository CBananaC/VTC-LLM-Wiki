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

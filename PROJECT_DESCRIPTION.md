# VTC LLM Wiki

## Project identity

- Root: `/Users/creamybanana/Downloads/VTC LLM Wiki`
- Type: `hybrid`
- Status: Bootstrapped locally; remote setup pending confirmation and live verification.

## Purpose

- Purpose: A unified, source-preserving LLM Wiki for the user’s Hong Kong VTC rehabilitation studies, combining course materials from every course with carefully identified additional books and other sources.
- Intended users: The student owner, ChatGPT, OpenCode, local language models, and other AI systems that need source-grounded study answers.
- Main outcome: A navigable multi-course study knowledge base with course-aware retrieval, explicit source provenance, generated-versus-verified labels, and a repeatable workflow for adding any new source.

## Scope

- Scope: Maintain one project-level catalogue and retrieval entry point for VTC course materials and additional study sources across courses and semesters. Preserve each source package's raw, OCR/layout, text/table, analysis, and retrieval layers, while allowing source-specific processors to remain inside their package.
- Current packages: `HHS4185 Course Materials - LLM Wiki/` and `Davidson 25th Edition - LLM Wiki/`, both moved into this project from the HHS4185 study folder with their files intact.
- Future package location: `sources/<course-code>/<source-id>/`, created by `tools/register_source.py`.
- Non-goals: Do not infer unrequested features, uploads, deployments, or publication. Do not treat generated extraction as verified medical or academic evidence.
- Inputs: VTC lecture/workshop/tutorial slides, official course documents, assessment material, past papers, books, journal or web sources, source metadata, and manually reviewed page images.
- Outputs: Source manifests, immutable raw-source references or copies, OCR/layout records, structured text and table candidates, analysis summaries, source-linked retrieval indexes, and a formal AI answer contract with provenance.
- Success criteria: A new source can be registered with one documented command; its hash and provenance are recorded; processing layers stay separate; retrieval returns source IDs and locators; course material is prioritized over supplemental sources where configured; and every generated candidate remains visibly unverified until manual review.
- Source of truth: This project folder and its project-level `AGENTS.md`.

## Remote destinations

- GitHub visibility: `public`
- GitHub repository: Pending confirmation/connection.
- Google Drive sharing: `restricted`
- Google Drive folder: Pending confirmation/connection.

## Validation and next decision

- Validate generated files, Git state/commits when applicable, and any live remote resource separately.
- Local status: The two existing wiki directories have been moved here; local Git is initialized; project rules and bootstrap metadata are committed.
- GitHub: Intended visibility is `public`, but the repository owner/name and any publication-safe file set still need confirmation. Public visibility must not be treated as permission to redistribute copyrighted course/book source material.
- Google Drive: Intended sharing is `restricted`; exact destination folder and upload scope remain to be confirmed.
- Next decision: Confirm the GitHub owner/repository name, review what may legally be public, and identify the restricted Drive folder before any remote creation, upload, permission change, or push.

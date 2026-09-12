# Rules

## Scope and documentation

- [`PLANS.md`](PLANS.md) owns status and plans.
- [`agents_docs/ARCHITECTURE.md`](agents_docs/ARCHITECTURE.md) owns the current pipeline, interfaces, and failures.
- [`agents_docs/DECISIONS.md`](agents_docs/DECISIONS.md) owns accepted decisions and rationale.

Read the relevant authoritative document before work. Update only that document and link to it instead of duplicating stable details elsewhere.

For features, refactoring, or architectural changes:

- Before substantial implementation, update the current plan in `PLANS.md`.
- Keep the plan focused on current work and immediate next steps. Preserve planned future stages and their details unless the user explicitly requests a revision.
- Update `agents_docs/ARCHITECTURE.md` when the implemented structure, data flow, interfaces, lifecycle, or failure behavior changes.
- Record accepted technical choices and their rationale in `agents_docs/DECISIONS.md`; preserve superseded decisions as history.
- After implementation, align plan status and architecture with the actual result. For a numbered staged plan, move the completed stage to `Recently Completed` with a concise summary and validation results, move `(current)` to the next stage, and renumber the remaining stages from 1 without shortening or rewording them.
- Validate changed links and diffs with the project's available checks.

Routine fixes do not require documentation updates unless they change documented behavior or project rules require it.

## Pipeline and code

- Follow the pipeline and component boundaries in `agents_docs/ARCHITECTURE.md`.
- Write configs with Pydantic models.

## Notebooks

- Keep notebooks linear: setup, runtime wiring, data preparation, indexing or search, checks, then optional UI adapters.
- Use sparse headings, minimal comments, non-duplicative Markdown, and concise Google-style docstrings.

## Safety and workflow

- Before editing, inspect the repository state and preserve unrelated or uncommitted work.
- Treat `data/` as read-only unless the task explicitly requires changing it.
- Use `.venv` and `uv`. Explain new dependencies and obtain confirmation before `uv add` (without custom cache dir).
- Run the smallest relevant project checks and report clearly which checks were and were not run.
- Do not commit or push changes unless the user explicitly requests it.

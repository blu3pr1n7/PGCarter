# Contributing

Contributions are welcome. This guide covers the workflow and expectations.

## Before you start

- Read the [Architecture](architecture.md) overview to understand the layer
  boundaries (extraction → models → SQL/JSON/docs, plus the analyzer).
- Set up your environment per [Development Setup](development.md).

## Workflow

1. **Fork and branch.** Create a feature branch off `master`.
2. **Make focused changes.** Keep SQL generation template-free and documentation
   template-driven — never embed Markdown in Python or generate SQL from
   templates.
3. **Add tests.** New extractors, checks, or behaviours need unit tests; prefer
   the `FakeDB` pattern so tests run without a live database.
4. **Run the full local gate:**

   ```bash
   make lint
   make typecheck
   make test
   ```

5. **Update docs.** If you change CLI flags, configuration, or behaviour, update
   the relevant page under `docs/` and the `README`.
6. **Open a pull request** describing the change and linking any related issue.

## Coding standards

- **Python 3.12+**, fully type-annotated (`mypy` runs with
  `disallow_untyped_defs`).
- **Ruff** for linting and formatting (line length 100; rule sets `E`, `F`, `I`,
  `UP`, `B`). Run `make format` before committing.
- **Read-only guarantee.** Never introduce code that writes to the target
  database or emits row data. Analysis SQL must pass `assert_safe`.
- **Resilience.** A failure in one extractor or check should be recorded in the
  run report, not abort the whole run.
- **Imports are absolute** (`from pgcarter.… import …`), never relative.

## Commit & PR conventions

- Keep commits scoped and message-clear.
- CI (see [the workflows](#continuous-integration)) runs tests, lint, and type
  checks on every push and pull request; the documentation build runs with
  `--strict`. All must pass.

## Continuous integration

| Workflow | Trigger | Does |
| --- | --- | --- |
| `tests.yml` | push / pull request | `pytest`, `ruff check`, `mypy` |
| `docs.yml` | push to `master`, manual | `mkdocs build --strict` and deploy to GitHub Pages |

A documentation change that breaks a link, references a missing file, or fails
the strict MkDocs build will fail CI.

## Reporting issues

Open an issue with: what you ran, what you expected, what happened (including the
relevant `report.json` / `run-report.json` summary and any log output), and your
PostgreSQL and Python versions.

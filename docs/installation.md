# Installation

## Requirements

- **Python 3.12+**
- A reachable **PostgreSQL** database for the online features (extraction and
  online profiling). Offline analysis needs only a previously generated JSON
  inventory.

`pgcarter` builds on [`psycopg`](https://www.psycopg.org/psycopg3/) (psycopg 3),
[`jinja2`](https://jinja.palletsprojects.com/),
[`typer`](https://typer.tiangolo.com/),
[`structlog`](https://www.structlog.org/), and `pyyaml`. No SQLAlchemy.

## Install from source

The project is currently distributed via source.

=== "uv (recommended)"

    ```bash
    git clone git@github.com:blu3pr1n7/pgcarter.git
    cd pgcarter
    uv venv --python 3.12
    uv pip install -e ".[dev]"
    ```

=== "pip"

    ```bash
    git clone https://github.com/blu3pr1n7/pgcarter.git
    cd pgcarter
    python3.12 -m venv .venv && . .venv/bin/activate
    pip install -e ".[dev]"
    ```

This installs the package in editable mode along with the development tools
(`pytest`, `ruff`, `mypy`).

!!! tip "Package install"
    Once published to an index, installation is the usual:

    ```bash
    pip install pgcarter
    # or with uv:
    uv pip install pgcarter   # into an active venv
    uv add pgcarter           # into a uv-managed project
    ```

## Verify the installation

```bash
pgcarter --help
pgcarter index --help
pgcarter analyze --help
```

You should see the two subcommands, `index` and `analyze`.

## Optional dependency groups

| Extra | Installs | Used for |
| --- | --- | --- |
| `dev` | pytest, pytest-cov, mypy, ruff | running tests, linting, type-checking |
| `docs` | mkdocs-material, mkdocstrings | building this documentation site locally |

```bash
uv pip install -e ".[docs]"   # to build the docs site (or: pip install -e ".[docs]")
```

## Next steps

- [Usage](usage.md) — run your first extraction and analysis
- [Configuration](configuration.md) — connection and analysis settings

"""Version consistency guard.

The package declares its version in two places — ``pgcarter/__init__.py``
(``__version__``, the runtime constant) and ``pyproject.toml`` (``project.version``,
which the build backend stamps onto the published artifact). They must always
agree, so a release can never ship a wheel whose metadata disagrees with the
importable ``__version__``. The release tooling also tags ``v<version>``; this
test pins the two in-repo declarations together and runs as part of ``make ci``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pgcarter

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_package_and_pyproject_versions_match():
    pyproject = tomllib.loads(_PYPROJECT.read_text())
    assert pgcarter.__version__ == pyproject["project"]["version"]

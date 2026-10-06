"""Docs must not point at files that do not exist (F-041)."""
import re
from pathlib import Path

import pytest

LOCALDEV = Path(__file__).resolve().parent.parent
REPO = LOCALDEV.parent
DOCS = [REPO / "CLAUDE.md", LOCALDEV / "CLAUDE.md", LOCALDEV / "docs" / "ARCHITECTURE.md", LOCALDEV / "docs" / "CODEMAP.md"]
# Backticked file paths and directories, including single-component directories.
PATH = re.compile(r"`(/?[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+/?|[A-Za-z0-9_.\-]+/)`")
# Absolute URL routes and check-in route examples are not filesystem paths.
ROUTE_PREFIXES = ("/", "api/<", "c/")


def _paths(text: str):
    for raw in PATH.findall(text):
        if any(ch in raw for ch in "*<>{}") or raw.startswith(("http", *ROUTE_PREFIXES)):
            continue
        yield raw


def _candidates(doc: Path):
    yield from _paths(doc.read_text())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("`fratos/`", ["fratos/"]),
        ("`greekos/`", ["greekos/"]),
        ("`api/platform/db.py`", ["api/platform/db.py"]),
        ("`/api/health` `/c/CODE` `c/CODE`", []),
        ("`https://example.com/` `api/<domain>/` `lib/*.ts`", []),
    ],
)
def test_path_extraction(text, expected):
    assert list(_paths(text)) == expected


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_backticked_paths_exist(doc):
    missing = [
        raw for raw in _candidates(doc)
        if not any((base / raw).exists() for base in (REPO, LOCALDEV, LOCALDEV / "greekos", LOCALDEV / "greekos" / "src"))
    ]
    assert not missing, f"{doc.name} points at paths that do not exist: {missing}"

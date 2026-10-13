"""The documents against the code: what the README and the API pages name
exists, every public name is documented, and no document tells the history of
the package (the changelog is where a change is recorded)."""

from __future__ import annotations

import importlib
import pathlib
import re

import pytest

import uripath
from uripath import URIPath
from uripath.schemes import _elsewhere, _registry

REPO = pathlib.Path(__file__).resolve().parent.parent
HEADER = pathlib.Path(uripath.__file__).resolve().parent / "AGENTS.md"
README = REPO / "README.md"
API = sorted((REPO / "docs" / "api").rglob("*.md"))
PUBLIC_MODULES = [
    "uripath",
    "uripath.exceptions",
    "uripath.query",
    "uripath.schemes",
    "uripath.source",
    "uripath.transports",
    "uripath.testing",
    "uripath.cli",
]
HISTORY = re.compile(
    r"\b(previously|formerly|no longer|used to|as before|was changed|"
    r"now returns|now raises|renamed from)\b",
    re.IGNORECASE,
)


def _section(text, heading):
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_the_readme_feature_table_has_a_row_for_every_scheme_the_package_knows():
    table = _section(README.read_text(encoding="utf-8"), "Features")
    rows = [line for line in table.splitlines() if line.startswith("| `")]
    named = {
        name
        for row in rows
        for name in re.findall(r"`([a-z][a-z0-9+.-]*):`", row.split("|")[1])
    }
    # `URIPath.schemes()` also lists the schemes that other tests define.
    assert named == set(_registry._BUILTIN_SCHEMES) | set(_elsewhere.SCHEMES)
    assert named <= set(URIPath.schemes())


def test_the_readme_names_the_distribution_of_each_scheme_it_does_not_contain():
    table = _section(README.read_text(encoding="utf-8"), "Features")
    rows = {
        re.search(r"`([a-z0-9]+):`", line).group(1): line
        for line in table.splitlines()
        if line.startswith("| `") and "uripath-" in line
    }
    assert set(rows) == set(_elsewhere.SCHEMES)
    for scheme, (distribution, _package, _install) in _elsewhere.SCHEMES.items():
        assert distribution in rows[scheme], scheme


@pytest.mark.parametrize("module", PUBLIC_MODULES)
def test_every_public_name_is_in_the_shipped_header(module):
    text = HEADER.read_text(encoding="utf-8")
    imported = importlib.import_module(module)
    missing = [
        name
        for name in imported.__all__
        if not re.search(rf"(?<![\w.]){re.escape(name)}(?!\w)", text)
    ]
    assert missing == []


def _directives():
    """`{dotted name: has a members list}` of every `:::` line of the API pages."""
    found = {}
    for page in API:
        lines = page.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.startswith("::: "):
                block = lines[index + 1 : index + 6]
                restricted = any(item.strip().startswith("members:") for item in block)
                found[line[4:].strip()] = restricted
    return found


def _resolve(dotted):
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            found = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for part in parts[cut:]:
            found = getattr(found, part)
        return found
    raise ImportError(dotted)


def test_every_object_an_api_page_renders_exists():
    for dotted in _directives():
        assert _resolve(dotted) is not None, dotted


@pytest.mark.parametrize("module", PUBLIC_MODULES)
def test_every_public_name_is_on_an_api_page(module):
    directives = _directives()
    prose = "\n".join(page.read_text(encoding="utf-8") for page in API)
    whole = module in directives and not directives[module]
    imported = importlib.import_module(module)
    missing = [
        name
        for name in imported.__all__
        if not whole
        and f"{module}.{name}" not in directives
        and f"`{name}`" not in prose
        and f"`{module}.{name}`" not in prose
        and name not in {"__version__"}
    ]
    assert missing == []


DOCUMENTS = [
    README,
    HEADER,
    REPO / "docs" / "index.md",
    *sorted((REPO / "docs" / "guides").glob("*.md")),
    *API,
]


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: p.name)
def test_a_document_describes_the_package_as_it_is(document):
    text = document.read_text(encoding="utf-8")
    found = [
        f"line {text.count(chr(10), 0, match.start()) + 1}: {match.group(0)}"
        for match in HISTORY.finditer(text)
    ]
    assert found == []


def test_the_history_check_reports_a_phrase():
    assert HISTORY.search("The name was previously Uri.")
    assert HISTORY.search("A query is no longer a str.")
    assert not HISTORY.search("The previous content is kept.")

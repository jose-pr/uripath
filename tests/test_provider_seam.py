"""The seam between `pathlib_next` and the URI schemes.

Every underscore name that a scheme module (or the command line) imports from
the core or reads as an attribute of one of its objects is documented in the
implementer sections of the two shipped headers (`pathlib_next`'s for a class
built on `Path`, this package's for a scheme), each helper that was made public
is the same object as the underscore name it replaced, and every name this
package takes from `pathlib_next` is public except the ones listed here.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import re

import pytest

import pathlib_next
import uripath

CORE = pathlib.Path(pathlib_next.__file__).resolve().parent
PACKAGE = pathlib.Path(uripath.__file__).resolve().parent
HEADERS = {
    "For path implementers": CORE / "AGENTS.md",
    "For scheme implementers": PACKAGE / "AGENTS.md",
}
HEADER = PACKAGE / "AGENTS.md"

# Names a scheme module reads that are its own: an attribute of one of its
# helper classes, or of a stdlib named tuple. Each is a name the scan finds
# in a core module too; a pair that no longer matches anything fails.
NOT_THE_CORES = {
    ("schemes/dav.py", "_path"): "the path a stream is for",
    ("schemes/http.py", "_path"): "the path a stream is for",
    ("schemes/dav.py", "_replace"): "a stdlib named tuple's method",
    ("schemes/_gitrepo.py", "_replace"): "a `Source` named tuple's method",
}

# (module, file that imports it, private name): what this package takes from a
# private place in `pathlib_next`. Nothing may be private.
PRIVATE_FROM_PATHLIB_NEXT: set[tuple[str, str, str]] = set()

# (module, public name): documented helpers a provider calls, defined in a
# private module and listed in the public module's `__all__`.
PROVIDER_HELPERS = [
    ("pathlib_next.providers", "check_follow"),
]

# (public module, module that defines it, public name, the underscore name it
# replaced)
PUBLIC_HELPERS = [
    ("uripath", "uripath", "same_authority", "_same_authority"),
    ("uripath", "uripath", "DerivedBackend", "_DerivedBackend"),
    ("uripath.source", "uripath.source._compose", "compose_uri", "_compose_uri"),
    ("uripath.source", "uripath.source._compose", "compose_host", "_compose_host"),
    ("uripath.source", "uripath.source._compose", "percent_encode", "_encode"),
    ("uripath.source", "uripath.source._parse", "is_drive", "_is_drive"),
    ("uripath.source", "uripath.source._compose", "SAFE_PATH", "_SAFE_PATH"),
    ("uripath.source", "uripath.source._parse", "ERRORS", "_ERRORS"),
]


def is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _files(directory: pathlib.Path):
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def core_sources() -> dict[str, str]:
    """Every module of the core that is not a provider package (`ftp`,
    `archive`), plus the URI core of this package (`uripath`, `source`,
    `query`), whose underscore names the schemes read as well."""
    skipped = (
        CORE / "uri",
        CORE / "tools",
        CORE / "ftp",
        CORE / "archive",
    )
    found = {
        "pathlib_next/" + p.relative_to(CORE).as_posix(): p.read_text(encoding="utf-8")
        for p in _files(CORE)
        if not any(s in p.parents for s in skipped) and p.name != "testing.py"
    }
    for path in (
        PACKAGE / "__init__.py",
        PACKAGE / "query.py",
        *_files(PACKAGE / "source"),
    ):
        found["uripath/" + path.relative_to(PACKAGE).as_posix()] = path.read_text(
            encoding="utf-8"
        )
    return found


def scheme_sources() -> dict[str, str]:
    """The schemes and the command line, by path relative to the package."""
    return {
        p.relative_to(PACKAGE).as_posix(): p.read_text(encoding="utf-8")
        for p in _files(PACKAGE)
        if "schemes" in p.relative_to(PACKAGE).parts or p.name == "_oldcli.py"
    }


def core_names(sources: dict[str, str]) -> set[str]:
    """The underscore names the core defines: functions, classes, module and
    class attributes, `self.x = ...` and `__slots__` entries."""
    found: set[str] = set()
    for text in sources.values():
        for node in ast.walk(ast.parse(text)):
            names: list[str] = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.append(target.id)
                        if target.id == "__slots__" and isinstance(
                            node.value, (ast.Tuple, ast.List)
                        ):
                            names += [
                                e.value
                                for e in node.value.elts
                                if isinstance(e, ast.Constant)
                            ]
                    elif isinstance(target, ast.Attribute) and isinstance(
                        target.value, ast.Name
                    ):
                        names.append(target.attr)
            found.update(n for n in names if is_private(n))
    return found


def _imported_module(relpath: str, node: ast.ImportFrom) -> str:
    """The dotted module a `from ... import` of the file at `relpath` (below
    the package) names."""
    package = ["uripath", *relpath.split("/")[:-1]]
    if node.level:
        package = package[: len(package) - (node.level - 1)]
        return ".".join([*package, *(node.module.split(".") if node.module else [])])
    return node.module or ""


def seam_names(core: set[str], sources: dict[str, str]) -> dict[str, set[str]]:
    """`{name: modules}` for each underscore name of `core` that a module of
    `sources` imports from outside the scheme layer or reads as an attribute."""
    used: dict[str, set[str]] = {}
    for relpath, text in sources.items():
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                module = _imported_module(relpath, node)
                if module.startswith("uripath.schemes"):
                    continue
                for alias in node.names:
                    if alias.name in core:
                        used.setdefault(alias.name, set()).add(relpath)
            elif isinstance(node, ast.Attribute) and node.attr in core:
                used.setdefault(node.attr, set()).add(relpath)
    return used


def documented_names() -> set[str]:
    """The names the python blocks of the implementer sections declare."""
    found: set[str] = set()
    for title, header in HEADERS.items():
        section, inside, fenced = [], False, False
        for line in header.read_text(encoding="utf-8").splitlines():
            if line.startswith("```"):
                fenced = not fenced
            elif not fenced and re.match(r"#{1,3} ", line):
                inside = line.startswith(f"### {title}")
            if inside:
                section.append(line)
        assert section, f"{header.name} has no '{title}' section"
        for block in re.findall(
            r"```python\n(.*?)```", "\n".join(section), flags=re.DOTALL
        ):
            for node in ast.walk(ast.parse(block)):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    found.add(node.name)
                elif isinstance(node, ast.Assign):
                    found.update(t.id for t in node.targets if isinstance(t, ast.Name))
                elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Name):
                    found.add(node.value.id)
    return found


@pytest.fixture(scope="module")
def core():
    return core_names(core_sources())


def test_the_scan_finds_the_names_the_schemes_use(core):
    used = seam_names(core, scheme_sources())
    assert {
        "_init",
        "_from_parsed_parts",
        "_format_parsed_parts",
        "_make_child_relpath",
        "_rename_target",
        "_pop_stat_hint",
        "_backend_for",
        "_scandir",
    } <= set(used)


def test_every_core_name_a_scheme_uses_is_documented_in_the_headers(core):
    used = seam_names(core, scheme_sources())
    documented = documented_names()
    undocumented = {
        name: sorted(modules)
        for name, modules in used.items()
        if name not in documented
        and not all((module, name) in NOT_THE_CORES for module in modules)
    }
    assert undocumented == {}


def test_the_scheme_owned_names_are_all_still_read_by_their_module(core):
    used = seam_names(core, scheme_sources())
    stale = [pair for pair in NOT_THE_CORES if pair[0] not in used.get(pair[1], ())]
    assert stale == []


def test_a_scheme_that_takes_an_undocumented_core_name_is_reported(core):
    sources = scheme_sources()
    sources["schemes/new.py"] = (
        "from pathlib_next.path import _relation\n"
        "\n"
        "class New:\n"
        "    def go(self):\n"
        "        return self._family()\n"
    )
    used = seam_names(core, sources)
    documented = documented_names()
    assert {"_relation", "_family"} <= set(used)
    assert {"_relation", "_family"}.isdisjoint(documented)


def test_no_scheme_imports_an_underscore_name_from_the_core(core):
    imported = []
    for relpath, text in scheme_sources().items():
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                module = _imported_module(relpath, node)
                if module.startswith("uripath.schemes"):
                    continue
                imported += [
                    (relpath, alias.name) for alias in node.names if alias.name in core
                ]
    assert imported == []


def _taken_from_pathlib_next():
    """`(module, file, name)` for every name the package imports from
    `pathlib_next`, and for every attribute it reads of a module imported
    from there (`_providers.stub`)."""
    taken = set()
    for p in _files(PACKAGE):
        relpath = p.relative_to(PACKAGE).as_posix()
        tree = ast.parse(p.read_text(encoding="utf-8"))
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and not node.level:
                module = node.module or ""
                if module != "pathlib_next" and not module.startswith("pathlib_next."):
                    continue
                for alias in node.names:
                    taken.add((module, p.name, alias.name))
                    if module == "pathlib_next" and alias.name[:1].islower():
                        aliases[alias.asname or alias.name] = (
                            f"pathlib_next.{alias.name}"
                        )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
            ):
                taken.add((aliases[node.value.id], p.name, node.attr))
    return taken


def test_every_name_taken_from_pathlib_next_is_public_but_the_listed_ones():
    private = set()
    for module, filename, name in _taken_from_pathlib_next():
        private_module = any(part.startswith("_") for part in module.split("."))
        if private_module or is_private(name):
            private.add((module, filename, name))
            continue
        try:
            importlib.import_module(f"{module}.{name}")
        except ImportError:
            pass
        else:
            continue  # a public submodule (`pathlib_next.providers`)
        exported = getattr(importlib.import_module(module), "__all__", None)
        if exported is not None:
            assert name in exported, (module, filename, name)
    assert private == PRIVATE_FROM_PATHLIB_NEXT


@pytest.mark.parametrize(("module", "owner", "public", "private"), PUBLIC_HELPERS)
def test_a_public_helper_is_the_object_its_underscore_name_stays_as(
    module, owner, public, private
):
    imported = importlib.import_module(module)
    assert getattr(imported, public) is getattr(importlib.import_module(owner), private)
    if hasattr(imported, "__all__"):
        assert public in imported.__all__
        assert private not in imported.__all__


@pytest.mark.parametrize(("module", "owner", "public", "private"), PUBLIC_HELPERS)
def test_a_public_helper_is_documented_in_the_header(module, owner, public, private):
    assert public in documented_names()


@pytest.mark.parametrize(("module", "public"), PROVIDER_HELPERS)
def test_a_provider_helper_is_exported_and_documented(module, public):
    imported = importlib.import_module(module)
    assert public in imported.__all__
    assert callable(getattr(imported, public))
    assert public in documented_names()

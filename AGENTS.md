# uripath — contributor orientation

Orientation for working in a checkout of this repository: layout, environments,
commands, CI and release. It is not the API reference and it does not ship.

| Header | Covers |
| --- | --- |
| [`src/uripath/AGENTS.md`](src/uripath/AGENTS.md) | The public API: `URI`, `URIPath`, `Source`, `Query`, every built-in scheme, the exceptions and the command, with signatures and gotchas. It ships in the wheel, so it stays self-contained (no repo-relative links) and changes in the same commit as any public API change. |

[`docs/divergences.md`](docs/divergences.md) records every deliberate difference
from `pathlib.Path` that this package owns; the ones of the classes in
`pathapi` are on that project's site. `pathlib.Path` parity is the
contract; a behavioral divergence that is not recorded is a bug.

## Layout

| Path | Contents |
| --- | --- |
| `src/uripath/` | The package (`src/` layout). `py.typed` and the API header ship with it. |
| `src/uripath/__init__.py`, `_uri.py`, `source/`, `query.py`, `exceptions.py` | The root only exports. `URI` (one large class), `Source` (a package of private modules), `Query` and the errors. |
| `src/uripath/schemes/` | The contract (`_path.py`: `URIPath`), the registry (`_registry.py`: the built-in table and the entry points) and one private module or package per scheme (`_file.py`, `_http/`, ...); `__init__.py` exports their names lazily. Registered through the `uripath.schemes` entry points in `pyproject.toml`. |
| `src/uripath/schemes/_unregistered.py` | The stand-in class of a scheme no class registers, and the `ImportError` that suggests names to look for. |
| `src/uripath/cli/`, `__main__.py` | The `uripath` command on `duho`, one module per subcommand; `import uripath` never imports it. |
| `src/uripath/_pathtext.py`, `_transfer.py`, `_rfc3986.py` | `as_path()`, `copy_stream()` and the RFC 3986 split and percent-coding on `urllib.parse`. |
| `tests/` | The pytest suite. `tests/conftest.py` holds the loopback servers; `tests/mutation/` is the mutation list; `tests/probes/` are child processes that tests run. |
| `benchmarks/` | `bench.py` and committed JSON results; see [`benchmarks/README.md`](benchmarks/README.md). Not shipped. |
| `examples/` | Runnable scripts. Networked ones skip (exit 0) unless their environment variables are set. |
| `docs/`, `mkdocs.yml` | MkDocs site: hand-written pages plus a `mkdocstrings` API reference. |
| `.github/workflows/` | `test.yml`, `release.yml`, `docs.yml`. |
| `CHANGELOG.md` | Keep a Changelog. Released sections are frozen records. |

## Environment

Python 3.9 is the floor (`requires-python = ">=3.9"`) and 3.14 is the latest
supported. Test on both ends before claiming a change works.

Keep one virtualenv per interpreter under `.venv/<version>-<os>-<arch>/`
(gitignored), where `<os>` is `os.name` (`nt`/`posix`) or `darwin`, and `<arch>`
is the architecture the interpreter was built for:

```bash
python -m venv .venv/3.14-posix-x86_64
.venv/3.14-posix-x86_64/bin/python -m pip install -e ".[dev]"
```

On Windows the interpreter is `.venv\<name>\Scripts\python.exe`. `dev` holds the
`cli` extra, every test server and the oracles of the property tests.

`pathapi` is a dependency. While it is not on PyPI, install the core editable
from its checkout first (`pip install -e ../pathapi`), then this package. A
`pathlib-next` 0.9 left in the environment installs a `uripath` script of its
own: uninstall it, or install this package last so that it owns the name.

A missing test server does not fail the suite: its tests are skipped instead, so
check `pytest -rs` before trusting a green run. A venv holding only this package
and `pytest` runs the tests that need nothing else (`test.yml` has a job for it).

## Checks

```bash
python -m pytest -q -rs                              # full suite (pythonpath=src is configured)
python -m pytest -q --cov=uripath --cov-report=term-missing
python -m black src/ tests/ benchmarks/ examples/    # formatting; --check to verify
mkdocs build --strict                                # docs must build with no warnings
python -m build && python -m twine check dist/*      # sdist + wheel into dist/
python tests/mutation/run.py --jobs 4                # every guard's tests must fail on a broken copy
python -m pytest -q tests --http-transports builtin,requests   # the path tests over each transport (needs a transport named `requests` installed)
python -m pytest -q -rs tests/test_public_surface.py -k "mypy_accepts or pyright_accepts"
```

- **The mutation list** (`tests/mutation/`) applies one single-line change to a
  guard of a temporary copy of `src/uripath` and checks that the tests named for
  it fail. Run it on demand, never in CI, after writing or changing a safety
  test; a mutant whose line has moved is `STALE` and fails the run. Its
  `README.md` says how to add one. It ships in the sdist with `tests/`.
- **Tests block non-loopback network access** and starting any program but the
  interpreter (`tests/hermetic.py`, applied in `tests/conftest.py`). Mark a test
  `@pytest.mark.allow_network` only when it must resolve a real name,
  `@pytest.mark.allow_program("tool")` when it runs one. `filterwarnings = error`
  includes `ResourceWarning`: close what a fixture opens.
- A test asserts what the server received, not just that no exception was
  raised, and never asserts how fast something happened or how far an
  operation got.
- **Typing**: the two typing tests run `mypy` and `pyright` (or `basedpyright`)
  on a consumer script and skip where neither is installed; the `typing` job
  installs them.
- **The documents are tested**: the README, the header and the API pages must
  name every public name, the examples run (`tests/test_documented_examples.py`)
  and the header's stubs are compared with the code (`tests/test_shipped_header.py`).

### Benchmarks

`python benchmarks/bench.py --help` lists the options. `--save` writes a JSON
result per (version, interpreter, platform) into `benchmarks/results/`; the
schema and the reproduce command are in
[`benchmarks/README.md`](benchmarks/README.md). A local run is a sanity check;
performance claims in the changelog or release notes come from CI runs
(`test.yml` with `benchmark` set).

### CI

Workflows live in `.github/workflows/`:

- `test.yml` runs on `workflow_dispatch` (inputs: `ref`, `pathapi_ref`,
  `benchmark`) or on a pushed `ci-*` tag, never on ordinary pushes. To test a
  commit without the dashboard, push a uniquely named throwaway tag
  (`ci-<topic>-<timestamp>`), follow the run to completion, then delete the tag
  locally and on the remote. Jobs: `test` (Ubuntu on 3.9 to 3.14, Windows and
  macOS on 3.9 and 3.14), `bare` (the package and `pytest` only, no extra),
  `floors` (every dependency at the lower bound `pyproject.toml` declares, on
  3.9), `typing`, and `benchmark` (manual runs only). Change a range in
  `pyproject.toml` only, and name the API that needs a raised floor in a comment
  beside it.
- `release.yml` runs on a `v*` tag: test, `floors` and `typing` gates, build
  (the tag must name the version built, `twine check`), an installed-wheel smoke
  test with and without the `cli` extra, a strict docs build, then the GitHub
  release whose notes come from that version's `CHANGELOG.md` section. For a
  final tag only (no `-` in it) it then publishes to PyPI through Trusted
  Publishing and dispatches `docs.yml` at the tag.
- `docs.yml` owns every GitHub Pages deploy: on a push to `main` that touches the
  docs sources and on `workflow_dispatch`, which `release.yml` fires for a final
  tag.
- **Which `pathapi` the jobs install.** Every job that installs the package
  first installs `pathapi` from `git+https://github.com/jose-pr/pathapi@<ref>`
  when a ref is given: the `pathapi_ref` input of a manual run of
  `test.yml` or `docs.yml`, else the repository variable `PATHAPI_REF` (the
  only source for a `ci-*` tag and for `release.yml`). With neither, pip takes
  the release range from PyPI. The ref must hold a version inside that range.
  Set the variable while the release is not on PyPI (`gh variable set
  PATHAPI_REF --body <branch-or-sha>`), delete it afterwards (`gh variable
  delete PATHAPI_REF`). `release.yml` refuses a final tag while it is set.

## Conventions

- **Formatting is black**, pinned to `target-version = ["py39"]` so it never
  emits syntax the floor cannot parse. No linter is enforced; the typing tests
  are the type check.
- **Every file is LF** (`.gitattributes` sets `* text=auto eol=lf`). On Windows,
  black writes CRLF: convert the files back to LF after formatting and check
  `git diff --stat` for whitespace-only churn.
- **3.9 compatibility**: any module using `X | Y` in a runtime-evaluated
  annotation needs `from __future__ import annotations`.
- **Comments** say what the code cannot, in one to three lines, about the code
  as it is: no history, and nothing that refers outside this repository.
- **`*.local.*` files** are per-machine overrides: gitignored and excluded from
  both build targets. Keep hostnames and credentials in those, never in tracked
  files.
- Logical commits in `type: description` form (`feat:`, `fix:`, `docs:`,
  `chore:`); keep code with its tests, and docs, config and CI in separate
  commits. No agent attribution in commit messages: no `Co-Authored-By:` naming
  a model or assistant, no `*-Session:` trailers, no session URLs, no
  "generated with" footers.

## Releasing

1. Move the `[Unreleased]` entries under a new `## [x.y.z] - <date>` heading and
   replace the `[Unreleased]` link definition at the bottom of `CHANGELOG.md`
   with one for the new heading and one for `[Unreleased]` (a comparison from
   the new tag).
2. Bump `version` in `pyproject.toml` in the same commit (PEP 440 syntax there;
   SemVer in tags and the changelog).
3. Before 1.0, bump the minor only when the documented API breaks. New methods,
   new optional arguments and fixes are patch releases.
   A fix that corrects behaviour (to `pathlib` parity, to what the
   documentation intends, or to remove a way to lose data) is a patch even
   where an earlier header described the old behaviour; when a caller can
   notice it, its changelog entry goes under `Changed` and says what to do.
4. Run the full suite on the floor and latest interpreters, `mkdocs build
   --strict`, `python -m build`, `twine check`, and the maintainer's leak check
   (a scan for private references and agent-attribution commit trailers). Judge
   it by exit code.
5. Push `main`, then the `v*` tag. Publishing is irreversible, so the tag is
   pushed only with the maintainer's explicit consent for that specific
   release. The release the dependency ranges ask of `pathapi` and `netimps`
   must be on PyPI first, and `PATHAPI_REF` deleted.

Once per repository, before the first release: register PyPI Trusted Publishing
for the project `uripath` (workflow `release.yml`, environment `pypi`); set
Pages to build from GitHub Actions and allow `v*` tags in the `github-pages`
environment (`gh api -X POST repos/jose-pr/uripath/pages -f build_type=workflow`,
`gh api -X POST repos/jose-pr/uripath/environments/github-pages/deployment-branch-policies
-f name='v*' -f type=tag`); and let workflows write (Settings, Actions, General,
Workflow permissions).

Changelog entries say what changed and what a user must do about it. They do
not describe how the work was done.

# uripath — contributor orientation

Orientation for working in a checkout of this repository: layout, environments,
commands, CI and release. It is not the API reference and it does not ship.

| Header | Covers |
| --- | --- |
| [`src/uripath/AGENTS.md`](src/uripath/AGENTS.md) | The public API: `Uri`, `UriPath`, `Source`, `Query` and every built-in scheme, with signatures and gotchas. It ships in the wheel, so it stays self-contained (no repo-relative links) and changes in the same commit as any public API change. |

[`docs/divergences.md`](docs/divergences.md) records every deliberate difference
from `pathlib.Path`. `pathlib.Path` parity is the contract; a behavioral
divergence that is not recorded there is a bug.

## Layout

| Path | Contents |
| --- | --- |
| `src/uripath/` | The package (`src/` layout). `py.typed` and the API header ship with it. |
| `src/uripath/schemes/` | One module or package per URI scheme, registered through the `uripath.schemes` entry points in `pyproject.toml` and the built-in table in `uripath/__init__.py`. |
| `src/uripath/schemes/_elsewhere.py` | The schemes and the HTTP transport that other distributions provide, and the `ImportError` naming what to install. |
| `tests/` | The pytest suite. `tests/conftest.py` holds the loopback servers. |
| `benchmarks/` | `bench.py`; see [`benchmarks/README.md`](benchmarks/README.md). Not shipped. |
| `examples/` | Runnable scripts. Networked ones skip (exit 0) unless their environment variables are set. |
| `docs/`, `mkdocs.yml` | MkDocs site: hand-written pages plus a `mkdocstrings` API reference. |
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

On Windows the interpreter is `.venv\<name>\Scripts\python.exe`.

`pathlib-next` is a dependency. To test against an unreleased core, install it
editable from its checkout first (`pip install -e ../pathlib-next`). Its version
may then sit below the range `pyproject.toml` declares, so install this package
with `--no-deps` and its remaining dependencies by name.

A missing test server does not fail the suite: its tests are skipped instead, so
check `pytest -rs` before trusting a green run.

## Checks

```bash
python -m pytest -q -rs                              # full suite (pythonpath=src is configured)
python -m pytest -q --cov=uripath --cov-report=term-missing
python -m black src/ tests/ benchmarks/ examples/    # formatting; --check to verify
mkdocs build --strict                                # docs must build with no warnings
python -m build                                      # sdist + wheel into dist/
python tests/mutation/run.py --jobs 4                # every guard's tests must fail on a broken copy
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

## Conventions

- **Formatting is black**, pinned to `target-version = ["py39"]` so it never
  emits syntax the floor cannot parse. No linter or type checker is enforced.
- **Every file is LF** (`.gitattributes` sets `* text=auto eol=lf`). On Windows,
  black writes CRLF: convert the files back to LF after formatting and check
  `git diff --stat` for whitespace-only churn.
- **3.9 compatibility**: any module using `X | Y` in a runtime-evaluated
  annotation needs `from __future__ import annotations`.
- **`*.local.*` files** are per-machine overrides: gitignored and excluded from
  both build targets. Keep hostnames and credentials in those, never in tracked
  files.
- Logical commits in `type: description` form (`feat:`, `fix:`, `docs:`,
  `chore:`); keep code with its tests, and docs, config and CI in separate
  commits. No agent attribution in commit messages.

## CI

Workflows live in `.github/workflows/`:

- `test.yml` runs on `workflow_dispatch` (inputs: `ref`, and `pathlib_next_ref`
  to install `pathlib-next` from a git ref of `jose-pr/pathlib-next` instead of
  the release) or on a pushed `ci-*` tag, never on ordinary pushes. To test a
  commit without the dashboard, push a uniquely named throwaway tag
  (`ci-<topic>-<timestamp>`), follow the run to completion, then delete the tag
  locally and on the remote. Its `floors` job installs every dependency at the
  lower bound `pyproject.toml` declares, on Python 3.9. Change a range in
  `pyproject.toml` only, and name the API that needs a raised floor in a comment
  beside it.
- `release.yml` runs on a `v*` tag: test and `floors` gates, build (the tag must
  name the version built, `twine check`), an installed-wheel smoke test, a strict
  docs build, then the GitHub release whose notes come from that version's
  `CHANGELOG.md` section. For a final tag only (no `-` in it) it then publishes
  to PyPI through Trusted Publishing and dispatches `docs.yml` at the tag.
- `docs.yml` owns every GitHub Pages deploy: on a push to `main` that touches the
  docs sources and on `workflow_dispatch`, which `release.yml` fires for a final
  tag.

## Releasing

1. Move the `[Unreleased]` entries under a new `## [x.y.z] - <date>` heading and
   add its link definition at the bottom of `CHANGELOG.md`.
2. Bump `version` in `pyproject.toml` in the same commit (PEP 440 syntax there;
   SemVer in tags and the changelog).
3. Before 1.0, bump the minor only when the documented API breaks. New methods,
   new optional arguments and fixes are patch releases.
4. Run the full suite on the floor and latest interpreters, `mkdocs build
   --strict`, `python -m build`, and the maintainer's leak check (a scan for
   private references and agent-attribution commit trailers). Judge it by exit
   code.
5. Push `main`, then the `v*` tag. Publishing is irreversible, so the tag is
   pushed only with the maintainer's explicit consent for that specific
   release.

Changelog entries say what changed and what a user must do about it. They do
not describe how the work was done.

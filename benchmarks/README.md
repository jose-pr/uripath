# Benchmarks

`bench.py` times `uripath` hot paths: URI parsing and composing, path joins and
name access, and HTTP directory traversal and listing parsing. Method notes are
on the docs site's Benchmarks page
([`docs/benchmarks.md`](../docs/benchmarks.md)).

Nothing here contacts an external host: the HTTP cases start an in-process
loopback server.

## Reproduce

From the repository root, in a virtualenv with the test servers installed:

```bash
python -m pip install -e ".[dev]"
python benchmarks/bench.py --save
```

That runs the benchmarks and writes
`benchmarks/results/<version>-py<major.minor>-<os>-<arch>.json`:

```bash
python benchmarks/bench.py --help
python benchmarks/bench.py --save --samples 9
python benchmarks/bench.py --save --name my-run
```

| Option | Effect |
| --- | --- |
| `--save` | Write the run to `benchmarks/results/<name>.json`. |
| `--name NAME` | File name without `.json`. Default `<version>-py<major.minor>-<os>-<arch>`. |
| `--results-dir DIR` | Write somewhere other than `benchmarks/results/`. |
| `--samples N` | Samples per metric for every case (1-100). Default: each case's own count, 1-5. |
| `--note TEXT` | Free text stored in the JSON. |

## Comparing runs

Compare on the **median**: one sample's time hides run-to-run noise. Only
compare runs from the same machine and interpreter, and change one thing at a
time. The `python`, `interpreter` and `processor` fields say what a file was
measured on.

A run on a developer machine is a sanity check. Performance claims in the
changelog or release notes come from CI runs.

## Result schema (`uripath.bench/1`)

One JSON object per run:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | string | `"uripath.bench/1"`. |
| `name` | string | The file name without `.json`. |
| `suite` | string | `"default"`. |
| `source` | string | `"ci"` when run under GitHub Actions, else `"local"`. |
| `note` | string or null | `--note` text. |
| `created_utc` | string | ISO 8601 UTC timestamp of the save. |
| `package` | object | `{"name": "uripath", "version": <pyproject version>}`. |
| `git` | object or null | `{"commit": <HEAD sha>, "dirty": <tracked files modified>}`; null outside a git checkout. |
| `python` | string | Implementation and version, e.g. `"CPython 3.14.6"`. |
| `interpreter` | string | `<major.minor>-<os>-<arch>`, where `<os>` is `os.name` (`nt`/`posix`) or `darwin` and `<arch>` is the architecture the interpreter was built for (`sysconfig.get_platform()`). |
| `processor` | string | `<platform.system()>-<platform.machine()>` of the host. |
| `cpu_count` | integer | `os.cpu_count()`. |
| `metrics` | object | Timing metrics, keyed by metric name (below). |
| `counters` | object | Call-count probes, keyed by name: `{"group": ..., <call name>: <count>, ...}`. |
| `errors` | object | Cases that raised: `{"group": ..., "error": "<Type>: <message>"}`. |
| `skipped` | object | Cases that could not run: `{"group": ..., "reason": ...}`. |

Each entry in `metrics`:

| Field | Type | Meaning |
| --- | --- | --- |
| `group` | string | `uri` or `http`. |
| `min_ms` | number | Fastest sample, in milliseconds per call. |
| `median_ms` | number | Median sample, in milliseconds per call. Compare on this. |
| `max_ms` | number | Slowest sample, in milliseconds per call. |
| `samples` | integer | Samples taken (N). |
| `calls_per_sample` | integer | Calls of the operation timed in each sample; each sample's time is divided by this. |

Metric names are `<group>: <case>`, e.g. `"uri: path join"`.

## Committed results

`results/` is tracked, so before/after numbers stay recoverable from history.

| File | What it is |
| --- | --- |
| `baseline-local-<version>-py<interpreter>.json` | Local sanity baseline of the default suite on a developer machine. Not CI; not a performance claim. |
| `ci-<os>-py3.14.json` | The `benchmark` job of the test workflow on a hosted runner, replaced at each release; earlier ones are in the file's history. |

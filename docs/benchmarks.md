# Benchmarks

`uripath` includes a benchmark harness at `benchmarks/bench.py` for checking
hot-path behavior of the URI layer and the HTTP schemes. It needs the test
servers: `pip install -e ".[dev]"`.

## Run It

```bash
python benchmarks/bench.py            # run the benchmarks
python benchmarks/bench.py --help     # options; runs nothing
```

## Saved Results

Every metric is timed over several samples. `--save` writes the run as JSON to
`benchmarks/results/<name>.json`, with the minimum, median and maximum
milliseconds per call of each metric plus the interpreter, platform and git
commit it ran on:

```bash
python benchmarks/bench.py --save
python benchmarks/bench.py --save --samples 9
```

`--samples N` applies one sample count to every case; without it each case uses
its own (1-5). The result schema and the committed results are described in
[`benchmarks/README.md`](https://github.com/jose-pr/uripath/blob/main/benchmarks/README.md).

Compare two runs on their medians, and only between runs from the same machine
and interpreter. A run on a developer machine is a sanity check; performance
claims in release notes come from CI runs.

## What It Covers

- URI parse and compose cost, for repeated and for unique URIs
- generic path joins and name/suffix access
- HTTP directory traversal on the built-in transport and the parser throughput
  on Apache `<pre>` and nginx `<table>` indexes

The HTTP cases run against an in-process loopback server, so nothing leaves the
machine.

## Caveats

Timings depend on the machine, the interpreter and what else is running; compare
medians, as described above.

# `uripath` CLI

`uripath` installs a `uripath` command for basic operations on local paths
and URI-backed paths.

```bash
uripath read https://example.com/path/file.txt
uripath write output.txt "hello"
uripath cp input.txt ftp://host/tmp/input.txt
uripath rm --recursive ftp://host/tmp/work
uripath sync --remove-missing source/ target/
```

Use `-` for stdin or stdout wherever a command reads or writes bytes:

```bash
uripath read path.txt > copy.txt
cat notes.txt | uripath write path.txt
uripath cp - ftp://host/stdin.bin < local.bin
uripath cp ftp://host/stdout.bin - > local.bin
```

## Commands

| Command | Behavior |
| --- | --- |
| `read PATH` | Writes `PATH`'s bytes to stdout, in chunks. `PATH` may be `-` (stdin). |
| `write PATH [DATA] [--encoding ENC]` | Writes `DATA` encoded with `ENC` (default `utf-8`), or stdin's bytes when `DATA` is omitted. Replaces an existing file. |
| `rm PATH [-r/--recursive] [--missing-ok] [--ignore-error]` | Removes a file or an empty directory; `-r` removes a tree. `--missing-ok` accepts a missing path; `--ignore-error` skips failures during the removal. |
| `cp SOURCE TARGET [-r/--recursive] [--overwrite] [--no-follow-symlinks] [--no-preserve-metadata]` | Copies a file, or a tree with `-r`. An existing target is refused without `--overwrite`, also when either side is `-` (which cannot be combined with `-r`). `--no-follow-symlinks` copies a link as a link. |
| `sync SOURCE TARGET [--dry-run] [--remove-missing] [--size-only] [-v/--verbose] [--no-follow-symlinks] [--no-follow-mounts]` | One-way sync with `PathSyncer`, comparing file content (a backend-native digest or a streamed md5), so same-size edits are copied. `--size-only` compares sizes only and misses same-size edits. `--remove-missing` deletes target entries that are not in the source. `--dry-run` prints each planned change without changing anything, and fails where the real run would (a symlink onto a target that cannot hold links); `-v` prints each change a real run makes. `--no-follow-symlinks` recreates source symlinks instead of following them. `--no-follow-mounts` makes a mount point inside TARGET (a mounted volume, a bind mount) an error, `OSError(EXDEV)` and exit status 1, instead of syncing into it; the default syncs into it, as `rsync` does. |

`sync --dry-run` and `sync -v` print one line per change:

```text
would mkdir dst
would copy src/a.txt -> dst/a.txt
would remove dst/old.txt
```

The other actions are `replace` (a target entry of another type is replaced)
and `symlink`.

## Paths

An argument containing `://`, or starting with a scheme that a class
registers (`data:`, `zip:`, `file:`, ...), is a `UriPath`; anything else is a
local path, so `C:/data`, `12:30.txt` and `notes:draft` stay local.

## Exit status

| Status | Meaning |
| --- | --- |
| 0 | success (also `--help`) |
| 1 | the operation failed: one line `uripath: <ExceptionType>: <message>` on stderr |
| 2 | a wrong invocation: the usage on stderr (a missing or unknown argument, `cp -r` with `-`, an unknown `--encoding`) |
| 130 | interrupted with Ctrl-C |
| 141 | the reader of stdout went away (`uripath read big.bin \| head`), quietly, on Windows too |

## From Python

`uripath._oldcli.main(argv=None, *, stdin=None, stdout=None,
stderr=None)` runs one command and returns its exit status; it never raises
`SystemExit`. `stdin` and `stdout` are binary streams and `stderr` a text or a
binary stream; the usage and help text go to the process's own stderr and
stdout.

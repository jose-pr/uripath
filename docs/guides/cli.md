# `uripath` command

`uripath` reads, writes, copies, removes and syncs local paths and URIs. It is
built on [`duho`](https://pypi.org/project/duho/), which the `cli` extra
installs:

<!-- example: skip: installs the package -->
```bash
pip install "uripath[cli]"
```

Without the extra the `uripath` script (and `python -m uripath`) prints that
line to stderr and exits with status 1.

These commands run as written in an empty directory:

```bash
mkdir work
uripath write work/note.txt "hello"
uripath read work/note.txt
uripath cp work/note.txt work/copy.txt
uripath sync --dry-run --remove-missing work work-backup
uripath sync work work-backup
uripath rm --recursive work-backup
```

Either side can be a URI:

<!-- example: skip: needs an FTP host -->
```bash
uripath cp input.txt ftp://host/tmp/input.txt
uripath rm --recursive ftp://host/tmp/work
uripath sync --remove-missing source/ ftp://host/target/
```

Use `-` for stdin or stdout wherever a command reads or writes bytes:

```bash
mkdir work
uripath write work/note.txt "hello"
uripath read work/note.txt > work/copy.txt
uripath write work/in.txt < work/note.txt
uripath cp - work/stdin.bin < work/note.txt
uripath cp work/note.txt - > work/stdout.bin
```

## Commands

| Command | Behavior |
| --- | --- |
| `read PATH` | Writes `PATH`'s bytes to stdout, in chunks. `PATH` may be `-` (stdin). |
| `write PATH [DATA] [--encoding ENC]` | Writes `DATA` encoded with `ENC` (default `utf-8`), or stdin's bytes when `DATA` is omitted. Replaces an existing file. `PATH` may be `-` (stdout). |
| `rm PATH [-r/--recursive] [--missing-ok] [--ignore-error]` | Removes a file or an empty directory; `-r` removes a tree. `--missing-ok` accepts a missing path; `--ignore-error` skips failures during the removal. |
| `cp SOURCE TARGET [-r/--recursive] [--overwrite] [--no-follow-symlinks] [--no-preserve-metadata]` | Copies a file, or a tree with `-r`. An existing target is refused without `--overwrite`, also when either side is `-` (which cannot be combined with `-r`). `--no-follow-symlinks` copies a link as a link; `--no-preserve-metadata` leaves out modes and times. |
| `sync SOURCE TARGET [--dry-run] [--remove-missing] [--size-only] [--no-follow-symlinks] [--no-follow-mounts]` | One-way sync with `PathSyncer`, comparing file content (a backend-native digest or a streamed md5), so same-size edits are copied. `--size-only` compares sizes only and misses same-size edits. `--remove-missing` deletes target entries that are not in the source. `--dry-run` prints each planned change without changing anything, and fails where the real run fails (a symlink onto a target that cannot hold links). `--no-follow-symlinks` recreates source symlinks instead of following them. `--no-follow-mounts` makes a mount point inside TARGET (a mounted volume, a bind mount) an error, `OSError(EXDEV)` and exit status 1, instead of syncing into it; the default syncs into it, as `rsync` does. |

Every command also takes `-v`, `-q` and `--loglevel`, which set how much the
`uripath` logger says on stderr. `sync` lists each change a real run makes, one
line each, while `-v` is given more often than `-q`.

A boolean option that is on by default has both spellings:
`--follow-symlinks` and `--no-follow-symlinks`, `--preserve-metadata` and
`--no-preserve-metadata`, `--follow-mounts` and `--no-follow-mounts`.

`sync --dry-run` and `sync -v` print one line per change:

```text
would mkdir dst
would copy src/a.txt -> dst/a.txt
would remove dst/old.txt
```

The other actions are `replace` (a target entry of another type is replaced)
and `symlink`.

Nothing is deleted or replaced unless it is asked for by name: `rm` refuses a
directory with content without `--recursive`, `sync` keeps what the source
lacks without `--remove-missing`, `cp` refuses an existing target without
`--overwrite`. The same holds when the command is served as a tool.

## Paths

An argument containing `://`, or starting with a scheme that a class
registers (`data:`, `zip:`, `file:`, ...), is a `URIPath`; anything else is a
local path, so `C:/data`, `12:30.txt` and `notes:draft` stay local. That is
what `uripath.as_path()` does. A path that starts with `-` is written
`./-name`: `--` ends the options and takes no argument after it.

## Exit status

| Status | Meaning |
| --- | --- |
| 0 | success (also `--help` and `--version`) |
| 1 | the operation failed: one line `uripath: <ExceptionType>: <message>` on stderr; also the `cli` extra not being installed |
| 2 | a wrong invocation: the usage or the problem on stderr (a missing or unknown argument, `cp -r` with `-`, an unknown `--encoding`) |
| 130 | interrupted with Ctrl-C |
| 141 | the reader of stdout went away (`uripath read big.bin \| head`), quietly, on Windows too |

Results go to stdout and diagnostics to stderr. No message carries a password
or a token.

## For agents

The command line describes itself and can be served as tools, with no code of
its own for either (see the `duho` documentation):

- `AGENT_HELP=1 uripath --help` prints one JSON document for every command.
- `URIPATH_MCP=stdio uripath` serves `read`, `write`, `rm`, `cp` and `sync` as
  MCP tools whose schemas come from the fields. A tool call has no standard
  input: `-` as a source, and `write` without `DATA`, fail with a message.

## From Python

`uripath.cli.main(argv=None)` runs one command and returns its exit status;
it needs the `cli` extra and does not exit the process. The commands call the
library: `uripath.as_path()` turns an argument into a path,
`uripath.copy_stream()` copies between a path and a stream, and `Path.copy()`,
`Path.rm()` and `PathSyncer` do the rest. Nothing the command does is reachable
only from it.

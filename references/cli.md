# CLI reference

Run `python3 "<skill>/scripts/ring.py" COMMAND`. Requires Python 3.9+ and SQLite.
All commands accept `--root PATH`, `--json` and `--commit` before or after the command.
Without a command, the CLI prints `status`.

## Common operations

```bash
ring.py init
ring.py remember "Uses pnpm"                     # ring1 by default
ring.py remember "Deployed version 2" --ring 2 --tags release
ring.py remember "Check migration" --ring 3
ring.py recall "pnpm package manager" --limit 3
ring.py recall "배포" --ring 2
ring.py list --ring 1
ring.py list --all                               # includes archive
ring.py status
ring.py snapshot --query "package manager"       # full kernel + relevant context
ring.py promote 12 --to 1
ring.py demote 12
ring.py forget 12                                # archive, not physical deletion
ring.py dream --dry-run
ring.py dream
```

These examples omit `python3` and the full script path for readability.
`remember --content TEXT`, `recall --query TEXT`, and `approve --id ID` remain valid.
IDs must be positive; unknown/archived IDs produce an error rather than a false success.
Identical active content in the same ring returns its existing ID without changing tags.
Use `list --all` to inspect archived content; there is no automatic archive expiry.

Recall treats input as plain text, not FTS query syntax. Terms are OR-matched, results
matching more terms rank first, then FTS relevance, salience and recency. Tags are
searchable. No-match output is explicit. `--json` returns an array of matching records
(an empty array for no match), or an object for status/change operations. Failures
exit nonzero and print an error to stderr; with `--json`, errors are JSON objects.

## Kernel proposals

```bash
ring.py propose "Agent name is Ring"
ring.py proposals
ring.py approve 1                                # only with explicit user approval
ring.py propose "Agent name is Ringo" --replace 7 # 7 is a MEMORY id
ring.py propose --remove 7
ring.py reject 2                                 # 2 is a PROPOSAL id
ring.py proposals --all
```

Proposal IDs and memory IDs are different sequences. Always use the returned ID.
Replacement/removal archives the old record only when approved. Direct writes,
moves and maintenance cannot alter ring0. The cap counts active content characters,
not Markdown decoration. The agent checks the user's approval; this local CLI is
not an authentication boundary against someone who can directly edit its database.

## Paths

1. `--root PATH` selects the project explicitly.
2. Otherwise `RING_ROOT` selects it.
3. Legacy `RING_DB` selects a custom SQLite file; exports go to that file's directory
   (or the parent project if the file is in `.agent`). With an explicit root, relative
   `RING_DB` paths resolve against that root and exports stay under that root.
4. Otherwise walk from the working directory upward, using the first `.agent/rings.db`
   or `.git` found. This supports nested packages and worktrees (`.git` may be a file).
5. Outside a project, use the working directory.

A global skill installation does not mean a global memory store. To share memory
deliberately, use the same `--root` (or `RING_ROOT`) directory across projects.

## Exports, Git and restore

SQLite is the source of truth. Content writes export every active and archived
record, with IDs, as Markdown and a full JSON backup. No `LIMIT 20/50` truncation is
used for exports or kernel context. Recall counters are persisted in SQLite; run
`export` before copying a backup to include the latest counters.

```bash
ring.py export
ring.py export --commit
ring.py --root /new/project restore /old/project/.agent/memory/state.json
```

`--commit` force-adds only the generated Markdown/JSON files and commits only those
paths, leaving unrelated staged changes alone. It never pushes. Git errors are
reported; the SQLite write remains saved even if export or commit fails. Retry
`export --commit` after correcting the cause. Ordinary commands work without Git.

Restore requires an empty database, checks the backup version and kernel cap, and
rolls back inserts on malformed input. Back up the original store before migrating
projects. Editing Markdown is not a supported write path. `state.json` is a snapshot,
not a multi-writer synchronization protocol.

## Maintenance and compatibility

`dream` archives exact duplicates within a ring (except ring0), promotes ring2 entries
with three recalls, and demotes ring1 entries unused for 90 days. A cold demotion resets
the recall counter so old accesses cannot immediately promote it again. Non-pinned
ring2 salience decreases by 10% for each elapsed 30-day period, counted once.
`pin` is a whole tag separated by spaces or commas (`shopping` is not pinned).

Dry runs roll back all memory, event and ranking changes and do not export or commit.
The command does not synthesize session summaries: the agent writes those as ring2.
The original `python3 scripts/dream.py` command is an alias for `ring.py dream`.

Original DBs are upgraded additively on first open. Old proposal IDs, memory IDs and
FTS data are retained. FTS5 is used when available; otherwise new stores use keyword
matching without installing extra packages. Vector search is not implemented.

# Project-local automatic memory

OpenCode V2 (tested against 2.0.16) can run Ring0 automatically. OpenChamber uses the
same OpenCode runtime. Enable it only in the project that should collect memories:

```bash
python3 /path/to/Ring0/scripts/install.py --project /path/to/project --auto
```

Add `--force` when updating existing Ring0 files. The installer installs a local
plugin at `.opencode/plugins/ring-memory/` and the skill at
`.opencode/skills/ring-memory/`. The plugin has no npm dependencies. OpenCode V2
discovers the local plugin when loading the project; watched plugin changes reload
automatically. The `opencode` CLI and Python 3.9+ must be available on the server PATH.

## Scope and storage

The installation directory is the memory boundary. Both the event adapter and Python
bridge check canonical session paths. Siblings, symlink escapes, and nested Git
projects are excluded. A globally configured `RING_DB` or `RING_ROOT` cannot redirect
automatic memory. `--global --auto` is rejected; each project opts in independently.

Sessions moved across project boundaries are excluded rather than importing their
old project history into the destination. Start a fresh session in the destination.
Moves between subdirectories of the same project are allowed. Backfill examines
location-switch records, not only a session's current directory.

```text
<project>/.agent/
├── rings.db       # curated ring0–3 and memory operation history
├── history.db     # projected messages, source IDs, processing checkpoints and leases
└── memory/        # Markdown and JSON exports of curated memory
```

The archive retains the full message JSON returned by OpenCode's API: user text,
assistant replies, tool inputs/results, shell records, attachments' metadata and
compaction summaries. This is an archive of API-provided messages; it does not
download referenced attachment binaries or expand output already truncated by the
host. A message's latest projection replaces its earlier streaming version by ID.

`state.json` backs up **curated memory**, not the conversation archive. Preserve both
SQLite files to keep raw records and automatic-processing state. Automatic capture
does not commit/push these files. Existing memory export/restore commands remain usable.

## Runtime flow

- **On load / reconnect:** import this directory's existing sessions through the
  authenticated `opencode api` CLI. Follow session and message pagination. Every
  minute, check for missed/changed sessions; unchanged sessions skip full reads.
  Large CLI responses use a project-local temporary file descriptor to avoid
  truncated pipe output in OpenCode 2.0.16; that file is immediately removed.
- **Before a model call:** capture persisted context, select all ring0 plus relevant
  ring1/ring2 and a few matching records from older sessions, and append one system
  text part. Tool-call/result pairs and the persisted conversation are not rewritten.
- **On tool/step completion:** queue a debounced capture. Event-stream readers never
  wait for model summarization. Before compaction, capture the current context too.
- **On turn completion/interruption:** process new completed records in bounded
  batches. A stateless model call creates a ring2 summary. Ring1 facts require an exact
  supporting quote from a user message in the batch. Assistant assertions alone do
  not become durable facts. Automatic processing cannot write or approve ring0.

Each batch has a stable fingerprint and a 3-minute lease. Interrupted batches become
eligible again; applying a batch twice does not create duplicate memory. Updates to
source text invalidate an in-flight summary. An extraction failure keeps the source
records pending for a later attempt. Multiple plugin instances share these checkpoints.

Recall counts advance once per user message, not once per tool continuation.
Summarizer input is capped at 16,000 text characters per batch; individual excerpts
are capped at 4,000. Full API records remain in the archive. Summaries use the session
model, falling back to OpenCode's configured default model.

Providers requiring session-bound routing (such as OpenCode Go) use the documented
transient `session.generate` fallback. It adds no messages or sessions, but also sees
the source session's current context, so its total input can exceed the batch excerpt
budget. Other generation errors leave the batch pending instead of creating a fallback
session or changing the user's model.

## Project settings

The installer creates `.opencode/ring-memory.json` if it does not exist and preserves
existing settings even during `--force` upgrades:

```json
{
  "enabled": true,
  "summarize": true,
  "backfill": true,
  "contextChars": 6000
}
```

`enabled: false` suspends collection, summarization and injection. `summarize: false`
keeps collection and retrieval without extra model calls. `backfill: false` disables
project-wide historical import/reconciliation; the live session still checks its
scope and captures new context. Settings are read during processing, so edits apply
without changing your main OpenCode configuration. Kernel content is always included
in full; `contextChars` budgets the remaining recalled context (minimum 2,500).

## Inspect and recover

```bash
python3 /path/to/skill/scripts/automatic.py --root /path/to/project status
python3 /path/to/skill/scripts/automatic.py --root /path/to/project sync
```

`status` reports archived sessions/messages, pending summary records, last full sync,
and the last error. `sync` performs an immediate project-local archive import. It
does not call a model; the running plugin processes the resulting backlog.

Hook failures are recorded and logged with `[ring-memory]`; the user's model request
can continue. Inspect the reported error, correct the cause, then use `sync` or let
the next reconciliation retry. An interrupted OpenCode tool call is handled by
OpenCode; this plugin does not edit or repair provider tool-call histories.

## Other hosts / manual mode

Without `--auto`, the skill and slash commands run on demand. For another agent host,
wire its own persisted-message events to capture, its request-context hook to snapshot,
and its idle callback to summary/consolidation. Merely running a cron job cannot put
memory into a model's context. Use the host's documented API rather than assuming
OpenCode's plugin interface is portable.

Official API reference: [OpenCode V2 plugins](https://opencode.ai/v2/docs/build/plugins).

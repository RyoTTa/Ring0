# Ring0 — Memory in plain language, managed by a skill

A memory skill that helps coding agents carry preferences, project decisions, and
recent work into future sessions. The core CLI requires only Python 3.9+.
Automatic mode uses OpenCode V2, with `python3` and `opencode` available on the
server's PATH. Summaries are generated using a model connected to OpenCode.
No separate memory server or pip installation is required.

```text
You: This project uses pnpm. Remember that.
Agent: Remembered: this project uses pnpm. (#1)

You: Which package manager did we decide to use?
Agent: The saved decision is pnpm. (#1)
```

## Automatic setup per project — OpenCode V2 / OpenChamber

Replace `/path/to/project` with the **absolute path of the project whose memories
you want to store**. Tested with OpenCode v2.0.16.

```bash
git clone https://github.com/RyoTTa/Ring0.git
python3 Ring0/scripts/install.py --project /path/to/project --auto
```

Open that project in OpenCode/OpenChamber to start conversation capture,
summarization, and memory injection. Automation and storage are **isolated per
installed project**. Check collection status with:

```bash
python3 /path/to/project/.opencode/skills/ring-memory/scripts/automatic.py --root /path/to/project status
```

If existing files differ, the installer stops before overwriting them. Review the
changed files and use `--force` when upgrading. Use `--dry-run` to preview the
installation paths.

If an agent handles installation, ask it to read this README, install into your
project, then verify that the `ring-memory.project` plugin is `active` and that
`status` shows captured records. Initial import and summarization run sequentially
when there is a large conversation history.

For the on-demand skill, omit `--auto`. To make the on-demand skill available in
all projects, use `python3 Ring0/scripts/install.py --global`.
For other agents, copy this folder into the host's skills directory as
`ring-memory`. The skill is named `ring-memory`; the project is named Ring0.

## Usage

Use natural-language requests or OpenCode commands.

| Request | Command |
| --- | --- |
| “Remember that I prefer short answers.” | `/remember I prefer short answers` |
| “Find our previous deployment decision.” | `/recall deployment` |
| “Show my saved memory status.” | `/rings` |
| “Clean up old memories.” | `/dream` |
| “Forget that preference.” | The agent finds and archives the entry |

Ordinary save requests go into ring1. You do not need to choose a ring number.
Search uses keywords and prefixes, including Korean text. Synonym matching and
cross-language semantic search are not supported; the agent searches with relevant
keywords.

## Project-local automatic memory (OpenCode V2)

To remember this project's conversations, replies, and tool execution records
without asking for each one to be saved:

```bash
python3 Ring0/scripts/install.py --project /path/to/project --auto
```

Add `--force` to upgrade an existing installation. The plugin runs automatically
when the project is opened in OpenCode/OpenChamber. It does not affect other
projects, and automatic mode cannot be combined with `--global`.

1. Import existing project sessions through all pages, then capture new conversations and tool results.
2. Before each model call, add all of ring0 plus relevant memories and historical records to the context.
3. After a response completes, summarize new records into ring2 and save facts supported by user statements into ring1.
4. Resume from saved processing checkpoints after a restart, without storing duplicate records.

Summarization uses the session's model and incurs additional model calls. To keep
capture, retrieval, and injection without those extra calls, set `summarize` to
`false` in the project's `.opencode/ring-memory.json`. Set `enabled: false` to
stop automatic processing.

Captured records are stored in `.agent/history.db`; curated memories are stored
in `.agent/rings.db`. Only sessions within the **installed project's path** are
processed. Nested folders with their own Git repositories are treated as separate
projects. See the [automatic integration guide](references/hooks.md) for settings
and status checks.

## The four rings

| Ring | Purpose | Rules |
| --- | --- | --- |
| **0 — kernel** | Core identity and persistent constraints | Requires user approval; 2,000 characters total; included in full in snapshots |
| **1 — long-term** | Preferences, project facts, and decisions | Default destination for ordinary memories; retrieved through search |
| **2 — episodic** | Recent outcomes and session summaries | Promoted after 3 recalls; salience decays in 30-day intervals |
| **3 — scratch** | Temporary working notes | Saved as needed and explicitly archived when the work is done |

`dream` archives duplicates, promotes frequently recalled ring2 entries to ring1,
and demotes ring1 entries unused for 90 days to ring2. The `pin` tag prevents
time-based decay and demotion. Repeated runs do not apply decay twice for the same
period. Ring0 is excluded from automatic consolidation.
Content is not physically deleted; archived entries are excluded from normal search.

## Use the CLI directly

You can run the CLI from the repository without installing the skill.

```bash
python3 scripts/ring.py remember "I prefer short answers" --tags preference
python3 scripts/ring.py recall "answers"
python3 scripts/ring.py list
python3 scripts/ring.py snapshot --query "answers"
python3 scripts/ring.py dream --dry-run
```

Use `--root /path/to/project` to select the storage location. If omitted, Ring0
looks for the nearest existing memory store or Git root, falling back to the
current directory. The installed script's location does not determine where
memories are stored.

To change ring0:

```bash
python3 scripts/ring.py propose "The agent's name is Ring"
python3 scripts/ring.py proposals
# Only after the user approves that proposal:
python3 scripts/ring.py approve 1
```

The legacy `--content`, `--query`, and `--id` syntax and `scripts/dream.py` remain
supported. Existing SQLite databases are upgraded on first use by adding the
required columns without deleting data.

## Storage and backups

```text
<project>/.agent/
├── rings.db                  # Source of truth: memories, proposals, and event history
└── memory/
    ├── ring0.md … ring3.md    # All active memories, with no entry-count limit
    ├── archive.md            # Archived content
    └── state.json            # Restorable backup, including metadata, proposals, and history
```

Changes to memory content trigger an export. **SQLite is the source of truth**;
Markdown files are for reading. Run `export` to include the latest recall counts
in your backup.

```bash
python3 scripts/ring.py export --commit
python3 scripts/ring.py --root /path/to/empty-project restore /path/to/state.json
```

Git commits happen only when you pass `--commit`. Memory export files are explicitly
added even if ignored, and unrelated staged files are excluded from the commit.
The database itself is not added to Git. Restore works only with an empty store.
Concurrent database merging across devices is not supported.

An installation without `--auto` runs on demand. Automatic mode is specific to
OpenCode V2; other hosts require integration with their own event and context hooks.

## Development

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_automatic.mjs
```

Tests use temporary directories inside the repository and remove them on completion.
See the [CLI reference](references/cli.md) for the full command list, storage paths,
and restore instructions.

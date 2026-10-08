# Ring0 — project memory that survives new sessions

**🇬🇧 English** · [🇰🇷 한국어](README.ko.md)

Your coding agent forgets everything between sessions. Ring0 fixes that: preferences,
project decisions, and recent work, stored per project and recalled automatically.

## Install

Copy/paste into your agent prompt:

```
Install the ring-memory skill from https://github.com/RyoTTa/Ring0, refer to the repo's AGENTS.md for instructions.
```

Or 🔗 check the [installation instructions](INSTALL.md) for OpenCode, Claude Code, and Codex.

## What it does

Say it once, and every future session remembers.

```text
You: This project uses pnpm. Remember that.
Agent: Remembered: this project uses pnpm. (#1)

(next session)
You: Which package manager did we decide to use?
Agent: The saved decision is pnpm. (#1)
```

## What changes

| Before | After |
| --- | --- |
| Every session starts from zero. You re-explain the stack, the conventions, the decisions you already made. | The agent opens with your project's goal, current decisions, and next actions already loaded. |
| "Did we decide pnpm or npm?" gets a guess. | It gets the saved decision, with its ID and history. |

## The rings

4 tiers, newest sessions keep working notes, durable facts live long. Full text in [SKILL.md](SKILL.md).

1. **ring0 — kernel.** Core identity and constraints. Needs your approval; capped at 2,000 chars; always loaded in full.
2. **ring1 — long-term.** Preferences, facts, decisions. The default save destination, found by keyword search.
3. **ring2 — episodic.** Session summaries and recent outcomes. Fades over 30-day periods unless pinned.
4. **ring3 — scratch.** Temporary notes, archived when the work is done.

Nothing is ever deleted, only archived with its history. Outdated decisions are
linked to their replacements with `supersede`, never silently overwritten.

## Hosts

| Host | Mode | Command |
| --- | --- | --- |
| OpenCode V2 | Automatic capture + recall (per project) | `install.py --project PATH --auto` |
| OpenCode | On-demand skill | `install.py --project PATH` or `--global` |
| Claude Code | On-demand skill | `install.py --host claude --project PATH` or `--global` |
| Codex | On-demand skill | `install.py --host codex --project PATH` or `--global` |

Only Python 3.9+ is required. No pip packages, no memory server. Storage is
SQLite inside your project (`.agent/`), isolated per project.

## Tune it

Fork, edit `SKILL.md` and the ring policy, then reinstall with `--force`.
`AGENTS.md` has the agent install checklist, `INSTALL.md` the per-host details.

## License

MIT. Star ⭐ if a future session ever surprised you by remembering.

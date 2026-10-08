# Install, update, remove

Needs only Python 3.9+ and `git`. No pip packages. Replace `/path/to/project`
with the absolute path of the project whose memories you want to store.

```bash
git clone https://github.com/RyoTTa/Ring0.git
```

Easiest path: paste this into your agent and let it do the rest
(full checklist in `AGENTS.md`):

```
Install the ring-memory skill from https://github.com/RyoTTa/Ring0, refer to the repo's AGENTS.md for instructions.
```

## OpenCode V2 — automatic (recommended)

Conversation capture, memory injection before each model call, and turn-end
summarization. Tested with OpenCode v2.0.16. OpenChamber uses the same runtime.

```bash
python3 Ring0/scripts/install.py --project /path/to/project --auto
```

What it does: skill to `<project>/.opencode/skills/ring-memory`, live plugin to
`<project>/.opencode/plugins/ring-memory`, slash commands to
`<project>/.opencode/commands`, settings to `<project>/.opencode/ring-memory.json`
if absent. Storage is `<project>/.agent/rings.db` (curated) plus
`<project>/.agent/history.db` (raw archive). Each project opts in separately;
`--auto` cannot be combined with `--global`.

Check it:

```bash
python3 /path/to/project/.opencode/skills/ring-memory/scripts/automatic.py --root /path/to/project status
```

## OpenCode — on-demand

No plugin, no background capture. Natural-language requests plus
`/remember`, `/recall`, `/rings`, `/dream`.

```bash
python3 Ring0/scripts/install.py --project /path/to/project   # this project
python3 Ring0/scripts/install.py --global                      # every project
```

## Claude Code — on-demand

Skill to project `.claude/skills/ring-memory` (commit it to share with the team)
or personal `~/.claude/skills/ring-memory` (every project on this machine).
Slash-command templates go to the matching `commands/` directory.
Talk to the agent in natural language; it runs the bundled CLI with
`--root` pointed at your project.

```bash
python3 Ring0/scripts/install.py --host claude --project /path/to/project   # this project
python3 Ring0/scripts/install.py --host claude --global                      # every project
```

## Codex — on-demand

Skill to project `.codex/skills/ring-memory` or personal `~/.codex/skills/ring-memory`.
Same deal as Claude Code: natural-language requests, project-scoped storage.

```bash
python3 Ring0/scripts/install.py --host codex --project /path/to/project   # this project
python3 Ring0/scripts/install.py --host codex --global                      # every project
```

## Update, preview, remove

```bash
python3 Ring0/scripts/install.py --project /path/to/project --auto --dry-run  # preview
python3 Ring0/scripts/install.py --project /path/to/project --auto --force    # upgrade
```

Add `--host claude|codex` for those hosts. Settings are preserved on `--force`.
If files differ, the installer stops before overwriting; review them first.

```bash
rm -rf /path/to/project/.opencode/plugins/ring-memory   # auto plugin
rm -rf /path/to/project/.opencode/skills/ring-memory     # skill (or .claude / .codex)
```

Keep `.agent/` if history matters, delete it to forget everything.

## Verify

Minimum: run the isolated temp-project round-trip
(save → recall → supersede → state). For OpenCode `--auto`, also confirm the
`ring-memory.project` plugin is `active` and `automatic.py status` shows records.
Full steps are in `AGENTS.md` section 3.

## Other hosts

Copy the repo folder into the host's skills directory as `ring-memory` and point
the CLI at your project with `--root`. Automatic per-turn injection needs the
host's own event hooks; see `references/hooks.md`. A cron job alone cannot put
memory into a model's context.

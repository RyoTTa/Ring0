# Install, update, remove

## OpenCode V2 project auto memory (recommended)

```bash
git clone https://github.com/RyoTTa/Ring0.git
python3 Ring0/scripts/install.py --project /path/to/project --auto
```

What it does: copies skill to `<project>/.opencode/skills/ring-memory`,
live plugin to `<project>/.opencode/plugins/ring-memory`, slash commands to
`<project>/.opencode/commands`, creates `<project>/.opencode/ring-memory.json`
if absent. Storage is `<project>/.agent/rings.db` (curated) and
`<project>/.agent/history.db` (raw archive). Each project opts in separately.

Update: add `--force`. Preview: add `--dry-run`. Settings are preserved.

## On-demand skill only

```bash
python3 Ring0/scripts/install.py --project /path/to/project
python3 Ring0/scripts/install.py --global
```

No plugin, no automatic capture. Use `/remember`, `/recall`, `/rings`, `/dream`
or natural-language requests.

## Remove

```bash
rm -rf /path/to/project/.opencode/plugins/ring-memory
rm -rf /path/to/project/.opencode/skills/ring-memory
```

Keep `.agent/` if history matters, delete it to forget everything. Remove
`.opencode/ring-memory.json` to clear settings.

## Other hosts

Copy `ring-memory/` into the host skills directory. Wire the host's own
persisted-message events to `automatic.py capture`, request-context hook to
`context`, and idle callback to `prepare`/`apply`. A cron job alone cannot
inject context. See `references/hooks.md`.

## Verify

See `AGENTS.md` section 3. Minimum: plugin `active`, `automatic.py status`
shows records, plus the isolated temp-project round-trip
(save → recall → supersede → state).

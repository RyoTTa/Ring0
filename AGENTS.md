# Ring0 agent install

Read this file and install Ring0 into the current project. Do not ask the user
to run Python commands manually.

## 1. Check environment

- `python3 --version` must be 3.9+.
- For `--auto`: `opencode --version` (tested 2.0.16) and OpenCode V2 project open.
- Install root is the current project directory (the one with `.git` or where
  the user asked). Never install globally unless asked. `--auto` is project-only.

## 2. Install

```bash
git clone https://github.com/RyoTTa/Ring0.git
python3 Ring0/scripts/install.py --project /path/to/project --auto --dry-run
python3 Ring0/scripts/install.py --project /path/to/project --auto
```

Without `--auto` for on-demand skill only. `--global` only for on-demand skill.
For Claude Code or Codex add `--host claude` / `--host codex` (on-demand only;
`--auto` is OpenCode-only). Preserve existing settings on `--force` upgrades.
See `INSTALL.md` for update/remove and other hosts.

## 3. Verify (must do all three)

```bash
python3 /path/to/project/.opencode/skills/ring-memory/scripts/automatic.py --root /path/to/project status
python3 Ring0/scripts/ring.py --root /path/to/project snapshot
```

1. `ring-memory.project` plugin is `active` in this project.
2. `status` shows captured sessions/records (or zero on a fresh project).
3. Isolated memory round-trip in a temp project (do not pollute the real store):

```bash
TMP=$(mktemp -d)
python3 Ring0/scripts/ring.py --root "$TMP" remember "verify token alpha" --kind fact --target verify --json
python3 Ring0/scripts/ring.py --root "$TMP" recall "verify token" --json
OLD=$(python3 Ring0/scripts/ring.py --root "$TMP" remember "old decision" --kind decision --target verify --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
NEW=$(python3 Ring0/scripts/ring.py --root "$TMP" remember "new decision" --kind decision --target verify --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
python3 Ring0/scripts/ring.py --root "$TMP" supersede "$OLD" "$NEW" --reason "verified replacement" --json
python3 Ring0/scripts/ring.py --root "$TMP" state goal "verify goal" --json
rm -rf "$TMP"
```

Report only after the round-trip succeeds: plugin state, status counts, recall hit,
supersede link, and state write. If anything fails, report the exact error and stop.
Do not claim automatic per-turn injection unless the project-local plugin is loaded.

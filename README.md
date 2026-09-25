# Ring0 — ring-tier lifetime memory skill

Long-term memory for coding agents, modeled on x86 protection rings. Lower ring = more privileged, more stable, harder to change.

| Ring | Name | Lifetime | How it's read |
|---|---|---|---|
| ring0 | kernel | permanent, 2000-char cap | injected whole every turn |
| ring1 | long-term | across sessions | top-k recall per turn |
| ring2 | episodic | ~30 days, decays | recency summary |
| ring3 | scratch | this turn only | kept as-is, summarized at session end |

## Rules that matter

- Writes default to the lowest ring that fits. Nothing auto-writes to ring0.
- ring0 changes go through `propose` → user `approve`. Direct writes are rejected.
- Nothing is ever deleted. Stale facts `demote` down a ring, so history stays auditable.
- Every write exports human-readable `.agent/memory/ringN.md` and git-commits. Markdown is the truth, SQLite is the index.

## Quick start

```bash
python scripts/ring.py remember --ring 1 --content "prefers short answers" --tags pref
python scripts/ring.py recall --query "answer style" --ring 1
python scripts/ring.py snapshot   # inject this at session start
python scripts/dream.py           # run on idle / session end, then git push
```

ring0 flow:

```bash
python scripts/ring.py propose --content "agent name is Ring"
python scripts/ring.py approve --id 1   # human only
```

## Lifetime wiring

A skill alone only loads on demand. For true lifetime behavior, hook session start to `snapshot` and session end / idle cron to `dream.py`. See `references/hooks.md`.

## Layout

- `SKILL.md` — the skill itself (agent instructions)
- `scripts/ring.py` — remember / recall / promote / demote / propose / approve / status / snapshot / export, no dependencies
- `scripts/dream.py` — sleeptime consolidation: decay, dedupe, promotion candidates, demotion of cold facts, overlap flags
- `references/hooks.md` — session hook wiring

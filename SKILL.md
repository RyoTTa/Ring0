---
name: ring-memory
description: Lifetime context with protection-ring tiers (ring0 kernel to ring3 scratch). Use this whenever the user mentions lifetime context, long-term memory, remember this, recall past work, ring0 ring1 ring2 ring3, persistent memory across sessions, or asks the agent to forget, promote, or consolidate memories. Prefer this over ad-hoc MEMORY.md notes.
---

Lifetime context in four rings. Lower number means more privileged, more stable, harder to change. Think x86 protection rings.

ring0 kernel: who the agent is, hard constraints, safety rules. Always injected whole. Cap 2000 chars. Writes only via propose then user approve, never silently. This cap is why ring0 stays trustworthy: everything in it is read on every turn, so it must stay small and certain.

ring1 long-term: user preferences, project facts, durable decisions. SQLite + FTS5, vector if sqlite-vec exists. Retrieved top-k per turn. Survives across sessions until demoted.

ring2 episodic: session summaries, recent outcomes, what changed when. Decays after 30 days unless tagged pin. Promoted to ring1 after 3+ recalls.

ring3 scratch: current plan, open todos, raw tool output. Per-turn only. Summarized into one ring2 entry at session end, then dropped.

Read path on every user turn, in this order: snapshot ring0 fully, recall ring1 top 3 with the user query, take ring2 recency top 5, keep ring3 from last turn. Token budget roughly 40/30/20/10. Never skip ring0.

Write path: decide the lowest ring that fits, default ring3. remember --ring N --content ... --tags .... recall --query ... --ring 1. promote --id X --to N moves up, demote moves down. Never delete: stale facts demote, they don't vanish, so history stays auditable.

ring0 protection: agent proposes with propose --content ..., user approves with approve --id X. Only then does the write land, and only if the 2000-char cap still holds. Direct remember --ring 0 without an approved proposal is rejected. This is proposal+approval, not auto-write.

Session lifecycle: on session start run snapshot and inject it. On session end summarize ring3 into ring2, run dream.py on idle or cron for decay, dedupe, promotion candidates, and contradiction flags. Every write auto-exports .agent/memory/ringN.md and git-commits, so markdown is the diffable truth and SQLite is the index. Sync with git push/pull.

If the DB or scripts are missing, fall back to MEMORY/RINGS.md with the same four sections so memory stays human-readable. If sqlite-vec is absent, keyword + salience + recency ranking is enough; do not add dependencies to get vectors.

Commands live in scripts/ring.py: remember, recall, promote, demote, propose, approve, status, snapshot, export. Consolidation lives in scripts/dream.py. Hook wiring lives in references/hooks.md.

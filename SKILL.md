---
name: ring-memory
description: Lifetime context with protection-ring tiers. Use whenever the user mentions long-term memory, lifetime context, remember this, recall, ring0 ring1 ring2 ring3, or wants the agent to persist knowledge across sessions.
---

Ring model for lifetime context. Lower ring means more privileged and more stable.

ring0 is kernel. Identity, hard constraints, safety rules. Always injected in context. Agent must never auto-write or auto-delete here, only explicit user confirmed edits. Limit small, like 2k chars.

ring1 is long-term semantic. User preferences, project facts, durable decisions. Persists across sessions. Stored in SQLite, retrieved by vector + keyword.

ring2 is episodic. Session summaries, recent task outcomes, what changed when. Has decay. Retrieved on demand, compacted periodically.

ring3 is working scratch. Current plan, open todos, tool outputs. Per-turn only. Never persisted unless explicitly promoted upward.

Rules for promotion: ring3 can propose to ring2 at turn end if useful beyond today. ring2 can propose to ring1 if it survives 3+ sessions or user says remember. ring1 to ring0 requires explicit user approval with exact wording. Demotion is opposite, stale ring1 goes to ring2, never silently to trash.

On every user turn, do this silently: load ring0 fully, search ring1 with current query top 3, load ring2 recency summary, keep ring3 from last turn. Budget roughly ring0 > ring1 hits > ring2 summary > ring3.

On write, decide ring first then call the script. Default to lowest privilege that fits, so prefer ring3, then ring2. Never write ring0 on your own.

Storage is SQLite at `.agent/rings.db` with table `memories(id, ring INTEGER, content TEXT, tags TEXT, created_at, updated_at, access_count, salience REAL)`. FTS5 on content for keyword search. If `sqlite-vec` is available use it for vector search, otherwise keyword + recency + salience ranking is enough. No server, no API key required.

Scripts:
- `scripts/ring.py remember --ring 1 --content "..." --tags "pref"` to save
- `scripts/ring.py recall --query "..." --ring 1 --limit 3` to search
- `scripts/ring.py promote --id <id> --to 1` to move upward
- `scripts/ring.py snapshot` to dump ring0+ring1 summary for prompt injection

If DB is missing, create it. If script fails, fall back to `MEMORY/RINGS.md` files with same ring sections so memory stays human-readable.

MemFS equivalent: every write auto-exports to `.agent/memory/ringN.md` and git-commits. DB is the index, markdown is the diffable truth. Sync to cloud with `git push`, restore with pull then reimport. Run `scripts/dream.py` on idle or cron for sleeptime consolidation: decay of old ring2, dedupe, access-based promotion to ring1, then export and commit. True LLM contradiction checks happen there when you wire your agent in, heuristics run without it.

On session end or compaction, summarize ring3 into one ring2 entry, update access_count and salience, decay ring2 older than 30 days unless pinned.

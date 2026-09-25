# Hook wiring

Skill alone only triggers on demand. For lifetime behavior wire two hooks.

Session start: run `python scripts/ring.py snapshot` and inject the output before the first turn. In OpenCode add a session-start hook, in Claude Code add a SessionStart hook, otherwise run it manually.

Session end or idle: run `python scripts/dream.py`, then `git push`. A 10-minute idle cron is enough. Dream handles decay of old ring2, dedupe, promotion of hot ring2 to ring1, demotion of cold ring1 to ring2, and prints overlap flags for you to resolve.

Compaction: before compacting, summarize ring3 into one ring2 entry with `remember --ring 2`, so working state survives the squeeze.

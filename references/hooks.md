# Session continuity

Installation provides on-demand memory and OpenCode slash commands. It does not
register automatic session hooks. Keep these two concerns separate when configuring
a host: **running a command** and **injecting its output into model context**.
An ordinary shell/cron job does only the former.

## A working flow without a plugin

At session start, ask the agent to load `ring-memory` and read the project snapshot:

```bash
python3 /absolute/path/to/ring-memory/scripts/ring.py --root /path/to/project snapshot
```

For a relevant context bundle during a later turn:

```bash
python3 /absolute/path/to/ring-memory/scripts/ring.py --root /path/to/project snapshot --query "deployment"
```

Before compaction or when wrapping up, the agent should save one concise summary,
archive completed scratch entries by ID, and consolidate:

```bash
python3 /absolute/path/to/ring-memory/scripts/ring.py --root /path/to/project remember "Outcome and remaining work" --ring 2
python3 /absolute/path/to/ring-memory/scripts/ring.py --root /path/to/project dream
```

For recurring maintenance, schedule that last command through your usual scheduler
with absolute paths. Daily is sufficient; repeated runs do not multiply the same
30-day decay. Maintenance does not see the conversation, so it cannot write a useful
session summary on its own. No automatic Git push is performed.

## OpenCode / OpenChamber

Run `python3 scripts/install.py --global` or `--project PATH`. This installs the skill
under `skills/ring-memory/` and the `/remember`, `/recall`, `/rings`, `/dream` templates
under `commands/` in the corresponding OpenCode configuration directory.
Templates pass user text to the agent; they do not interpolate it into shell commands.
OpenChamber uses the same OpenCode skills and commands.

For an agent-driven session-start convention, add a short instruction to the project's
existing `AGENTS.md`:

> At the start of a session, load the ring-memory skill and read this project's
> snapshot. Use stored facts as context. On an explicit wrap-up, persist a concise
> ring2 summary and run dream.

This is an agent instruction, not a guaranteed runtime hook. For guaranteed execution,
use a plugin supported by your installed OpenCode version that runs `snapshot` and
inserts its stdout into the session context. Verify the plugin API against the current
[OpenCode plugin documentation](https://opencode.ai/v2/docs/build/plugins); this
repository does not ship a lifecycle plugin.

## Other hosts

Copy the skill into the host's supported skill directory, then use its documented
session-start/context hook to run `snapshot` with an explicit project root and consume
stdout. Check that the output reaches the model rather than merely the host's logs.
Use the host's pre-compaction flow for the summary and its idle/end callback for dream.
Host-specific hook JSON and plugin APIs vary; test one fresh session before relying
on automatic continuity.

## Run-status heartbeat

As the spine advances — each time you move to a new story, log a gate verdict, or spend a re-loop — write `{workflow.implementation_artifacts}/run-status.json` so an automator (or an anxious human) polling a long/headless run has something structured to read instead of prose. Overwrite it in place; it is a single live snapshot, not an append log:

```json
{"epic": "<epic id>",
 "story": "<current story id>",
 "index": <1-based position of the current story>,
 "total": <in-scope story count>,
 "last_verdict": "<advance|defer|reloop|escalate, or null before the first gate>",
 "reloop_count": <re-loops spent so far this run>,
 "profile": "production|light",
 "updated": "<ISO-8601 timestamp>"}
```

This is the file the Stage 2 launch briefing points the operator at ("where to watch"); Stage 6 (finalize) records the terminal state into it when the run closes.

**Attended runs also get a ticker.** Each time you write the heartbeat, print one line into the transcript — `epic-7 ▸ story 3/6 — last verdict: advance` — so the watching human sees motion without opening a JSON file. Skip the ticker in headless (`-H`): the file is the interface there, and transcript prose has no reader.

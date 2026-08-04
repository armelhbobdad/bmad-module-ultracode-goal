---
title: Operating Tips
description: "Field notes from driving a real 22-story epic: giving Bash room for a foreground drive, reading the driver stop reasons that need a decision, why row order is the only sequencing mechanism, splitting a story that escalates, and the verification traps that produce confident false greens."
---

Everything here was learned by driving one real epic (22 stories, 12 landed across a single day, four of them split on contact, three of those consecutively) rather than from reading the scripts. Where a tip contradicts an intuition, the measurement is given. The numbers are one run on one codebase: treat them as something to measure your own against, not as properties of the tool.

For the designed behavior of the run's own failure modes (preflight, the gate, hooks, budget, resume) see [troubleshooting](./troubleshooting.md). The driver's stop reasons are documented here and nowhere else in these docs; the full set is `drive_epic.py`'s `STOP_*` constants.

## Running the loop

### Give Bash an hour so drives can run in the foreground

A `drive_epic.py` invocation took 25 to 45 minutes per story in the run behind these notes; measure your own before sizing a timeout. The Bash tool defaults to a 120-second timeout with a 600-second ceiling (measured on Claude Code 2.1.220, and neither of those env vars appears in the published settings reference, so re-check them if the numbers stop matching). So an agent driving the loop cannot ask to watch a drive to the end: past the timeout the harness moves the command to the background, where it keeps running with nothing watching it.

Raise the ceiling in `~/.claude/settings.json`:

```json
{
  "env": {
    "BASH_DEFAULT_TIMEOUT_MS": "120000",
    "BASH_MAX_TIMEOUT_MS": "3600000"
  }
}
```

`BASH_DEFAULT_TIMEOUT_MS` is already the stock default and is here as a pin; only the ceiling changes. **Env settings are read at startup**, so this takes effect on the next session, not the current one.

The ceiling only sets what a call is *allowed* to ask for. A call that passes no `timeout` of its own is still cut at the 120-second default however high the ceiling is, so ask for the full hour on the drive call itself. And the cut is not a kill: the command is moved to the background and runs to completion there (measured: a 135-second command finished after being backgrounded at 120 seconds), so what you lose is the foreground, not the work.

Two limits to respect. An hour covers roughly one story at the rate above, so pair a foreground drive with `--limit 1`. And the driver's own `--session-timeout` defaults to two hours, which a one-hour Bash ceiling can never reach: if you want the driver's wall clock to be the thing that stops a drive, pass a `--session-timeout` below the ceiling, or raise `BASH_MAX_TIMEOUT_MS` past the driver's default.

The tradeoff is real: a foreground drive blocks the agent for its whole duration. For a strict drive-then-verify loop that costs nothing, because there is nothing to do in between. If you want the agent working on something else while a story runs, background is still the right mechanism.

### The recall latch does not repair itself between drives

That Stage 6 removes `.mem-state.json` at close-out is covered in [cross-session recall](./cross-session-recall.md). The resume half is not in these docs, so: a resume re-writes the latch by re-running Stage 1's latch step. (The story's baseline marker is the opposite case, re-read and never regenerated. Do not carry the latch's rule across to it.)

The operational addition, worth knowing before you chain drives: **observed across a multi-drive day, the spawned session's own attempt to write the latch was permission-denied, so a missing latch did not repair itself on the next spawn.** What denied it was never diagnosed, and UCG's own PreToolUse recall gate is not a candidate, since it no-ops when the latch is absent, which is exactly the state Stage 6 leaves behind. Treat this as an unexplained observation: check for the file rather than assume it.

Re-assert from the parent between drives with the skill's own latch writer, never by hand (a hand-written latch forges the capability check the file exists to record):

```bash
uv run <skill-root>/scripts/mem_recall.py latch \
  --impl-artifacts <impl-artifacts> --run-id <run-id> \
  --recall off --claude-mem-absent
```

That writes a latch recording claude-mem as absent with recall off, which restores fail-closed gating. Use the `--recall on --probe <probe.json>` form when recall is meant to be live. Otherwise accept that spawns 2..N run with recall gating silently off.

## Reading the driver's stop reasons

The driver names thirteen stop reasons (`drive_epic.py`'s `STOP_*` constants). Three mean the invocation finished its work and exit 0: `all-done`, `limit-reached`, `dry-run`. Every other stop is a fail-closed halt and exits 1, so a wrapper can branch on the exit code before it parses anything.

These six are the ones you will actually meet in a working week, and getting them confused wastes a spawn or, worse, propagates an ungated story. The rest name their own cause and need no table: `dry-run`, the pre-spawn refusals (`no-sprint-status`, `epic-not-found`, `sprint-status-elsewhere`, `stale-result`), a row carrying a status the driver does not recognize (`unknown-status`), and a drive that was killed (`signalled`).

| Stop reason | What happened | What to do |
|---|---|---|
| `all-done` | Every story of the Epic is `done`. | Nothing. The Epic is finished. |
| `limit-reached` | Normal. `--limit` was reached. | Nothing. Drive again. |
| `blocked` | The story escalated, and a typed sidecar holds the pending decision. | Run `/ucg-resolve`, which reconstructs every pending decision from the sidecars and walks them. |
| `no-terminal` | The spawn exited without a readable result envelope. | **The work may be complete.** See below. |
| `no-progress` | The spawn reported `complete` but the row is not `done`. | Usually a split. Check whether a *child* advanced (`/ucg-status`). |
| `session-timeout` | The spawn outran `--session-timeout` (two hours by default). | Re-drive. The in-flight story is un-gated; see `no-terminal` below. |

Reading the `blocked` sidecar by hand instead: it is `<impl-artifacts>/escalation-<story-id>.json`, four string fields (`source`, `kind`, `decision_needed`, `evidence`), and it is distinct from the `.escalation-<story>.md` marker the Stop hook writes. Not every `blocked` terminal has one: a Stage 1 refusal carries its whole decision in the `reason` the driver already printed.

### `no-terminal`: the work is often done, and the story file may lie about it

A spawn that dies on a transient upstream error (an API 500, for instance) can have already committed its work and run its full verification, and still leave no gate artifact.

The dangerous part is what it leaves behind. In the observed case the dead session **had already written its own close-out into the story file, reading "gate PASS"**, while there was no `trace-*.md`, no `gate-decision-*.json`, no decision-log entry, and `sprint-status.yaml` still said `ready-for-dev`. The gate had never run.

**On any resume, believe the artifacts and the sprint-status row, never the story file's prose.** Check for the gate *file* before treating a story as gated.

The correct recovery is to re-drive the story. The skill re-enters at Execute, re-measures the committed tree, produces the trace evidence (TEA's `bmad-testarch-trace`, or hand-authored to `gate_eval.py`'s shape on a stack where TEA's browser chain cannot run), and runs `gate_eval.py` for real. Because the dead session already committed, make sure the re-drive re-reads the story's existing baseline marker rather than regenerating it: a rebuilt baseline re-anchors the evidence range to a mid-story HEAD, and the trace then measures only the tail of the work.

Do not hand-mark the story `done` on the strength of your own verification, however thorough: that substitutes your judgment for the gate and produces exactly the artifact-free "PASS" the tool exists to prevent.

### `no-progress`: check for a split before assuming failure

If a spawn splits its story into children and advances a child, the parent row stays un-`done`, so the driver correctly reports that the story it was told to drive did not advance. Nothing is wrong. Confirm a child went `done` and that the children are ordered ahead of the parent.

## Sequencing: row order is the only mechanism

This is the single most surprising thing about operating the driver.

**`pending_ids` keeps every story row that is not `done`**, `epic_stories` hands them over in file order, and the drive loop takes the first of those. Setting a story to `backlog`, or inventing a `blocked` status, changes nothing: the driver will still pick it. `epic-N`, retrospective and `BUG-` rows are filtered out upstream and are never drivable.

So the only way to gate story B behind story A is to **put A above B in `sprint-status.yaml`**. `done` is the only status the machine reads; every other value is documentation for humans, and order is what sequences the run. The `done` match is exact, so a hand-edited `Done` or `DONE` row reads as pending and gets re-driven.

Two consequences:

- **Verify a sequencing change by asking the driver, not by reading the file.** Reading `sprint-status.yaml` tells you what you wrote, not what the driver will pick. `--dry-run` ([introduced in getting started](./getting-started.md)) prints one line per story it would spawn, in the order it would take them, and starts nothing. Add `--limit 1` to print exactly the row that gets picked next. That makes it the cheap check to run after every edit to that file. For a stronger assertion, import the driver's own functions from the project root and read the index directly. These are `@internal` (see the stability policy) and can change without a deprecation note:

  ```bash
  python3 - <<'PY'
  import sys, pathlib
  sys.path.insert(0, ".claude/skills/ultracode-goal/scripts")
  import preflight_check, drive_epic
  root = pathlib.Path(".")                                       # edit these two
  arts = pathlib.Path("_bmad-output/implementation-artifacts")    # to match your project
  st = drive_epic.epic_stories(
      preflight_check.build_rollup(root, arts), drive_epic.normalise_epic("7")) or []
  print(drive_epic.pending_ids(st)[:3])
  PY
  ```

  Keep the `or []`: it is what turns a mistyped epic id into an empty list instead of a traceback.

- **Umbrella stories belong last.** A story that "ships nothing of its own" and only completes when its children do will otherwise be picked, burn a full spawn discovering it has no work, and stop with `no-progress`.

  An umbrella row is the one row worth hand-marking `done`, and it is not a license to hand-mark a story that had work (see the `no-terminal` recovery above). Know what it costs: the Epic-level trace gate fires on *every* story of the Epic being `done`, and a drive that finds the Epic already all-done stops without spawning. So mark it inside a run that then authors the Epic-level gate and Finalize, or accept that the Epic closes with neither.

When you move a row, leave the reasoning in a comment beside it. A future session reading an unexplained reorder will assume it was accidental and undo it.

## When a story escalates as too large

Expect this. In the epic behind these notes, stories drafted before the substrate they depend on existed ran two to four times one invocation: three consecutive stories split (into 3, 3, and 4 pieces), and every split was diagnosed by measurement rather than estimated up front.

### Keep real call sites in every half

The tempting split is primitive-from-call-sites: land the mechanism in one story, adopt it in the next. **Resist it when a guard needs both.** A primitive with no call site cannot have a non-vacuous whole-tree guard: no scan finds anything, and the acceptance test degrades into an assertion about intent.

Prefer a split along a domain boundary where each half keeps genuine callers and a genuine test subject.

### If you must split a primitive out, use an enumerated exemption list

When the first half genuinely cannot satisfy a whole-tree guard, ship the guard at full strength and have it **enumerate, by name, every site still outstanding**, printing the list on every run including passing ones. Then make emptying the list the last half's Definition of Done, and delete the exemption mechanism with it rather than leaving an empty array.

This keeps the first half honest (it does not claim the acceptance criterion) while keeping the guard live and the debt visible. Observed working: the list shrank on each story and reached zero across two of them, each entry naming the story that owed it, and the guard was mutation-proved live at every stage.

### Check sibling stories before accepting a plan

A split plan derived from the work in front of you can rest on a change that another story forbids.

Observed: one story's preserved work-in-progress made a destructive schema change that a later story in the same epic explicitly forbade, having pre-registered the objection as "a blocking finding to raise" against precisely this story. **Grep the epic for constraints on anything you are about to change destructively.**

The consequence went further than the schema. The earlier conclusion "no green subset exists, so this story is atomic" had been measured over a configuration built on the forbidden change. Correcting it dissolved the coupling and the substrate landed green with nothing rewired.

**Generalizable: when a measurement says a change is atomic, check whether the coupling comes from the change being wrong before accepting it as a property of the problem.**

## Verifying a spawn's own report

The gate is a real verdict and worth trusting. The prose around it is not evidence. A short independent pass catches things a green gate does not.

**Re-measure the committed tree, not the working tree.** A spawn mid-write leaves files dirty; a sweep taken then describes something that was never committed. Check `git status` is clean and that HEAD is what you expect before running anything.

**Mutation-test every new guard.** Reading a guard never finds its blindness. Delete or invert its subject and confirm it goes red. In the observed epic, six guards were mutation-proved this way and all six were live, but two *tests* were found vacuous by the same method, and one guard's own twin turned out to model the dropped constraint rather than delete it, which is strictly weaker.

**Prefer executed mutation over a modeled mutant.** A hand-written mutant that differs from the real pre-fix code proves nothing about the real branch. Where a story claims a mutation-proof, re-run one yourself against the shipped code.

**Make the mutation harness hard-error on a missing anchor.** Observed: a harness silently skipped its mutation twice when a refactor moved the anchor, and reported the suite's ordinary green as a passing twin.

**Back files up with `cp` and restore from the backup.** Never `git checkout -- <path>` or `git restore <path>` to undo a mutation: both restore from the *index*, and an intent-to-add entry (`git add -N`) holds the empty blob, so they truncate the file to zero bytes and exit 0 (measured on git 2.47). For a file that has a committed version, `git checkout HEAD -- <path>` is safe. For a file the story just created, nothing git offers is: `git checkout HEAD --` refuses, and `git restore --source=HEAD --` deletes the file with exit 0. The `cp` backup is the only restore that always works.

## Verification traps that produce confident false greens

Each of these was hit while verifying real work, and each one first looked like a result.

**The piped exit code.** `cmd | tail && echo OK || echo FAIL` reports `tail`'s exit status, not `cmd`'s. A scanner that correctly exited 1 was recorded as "green, the guard is dead". `$?` after a pipeline is *also* `tail`'s status, so capturing it changes nothing. Use `${PIPESTATUS[0]}` on the very next line (after `&& echo OK || echo FAIL` it has already been overwritten), or put `set -o pipefail` in front of the pipeline, or drop the pipe and capture `$?` from the bare command. `PIPESTATUS` is bash only: in a `sh` or Makefile recipe use `set -o pipefail` where the shell supports it, or drop the pipe.

**The self-matching process check.** `pgrep -af "drive_epic.py --epic 7"` matches the shell command containing that pattern, so it finds itself. Read carelessly, a stopped drive looks alive. Match on something your own command line cannot contain (`--epic [7]`) and read the exit status rather than the output. Note the Bash tool puts your whole command string in the wrapping shell's argv, so the bracket trick only holds while the plain pattern appears nowhere else in the same call.

**Probe errors that masquerade as findings.** Three separate times, a failed reproduction looked like a refutation or a discovered property:

- A function read its input from disk and ignored the text passed to it, so both arms of a comparison returned the same violation.
- A field was named differently than the probe assumed, so every containment check silently read `undefined`, producing a "0 of 40 correct" result that was pure probe error.
- A compile error on a misremembered constructor name made a type look like it had *no* such constructor at all. It had one, under a different name, and the property nearly reported was false.

**On a typed API, a compile error is evidence about your probe first and about the subject second.** Check the probe before reporting either a finding or a clean result.

**A red-phase gate can pass over an empty collection.** A suite that runs *no cases* can still exit 0: a test target compiled out or filtered away (`cargo test` prints `running 0 tests ... ok`), a runner told `--passWithNoTests` with nothing matched, or an exit code swallowed by a pipe (see above). A missing subject module is the opposite case and is loud, not silent: pytest exits 2 on the collection error and 5 when it merely collects nothing, vitest exits 1 even under `--passWithNoTests`, and `cargo test` exits 101. So read the collected count *as well as* the exit code, and assert the count is the number you expect. UCG's own red phase is an all-skipped suite, which correctly exits 0 with every case reported *skipped*: a zero in the collected column is the thing to distrust, not a zero exit.

**A `not.toContain` over an empty container is vacuous**, as is any absence assertion whose container is empty for an unrelated reason. Assert something positive alongside it: that the scan found a non-zero number of items, that the batch is non-empty, that the file count is not zero.

## Environment gotchas

**UCG's own empty-index guard constrains tool sequencing.** The PreToolUse guard inspects the command string before it runs, so a `git add <paths> && git commit` that relies on its own `add` to fill the index is denied: at evaluation time the index is still empty. Stage in one call, commit in the next. This is not a host-project quirk, it is one of the guard's invariants, armed in every project UCG runs in, and the deny message says exactly this. Two sharper edges: it probes the staged index in the hook event's working directory, so it can refuse a commit you aimed at a different checkout, and two command shapes still deny on a mere *mention* of the verb (inside `$(...)` or backticks), so write prose about committing with Write or Edit rather than a Bash heredoc.

**The spawned session's sandbox may refuse network egress when the parent's does not.** A story escalated reporting that two data files "cannot be fetched" and a dependency was "absent". From the parent session both were trivially available: the dependency was already in the local package cache and a plain `curl` reached the upstream host. **When a spawn reports a dependency it cannot fetch, check the local package caches and try the fetch yourself before accepting the block.**

**Pin the parallelism of the verification suite if it is timing-sensitive.** Observed: a full-concurrency test run was flaky two green in five, because one unrelated gate crept past a 10-second default timeout under contention while taking 1.7 seconds alone. Pinning the runner to one worker (`ava --concurrency=1`; your runner's own name for it will differ) was green every time. A flaky verification tier makes every story's evidence unreliable, which is worse than a slow one.

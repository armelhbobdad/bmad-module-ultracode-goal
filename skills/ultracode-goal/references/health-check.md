---
# UltraCode-Goal self-improvement health check — captures real workflow
# friction as GitHub issues. (No name/description keys: those belong only
# in SKILL.md frontmatter; this is a stage reference, not a skill.)
healthCheckRepo: '{workflow.health_check_repo}'  # empty = health check off
localFallbackFolder: '{workflow.health_check_queue_path}'
seenCachePath: '{workflow.health_check_seen_cache}'
liveSubmitSeverities: ['bug']  # friction/gap go local-queue-default with explicit opt-in
autosubmit: '{workflow.health_check_autosubmit}'
---

# Health Check: Workflow Self-Improvement

This is the terminal step of Stage 6 (Finalize) — Stage 7 in SKILL.md's stages table. Finalize loads it by bare path (`references/health-check.md`); it is fully self-contained and chains nowhere. Reflect on the ultracode-goal run that just completed — honestly, precisely, on evidence, reporting only what you actually experienced executing THIS run's stages. If real friction, bugs, or gaps were encountered in the *workflow instructions* (not the user's code), capture them as structured findings for review and optional submission as GitHub issues. Zero overhead for clean runs: if nothing went wrong, log one line and exit.

## Anti-fabrication rules

- Report only friction you **actually hit this run** — a fabricated issue is worse than none, because it pollutes the maintainers' queue. Reporting zero issues is the healthy, expected outcome for a well-designed workflow.
- Every finding cites the **specific stage reference file and section** where the issue occurred.
- If you are unsure whether something was a real issue or your own confusion, do not report it.

## 0. Announce arrival

Display, in `{communication_language}`: "Running a quick self-improvement check on this run. If nothing rough came up, I will close out immediately."

In headless (`-H`), skip the display and log: "headless: skipped health-check arrival announcement". The line is informational, not a commitment gate — proceed to §0.5 without waiting.

## 0.5. Enabled gate

If `{workflow.health_check_repo}` is **empty**, the health check is off — there is nowhere to file, so there is nothing to run. Log one line — "health-check disabled (health_check_repo empty); skipping" — and **exit immediately**. Do nothing else: no reflection, no files, no JSON side effects. In headless this returns control so Finalize emits its final JSON unchanged.

Otherwise continue to §1.

## 1. Read run context

From this run's `.decision-log.md` and session context, identify:

- **Stage(s) executed** — which of `ingest-and-scope`, `preflight`, `define-done`, `execute`, `gate`, `finalize` you actually followed.
- **Friction points** — moments where a stage instruction was unclear, wrong, contradictory, or silent on a scenario you hit.

The finding's `stage` is whichever of the six you were following when the issue bit you.

## 2. Reflect on execution

Silently review the run. Ask:

- Did a stage instruction lead me astray or cause unnecessary back-and-forth?
- Was a stage ambiguous, so I guessed rather than followed clear guidance?
- Did I hit a scenario no stage accounted for?
- Were any stage instructions wrong or contradictory?

If the answer to ALL is "no", display "Health Check: clean run. No workflow issues to report." and **STOP** — the run is done. In headless, log "health-check: clean run, no findings" and return.

## 3. Severity definitions

Classify each genuine finding:

- **`bug`** — Stage instructions were wrong or contradictory.
- **`friction`** — Stage worked but was unclear, ambiguous, or caused unnecessary back-and-forth.
- **`gap`** — A scenario arose that the workflow did not account for at all.

## 4. Route by run mode

The routing fork is the run mode, decided once here.

### 4a. Attended routing (HALT gate)

In an attended run there is a human at the keyboard. Present every finding, then HALT.

Present each finding:

| Field | Value |
|-------|-------|
| Severity | `bug` / `friction` / `gap` |
| Stage | one of the six |
| Step File | `skills/ultracode-goal/references/{stage}.md` |
| Section | the stable section-heading slug (never line numbers) |
| Defect Key | one to four kebab-case words naming the thing the fix would change (§5a step 1) |

Then ask:

"Submit these findings?

- **[Y]** Yes: submit all findings
- **[N]** No: discard all findings
- **[E]** Edit: let me revise before submitting
- **[Q]** Queue locally: save every finding to `{workflow.health_check_queue_path}/`, submit nothing

You are the final filter. Reject any finding that does not reflect a real issue you observed."

**HALT and wait for input.**

- **[Y]** → proceed to §5 (severity routing).
- **[N]** → display "Findings discarded. Workflow complete." and STOP.
- **[E]** → let the user keep, modify, or remove findings; re-present the revised list and ask again.
- **[Q]** → compute each finding's fingerprints with the script (§5a step 1), then write every finding, whatever its severity, to the local queue (§5c) with the reason "The review gate queued these locally." Make no GitHub call: no `gh auth status`, no search, no issue.

### 4-headless. Unattended routing (no human at the gate)

In headless (`-H`) there is no human to answer [Y]/[N]/[E]/[Q], so that gate is **bypassed deterministically**, never blocking for input:

- If `{workflow.health_check_autosubmit}` is **false** (the default): **queue EVERY finding locally** (§5c) with the reason "Headless runs queue every finding while health_check_autosubmit is off." Never live-submit in an unattended run with autosubmit off.
- If `{workflow.health_check_autosubmit}` is **true**: **live-submit `bug` findings only** (§5a), still script-fingerprinted, remote-dedup-searched, and seen-cache-guarded. **Friction and gap always queue** (§5c) with the reason "Headless runs never submit friction or gap findings." At a matching or possibly matching issue (§5a-i) there is nobody to choose, so the run takes **[S]**: the finding is queued with the match reason, and nothing is posted.

The health check must **never block or delay the final headless JSON emit** — a stall here strands the automator that is waiting on that JSON. It is fire-and-queue: do the routing above, then return so Finalize emits its JSON. If `gh` is unavailable at any live-submit step, fall through to §5c — never stall.

## 5. Severity routing (attended [Y] path)

Route each confirmed finding:

- **`bug`** → live-submit (§5a). High signal, priority for maintainers.
- **`friction` / `gap`** → local queue by default (§5c). These are the most subjective categories and produce the most near-duplicates. Ask **once per session**: "Also submit the {N} friction/gap finding(s) as GitHub issues? [y/N]"; only on explicit affirm do they route through §5a. Those that stay local still get their fingerprints (§5a step 1) and go to §5c with the reason "Friction and gap findings stay local unless you opt in."

### 5a. Live-submit: fingerprint, dedup, create

For each finding routed to live-submit:

**1. Compute the fingerprints via the script**, never inline shell. The fingerprints and the seen-cache are computed and managed deterministically by `health_check_fp.py`:

```
uv run {skill-root}/scripts/health_check_fp.py fingerprint \
  --severity {severity} --stage {stage} --section-slug {slug} --defect-key {defect-key}
```

→ `{"fp": "fp-xxxxxxx", "legacy_fp": "fp-xxxxxxx", "tuple": "<exact hashed input of fp>"}`. `{fp}` hashes severity, stage, step file, section slug and defect key; `{legacy_fp}` is the same hash without the defect key. The `section-slug` is a kebab-case stable heading slug (e.g. `verdict-mapping`), **never line numbers**: they drift when files are edited.

**The defect key** names the defect itself, so two different defects in one section get two fingerprints while two reports of one defect that name the same thing get the same one. It is one to four lower-case ASCII words joined by hyphens that name the thing the fix would change, in the stage reference's or the script's own words: a script, a subcommand, a function, a flag, a field, a verdict, a rule's term or a section's concept. Pick the most specific name the fix would edit. To turn a name into the key, drop its leading dashes and underscores, split it at spaces, underscores, hyphens, dots and each lower-case letter followed by an upper-case one, drop every character of each word that is not an ASCII letter or digit, lower-case each word and join them with hyphens (`gate_status` gives `gate-status`, `--cycle-profile` gives `cycle-profile`, `operator's own evidence` gives `operators-own-evidence`); a name of more than four words keeps its last four. When the defect is a missing rule, there is no name to copy yet: name the case the rule should cover in two to four of the stage reference's own words, the noun the rule would be about, then what makes the case distinct (a missing rule for a story whose acceptance criteria moved, in a section whose rule covers a re-gated story, gives `story-moved-criteria`). Never use a line number, a file name or path (the step file already says where), a severity, or words from this run's own story: whoever reports the same defect next must reach the same key from the source alone. Never use the section's own subject alone either: every defect in the section shares it.

**`legacy_fp` is the section fingerprint**, which every defect of one severity in one section shares. Seen-cache records and issues made by a version of this module without the defect key carry it as their fingerprint, and every issue this step files records it in its body (§5a-ii), so a match on it is only ever a possible match (steps 2 and 4).

A value that breaks its rule (a severity, stage or slug outside its set, a defect key that is not one to four kebab-case words) makes the call exit 1 with a JSON `error` naming the rule: fix that value and run the call again.

**Install-mode-invariant dedup (explicit rule):** the script's `workflow` component is `ultracode-goal/{stage}` and its `step_file` component is ALWAYS the source-repo form `skills/ultracode-goal/references/{stage}.md`, regardless of where the skill is installed (the `{project-root}/_bmad/` tree vs. a dev checkout). The same defect therefore dedups to the same `fp` across every install. Do not substitute the installed path.

**2. Check the seen-cache via the script:**

```
uv run {skill-root}/scripts/health_check_fp.py seen --fp {fp} --legacy-fp {legacy_fp} --cache {seenCachePath}
```

→ `{"seen": ..., "status": ..., "record": ..., "matched_on": ...}`. **`seen` is the suppression verdict, not mere cache presence.** The script reads the record under `{fp}`, and only when the cache has none, the record under `{legacy_fp}`; `matched_on` names which (`null` when neither exists). For a `created`, `reacted` or `commented` record with an `https://` issue URL, the script asks the issue itself, `gh issue view --json state,stateReason`, with `gh` found outside the current folder, run without a shell and stopped after 10 seconds: the cache is machine-local and records only what *this* user did on *this* machine, while an issue's state is shared, so it is the better authority. Never run that check yourself, and never put a recorded URL into a shell command. If the call fails or prints no JSON, continue as `unseen`: this check never halts a run. Read `status`:

- **`unseen`** (`seen: false`): no record under either fingerprint, or a record found only under `{legacy_fp}` (`matched_on: legacy_fp`) that would have suppressed. That record was written by a version without the defect key, and every defect of this severity in this section shares its fingerprint, so it may be another defect's: log `"{fp}: legacy record {legacy_fp} may be another defect, reporting"`; step 4 still offers its issue while that issue is open. Proceed.
- **`handled`** (`seen: true`): a record under `{fp}` with no issue URL, or whose issue is `OPEN`, reads `CLOSED/NOT_PLANNED`, or could not be checked (offline, no `gh`, the time limit, a deleted issue). **The only verdict that suppresses**: skip the finding and log `"{fp}: already handled on {record.date}, {record.issue_url}, skipping"`. `CLOSED/NOT_PLANNED` is **not a fix**: it is how the dedup Action closes a duplicate (`state_reason: 'not_planned'`) and how a maintainer closes a wontfix, and treating it as one would file a `REGRESSION` issue against a live defect nobody fixed, every session. `stateReason` is load-bearing: `state` alone cannot tell a fix from an auto-closed duplicate.
- **`regression`** (`seen: false`, `matched_on: fp`): the record is `resolved` (written when the defect was fixed), or its issue reads `CLOSED/COMPLETED`, or `MERGED` (the record points at the resolving PR). A fresh sighting of a fixed defect is a **regression, not a duplicate**. Proceed with the regression treatment below.
- **`possible-regression`** (`seen: false`, `matched_on: legacy_fp`): the same, found only under `{legacy_fp}`, so what was fixed may be another defect in this section. Proceed with the possible-regression treatment below.
- **`unrecognized`** (`seen: false`): the record carries no action or one this version does not write (an old `queued` record included), so it cannot be confirmed handled. Proceed as an ordinary submission.

**Why anything uncertain reports.** A duplicate report is self-healing: the dedup Action closes it and moves the upvote to the canonical issue. A silenced regression is caught by nothing. When the verdict is in doubt, report.

**Regression treatment** (`regression` only). Title the issue `[health-check][{severity}][{fp}] {workflow}: REGRESSION: {short description}` and open the body with `Regression of {record.issue_url} (resolved {record.date}).` When `record.issue_url` is empty (the prior sighting was only ever local), write `Regression of a previously resolved local finding (resolved {record.date}).` instead: the `{fp}` label still ties the two together server-side. Record the outcome with `--regression` (§5b).

**Possible-regression treatment** (`possible-regression` only). Leave the title unmarked, since this record cannot prove a recurrence, and open the body with `Possibly a regression of {record.issue_url} (resolved {record.date}): that report's fingerprint has no defect key, so it may be another defect in this section.` When `record.issue_url` is empty, write `Possibly a regression of a previously resolved local finding in this section (resolved {record.date}).` Record the outcome without `--regression`: the `resolved` record sits under `{legacy_fp}`, and the script writes under `{fp}` alone.

**What this does and does not catch.** A fix that renames the section it touches, or renames the thing the defect key names, changes `{fp}`, and so does a report that names one defect by another thing than an earlier report did. Such a report arrives as `unseen` and is filed as a first sighting, which is safe: once filed, the dedup Action flags it as a possible duplicate (§5a-ii). These branches catch the regressions that recur under the same section, in the same stage, under the same key.

**3. Check GitHub CLI** with `gh auth status`. If it fails, fall through to §5c with the reason "GitHub CLI is not available."

**4. Remote dedup search**: one deterministic call, and a second only when the first finds nothing:

```
gh search issues --repo {healthCheckRepo} --state open "{fp} in:title" --json number,url,title --limit 1
```

An issue it finds reports this defect. When it finds none, search once more, for the section fingerprint in titles and bodies:

```
gh search issues --repo {healthCheckRepo} --state open "{legacy_fp} in:title,body" --json number,url,title --limit 5
```

Each issue this second search finds is a **possible match**: it was filed by a version whose fingerprints carry no defect key, or it reports a defect of this severity in this section under another defect key. Every such defect shares that fingerprint, so only the user decides (§5a-i).

**5a-i. If a matching open issue exists**, present:

> "Matching report found: #{N} — {title}
>
> Your finding has the same fingerprint `{fp}`. Options:
> - **[R]** React (👍) on the existing issue — silent upvote, no comment
> - **[C]** React + comment with YOUR environment/evidence delta (only if it materially differs)
> - **[N]** Create a new issue anyway — only if you are certain this is a distinct defect
> - **[S]** Skip — do not submit this finding"

**Possible matches.** When the issues came from the `{legacy_fp}` search, list each one and present the same options under this opening instead:

> "Possible match: #{N}: {title} (one line for each issue found)
>
> It carries this section's fingerprint `{legacy_fp}`, which every `{severity}` finding in this section shares: it was filed by a version whose fingerprints carry no defect key, or it reports another defect in this section under another key, so it may report another defect. Pick **[R]** or **[C]** only if it reports this one, naming it when more than one is listed, and **[N]** if none does. Options:"

**Unattended default: [S].** Only the user decides a match. A run with nobody to ask (headless with `{workflow.health_check_autosubmit}` true) takes **[S]** at an exact or a possible match, so the finding goes to the local queue (§5c) with the match reason, and nothing is posted on a guess.

Execute the choice:

- **R:** `gh api -X POST /repos/{healthCheckRepo}/issues/{N}/reactions -f content='+1'`, then record `reacted` (§5b).
- **C:** the reaction call, then write the minimal env+delta body (the Environment table plus ONE sentence on what differs; no session narrative) to a body file as §5a-ii says, and run `gh issue comment {N} --repo {healthCheckRepo} --body-file {body-file}`; then record `commented` (§5b).
- **N:** after an exact match, the open issue carries this same fingerprint, so a new issue under it would be closed as its duplicate: choose a more specific defect key that names what sets this defect apart (the more specific name the fix edits, or the case it covers, still in the source's words), recompute the fingerprints with it (step 1), then proceed to §5a-ii. After a possible match, proceed to §5a-ii as is: that issue's `fp-*` label differs from `{fp}`.
- **S:** record nothing, and write the finding to the local queue (§5c) with the reason "You skipped these at the dedup gate." (the match reason when nobody was asked).

If the reaction or the comment call exits non-zero, log its error and make no further call for this finding: **C** posts no comment after a failed reaction, and a reaction already added stays. Record nothing and write the finding to the local queue (§5c) with the reason "Posting these to GitHub failed."

**5a-ii. If no matching open issue exists** (or the user chose **[N]**), create one.

**First, ensure the `{fp}` label exists** — it is per-fingerprint, so the first reporter of any defect creates a brand-new label, and `gh issue create --label {fp}` hard-fails if the label is missing. Guard it idempotently:

```
gh label create "{fp}" --repo {healthCheckRepo} --color "ededed" \
  --description "Health-check fingerprint dedup key" 2>/dev/null || true
```

The `2>/dev/null || true` keeps it idempotent — a pre-existing label is not an error. The other labels (`health-check`, `workflow-improvement`, `bug`/`friction`/`gap`) are pre-created repo labels and need no guard.

**Then create the issue:**

```
gh issue create --repo {healthCheckRepo} \
  --title "[health-check][{severity}][{fp}] {workflow}: {short description}" \
  --label "health-check,workflow-improvement,{severity},{fp}" \
  --body-file {body-file}
```

After a `regression` verdict, the `--title` value is the regression treatment's title instead, with `REGRESSION: ` before `{short description}`.

**Pass every body as a file, never inline.** Write the structured body below with the Write tool to `hc-body-{fp}.md` in this run's folder (beside `.decision-log.md`), then name that file with `--body-file`. A body often quotes paths, and an inline `--body "..."` puts them in the command itself: while a recall latch is still present (Finalize's unlatch failed, so the report names the latch path), the guard denies any Bash command that names the latch, and quotes, backticks and `$` in a body break shell quoting. The guard reads the paths a Write names, not what it writes, so a body file passes, and it stays in the run folder as the record of what was sent.

The `{workflow}` in the title is `ultracode-goal/{stage}`. The `{fp}` appears in both title (human-readable) and label (server-side filterable) so maintainers can query all reports for a defect via the `fp-*` label without parsing title text. The title stays on the command line, so write `{short description}` with no backtick, `$`, double quote or backslash.

The dedup Action also reads the body's `Section fingerprint:` line. When the new issue matches no open issue's fingerprint but another open health-check issue records the same section fingerprint under a different defect key, or was filed without a key and carries it as its label, the Action comments with a link to each and adds the `possible-duplicate` label. It closes nothing on that match: two reports of one defect can name it by different keys, and every defect of one severity in one section shares the section fingerprint, so a maintainer decides.

After the issue is created, record it (§5b) so this user does not re-report it while that issue stays open. If the body Write or `gh issue create` fails, log its error and record nothing (so after a `regression` verdict the `resolved` record stays), and write the finding to the local queue (§5c) with the reason "Posting these to GitHub failed."

**Writing rules — non-negotiable:**

- **One issue per finding.** Two independent problems → two issues.
- **Respect length budgets.** Finding, Expected, Actual, Impact, Suggested Fix are **each ONE sentence**. Evidence is 2-5 bullets, not prose.
- **Quote, do not paraphrase.** In Evidence, cite the exact `file:line` with the quoted text in quotes.
- **Cite only this module's files.** Evidence quotes `SKILL.md`, the stage references and the scripts under `skills/ultracode-goal/`, never the user's project code, the Epic's content or a secret.
- **Never narrate the session.** The reader wants the defect, not the story. If a sentence starts with "During my run…", delete it.

**Issue body** — a markdown report with these sections in order: **Workflow**
(`ultracode-goal/{stage}`), **Step File** (`skills/ultracode-goal/references/{stage}.md`),
**Section** (`{slug}`), **Severity** (`bug | friction | gap`), **Fingerprint** (`{fp}`)
followed by the line `` Section fingerprint: `{legacy_fp}` ``, exactly so and at the start of
a line of its own (the dedup Action reads it; never a label), **Defect Key** (`{defect-key}`),
**Finding**, **Expected**, **Actual**, **Evidence**, **Impact**, **Suggested Fix**, and an
**Environment** table. A regression's or possible regression's line (step 2) opens the body,
above **Workflow**. Per the writing rules above, Finding / Expected / Actual / Impact /
Suggested Fix are each one sentence, and Evidence is 2-5 quoted `file:line` bullets with no
narrative. The Environment table carries: Date (ISO), OS, AI Editor, Model, Profile
(`production | light`), Run mode (`attended | headless`), and Module Version (from the script
below, else `N/A`).

**Module Version comes from the script** — never walk the file ladder in-prompt:

```
uv run {skill-root}/scripts/health_check_fp.py version --project-root {project-root} --skill-root {skill-root}
```

→ `{"version": "<resolved>", "source": "<which probe hit>"}`. Write `version` into the Environment table; when it is `null` (`source: "N/A"`), write `N/A`. The script probes the same first-hit-wins ladder deterministically: `{project-root}/_bmad/ucg/VERSION` → `{skill-root}/VERSION` → `.claude-plugin/marketplace.json` `plugins[0].version` → `package.json` `version`.

After creating all issues, display "{N} issue(s) created on {healthCheckRepo}:" then each URL. Then display "Workflow complete." unless a finding of this run went to the local queue, whose §5c block ends with it.

### 5b. Record the outcome

Record each outcome that ties a finding to an open issue, via the script, with that issue's URL and today's date:

```
uv run {skill-root}/scripts/health_check_fp.py record --fp {fp} --cache {seenCachePath} \
  --issue-url "{url}" --action created|reacted|commented --date {YYYY-MM-DD}
```

`created` after `gh issue create` succeeded, `{url}` being the URL it printed; `reacted` after **R** and `commented` after **C**, `{url}` being the matched issue's `url` from the search, also when the match came from the `{legacy_fp}` search. After a `regression` verdict, add `--regression`: the issue now tracks the recurrence, so it replaces the `resolved` record the fix left under `{fp}`. Nothing else is recorded: not a queued finding, not **[S]**, not a failed call. A queued finding is not an issue, and a record for it would suppress the same defect when a later attended run approves it with **[Y]**.

The call prints `{"written": ..., "fp": ..., "record": ..., "set_aside": ...}`, `record` being what the cache now holds under `{fp}`. `"written": false` means a `resolved` record was left as it is: the script never downgrades a fix without `--regression`. When `set_aside` is not null, tell the user (log it in headless) that `{seenCachePath}` did not parse, so it was renamed to that path and a new cache was started, and that they keep its records by repairing that file and copying its entries into `{seenCachePath}`. If the call fails, log its error and go on: a lost record costs at most a duplicate report, which the dedup Action closes.

**What the script guarantees.** It sets the `{fp}` key alone and keeps every other record, those under `{legacy_fp}` included. It holds `{seenCachePath}.lock` while it reads and writes, so parallel runs keep each other's records. It accepts `created`, `reacted` and `commented` only with an `https://` URL, and `resolved` with such a URL or an empty one. `resolved` is written by hand when a defect is fixed (see the health-check section of `CONTRIBUTING.md`), and it is the only action that does not suppress.

### 5c. Local queue (every finding that stays local)

A finding stays local for one of these reasons, each with the sentence its block shows:

| Why it stays local | Reason sentence |
|--------------------|-----------------|
| The review gate resolved to **[Q]** (§4a) | "The review gate queued these locally." |
| A headless run with autosubmit off (§4-headless) | "Headless runs queue every finding while health_check_autosubmit is off." |
| A friction or gap finding in a headless run (§4-headless) | "Headless runs never submit friction or gap findings." |
| The user declined the friction/gap opt-in (§5) | "Friction and gap findings stay local unless you opt in." |
| `gh auth status` failed (§5a step 3) | "GitHub CLI is not available." |
| The user chose **[S]** at a matching issue (§5a-i) | "You skipped these at the dedup gate." |
| A run with nobody to ask took **[S]** at a match (§5a-i), the match reason | "These may match an open issue on {healthCheckRepo}; review them before submitting." |
| A body Write, reaction, comment or `gh issue create` failed (§5a-i, §5a-ii) | "Posting these to GitHub failed." |

Every queued finding still gets its fingerprints from the script (§5a step 1), so its file carries the same `fp` a live report would. **Record nothing in the seen-cache for it** (§5b).

**Filename:** `hc-ultracode-goal-{stage}-{YYYYMMDD-HHmmss}.md`, one file per finding. When that name is already taken (two findings of one stage written in the same second), append `-2`, `-3` and so on before `.md` (`hc-ultracode-goal-gate-20261114-093012-2.md`), so no file is ever overwritten.

**File content:** the same structured body as §5a-ii (for a submission that failed, the text of its body file, unchanged), prefixed with YAML frontmatter:

```yaml
---
type: workflow-health-finding
workflow: ultracode-goal/{stage}
step_file: skills/ultracode-goal/references/{stage}.md
severity: {bug | friction | gap}
fingerprint: {fp-xxxxxxx}
section_fingerprint: {legacy_fp}
defect_key: {defect-key}
date: {ISO date}
---
```

After writing the files, display this block, once per reason when findings stayed local for more than one, each block listing its own files:

"{N} finding(s) saved locally:" then each path, then:

"{reason sentence} To submit one as an issue, run:
`gh issue create --repo {healthCheckRepo} --title \"[title]\" --body-file {file-path}`

Or open one at <https://github.com/{healthCheckRepo}/issues/new/choose>"

Then display "Workflow complete." once, after the last block.

In an unattended run, display nothing and wait for nothing: log the same lines (each path, the reason sentence and the `gh issue create --body-file` command), then return.

## Terminal step

This is the terminal step of Finalize — when it returns the run is fully done, nothing further to load. In headless, Finalize emits the final JSON only **after** this step returns, so it must not stall the emit (the never-block rule lives in §4-headless).

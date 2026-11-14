# Health Check: Workflow Self-Improvement

Reflect on the ultracode-goal run that just completed and capture the friction, bugs and gaps you hit in this module's workflow instructions (not the user's code) as structured findings, for its maintainers to fix.

## Anti-fabrication rules

- Report only friction you **actually hit this run** — a fabricated issue is worse than none, because it pollutes the maintainers' queue. Reporting zero issues is the healthy, expected outcome for a well-designed workflow.
- Every finding cites the **specific stage reference file and section** where the issue occurred.
- If you are unsure whether something was a real issue or your own confusion, do not report it.

## 1. Enabled gate

If `{workflow.health_check_repo}` is empty, the check is off: log "health-check disabled (health_check_repo empty); skipping" and return, touching nothing else. Otherwise, in an attended run, tell the user in `{communication_language}` that you are running a quick self-improvement check that closes at once if nothing rough came up.

## 2. Find the findings

Read the `friction:` entries this invocation wrote first, the scope Finalize's decision-log audit walks: an entry an earlier invocation wrote was that invocation's to report. Find them with the Grep tool, never a shell grep, in `.decision-log.md` or, on a log too large to Read, in this session's `dlog-slice-*.md` files. Each names the stage file and the section heading where an instruction was unclear, contradictory or silent on the case in hand. Then, from the rest of the log and what is still in context, find each point where a stage instruction you were following was wrong or contradictory (`bug`), worked but left you guessing or going back and forth (`friction`), or was silent on a case you hit (`gap`). Report only what a logged entry or the live context shows. A finding's `stage` is whichever of `ingest-and-scope`, `preflight`, `define-done`, `execute`, `gate`, `finalize` you were following when it bit. If there is none, display "Health Check: clean run. No workflow issues to report." (headless: log "health-check: clean run, no findings") and return.

## 3. Fingerprint and draft each finding

Every finding, whatever its route, gets its fingerprints and its issue body on disk before anyone reviews it: the gate (§4a) then shows the very text that gets posted or queued, and a gate left unanswered leaves the drafts in the run folder.

**Name the section and the defect.** The section is the heading of the innermost section of `references/{stage}.md` whose instruction bit, copied exactly as that file writes it, numbering included. A bold run-in label (`**Foo.**`) is no heading: take the heading that encloses it. A defect in an instruction of `SKILL.md` or of a script takes the heading of the stage-file section that was running when it bit, or the file's H1 when none fits. Never a line number: it drifts when the file is edited. The defect name is the thing the fix would change, in the stage reference's or the script's own words: a script by its file name, a subcommand, a function, a flag, a field, a verdict, a rule's term or a section's concept. Pick the most specific name the fix would edit, so two different defects in one section get two fingerprints while two reports of one defect that name the same thing get one. When the defect is a missing rule, there is no name to copy yet: name the case the rule should cover in two to four of the stage reference's own words, the noun the rule would be about, then what makes the case distinct (a missing rule for a story whose acceptance criteria moved, in a section whose rule covers a re-gated story, is `story moved criteria`). Never use a path, a line number, a severity or words from this run's own story: whoever reports the same defect next must reach the same name from the source alone. Never use the section's own subject alone either: every defect in the section shares it.

**Compute the fingerprints with the script.** Write the two names with the Write tool to `hc-name-{n}.json` in this run's folder (beside `.decision-log.md`), `{n}` being the finding's number, as the JSON object `{"section_heading": "<the heading>", "defect_name": "<the name>"}` with each value JSON-escaped, so no quote in a name meets the shell. Then run, `<run folder>` being that folder's full path:

```
uv run {skill-root}/scripts/health_check_fp.py fingerprint --severity {severity} --stage {stage} \
  --stdin < "<run folder>/hc-name-{n}.json"
```

→ `{"fp", "legacy_fp", "tuple", "section_slug", "defect_key"}`. The script turns the heading into the section slug and the name into the defect key, one to four lower-case ASCII words joined by hyphens (`gate_eval.py` gives `gate-eval`, `operator's own evidence` gives `operators-own-evidence`). `{fp}` hashes the severity, the stage, its step file, the slug and the key; `{legacy_fp}` is the same hash without the key: the section fingerprint, which every defect of one severity in one section shares, so a match on it is only ever a possible match. A value that breaks its rule makes the call exit 1 with a JSON `error` naming the rule. When it names the severity, the stage or the name, fix that value and run the call once more; when it refuses the heading, take the heading that encloses that one (the file's H1 at the top) and run the call once more. Never loop: when that second call fails too, or a call prints no JSON at all (uv or Python could not run), log it, naming the finding, and drop that finding. Two findings that get one `{fp}` are one defect: merge them into one finding before drafting.

**Write the draft.** Write each finding's issue body with the Write tool to `hc-body-{fp}.md` in the run folder. Every route uses that file as it stands: the gate shows it, `gh` posts it with `--body-file`, and the queue copies it. After the gate the draft changes only by a regression's opening line (§5a step 1) or an **[N]** re-key at the dedup gate (§5a-i). Never put a body on a command line: a body often quotes paths, and while a recall latch is still present (Finalize's unlatch failed, so the report names the latch path) the guard denies any Bash command that names the latch; quotes, backticks and `$` in a body also break shell quoting. The guard reads the paths a Write names, not what it writes, so a body file passes. Before writing `hc-name-{n}.json` or `hc-body-{fp}.md`, Read a file of that name an earlier invocation left, since the Write tool refuses to overwrite a file it has not read. If either Write fails, log its error, naming the finding, and drop that finding: there is no text to show, post or queue.

Give each finding a `{short description}` for its title too, with no backtick, `$`, double quote or backslash: the title stays on the command line.

**Writing rules** (a maintainer triages the issue without this run in the room):

- **One issue per finding.** Two independent problems → two issues.
- **Respect length budgets.** Finding, Expected, Actual, Impact, Suggested Fix are each one sentence. Evidence is 2-5 bullets, not prose.
- **Quote, do not paraphrase.** In Evidence, cite the exact `file:line` with the quoted text in quotes.
- **Cite only this module's files.** Evidence quotes `SKILL.md`, the stage references and the scripts under `skills/ultracode-goal/`, never the user's project code, the Epic's content or a secret.
- **Never narrate the session.** The reader wants the defect, not the story. If a sentence starts with "During my run…", delete it.

**Issue body**: a markdown report with these `## ` headings in order, as the issue template
writes them, since the dedup Action reads the `## Fingerprint` and `## Severity` sections:
`## Workflow` (`ultracode-goal/{stage}`), `## Step File`
(`skills/ultracode-goal/references/{stage}.md`), `## Section` (`{section_slug}`), `## Severity`
(`{severity}`), `## Fingerprint` with `` `{fp}` `` alone on the line below it, followed by the
line `` Section fingerprint: `{legacy_fp}` ``, exactly so and at the start of a line of its own
(the dedup Action reads it; never a label), `## Defect Key` (`{defect_key}`), `## Finding`,
`## Expected`, `## Actual`, `## Evidence`, `## Impact`, `## Suggested Fix`, and
`## Environment`, a table carrying: Date (ISO), OS, AI Editor, Model, Profile
(`production | light`), Run mode (`attended | headless`), and Module Version.

**Module Version comes from the script:**

```
uv run {skill-root}/scripts/health_check_fp.py version --project-root {project-root} --skill-root {skill-root}
```

→ `{"version", "source"}`. Write `version` into the Environment table; write `N/A` when it is `null`, or when the call fails or prints no JSON.

## 4. Route by run mode

The routing fork is the run mode, decided once here.

### 4a. Attended routing (HALT gate)

In an attended run there is a human at the keyboard. Show every finding, then HALT. For each one show its title (as §5a-ii's `--title` spells it, with this finding's values), the path of its draft and the draft's full text. Say that when the seen-cache check finds the defect was fixed before, one line naming that fix opens the body, and a confirmed regression's title gains `REGRESSION: ` before its short description (§5a step 1).

Then ask:

"Submit these findings?

- **[Y]** Yes: submit the bug findings; friction and gap findings stay local
- **[A]** All: submit every finding, friction and gap included
- **[N]** No: discard all findings
- **[E]** Edit: let me revise before submitting
- **[Q]** Queue locally: save every finding to `{workflow.health_check_queue_path}/`, submit nothing

You are the final filter. Reject any finding that does not reflect a real issue you observed."

**HALT and wait for input.**

- **[Y]** or **[A]** → proceed to §5 (severity routing).
- **[N]** → display "Findings discarded. Workflow complete." and STOP.
- **[E]** → let the user keep, modify or remove findings, and make each change in that finding's draft. A change to a finding's severity, stage, section or defect name changes its fingerprints: run §3's call again and write the draft anew as `hc-body-{fp}.md` under the new `{fp}`. Then show the revised findings and ask again.
- **[Q]** → write every finding, whatever its severity, to the local queue (§5c) with the reason "The review gate queued these locally." Make no GitHub call: no `gh auth status`, no search, no issue.

### 4-headless. Unattended routing (no human at the gate)

In headless (`-H`) nobody answers the gate, so this routing takes its place:

- If `{workflow.health_check_autosubmit}` is **false** (the default): queue every finding locally (§5c), since nobody approved a public post, with the reason "Headless runs queue every finding while health_check_autosubmit is off."
- If `{workflow.health_check_autosubmit}` is **true**: live-submit the `bug` findings (§5a) and queue the friction and gap findings (§5c) with the reason "Headless runs never submit friction or gap findings." At a matching or possibly matching issue (§5a-i) there is nobody to choose, so the run takes **[S]**: the finding is queued with the match reason, and nothing is posted.

Never block or delay the final headless JSON emit: Finalize emits it only after this step returns, and an automator is waiting on it. So nothing here waits for input, and a `gh` call that fails at any live-submit step, either search included, sends the finding to §5c with that step's reason from the §5c table.

## 5. Severity routing (attended [Y] and [A])

- **[Y]**: each `bug` finding live-submits (§5a). Each `friction` and `gap` finding, the most subjective kinds and the ones that draw the most near-duplicates, goes to the local queue (§5c) with the reason "Friction and gap findings stay local unless you choose [A]."
- **[A]**: every finding live-submits (§5a).

### 5a. Live-submit: dedup, create

For each finding routed to live-submit:

**1. Check the seen-cache via the script:**

```
uv run {skill-root}/scripts/health_check_fp.py seen --fp {fp} --legacy-fp {legacy_fp} --cache "{workflow.health_check_seen_cache}"
```

→ `{"seen", "status", "record", "matched_on"}`. Where the record names an issue, the script reads that issue's state itself: never run that check yourself, and never put a recorded URL into a shell command. If the call fails or prints no JSON, treat it as `unseen`. Act on `status`:

- `handled`, the only verdict that suppresses: skip the finding and log `"{fp}: already handled on {record.date}, {record.issue_url}, skipping"`.
- `unseen` or `unrecognized`: report it as a first sighting. When `matched_on` is `legacy_fp`, log `"{fp}: legacy record {legacy_fp} may be another defect, reporting"`.
- `regression`: the regression treatment below.
- `possible-regression`: the possible-regression treatment below.

**Regression treatment** (`regression` only). Title the issue `[health-check][{severity}][{fp}] {workflow}: REGRESSION: {short description}` and open its draft with `Regression of {record.issue_url} (resolved {record.date}).`, above `## Workflow`. When `record.issue_url` is empty (the prior sighting was only ever local), write `Regression of a previously resolved local finding (resolved {record.date}).` instead: the `{fp}` label still ties the two together server-side. Record the outcome with `--regression` (§5b).

**Possible-regression treatment** (`possible-regression` only). Leave the title unmarked, since this record cannot prove a recurrence, and open its draft with `Possibly a regression of {record.issue_url} (resolved {record.date}): that report's fingerprint has no defect key, so it may be another defect in this section.` When `record.issue_url` is empty, write `Possibly a regression of a previously resolved local finding in this section (resolved {record.date}).` Record the outcome without `--regression`: the `resolved` record sits under `{legacy_fp}`, and the script writes under `{fp}` alone.

If adding either opening line to the draft fails, log its error and write the finding to the local queue (§5c) with the reason "Posting these to GitHub failed."

**2. Check GitHub CLI** with `gh auth status`. If it fails, fall through to §5c with the reason "GitHub CLI is not available."

**3. Remote dedup search**: one deterministic call, and a second only when the first finds nothing:

```
gh search issues --repo {workflow.health_check_repo} --state open "{fp} in:title" --json number,url,title --limit 1
```

An issue it finds reports this defect. When it finds none, search once more, for the section fingerprint in titles and bodies:

```
gh search issues --repo {workflow.health_check_repo} --state open "{legacy_fp} in:title,body" --json number,url,title --limit 5
```

Each issue this second search finds is a **possible match**: only the user decides (§5a-i).

If either search exits non-zero, it has not shown that no issue matches: log its error and send the finding to the local queue (§5c) with the reason "Posting these to GitHub failed."

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

- **R:** `gh api -X POST /repos/{workflow.health_check_repo}/issues/{N}/reactions -f content='+1'`, then record `reacted` (§5b).
- **C:** the reaction call, then write the minimal env+delta body (the Environment table plus one sentence on what differs; no session narrative) with the Write tool to `hc-comment-{fp}.md` in the run folder, show the user its text, and run `gh issue comment {N} --repo {workflow.health_check_repo} --body-file "<run folder>/hc-comment-{fp}.md"`; then record `commented` (§5b).
- **N:** after an exact match, the open issue carries this same fingerprint, so a new issue under it would be closed as its duplicate: choose a more specific defect name that sets this defect apart (the more specific name the fix edits, or the case it covers, still in the source's words), run §3's call again with it and write the draft anew under the new `{fp}`, without a line the old verdict added. Then run steps 1 to 3 again for the new fingerprints and act on what they return as for any finding: the new `seen` verdict alone decides the regression treatment and `--regression`. After a possible match, proceed to §5a-ii as is: that issue's `fp-*` label differs from `{fp}`.
- **S:** record nothing, and write the finding to the local queue (§5c) with the reason "You skipped these at the dedup gate." (the match reason when nobody was asked).

If the reaction or the comment call exits non-zero, log its error and make no further call for this finding: **C** posts no comment after a failed reaction, and a reaction already added stays. Record nothing and write the finding to the local queue (§5c) with the reason "Posting these to GitHub failed."

**5a-ii. If no matching open issue exists** (or the user chose **[N]**), create one.

**First, ensure the `{fp}` label exists.** It is per-fingerprint, so the first reporter of any defect creates a brand-new label when they have push access to {workflow.health_check_repo}, and `gh issue create --label {fp}` hard-fails if the label is missing. Guard it idempotently:

```
gh label create "{fp}" --repo {workflow.health_check_repo} --color "ededed" \
  --description "Health-check fingerprint dedup key" 2>/dev/null || true
```

The `2>/dev/null || true` keeps it idempotent: a pre-existing label is not an error. The other labels (`health-check`, `workflow-improvement`, `bug`/`friction`/`gap`) are pre-created repo labels and need no guard.

**Then create the issue** from the finding's draft:

```
gh issue create --repo {workflow.health_check_repo} \
  --title "[health-check][{severity}][{fp}] {workflow}: {short description}" \
  --label "health-check,workflow-improvement,{severity},{fp}" \
  --body-file "<run folder>/hc-body-{fp}.md"
```

After a `regression` verdict, the `--title` value is the regression treatment's title instead, with `REGRESSION: ` before `{short description}`.

**If `gh issue create` exits non-zero, run it once more without the `--label` line**, with the same title and body file. A reporter without push access to {workflow.health_check_repo} cannot create the label (the guard's `|| true` hides that) or set any label: the first run fails on the missing `{fp}` label, and where the label exists GitHub drops the labels without a word. The dedup Action applies the labels from the title, so an issue filed without them is deduped like any other.

The `{workflow}` in the title is `ultracode-goal/{stage}`. The `{fp}` appears in both title and label: maintainers query all reports for a defect via the `fp-*` label, and the dedup Action reads the title's `[health-check][{severity}][{fp}]` prefix to label an issue filed without labels, so keep that prefix exactly as written.

After the issue is created, by the first run or the retry, record it (§5b) so this user does not re-report it while that issue stays open. If `gh issue create` fails on its retry too, log its error and record nothing (so after a `regression` verdict the `resolved` record stays), and write the finding to the local queue (§5c) with the reason "Posting these to GitHub failed."

After creating all issues, display "{N} issue(s) created on {workflow.health_check_repo}:" then each URL. Then display "Workflow complete." unless a finding of this run went to the local queue, whose §5c block ends with it.

### 5b. Record the outcome

Record each outcome that ties a finding to an open issue, via the script, with that issue's URL and today's date:

```
uv run {skill-root}/scripts/health_check_fp.py record --fp {fp} --cache "{workflow.health_check_seen_cache}" \
  --issue-url "{url}" --action created|reacted|commented --date {YYYY-MM-DD}
```

`created` after `gh issue create` succeeded, on its first run or its retry without `--label`, `{url}` being the URL it printed; `reacted` after **R** and `commented` after **C**, `{url}` being the matched issue's `url` from the search, also when the match came from the `{legacy_fp}` search. After a `regression` verdict, add `--regression`: the issue now tracks the recurrence, so it replaces the `resolved` record the fix left under `{fp}`. Nothing else is recorded: not a queued finding, not **[S]**, not a failed call. A queued finding is not an issue, and a record for it would suppress the same defect when a later attended run approves it.

The call prints `{"written", "fp", "record", "set_aside"}`. `"written": false` is no error: the script kept a `resolved` record. When `set_aside` is not null, tell the user (log it in headless) that `{workflow.health_check_seen_cache}` did not parse, so it was renamed to that path and a new cache was started, and that they keep its records by repairing that file and copying its entries into `{workflow.health_check_seen_cache}`. If the call fails, log its error and go on: a lost record costs at most a duplicate report, which the dedup Action closes.

### 5c. Local queue (every finding that stays local)

A finding stays local for one of these reasons, each with the sentence its block shows:

| Why it stays local | Reason sentence |
|--------------------|-----------------|
| The review gate resolved to **[Q]** (§4a) | "The review gate queued these locally." |
| A headless run with autosubmit off (§4-headless) | "Headless runs queue every finding while health_check_autosubmit is off." |
| A friction or gap finding in a headless run (§4-headless) | "Headless runs never submit friction or gap findings." |
| A friction or gap finding approved with **[Y]**, not **[A]** (§5) | "Friction and gap findings stay local unless you choose [A]." |
| `gh auth status` failed (§5a step 2) | "GitHub CLI is not available." |
| The user chose **[S]** at a matching issue (§5a-i) | "You skipped these at the dedup gate." |
| A run with nobody to ask took **[S]** at a match (§5a-i), the match reason | "These may match an open issue on {workflow.health_check_repo}; review them before submitting." |
| A search, a regression line's edit, the reaction or the comment failed, or `gh issue create` failed twice (§5a steps 1 and 3, §5a-i, §5a-ii) | "Posting these to GitHub failed." |

Write each such finding into `{workflow.health_check_queue_path}` with the script. It creates the folder when absent, names the file so that no other file is overwritten, and copies the draft unchanged:

```
uv run {skill-root}/scripts/health_check_fp.py queue --queue-dir "{workflow.health_check_queue_path}" \
  --stage {stage} --body-file "<run folder>/hc-body-{fp}.md"
```

→ `{"path": "<the file it wrote>"}`. If the call fails, log its error and list the draft itself in that file's place: it holds the same text. A queued finding carries the same `fp` a live report would. **Record nothing in the seen-cache for it** (§5b).

After writing the files, display this block, once per reason when findings stayed local for more than one, each block listing its own files:

"{N} finding(s) saved locally:" then each path, each followed by the two commands that submit it, filled in with that finding's values (`{file-path}` being that path; after a `regression` verdict, `REGRESSION: ` goes before `{short description}`, as in §5a-ii):

```
gh label create "{fp}" --repo {workflow.health_check_repo} --color "ededed" \
  --description "Health-check fingerprint dedup key" 2>/dev/null || true
gh issue create --repo {workflow.health_check_repo} \
  --title "[health-check][{severity}][{fp}] {workflow}: {short description}" \
  --label "health-check,workflow-improvement,{severity},{fp}" \
  --body-file {file-path}
```

then:

"{reason sentence} Run a finding's two commands to submit it as an issue, or open one at <https://github.com/{workflow.health_check_repo}/issues/new/choose>. Without push access to {workflow.health_check_repo}, drop the `gh label create` command and the `--label` line: you can neither create a label nor set one, and the dedup Action labels the issue from its title."

Then display "Workflow complete." once, after the last block.

In an unattended run, display nothing and wait for nothing: log the same lines (each path with its `gh label create` and `gh issue create --body-file` commands, and the reason sentence with its note for a reporter without push access), then return.

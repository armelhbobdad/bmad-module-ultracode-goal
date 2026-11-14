#!/usr/bin/env python3
"""health-check-dedup.yaml: the server-side dedup Action for health-check issues.

The Action only runs for real when an issue is opened on GitHub, so these tests
read its github-script body with PyYAML and run it under node, the way
actions/github-script does (as the body of an async function given `github`,
`context` and `core`), with a stubbed `github` client. Every write call is
recorded and nothing reaches GitHub.

Covers:
  - An exact fingerprint match closes the later issue as a not-planned
    duplicate and upvotes the earlier one; the earlier issue's own run closes
    nothing, since the canonical issue must be numbered below the one the run
    is for (two reports filed together never close each other)
  - A run for an issue that is no longer open makes no call, and the run reads
    the issue's current state instead of the event's snapshot
  - A `labeled` event acts only for `health-check` or an `fp-*` label: a
    maintainer's triage label never re-flags or re-closes an issue
  - The job runs for an issue labeled `health-check` or titled
    `[health-check]...`. An issue with no `fp-*` label (a reporter without
    push access sets none) gets the `fp-*` label created, a 422 ignored, then
    the labels it lacks added, from its title or else its body's Fingerprint
    and Severity sections, and is then deduped or flagged as a labeled issue
    is; an unfilled template (its placeholder, or only a `Section
    fingerprint:` line) gets no call, and a labeled issue no label call
  - A shared section fingerprint under another defect key (a body line, or a
    keyless issue's label) with an earlier open issue gets the
    `possible-duplicate` label, then one "Possible duplicate" comment, and is
    never closed or upvoted; the earlier issue's own run, an issue already
    flagged, and one sharing nothing get no call
  - Runs for one issue share a concurrency group, so they never overlap; a
    newer pending run may replace an older pending one
  - The `Section fingerprint:` line the stage reference tells the health
    check to write, and the one the issue template carries, is the one the
    Action's SECTION_RE reads

The behaviour tests need node and are skipped without it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "health-check-dedup.yaml"
HEALTH_CHECK_MD = REPO_ROOT / "skills" / "ultracode-goal" / "references" / "health-check.md"
ISSUE_TEMPLATE = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "workflow-health-check.md"
GITHUB_SCRIPT_PIN = "actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3 # v9.0.0"

# Runs the Action's script with a stubbed `github` client. Every write call is recorded in order.
_NODE_RUNNER = r"""
const fs = require('fs');
const [scriptPath, scenarioPath] = process.argv.slice(2);
const script = fs.readFileSync(scriptPath, 'utf8');
const scenario = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));
const calls = [];
const withLabels = i => ({ ...i, labels: (i.labels || []).map(name => ({ name })) });
const current = { state: 'open', ...withLabels(scenario.issue) };
const open = scenario.open.map(withLabels).filter(i => i.number !== current.number);
if (current.state === 'open') open.push(current);
const listForRepo = async ({ labels, state }) => {
  if (state !== 'open') throw new Error(`listForRepo asked for state ${state}`);
  const want = labels.split(',');
  return { data: open.filter(i => want.every(w => i.labels.some(l => l.name === w))) };
};
const github = {
  paginate: async (fn, params) => (await fn(params)).data,
  rest: {
    issues: {
      get: async p => {
        if (p.issue_number !== current.number) throw new Error(`get for #${p.issue_number}`);
        return { data: current };
      },
      listForRepo,
      createComment: async p => { calls.push(['comment', p.issue_number, p.body]); },
      addLabels: async p => { calls.push(['label', p.issue_number, p.labels]); },
      update: async p => { calls.push(['update', p.issue_number, p.state, p.state_reason]); },
      createLabel: async p => {
        calls.push(['createLabel', p.name]);
        if (scenario.labelExists) { const e = new Error('exists'); e.status = 422; throw e; }
      },
    },
    reactions: { createForIssue: async p => { calls.push(['react', p.issue_number, p.content]); } },
  },
};
// The payload is the snapshot the event carried: open, with no labels. The Action must read the issue itself.
const payload = { action: scenario.event || 'opened', issue: { number: current.number, state: 'open', labels: [] } };
if (scenario.label) payload.label = { name: scenario.label };
const context = { payload, repo: { owner: 'o', repo: 'r' } };
const core = { info: () => {} };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('github', 'context', 'core', script)(github, context, core)
  .then(() => process.stdout.write(JSON.stringify(calls)))
  .catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""

FP_A, FP_B, FP_C, FP_S = "fp-aaaaaaa", "fp-bbbbbbb", "fp-ccccccc", "fp-5555555"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="the Action's script runs under node")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _script() -> str:
    return _workflow()["jobs"]["dedup"]["steps"][0]["with"]["script"]


def _body(section_fp: str | None) -> str:
    line = f"Section fingerprint: `{section_fp}`\n\n" if section_fp else ""
    return f"## Fingerprint\n`fp-x`\n\n{line}## Finding\nOne sentence.\n"


def _issue(number: int, fp: str, section_fp: str | None, *extra: str, state: str = "open",
           body: str | None = None) -> dict:
    return {"number": number, "state": state, "labels": ["health-check", fp, *extra],
            "body": _body(section_fp) if body is None else body}


def _bare(number: int, title: str, body: str, *labels: str) -> dict:
    """An issue as GitHub files it for a reporter without push access: no label they passed survives."""
    return {"number": number, "state": "open", "labels": list(labels), "title": title, "body": body}


def _template(fp: str | None = None, severity: str | None = None, section_fp: str | None = None) -> str:
    """The issue template's body as a reporter submits it, with the given fields filled in."""
    text = ISSUE_TEMPLATE.read_text(encoding="utf-8").split("---\n", 2)[2]
    for value, old, new in (
        (fp, "`fp-XXXXXXX`\n\nSection fingerprint:", f"`{fp}`\n\nSection fingerprint:"),
        (section_fp, "Section fingerprint: `fp-XXXXXXX`", f"Section fingerprint: `{section_fp}`"),
        (severity, "covered at all -->\n", f"covered at all -->\n`{severity}`\n"),
    ):
        if value:
            assert text.count(old) == 1, old
            text = text.replace(old, new)
    return text


def _run(tmp_path: Path, issue: dict, others: list[dict], label_exists: bool = False, event: str = "opened",
         label: str | None = None) -> list:
    (tmp_path / "script.js").write_text(_script(), encoding="utf-8")
    (tmp_path / "runner.js").write_text(_NODE_RUNNER, encoding="utf-8")
    scenario = {"issue": issue, "open": others, "labelExists": label_exists, "event": event, "label": label}
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    done = subprocess.run(
        ["node", str(tmp_path / "runner.js"), str(tmp_path / "script.js"), str(tmp_path / "scenario.json")],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# --- exact fingerprint match ------------------------------------------------


@needs_node
def test_an_exact_match_closes_the_later_issue_and_upvotes_the_earlier(tmp_path):
    calls = _run(tmp_path, _issue(12, FP_A, FP_S), [_issue(10, FP_A, FP_S)])
    assert [c[:2] for c in calls] == [["comment", 12], ["label", 12], ["update", 12], ["react", 10]]
    assert calls[0][2].startswith(f"Auto-deduped: same fingerprint `{FP_A}` as #10.")
    assert calls[1] == ["label", 12, ["duplicate"]]
    assert calls[2] == ["update", 12, "closed", "not_planned"]
    assert calls[3] == ["react", 10, "+1"]


@needs_node
def test_the_canonical_is_the_lowest_numbered_earlier_issue(tmp_path):
    calls = _run(tmp_path, _issue(12, FP_A, FP_S), [_issue(10, FP_A, FP_S), _issue(7, FP_A, FP_S)])
    assert ["react", 7, "+1"] in calls
    assert ["update", 12, "closed", "not_planned"] in calls


@needs_node
def test_the_earlier_issues_own_run_closes_nothing(tmp_path):
    # Both are open with one fingerprint: the run for #10 must not close #10 in favour of #12, or two
    # reports filed together would each close the other.
    assert _run(tmp_path, _issue(10, FP_A, FP_S), [_issue(12, FP_A, FP_S)]) == []


@needs_node
def test_a_run_for_an_issue_no_longer_open_makes_no_call(tmp_path):
    # GitHub sends `opened` and one `labeled` event per label, so the job runs several times for one issue:
    # a later run reads the issue closed by an earlier one and stops.
    closed = _issue(12, FP_A, FP_S, "duplicate", state="closed")
    assert _run(tmp_path, closed, [_issue(10, FP_A, FP_S)]) == []


@needs_node
@pytest.mark.parametrize("label", ["confirmed", "possible-duplicate", "duplicate", "bug", "fp-123"])
def test_a_labeled_event_for_any_other_label_makes_no_call(tmp_path, label):
    # A maintainer reopened the duplicate, or removed `possible-duplicate`, then triaged it with another label.
    assert _run(tmp_path, _issue(12, FP_A, FP_S), [_issue(10, FP_A, FP_S)], event="labeled", label=label) == []
    assert _run(tmp_path, _issue(12, FP_B, FP_S), [_issue(9, FP_S, None)], event="labeled", label=label) == []


@needs_node
@pytest.mark.parametrize("label", ["health-check", FP_A])
def test_a_labeled_event_for_health_check_or_a_fingerprint_acts(tmp_path, label):
    calls = _run(tmp_path, _issue(12, FP_A, FP_S), [_issue(10, FP_A, FP_S)], event="labeled", label=label)
    assert ["update", 12, "closed", "not_planned"] in calls
    assert ["react", 10, "+1"] in calls


@needs_node
def test_another_event_makes_no_call(tmp_path):
    assert _run(tmp_path, _issue(12, FP_A, FP_S), [_issue(10, FP_A, FP_S)], event="edited") == []


@needs_node
def test_an_issue_without_a_fingerprint_label_makes_no_call(tmp_path):
    issue = {"number": 12, "labels": ["health-check"], "body": _body(FP_S)}
    assert _run(tmp_path, issue, [_issue(10, FP_A, FP_S)]) == []


# --- a report filed without labels -----------------------------------------------

TITLE_B = f"[health-check][bug][{FP_B}] ultracode-goal/gate: x"
FP_T = "fp-1234abc"


def _labeled(number: int, *labels: str) -> list:
    return ["label", number, list(labels)]


@needs_node
@pytest.mark.parametrize("label_exists", [False, True], ids=["new-label", "label-exists"])
def test_an_unlabeled_report_is_labeled_from_its_title(tmp_path, label_exists):
    # Filed by a reporter without push access: GitHub kept none of its labels. A 422 on the fp-* label is no error.
    calls = _run(tmp_path, _bare(12, TITLE_B, _body(FP_S)), [], label_exists=label_exists)
    assert calls == [["createLabel", FP_B], _labeled(12, "health-check", "workflow-improvement", "bug", FP_B)]


@needs_node
def test_the_title_is_read_whatever_its_case(tmp_path):
    # The job's startsWith ignores case, so the title it lets through is read the same way.
    calls = _run(tmp_path, _bare(12, "[Health-Check][Bug][FP-BBBBBBB] ultracode-goal/gate: x", _body(FP_S)), [])
    assert calls == [["createLabel", FP_B], _labeled(12, "health-check", "workflow-improvement", "bug", FP_B)]


def _filed_titles() -> list[str]:
    """Every issue title the stage reference tells the health check to write, as a template."""
    text = HEALTH_CHECK_MD.read_text(encoding="utf-8")
    titles = re.findall(r"(\[health-check\](?:\[[^\]\s]*\])* \{workflow\}: [^\"`\n]*)", text)
    # The first run's `--title` (§5a-ii), the §5c submit command's, and the regression treatment's.
    assert len(titles) == 3, titles
    assert sum(f'--title "{title}"' in text for title in titles) == 2
    assert sum("REGRESSION: " in title for title in titles) == 1
    return titles


@needs_node
@pytest.mark.parametrize("severity", ["bug", "friction", "gap"])
def test_every_title_the_health_check_writes_is_read_by_the_action(tmp_path, severity):
    fp = "fp-0a1b2c3"
    for template in _filed_titles():
        title = (template.replace("{severity}", severity).replace("{fp}", fp)
                 .replace("{workflow}", "ultracode-goal/gate").replace("{short description}", "x"))
        calls = _run(tmp_path, _bare(12, title, ""), [])
        assert calls == [["createLabel", fp], _labeled(12, "health-check", "workflow-improvement", severity, fp)], title


@needs_node
def test_an_unlabeled_report_is_then_flagged_as_a_labeled_one_is(tmp_path):
    keyless = _issue(9, FP_S, None)
    calls = _run(tmp_path, _bare(12, TITLE_B, _body(FP_S)), [keyless])
    assert calls[:2] == [["createLabel", FP_B], _labeled(12, "health-check", "workflow-improvement", "bug", FP_B)]
    assert calls[2:] == _run(tmp_path, _issue(12, FP_B, FP_S), [keyless])
    _assert_flagged(calls[2:], 12, "#9", FP_S)


@needs_node
def test_an_unlabeled_exact_duplicate_is_labeled_then_closed(tmp_path):
    earlier = _issue(9, FP_B, FP_S)
    calls = _run(tmp_path, _bare(12, TITLE_B, _body(FP_S)), [earlier])
    assert calls[:2] == [["createLabel", FP_B], _labeled(12, "health-check", "workflow-improvement", "bug", FP_B)]
    assert [c[:2] for c in calls[2:]] == [["comment", 12], ["label", 12], ["update", 12], ["react", 9]]
    assert calls[2][2].startswith(f"Auto-deduped: same fingerprint `{FP_B}` as #9.")
    assert calls[3:] == [["label", 12, ["duplicate"]], ["update", 12, "closed", "not_planned"], ["react", 9, "+1"]]
    assert calls[2:] == _run(tmp_path, _issue(12, FP_B, FP_S), [earlier])


@needs_node
@pytest.mark.parametrize(
    "body",
    [
        f"## Severity\n`bug`\n\n## Fingerprint\n`{FP_T}`\n\nSection fingerprint: `{FP_S}`\n",
        # The section line first: the fingerprint is the first one on any other line.
        f"## Fingerprint\nSection fingerprint: `{FP_S}`\n`{FP_T}`\n\n## Severity\n**bug**\n",
        # What a comment holds is never read.
        f"## Fingerprint\n<!-- not `fp-7777777` -->\n`{FP_T}`\n\n## Severity\n<!--\ngap\n-->\nbug\n",
        _template(fp=FP_T, severity="bug", section_fp=FP_S),
        # Filed from the web, the body has CRLF line endings.
        _template(fp=FP_T, severity="bug", section_fp=FP_S).replace("\n", "\r\n"),
    ],
    ids=["sections", "section-line-first", "comments", "issue-template", "issue-template-crlf"],
)
def test_a_template_filing_whose_labels_were_dropped_is_labeled_from_its_body(tmp_path, body):
    calls = _run(tmp_path, _bare(12, "[health-check] x", body), [])
    assert calls == [["createLabel", FP_T], _labeled(12, "health-check", "workflow-improvement", "bug", FP_T)]


@needs_node
@pytest.mark.parametrize(
    "body",
    [
        f"## Fingerprint\n`{FP_T}`\n\n## Finding\nOne sentence.\n",
        f"## Severity\n\n## Fingerprint\n`{FP_T}`\n",
        f"## Severity\nbug or gap\n\n## Fingerprint\n`{FP_T}`\n",
        # The template's Severity comment names every severity: a comment is never read.
        _template(fp=FP_T, section_fp=FP_S),
    ],
    ids=["no-section", "empty-section", "not-one-severity", "issue-template"],
)
def test_a_report_with_no_severity_gets_no_severity_label(tmp_path, body):
    calls = _run(tmp_path, _bare(12, "[health-check] x", body), [])
    assert calls == [["createLabel", FP_T], _labeled(12, "health-check", "workflow-improvement", FP_T)]


@needs_node
@pytest.mark.parametrize(
    "body",
    [
        f"## Fingerprint\n`fp-XXXXXXX`\n\nSection fingerprint: `{FP_S}`\n\n## Severity\nbug\n",
        _template(severity="bug", section_fp=FP_S),
        _template(),
        # A fingerprint outside the Fingerprint section is not the report's.
        f"## Fingerprint\n`fp-XXXXXXX`\n\n## Finding\nSee `{FP_T}`.\n",
        # A decorated section line is still the section fingerprint, never the defect's: only a line that is the
        # fingerprint alone is read, or the report would be closed against a keyless issue on a section match.
        f"## Fingerprint\n`fp-XXXXXXX`\n**Section fingerprint:** `{FP_S}`\n",
        f"## Fingerprint\n`fp-XXXXXXX`\n- Section fingerprint: `{FP_S}`\n",
        f"## Fingerprint\n`fp-XXXXXXX`\n> Section fingerprint: `{FP_S}`\n",
    ],
    ids=["sections", "issue-template", "issue-template-unfilled", "fp-elsewhere", "bold-section-line",
         "bulleted-section-line", "quoted-section-line"],
)
@pytest.mark.parametrize("labels", [(), ("health-check", "workflow-improvement")], ids=["bare", "template-labels"])
def test_an_unfilled_template_gets_no_label_and_no_call(tmp_path, body, labels):
    assert _run(tmp_path, _bare(12, "[health-check] x", body, *labels), [_issue(9, FP_S, None)]) == []


@needs_node
@pytest.mark.parametrize(
    "issue, added",
    [
        # Filed from the template: its labels are kept, and the fp-* and severity ones are not set.
        (_bare(12, "[health-check] x", _template(fp=FP_T, severity="gap", section_fp=FP_S),
               "health-check", "workflow-improvement"), ["gap", FP_T]),
        (_bare(12, TITLE_B, _body(FP_S), "health-check", "bug"), ["workflow-improvement", FP_B]),
    ],
    ids=["template-labels", "title"],
)
def test_only_the_missing_labels_are_added(tmp_path, issue, added):
    calls = _run(tmp_path, issue, [])
    assert calls == [["createLabel", added[-1]], _labeled(12, *added)]


@needs_node
def test_a_collaborators_labeled_report_gets_no_label_call(tmp_path):
    # The labels went on with the issue: the title is never read, even when it names another fingerprint.
    issue = {**_issue(12, FP_A, FP_S), "title": TITLE_B}
    assert _run(tmp_path, issue, []) == []
    calls = _run(tmp_path, issue, [_issue(10, FP_A, FP_S)])
    assert [c[:2] for c in calls] == [["comment", 12], ["label", 12], ["update", 12], ["react", 10]]
    assert calls[1] == ["label", 12, ["duplicate"]]


# --- section fingerprint: flag, never close ----------------------------------


def _assert_flagged(calls: list, number: int, refs: str, section_fp: str) -> None:
    comments = [c for c in calls if c[0] == "comment"]
    assert len(comments) == 1 and comments[0][1] == number
    assert comments[0][2].startswith(f"Possible duplicate of {refs}: same section fingerprint `{section_fp}`")
    assert not any(c[0] in ("update", "react") for c in calls), "a section match closes and upvotes nothing"
    # The label that stops a later run goes on before the comment, after the label is created.
    assert [c[0] for c in calls] == ["createLabel", "label", "comment"]
    assert calls[1] == ["label", number, ["possible-duplicate"]]


@needs_node
def test_a_keyless_issue_whose_label_is_the_section_fingerprint_is_flagged(tmp_path):
    # An issue filed without a defect key carries the section fingerprint as its fingerprint label.
    calls = _run(tmp_path, _issue(12, FP_B, FP_S), [_issue(9, FP_S, None)])
    _assert_flagged(calls, 12, "#9", FP_S)
    assert ["createLabel", "possible-duplicate"] in calls


@needs_node
def test_an_issue_recording_the_section_fingerprint_under_another_key_is_flagged(tmp_path):
    calls = _run(tmp_path, _issue(12, FP_B, FP_S), [_issue(9, FP_C, FP_S), _issue(11, "fp-4444444", "fp-6666666")])
    _assert_flagged(calls, 12, "#9", FP_S)
    assert "#11" not in calls[[c[0] for c in calls].index("comment")][2]


@needs_node
def test_a_new_keyless_issue_is_flagged_against_a_keyed_one(tmp_path):
    # Filed by hand without the key: its label is its section fingerprint, which a keyed issue records.
    calls = _run(tmp_path, _issue(12, FP_S, None), [_issue(9, FP_C, FP_S)])
    _assert_flagged(calls, 12, "#9", FP_S)


@needs_node
@pytest.mark.parametrize(
    "older, newer",
    [
        (_issue(9, FP_S, None), _issue(12, FP_B, FP_S)),  # a keyless report, then a keyed one
        (_issue(9, FP_C, FP_S), _issue(12, FP_S, None)),  # a keyed report, then a keyless one
        (_issue(9, FP_C, FP_S), _issue(12, FP_B, FP_S)),  # two keys in one section
    ],
    ids=["keyless-then-keyed", "keyed-then-keyless", "two-keys"],
)
def test_only_the_later_of_two_reports_is_flagged(tmp_path, older, newer):
    # Filed together, or the older one relabeled later: the earlier issue's own run flags nothing.
    assert _run(tmp_path, older, [newer]) == []
    _assert_flagged(_run(tmp_path, newer, [older]), 12, "#9", FP_S)


@needs_node
def test_an_existing_possible_duplicate_label_is_not_an_error(tmp_path):
    calls = _run(tmp_path, _issue(12, FP_B, FP_S), [_issue(9, FP_S, None)], label_exists=True)
    _assert_flagged(calls, 12, "#9", FP_S)


@needs_node
def test_an_issue_already_flagged_makes_no_call(tmp_path):
    flagged = _issue(12, FP_B, FP_S, "possible-duplicate")
    assert _run(tmp_path, flagged, [_issue(9, FP_S, None)]) == []


@needs_node
def test_no_shared_section_fingerprint_makes_no_call(tmp_path):
    assert _run(tmp_path, _issue(12, FP_B, FP_S), [_issue(9, FP_C, "fp-6666666")]) == []


@needs_node
def test_a_pull_request_is_never_flagged_against(tmp_path):
    pr = {**_issue(9, FP_S, None), "pull_request": {"url": "https://example.invalid/pr/9"}}
    assert _run(tmp_path, _issue(12, FP_B, FP_S), [pr]) == []


# --- the job ------------------------------------------------------------------


def test_runs_for_one_issue_never_overlap_and_a_pending_one_may_be_replaced():
    # cancel-in-progress false: a running job finishes, while GitHub keeps only the newest pending run.
    job = _workflow()["jobs"]["dedup"]
    assert job["concurrency"] == {
        "group": "health-check-dedup-${{ github.event.issue.number }}",
        "cancel-in-progress": False,
    }


def test_the_job_runs_for_a_health_check_label_or_title():
    # An issue filed by a reporter without push access carries no label, only the title the health check writes.
    assert _workflow()["jobs"]["dedup"]["if"] == (
        "contains(github.event.issue.labels.*.name, 'health-check') "
        "|| startsWith(github.event.issue.title, '[health-check]')"
    )


def test_the_github_script_pin_is_kept():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert f"uses: {GITHUB_SCRIPT_PIN}" in text


def test_the_header_says_a_section_match_is_flagged_and_never_closed():
    header = WORKFLOW.read_text(encoding="utf-8").split('"on":', 1)[0]
    flowed = " ".join(re.sub(r"^#\s?", "", header, flags=re.MULTILINE).split())
    assert "adds the `possible-duplicate` label" in flowed
    assert "It closes nothing on that match" in flowed
    assert "numbered below this one" in flowed


def test_the_header_says_an_unlabeled_report_is_labeled_from_its_title_or_body():
    header = WORKFLOW.read_text(encoding="utf-8").split('"on":', 1)[0]
    flowed = " ".join(re.sub(r"^#\s?", "", header, flags=re.MULTILINE).split())
    assert "or whose title starts with `[health-check]`" in flowed
    assert "`[health-check][{severity}][{fp}] ...`, or else from the body's `## Fingerprint` and `## Severity`" in flowed
    assert "never from a `Section fingerprint:` line or the template's `fp-XXXXXXX` placeholder" in flowed


# --- the body the health check files -------------------------------------------


def _section_re() -> re.Pattern:
    """The Action's SECTION_RE, as a Python pattern (the JS literal uses only syntax both share)."""
    match = re.search(r"const SECTION_RE = /(.+)/m;", _script())
    assert match, "SECTION_RE is a multiline regex literal in the Action's script"
    return re.compile(match.group(1), re.MULTILINE)


def _filed_line() -> str:
    """The Section fingerprint line the stage reference writes into an issue body, filled in."""
    text = HEALTH_CHECK_MD.read_text(encoding="utf-8")
    lines = re.findall(r"`` (Section fingerprint: `\{legacy_fp\}`) ``", text)
    assert lines, "the stage reference names the Section fingerprint body line"
    assert len(set(lines)) == 1
    return lines[0].replace("{legacy_fp}", FP_S)


def test_the_section_line_of_a_filed_body_matches_the_actions_section_re():
    body = f"## Fingerprint\n`{FP_B}`\n{_filed_line()}\n\n## Defect Key\n`gate-status`\n"
    match = _section_re().search(body)
    assert match and match.group(1) == FP_S


def test_the_stage_reference_puts_the_section_line_at_the_start_of_its_own_line():
    flowed = " ".join(HEALTH_CHECK_MD.read_text(encoding="utf-8").split())
    assert "`` Section fingerprint: `{legacy_fp}` ``, exactly so and at the start of a line of its own" in flowed


def test_the_issue_templates_section_line_matches_once_filled_in():
    lines = [line for line in ISSUE_TEMPLATE.read_text(encoding="utf-8").splitlines()
             if line.startswith("Section fingerprint:")]
    assert lines == ["Section fingerprint: `fp-XXXXXXX`"]
    match = _section_re().search(lines[0].replace("fp-XXXXXXX", FP_S))
    assert match and match.group(1) == FP_S


@needs_node
def test_the_action_reads_the_section_line_of_a_filed_body(tmp_path):
    body = f"## Fingerprint\n`{FP_B}`\n{_filed_line()}\n\n## Finding\nOne sentence.\n"
    calls = _run(tmp_path, _issue(12, FP_B, None, body=body), [_issue(9, FP_S, None)])
    _assert_flagged(calls, 12, "#9", FP_S)

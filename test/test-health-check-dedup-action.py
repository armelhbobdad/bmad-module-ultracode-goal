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
    and Severity sections (the fingerprint read in any letter case, and
    labeled in lower case), and is then deduped or flagged as a labeled issue
    is; an unfilled template (its placeholder, or only a `Section
    fingerprint:` line) gets no call, and a labeled issue no label call
  - Every label name and a `Section fingerprint:` line are read in any letter
    case: an issue labeled `FP-ABC1234` is deduped as one labeled
    `fp-abc1234`, an upper-case section line is flagged as a lower-case one
    is, a `Health-Check` label acts as `health-check` does, an issue labeled
    `Possible-Duplicate` is not flagged again, and a report labeled
    `Health-Check` gets no second `health-check` label
  - A shared section fingerprint under another defect key (a body line, or a
    keyless issue's label) with an earlier open issue gets the
    `possible-duplicate` label, then one "Possible duplicate" comment, and is
    never closed or upvoted; the earlier issue's own run, an issue already
    flagged, and one sharing nothing get no call
  - With no earlier open issue, a report whose Environment table gives a
    Module Version lower than the latest release (compared number by number,
    with mutant twins for a comparison as text and for an equal version), of a
    fingerprint an earlier issue was closed as completed for, is commented on
    in the agreed words, labeled `duplicate` and closed as not planned, never
    as completed; the Environment table is read under a heading, after a bold
    label or under its own header cell, as copies have written it; a fixed
    issue past the first page of closed issues is found (with a one-page
    mutant twin); every doubt (no single plain X.Y.Z version, no completed
    earlier issue, no release, a tag that is not X.Y.Z, a close after the
    release, a failed call) and an equal or newer version leave it open and
    go on to the possible-duplicate flag, each beside a twin run with no
    doubt that closes it, and a copy of the Action in another repository
    closes nothing this way; the workflow grants `contents: read` and nothing
    broader for the release, and its script holds no `${{ }}`
  - Runs for one issue share a concurrency group, so they never overlap; a
    newer pending run may replace an older pending one
  - The title and the body header `health_check_fp.py fingerprint` prints
    for a finding are read by the Action: the title's prefix by its title
    regex, the body header's `## Fingerprint` and `## Severity` sections by
    its body reader and its `Section fingerprint:` line by SECTION_RE; the
    issue template's section line is read by SECTION_RE once filled in

The behaviour tests need node and are skipped without it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "health-check-dedup.yaml"
HEALTH_CHECK_MD = REPO_ROOT / "skills" / "ultracode-goal" / "references" / "health-check.md"
ISSUE_TEMPLATE = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "workflow-health-check.md"
DOCS_MD = REPO_ROOT / "docs" / "health-check.md"
FP_SCRIPT = REPO_ROOT / "skills" / "ultracode-goal" / "scripts" / "health_check_fp.py"
GITHUB_SCRIPT_PIN = "actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3 # v9.0.0"

# Runs the Action's script with a stubbed `github` client. Every write call is recorded in order.
_NODE_RUNNER = r"""
const fs = require('fs');
const [scriptPath, scenarioPath] = process.argv.slice(2);
const script = fs.readFileSync(scriptPath, 'utf8');
const scenario = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));
const calls = [];
// Every read call too, in order, kept apart from the writes.
const reads = [];
const withLabels = i => ({ ...i, labels: (i.labels || []).map(name => ({ name })) });
const current = { state: 'open', ...withLabels(scenario.issue) };
const open = scenario.open.map(withLabels).filter(i => i.number !== current.number);
if (current.state === 'open') open.push(current);
const closed = (scenario.closed || []).map(withLabels).map(i => ({ state: 'closed', ...i }));
const failure = status => Object.assign(new Error(`HTTP ${status}`), { status });
// GitHub matches a label name in any letter case, as it holds one label per name in any case. It serves the
// newest issue first, one page at a time: `page` (from 1) of `per_page` (30 when not given, 100 at most).
const listForRepo = async ({ labels, state, page = 1, per_page = 30 }) => {
  reads.push(['list', state, labels]);
  const want = labels.split(',').map(w => w.toLowerCase());
  const matches = i => want.every(w => i.labels.some(l => l.name.toLowerCase() === w));
  if (state !== 'open' && state !== 'closed') throw new Error(`listForRepo asked for state ${state}`);
  if (state === 'closed' && scenario.closedError) throw failure(scenario.closedError);
  const size = Math.min(per_page, 100);
  const all = (state === 'open' ? open : closed).filter(matches).sort((a, b) => b.number - a.number);
  return { data: all.slice((page - 1) * size, page * size) };
};
// No release is a 404, as GitHub answers for a repository that has none; a `status` is that failure.
const getLatestRelease = async p => {
  reads.push(['release', p.owner, p.repo]);
  if (!scenario.release) throw failure(404);
  if (scenario.release.status) throw failure(scenario.release.status);
  return { data: scenario.release };
};
const github = {
  // Every page in turn, as octokit's paginate follows the next-page link until there is none.
  paginate: async (fn, params) => {
    const all = [];
    for (let page = 1; ; page++) {
      const { data } = await fn({ ...params, page });
      all.push(...data);
      if (data.length < Math.min(params.per_page || 30, 100)) return all;
    }
  },
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
    repos: { getLatestRelease },
  },
};
// The payload is the snapshot the event carried: open, with no labels. The Action must read the issue itself.
const payload = { action: scenario.event || 'opened', issue: { number: current.number, state: 'open', labels: [] } };
if (scenario.label) payload.label = { name: scenario.label };
// The module's own repository unless the scenario names another (a copy of the Action).
const [owner, repo] = (scenario.repo || 'armelhbobdad/bmad-module-ultracode-goal').split('/');
const context = { payload, repo: { owner, repo } };
const core = { info: () => {} };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('github', 'context', 'core', script)(github, context, core)
  .then(() => process.stdout.write(JSON.stringify({ calls, reads })))
  .catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""

FP_A, FP_B, FP_C, FP_S = "fp-aaaaaaa", "fp-bbbbbbb", "fp-ccccccc", "fp-5555555"
# A section fingerprint whose hex has letters, so upper-casing it changes more than its `fp-`.
FP_U = "fp-5e5a5b5"

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


def _template(fp: str | None = None, severity: str | None = None, section_fp: str | None = None,
              version: str | None = None) -> str:
    """The issue template's body as a reporter submits it, with the given fields filled in."""
    text = ISSUE_TEMPLATE.read_text(encoding="utf-8").split("---\n", 2)[2]
    for value, old, new in (
        (fp, "`fp-XXXXXXX`\n\nSection fingerprint:", f"`{fp}`\n\nSection fingerprint:"),
        (section_fp, "Section fingerprint: `fp-XXXXXXX`", f"Section fingerprint: `{section_fp}`"),
        (severity, "covered at all -->\n", f"covered at all -->\n`{severity}`\n"),
        (version, "| Module Version |  |", f"| Module Version | {version} |"),
    ):
        if value:
            assert text.count(old) == 1, old
            text = text.replace(old, new)
    return text


def _run_full(tmp_path: Path, issue: dict, others: list[dict], label_exists: bool = False, event: str = "opened",
              label: str | None = None, closed: list[dict] | None = None, release: dict | None = None,
              closed_error: int | None = None, script: str | None = None,
              repo: str | None = None) -> tuple[list, list]:
    """The write calls and the read calls of one run. `closed` are the repository's closed issues, `release` its
    latest release (None: it has none), `script` stands in for the Action's own (a mutant), and `repo` is the
    OWNER/REPO the run is for (None: the module's own)."""
    (tmp_path / "script.js").write_text(_script() if script is None else script, encoding="utf-8")
    (tmp_path / "runner.js").write_text(_NODE_RUNNER, encoding="utf-8")
    scenario = {"issue": issue, "open": others, "labelExists": label_exists, "event": event, "label": label,
                "closed": closed or [], "release": release, "closedError": closed_error, "repo": repo}
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    done = subprocess.run(
        ["node", str(tmp_path / "runner.js"), str(tmp_path / "script.js"), str(tmp_path / "scenario.json")],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    return out["calls"], out["reads"]


def _run(tmp_path: Path, issue: dict, others: list[dict], **kwargs) -> list:
    return _run_full(tmp_path, issue, others, **kwargs)[0]


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
@pytest.mark.parametrize("label", ["health-check", FP_A, "Health-Check", FP_A.upper()])
def test_a_labeled_event_for_health_check_or_a_fingerprint_acts(tmp_path, label):
    calls = _run(tmp_path, _issue(12, FP_A, FP_S), [_issue(10, FP_A, FP_S)], event="labeled", label=label)
    assert ["update", 12, "closed", "not_planned"] in calls
    assert ["react", 10, "+1"] in calls


@needs_node
@pytest.mark.parametrize("event, label", [("opened", None), ("labeled", "FP-ABC1234")], ids=["opened", "labeled"])
def test_an_upper_case_fingerprint_label_is_deduped_as_one(tmp_path, event, label):
    """A label created as `FP-ABC1234` is that fingerprint's: it is read, searched and named in lower case."""
    calls = _run(tmp_path, _issue(12, "FP-ABC1234", FP_S), [_issue(10, "FP-ABC1234", FP_S)], event=event,
                 label=label)
    assert calls == [
        ["comment", 12, calls[0][2]], ["label", 12, ["duplicate"]], ["update", 12, "closed", "not_planned"],
        ["react", 10, "+1"],
    ]
    assert calls[0][2].startswith("Auto-deduped: same fingerprint `fp-abc1234` as #10.")
    # The earlier issue's own run still closes nothing.
    assert _run(tmp_path, _issue(10, "FP-ABC1234", FP_S), [_issue(12, "FP-ABC1234", FP_S)], event=event,
                label=label) == []


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


def _fingerprint(severity: str, stage: str = "gate", description: str = "the gate reads a stale trace") -> dict:
    """What `health_check_fp.py fingerprint --stdin` prints for a finding, as the stage reference runs it."""
    names = {"section_heading": "Route on the verdict", "defect_name": "gate_status", "short_description": description}
    done = subprocess.run(
        [sys.executable, str(FP_SCRIPT), "fingerprint", "--severity", severity, "--stage", stage, "--stdin"],
        input=json.dumps(names), capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout)


def _title_re() -> re.Pattern:
    """The Action's title regex, as a Python pattern (the JS literal uses only syntax both share)."""
    match = re.search(r"const title = /(.+)/i\.exec", _script())
    assert match, "the Action reads the title with a case-blind regex literal"
    return re.compile(match.group(1), re.IGNORECASE)


@pytest.mark.parametrize("severity", ["bug", "friction", "gap"])
def test_the_scripts_titles_match_the_actions_title_regex(severity):
    payload = _fingerprint(severity)
    for key in ("title", "regression_title"):
        match = _title_re().match(payload[key])
        assert match and match.groups() == (severity, payload["fp"]), payload[key]
        # The job's own filter lets it through.
        assert payload[key].startswith("[health-check]")


def test_the_stage_reference_files_the_scripts_title_and_opens_the_draft_with_its_header():
    """No title and no machine-read body line is built by hand any more (determinism-1, determinism-2)."""
    text = HEALTH_CHECK_MD.read_text(encoding="utf-8")
    flowed = " ".join(text.split())
    # The live create takes the title, and so does the queue call that prints a queued finding's create.
    assert text.count('--title "{title}"') == 2
    assert not re.search(r"\[health-check\]\[\{severity\}\]", text), "no title template left in the prose"
    assert "opening with the call's `body_header` exactly as printed" in flowed
    assert "Section fingerprint:" not in text


@needs_node
@pytest.mark.parametrize("severity", ["bug", "friction", "gap"])
def test_every_title_the_health_check_writes_is_read_by_the_action(tmp_path, severity):
    payload = _fingerprint(severity)
    fp = payload["fp"]
    for title in (payload["title"], payload["regression_title"]):
        calls = _run(tmp_path, _bare(12, title, ""), [])
        assert calls == [["createLabel", fp], _labeled(12, "health-check", "workflow-improvement", severity, fp)], title


@needs_node
@pytest.mark.parametrize("severity", ["bug", "friction", "gap"])
def test_a_drafted_body_alone_is_read_by_the_action(tmp_path, severity):
    """Under a title the Action cannot read, the body header still gives the fingerprint and the severity."""
    payload = _fingerprint(severity)
    body = payload["body_header"] + "\n## Finding\nOne sentence.\n"
    calls = _run(tmp_path, _bare(12, "[health-check] x", body), [])
    assert calls == [["createLabel", payload["fp"]],
                     _labeled(12, "health-check", "workflow-improvement", severity, payload["fp"])]


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
@pytest.mark.parametrize("line", ["`FP-ABC1234`", "Fp-AbC1234", "  `fp-ABC1234`  "])
def test_the_bodys_fingerprint_is_read_whatever_its_case(tmp_path, line):
    """Case-blind, as the title is: the report is labeled and deduped under the fingerprint in lower case."""
    body = f"## Severity\n`gap`\n\n## Fingerprint\n{line}\n\nSection fingerprint: `{FP_S}`\n"
    calls = _run(tmp_path, _bare(12, "[health-check] x", body), [])
    assert calls == [["createLabel", "fp-abc1234"],
                     _labeled(12, "health-check", "workflow-improvement", "gap", "fp-abc1234")]
    # An earlier open issue under the lower-case label is the canonical one.
    calls = _run(tmp_path, _bare(12, "[health-check] x", body), [_issue(9, "fp-abc1234", FP_S)])
    assert calls[:2] == [["createLabel", "fp-abc1234"],
                         _labeled(12, "health-check", "workflow-improvement", "gap", "fp-abc1234")]
    assert calls[2:] == [
        ["comment", 12, calls[2][2]], ["label", 12, ["duplicate"]], ["update", 12, "closed", "not_planned"],
        ["react", 9, "+1"],
    ]
    assert calls[2][2].startswith("Auto-deduped: same fingerprint `fp-abc1234` as #9.")


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
        f"## Fingerprint\n`fp-XXXXXXX`\nSECTION FINGERPRINT: `{FP_U.upper()}`\n",
    ],
    ids=["sections", "issue-template", "issue-template-unfilled", "fp-elsewhere", "bold-section-line",
         "bulleted-section-line", "quoted-section-line", "upper-case-section-line"],
)
@pytest.mark.parametrize("labels", [(), ("health-check", "workflow-improvement")], ids=["bare", "template-labels"])
def test_an_unfilled_template_gets_no_label_and_no_call(tmp_path, body, labels):
    assert _run(tmp_path, _bare(12, "[health-check] x", body, *labels), [_issue(9, FP_S, None)]) == []
    assert _run(tmp_path, _bare(12, "[health-check] x", body, *labels), [_issue(9, FP_U, None)]) == []


@needs_node
@pytest.mark.parametrize(
    "issue, added",
    [
        # Filed from the template: its labels are kept, and the fp-* and severity ones are not set.
        (_bare(12, "[health-check] x", _template(fp=FP_T, severity="gap", section_fp=FP_S),
               "health-check", "workflow-improvement"), ["gap", FP_T]),
        (_bare(12, TITLE_B, _body(FP_S), "health-check", "bug"), ["workflow-improvement", FP_B]),
        # A label the repository spells in another letter case is the same label.
        (_bare(12, TITLE_B, _body(FP_S), "Health-Check", "BUG"), ["workflow-improvement", FP_B]),
    ],
    ids=["template-labels", "title", "title-labels-in-another-case"],
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


def _upper_body(section_fp: str) -> str:
    """A body whose section line was retyped in upper case."""
    return _body(None).replace("## Finding", f"SECTION FINGERPRINT: `{section_fp.upper()}`\n\n## Finding")


@needs_node
@pytest.mark.parametrize(
    "newer, older",
    [
        # The new issue's section line in upper case, against a keyless issue's label.
        (_issue(12, FP_B, None, body=_upper_body(FP_U)), _issue(9, FP_U, None)),
        # An earlier keyed issue's section line in upper case.
        (_issue(12, FP_B, FP_U), _issue(9, FP_C, None, body=_upper_body(FP_U))),
        # A keyless issue's label in upper case, and a new keyless one under it.
        (_issue(12, FP_B, FP_U), _issue(9, FP_U.upper(), None)),
        (_issue(12, FP_U.upper(), None), _issue(9, FP_C, FP_U)),
    ],
    ids=["own-line", "their-line", "their-label", "own-label"],
)
def test_an_upper_case_section_fingerprint_is_flagged(tmp_path, newer, older):
    """Read in any letter case, as the body's Fingerprint line is, and named in lower case."""
    _assert_flagged(_run(tmp_path, newer, [older]), 12, "#9", FP_U)


@needs_node
def test_an_existing_possible_duplicate_label_is_not_an_error(tmp_path):
    calls = _run(tmp_path, _issue(12, FP_B, FP_S), [_issue(9, FP_S, None)], label_exists=True)
    _assert_flagged(calls, 12, "#9", FP_S)


@needs_node
@pytest.mark.parametrize("label", ["possible-duplicate", "Possible-Duplicate"])
def test_an_issue_already_flagged_makes_no_call(tmp_path, label):
    # A re-run must not post a second comment, whatever case the repository's label is spelled in.
    flagged = _issue(12, FP_B, FP_S, label)
    assert _run(tmp_path, flagged, [_issue(9, FP_S, None)]) == []


@needs_node
def test_no_shared_section_fingerprint_makes_no_call(tmp_path):
    assert _run(tmp_path, _issue(12, FP_B, FP_S), [_issue(9, FP_C, "fp-6666666")]) == []


@needs_node
def test_a_pull_request_is_never_flagged_against(tmp_path):
    pr = {**_issue(9, FP_S, None), "pull_request": {"url": "https://example.invalid/pr/9"}}
    assert _run(tmp_path, _issue(12, FP_B, FP_S), [pr]) == []


# --- a report from a copy older than the fix -------------------------------------

LATEST = {"tag_name": "v8.0.0", "published_at": "2026-11-02T10:00:00Z"}
FIXED_AT = "2026-11-02T09:00:00Z"
RELEASE_READ = ["release", "armelhbobdad", "bmad-module-ultracode-goal"]
CLOSE = ["update", 12, "closed", "not_planned"]


def _env_body(version: str | None) -> str:
    """A filed body whose `## Environment` table gives this Module Version, or has no such row for None."""
    row = "" if version is None else f"| Module Version | {version} |\n"
    return _body(FP_S) + f"\n## Environment\n| Field | Value |\n|-------|-------|\n| Date | 2026-11-02 |\n{row}"


def _reported(version: str | None = "5.0.0", fp: str = FP_A, body: str | None = None) -> dict:
    return _issue(12, fp, FP_S, body=_env_body(version) if body is None else body)


def _closed(number: int, fp: str = FP_A, reason: str | None = "completed", closed_at: str | None = FIXED_AT,
            **extra) -> dict:
    return {"number": number, "state": "closed", "state_reason": reason, "closed_at": closed_at,
            "labels": ["health-check", fp], "body": _body(FP_S), **extra}


def _release(tag: str, published_at: str = LATEST["published_at"]) -> dict:
    return {"tag_name": tag, "published_at": published_at}


def _comment(fp: str, number: int, version: str, tag: str) -> str:
    return (f"Auto-deduped: same fingerprint `{fp}` as #{number}, which was fixed. This report gives Module Version "
            f"{version}, older than the latest release, {tag}. Please update to {tag}, and if the behaviour is still "
            "there on that release, report it again in a new issue.")


def _assert_the_twin_closes(tmp_path: Path) -> None:
    """Twin of a doubt case: the same run with no doubt (5.0.0, #10 fixed before v8.0.0) closes the issue."""
    calls = _run(tmp_path, _reported("5.0.0"), [], closed=[_closed(10)], release=LATEST)
    assert calls == [["comment", 12, _comment(FP_A, 10, "5.0.0", "v8.0.0")], ["label", 12, ["duplicate"]], CLOSE]


@needs_node
def test_an_outdated_copys_report_of_a_fixed_defect_is_closed_as_not_planned(tmp_path):
    calls, reads = _run_full(tmp_path, _reported("5.0.0"), [], closed=[_closed(10)], release=LATEST)
    assert calls == [["comment", 12, _comment(FP_A, 10, "5.0.0", "v8.0.0")], ["label", 12, ["duplicate"]], CLOSE]
    # The open search found nothing, then the closed issues of the same labels were read, then the release.
    assert reads == [["list", "open", f"health-check,{FP_A}"], ["list", "closed", f"health-check,{FP_A}"],
                     RELEASE_READ]
    # The comment is public and permanent: it says the earlier issue was fixed, never that this report's behaviour is.
    comment = calls[0][2]
    assert "#10, which was fixed." in comment and "report it again in a new issue." in comment
    assert chr(0x2014) not in comment and "completed" not in comment and "is fixed" not in comment


@needs_node
@pytest.mark.parametrize(
    "issue",
    [
        _reported(body=_env_body("`5.0.0`")),
        _reported(body=_env_body("v5.0.0")),
        _reported(body=_env_body("5.0.0").replace("| Module Version |", "| **Module Version** |")),
        _reported(body=_env_body("5.0.0").replace("| Module Version | 5.0.0 |", "|Module Version|5.0.0")),
        # The issue template's own table, filled in, and as the web files it with CRLF line endings.
        _reported(body=_template(fp=FP_A, severity="bug", section_fp=FP_S, version="5.0.0")),
        _reported(body=_template(fp=FP_A, severity="bug", section_fp=FP_S, version="5.0.0").replace("\n", "\r\n")),
        # Copies older than 7.2.0 were asked only for an Environment table: after a bold label, or under its own
        # header cell, as well as under a heading.
        _reported(body=_body(FP_S) + "\n**Environment:**\n\n| Field | Value |\n|---|---|\n| Module Version | 5.0.0 |\n"),
        _reported(body=_body(FP_S) + "\n| Environment | |\n|---|---|\n| Date | 2026-11-02 |\n| Module Version | 5.0.0 |\n"),
        _reported(body=_body(FP_S) + "\n### Environment\nAs the script printed it.\n\n| Module Version | 5.0.0 |\n"),
    ],
    ids=["backticks", "leading-v", "bold-field", "no-outer-pipes-spacing", "issue-template", "issue-template-crlf",
         "bold-label", "header-cell", "heading-then-text"],
)
def test_the_module_version_is_read_from_the_environment_table(tmp_path, issue):
    calls = _run(tmp_path, issue, [], closed=[_closed(10)], release=LATEST)
    assert calls == [["comment", 12, _comment(FP_A, 10, "5.0.0", "v8.0.0")], ["label", 12, ["duplicate"]], CLOSE]


@needs_node
@pytest.mark.parametrize(
    "table",
    ["\n**Environment:**\n\n| Field | Value |\n|---|---|\n| Module Version | 5.0.0 |\n",
     "\n| Environment | |\n|---|---|\n| Module Version | 5.0.0 |\n"],
    ids=["bold-label", "header-cell"],
)
def test_a_reader_of_the_heading_alone_misses_an_older_copys_table(tmp_path, table):
    """Mutant twin: read under an `## Environment` heading only, an older copy's table gives no version."""
    script = _script()
    reader = "const rows = environmentRows(i)"
    assert script.count(reader) == 1
    heading_only = script.replace(reader, "const rows = bodySection(i, 'environment')")
    issue = _reported(body=_body(FP_S) + table)
    assert _run(tmp_path, issue, [], closed=[_closed(10)], release=LATEST)[-1] == CLOSE
    assert _run(tmp_path, issue, [], closed=[_closed(10)], release=LATEST, script=heading_only) == []


@needs_node
def test_an_unlabeled_outdated_report_is_labeled_then_closed(tmp_path):
    issue = _bare(12, f"[health-check][bug][{FP_A}] ultracode-goal/gate: x", _env_body("7.3.0"))
    calls = _run(tmp_path, issue, [], closed=[_closed(10)], release=LATEST)
    assert calls == [["createLabel", FP_A], _labeled(12, "health-check", "workflow-improvement", "bug", FP_A),
                     ["comment", 12, _comment(FP_A, 10, "7.3.0", "v8.0.0")], ["label", 12, ["duplicate"]], CLOSE]


@needs_node
def test_the_latest_fix_is_the_one_linked(tmp_path):
    fixes = [_closed(4, closed_at="2026-10-01T00:00:00Z"), _closed(9), _closed(7, reason="not_planned")]
    calls = _run(tmp_path, _reported("5.0.0"), [], closed=fixes, release=LATEST)
    assert calls[0] == ["comment", 12, _comment(FP_A, 9, "5.0.0", "v8.0.0")]
    assert calls[1:] == [["label", 12, ["duplicate"]], CLOSE]


# Versions compared number by number: each pair below is older, then not older, read as numbers. The pairs marked
# `text` get the other answer when the parts are compared as text, and `equal` when an equal version counts as older.
OLDER = [
    ("5.0.0", "v8.0.0", ""), ("7.99.99", "v8.0.0", ""), ("0.0.1", "v8.0.0", ""), ("8.0.0", "v8.0.1", ""),
    ("8.0.0", "8.0.1", ""), ("9.0.0", "v10.0.0", "text"), ("8.9.0", "v8.10.0", "text"), ("8.0.9", "v8.0.10", "text"),
]
NOT_OLDER = [
    ("8.0.0", "v8.0.0", "equal"), ("8.0.0", "8.0.0", "equal"), ("8.0.1", "v8.0.0", ""), ("8.1.0", "v8.0.0", ""),
    ("9.0.0", "v8.0.0", ""), ("10.0.0", "v9.0.0", "text"), ("8.10.0", "v8.9.0", "text"),
    ("8.0.10", "v8.0.9", "text"),
]


def _closes(tmp_path: Path, version: str, tag: str, script: str | None = None) -> bool:
    calls = _run(tmp_path, _reported(version), [], closed=[_closed(10)], release=_release(tag), script=script)
    assert all(c[0] != "update" or c[3] == "not_planned" for c in calls), "never a completed close"
    return CLOSE in calls


@needs_node
@pytest.mark.parametrize("version, tag, _twin", OLDER, ids=[f"{v}<{t}" for v, t, _ in OLDER])
def test_a_version_older_than_the_latest_release_is_closed(tmp_path, version, tag, _twin):
    calls = _run(tmp_path, _reported(version), [], closed=[_closed(10)], release=_release(tag))
    assert calls == [["comment", 12, _comment(FP_A, 10, version, tag)], ["label", 12, ["duplicate"]], CLOSE]


@needs_node
@pytest.mark.parametrize("version, tag, _twin", NOT_OLDER, ids=[f"{v}>={t}" for v, t, _ in NOT_OLDER])
def test_a_version_equal_to_or_newer_than_the_latest_release_stays_open(tmp_path, version, tag, _twin):
    calls, reads = _run_full(tmp_path, _reported(version), [], closed=[_closed(10)], release=_release(tag))
    assert calls == []
    # It got as far as the comparison: the release was read.
    assert reads[-2:] == [RELEASE_READ, ["list", "open", "health-check"]]


# The Action's comparison, and two mutants of it the tables above must catch.
_IS_OLDER = "return n !== undefined && a[n] < b[n];"
_MUTANTS = {
    "text": "return a.join('.') < b.join('.');",
    "equal": "return n === undefined || a[n] < b[n];",
}


@needs_node
@pytest.mark.parametrize("mutant", sorted(_MUTANTS))
def test_mutant_comparisons_are_caught(tmp_path, mutant):
    """Twin: the same cases run against a mutant of the comparison, and every case marked for it changes answer."""
    script = _script()
    assert script.count(_IS_OLDER) == 1, "the comparison the mutants replace is in the script, once"
    mutated = script.replace(_IS_OLDER, _MUTANTS[mutant])
    marked = [(v, t, True) for v, t, m in OLDER if m == mutant] + [(v, t, False) for v, t, m in NOT_OLDER if m == mutant]
    assert marked, "each mutant has cases that tell it apart"
    for version, tag, older in marked:
        assert _closes(tmp_path, version, tag) is older, (version, tag)
        assert _closes(tmp_path, version, tag, script=mutated) is not older, (mutant, version, tag)


@needs_node
@pytest.mark.parametrize(
    "body",
    [
        _body(FP_S),
        _env_body(None),
        _env_body(""),
        _env_body("N/A"),
        _env_body("5.0"),
        _env_body("5"),
        _env_body("5.0.0.1"),
        _env_body("5.0.0-beta.1"),
        _env_body("5.0.0+build.7"),
        _env_body("05.0.0"),
        _env_body("V5.0.0"),
        _env_body("5.0.0 (plugin)"),
        _env_body("5.0.0 | 4.0.0"),
        # Two rows, even of one value, are not one Module Version.
        _env_body("5.0.0") + "| Module Version | 5.0.0 |\n",
        # A row outside the Environment section, or inside a comment, is not the table's.
        _body(FP_S) + "\n## Evidence\n| Module Version | 5.0.0 |\n\n## Environment\n| Date | 2026-11-02 |\n",
        _env_body(None) + "<!-- | Module Version | 5.0.0 | -->\n",
        # A table after another bold label, or under another header cell, is not the Environment table.
        _body(FP_S) + "\n**Evidence:**\n\n| Module Version | 5.0.0 |\n",
        _body(FP_S) + "\n| Evidence | |\n|---|---|\n| Module Version | 5.0.0 |\n",
        # A row in each of two Environment tables is two rows.
        _env_body("5.0.0") + "\n**Environment:**\n\n| Module Version | 4.0.0 |\n",
        # The template as filed, its Module Version left blank.
        _template(fp=FP_A, severity="bug", section_fp=FP_S),
    ],
    ids=["no-environment", "no-row", "empty", "n-a", "two-parts", "one-part", "four-parts", "prerelease", "build",
         "leading-zero", "capital-v", "trailing-words", "three-cells", "two-rows", "outside-environment",
         "in-a-comment", "other-label", "other-header-cell", "two-tables", "template-blank"],
)
def test_no_single_plain_module_version_leaves_the_issue_open_with_no_lookup(tmp_path, body):
    calls, reads = _run_full(tmp_path, _reported(body=body), [], closed=[_closed(10)], release=LATEST)
    assert calls == []
    assert reads == [["list", "open", f"health-check,{FP_A}"], ["list", "open", "health-check"]]
    _assert_the_twin_closes(tmp_path)


@needs_node
@pytest.mark.parametrize(
    "closed",
    [
        [],
        [_closed(10, reason="not_planned")],
        [_closed(10, reason="duplicate")],
        [_closed(10, reason=None)],
        # A later issue is never the earlier one, and a pull request is not an issue.
        [_closed(14)],
        [_closed(10, pull_request={"url": "https://example.invalid/pr/10"})],
        # Another fingerprint's fix is not this one's.
        [_closed(10, fp=FP_B)],
    ],
    ids=["none", "not-planned", "duplicate", "no-reason", "later", "pull-request", "other-fingerprint"],
)
def test_no_earlier_completed_issue_leaves_the_issue_open_with_no_release_read(tmp_path, closed):
    calls, reads = _run_full(tmp_path, _reported("5.0.0"), [], closed=closed, release=LATEST)
    assert calls == []
    assert RELEASE_READ not in reads and ["list", "closed", f"health-check,{FP_A}"] in reads


@needs_node
@pytest.mark.parametrize(
    "closed, release, closed_error",
    [
        ([_closed(10)], None, None),
        ([_closed(10)], {"status": 500}, None),
        ([_closed(10)], {"status": 403}, None),
        ([_closed(10)], None, 502),
        ([_closed(10)], _release("v9.0.0-rc.1"), None),
        ([_closed(10)], _release("latest"), None),
        ([_closed(10)], {"published_at": LATEST["published_at"]}, None),
        # The fix closed after the latest release was published may not be in it.
        ([_closed(10)], _release("v8.0.0", published_at="2026-11-02T08:00:00Z"), None),
        ([_closed(10)], {"tag_name": "v8.0.0"}, None),
        ([_closed(10, closed_at=None)], LATEST, None),
        ([_closed(10), _closed(4, closed_at="2026-11-03T09:00:00Z")], LATEST, None),
    ],
    ids=["no-release", "release-500", "release-403", "closed-list-502", "prerelease-tag", "tag-not-a-version",
         "no-tag", "fix-after-release", "no-publish-date", "no-close-date", "a-fix-after-release"],
)
def test_every_doubt_after_the_body_leaves_the_issue_open(tmp_path, closed, release, closed_error):
    assert _run(tmp_path, _reported("5.0.0"), [], closed=closed, release=release, closed_error=closed_error) == []
    _assert_the_twin_closes(tmp_path)


@needs_node
@pytest.mark.parametrize("repo", ["o/r", "armelhbobdad/bmad-module-ultracode-goal-fork", "someone/bmad-module-ultracode-goal"])
def test_a_copy_of_the_action_in_another_repository_closes_nothing_this_way(tmp_path, repo):
    """Another repository's releases are not module versions: the report stays open, and nothing is looked up."""
    calls, reads = _run_full(tmp_path, _reported("5.0.0"), [], closed=[_closed(10)], release=LATEST, repo=repo)
    assert calls == []
    assert reads == [["list", "open", f"health-check,{FP_A}"], ["list", "open", "health-check"]]
    # Twin: in the module's repository, named in any letter case, the same report is closed.
    calls = _run(tmp_path, _reported("5.0.0"), [], closed=[_closed(10)], release=LATEST,
                 repo="ArmelHBobdad/BMAD-Module-UltraCode-Goal")
    assert calls == [["comment", 12, _comment(FP_A, 10, "5.0.0", "v8.0.0")], ["label", 12, ["duplicate"]], CLOSE]


@needs_node
def test_a_report_left_open_is_still_flagged_and_one_closed_is_not(tmp_path):
    keyless = _issue(9, FP_S, None)
    _assert_flagged(_run(tmp_path, _reported("8.0.0"), [keyless], closed=[_closed(10)], release=LATEST),
                    12, "#9", FP_S)
    calls = _run(tmp_path, _reported("5.0.0"), [keyless], closed=[_closed(10)], release=LATEST)
    assert [c[0] for c in calls] == ["comment", "label", "update"] and calls[-1] == CLOSE


@needs_node
def test_an_earlier_open_issue_still_takes_the_report_with_no_closed_lookup(tmp_path):
    calls, reads = _run_full(tmp_path, _reported("5.0.0"), [_issue(11, FP_A, FP_S)], closed=[_closed(10)],
                             release=LATEST)
    assert calls[0][2].startswith(f"Auto-deduped: same fingerprint `{FP_A}` as #11.")
    assert calls[1:] == [["label", 12, ["duplicate"]], CLOSE, ["react", 11, "+1"]]
    assert reads == [["list", "open", f"health-check,{FP_A}"]]
    # Twin: with no earlier open issue, the same report is closed against the fixed one.
    _assert_the_twin_closes(tmp_path)


def _closed_pages(fixed_number: int) -> list[dict]:
    """A full first page of later closed duplicates, then the fixed issue alone on page 2 (newest first)."""
    return [_closed(n, reason="not_planned") for n in range(400, 500)] + [_closed(fixed_number)]


@needs_node
def test_a_fixed_issue_past_the_first_page_of_closed_issues_is_found(tmp_path):
    report = _issue(600, FP_A, FP_S, body=_env_body("5.0.0"))
    calls, reads = _run_full(tmp_path, report, [], closed=_closed_pages(3), release=LATEST)
    assert calls == [["comment", 600, _comment(FP_A, 3, "5.0.0", "v8.0.0")], ["label", 600, ["duplicate"]],
                     ["update", 600, "closed", "not_planned"]]
    assert reads.count(["list", "closed", f"health-check,{FP_A}"]) == 2
    # Mutant twin: a reader of the first page alone misses the fixed issue and leaves the report open.
    script = _script()
    paged = "closed = await github.paginate("
    assert script.count(paged) == 1
    one_page = script.replace(paged, "closed = await (async (fn, p) => (await fn(p)).data)(")
    assert _run(tmp_path, report, [], closed=_closed_pages(3), release=LATEST, script=one_page) == []


def test_the_action_never_closes_as_completed():
    """A health check reads a completed close of the issue it filed as a fix, and would report again as a regression."""
    script = _script()
    assert re.findall(r"state_reason: '(\w+)'", script) == ["not_planned", "not_planned"]
    # The one `completed` it holds is the state it reads on an earlier issue.
    assert script.count("'completed'") == 1 and "m.state_reason === 'completed'" in script


@needs_node
def test_the_reporters_text_reaches_no_expression_and_no_comment(tmp_path):
    """The issue text is the reporter's: the script reads it from the API at run time, never through `${{ }}`, and
    the comment it posts holds only the checked fingerprint, issue number, version numbers and release tag."""
    assert "${{" not in _script()
    hostile = "${{ secrets.GITHUB_TOKEN }} `$(touch pwned)` [link](https://example.invalid)"
    body = _body(FP_S) + f"\n## Environment\n| Field | Value |\n|---|---|\n| OS | {hostile} |\n| Module Version | 5.0.0 |\n"
    issue = {**_reported(body=body), "title": f"[health-check][bug][{FP_A}] {hostile}"}
    calls = _run(tmp_path, issue, [], closed=[_closed(10, title=hostile)], release=LATEST)
    assert calls == [["comment", 12, _comment(FP_A, 10, "5.0.0", "v8.0.0")], ["label", 12, ["duplicate"]], CLOSE]


def test_the_release_is_read_with_contents_read_and_nothing_broader():
    workflow = _workflow()
    assert workflow["permissions"] == {"issues": "write", "contents": "read"}
    assert "permissions" not in workflow["jobs"]["dedup"]


def test_the_header_and_the_docs_say_an_outdated_report_is_closed_as_not_planned():
    header = WORKFLOW.read_text(encoding="utf-8").split('"on":', 1)[0]
    flowed = " ".join(re.sub(r"^#\s?", "", header, flags=re.MULTILINE).split())
    assert "an earlier issue with the same fingerprint that was closed as completed" in flowed
    assert "adds the `duplicate` label and closes the new issue as not planned. Never as completed" in flowed
    assert "Any doubt leaves the issue open and goes on to step 5" in flowed
    assert ("Environment table (under an `Environment` heading, after a bold `Environment` label, or headed by an "
            "`Environment` cell: copies have written it all three ways)") in flowed
    docs = " ".join(DOCS_MD.read_text(encoding="utf-8").split())
    level3 = docs[docs.index("3. **Server-side**"):]
    level3 = level3[:level3.index("One limit:")]
    assert ("but an earlier one with it was closed as completed, and the new issue's Environment table gives a Module "
            "Version lower than the repository's latest release (compared number by number), the copy that filed it "
            "may lack the fix") in level3
    assert ("the Action comments that the earlier issue was fixed, names the latest release, and asks the reporter to "
            "update and to report again if the behaviour is still there on that release, then adds the `duplicate` "
            "label and closes the issue as not planned. It never closes one as completed") in level3
    assert ("A Module Version that is missing, given twice or not a plain `X.Y.Z`, a repository with no release or whose "
            "latest release's tag is not a plain `X.Y.Z`, a fix closed after the latest release was published, or a "
            "failed call leaves the issue open for a maintainer.") in level3
    assert ("A copy of the Action in another repository closes nothing this way, since only this module's repository "
            "releases module versions.") in level3
    assert "a repository other than this module's (a copy of the Action elsewhere" in flowed


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
    match = re.search(r"const SECTION_RE = /(.+)/mi;", _script())
    assert match, "SECTION_RE is a multiline, case-blind regex literal in the Action's script"
    return re.compile(match.group(1), re.MULTILINE | re.IGNORECASE)


def test_the_section_line_of_a_filed_body_matches_the_actions_section_re():
    payload = _fingerprint("bug")
    match = _section_re().search(payload["body_header"])
    assert match and match.group(1) == payload["legacy_fp"]
    # The keyed fingerprint is never read as the section's.
    assert payload["fp"] != payload["legacy_fp"]
    # A regression's opening line above the header leaves the line where SECTION_RE reads it.
    opened = f"Regression of https://github.com/o/r/issues/1 (resolved 2026-07-19).\n\n{payload['body_header']}"
    assert _section_re().search(opened).group(1) == payload["legacy_fp"]


def test_the_issue_templates_section_line_matches_once_filled_in():
    lines = [line for line in ISSUE_TEMPLATE.read_text(encoding="utf-8").splitlines()
             if line.startswith("Section fingerprint:")]
    assert lines == ["Section fingerprint: `fp-XXXXXXX`"]
    match = _section_re().search(lines[0].replace("fp-XXXXXXX", FP_S))
    assert match and match.group(1) == FP_S


@needs_node
def test_the_action_reads_the_section_line_of_a_filed_body(tmp_path):
    payload = _fingerprint("bug")
    fp, section_fp = payload["fp"], payload["legacy_fp"]
    body = payload["body_header"] + "\n## Finding\nOne sentence.\n"
    calls = _run(tmp_path, _issue(12, fp, None, body=body), [_issue(9, section_fp, None)])
    _assert_flagged(calls, 12, "#9", section_fp)

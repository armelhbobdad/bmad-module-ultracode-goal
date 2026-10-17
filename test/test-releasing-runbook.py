#!/usr/bin/env python3
"""docs/_internal/RELEASING.md: the maintainer runbook's commands and records.

The runbook's commands run against the live repository and the npm
registry, mostly during an incident, so these tests check what can be
checked without them: every command reads the ruleset by name and stops on
an empty id, the baselines the commands read are committed where they say,
every restore reads the one committed filter, which agrees with the
baseline, every pointer the workflows and tools give into the runbook lands
on a section, and the prose names no planning label and no file outside the
repository.

Covers:
  - Preconditions: before Branch Protection, with a check for gh, its admin
    rights, jq, node, the npm login, the package's owners, npm's version and
    the account's 2FA
  - No command names a ruleset or environment id; a recorded id is labelled
    as the value at the time of writing
  - Every ruleset lookup pipes gh into jq with release.yaml's guard and is
    followed by an empty-id check before any use; the guard turns an error
    body or a list without main-protection into nothing (run with jq), and
    names the ruleset tools/release-state.js and
    tools/check-required-checks.js read
  - The baselines are committed in release-audits/baselines/, parse, and
    are the files the capture writes and the restore reads; there is no
    branch-policies baseline while the environment has no branch policy
  - Every restore snippet reads the one filter file,
    release-audits/baselines/ruleset-put.jq, and the drill record names it;
    run on the baseline, it keeps every field a PUT takes, every rule and
    every rule parameter, do_not_enforce_on_create among them (a PUT takes
    it); run on a ruleset with a null integration_id, it drops a required
    check's null keys, which a PUT has refused, and keeps its other keys
  - The restore shows its diff and sends the PUT only on an answer of y
    (run with a stub gh)
  - The environment's restore JSON agrees with its baseline, which the
    runbook leaves to this test instead of a check by hand
  - The required-checks list: the section check-required-checks.js names
    holds it between its markers
  - Scenario C is retired, and the matrix lists every scenario that remains
  - Every `RELEASING.md, "<name>"` pointer in .github/ and tools/ names a
    part of exactly one ### heading, every `RELEASING.md § <section>`
    pointer and `RELEASING.md, <section>` pointer a heading
  - Scenario F revokes with npm trust and says what to do without an npm
    login; the Trusted Publisher section inspects with npm trust list, has
    a slot for the last check and says who approves a publish
  - No planning label, no reference outside the repository, nothing
    described as future work
  - The dist-tag policy, the registry's stale tags as a dated observation,
    its post-publish step, no verification comment expecting rc or alpha,
    and the install smoke dispatch with an exact version, the run found by
    its title, and its install-smoke.json record

The tests that run jq or bash skip where those are missing, and on Windows.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
RELEASING = REPO_ROOT / "docs" / "_internal" / "RELEASING.md"
RELEASE_YAML = REPO_ROOT / ".github" / "workflows" / "release.yaml"
INSTALL_SMOKE = REPO_ROOT / ".github" / "workflows" / "install-smoke.yaml"
RELEASE_STATE = REPO_ROOT / "tools" / "release-state.js"
CHECK_REQUIRED = REPO_ROOT / "tools" / "check-required-checks.js"
BASELINES = REPO_ROOT / "release-audits" / "baselines"
RULESET_BASELINE = BASELINES / "baseline-ruleset-main-protection.json"
ENV_BASELINE = BASELINES / "baseline-env-release.json"
POLICIES_BASELINE = BASELINES / "baseline-env-release-branch-policies.json"
PUT_FILTER = BASELINES / "ruleset-put.jq"
PUT_FILTER_RUN = "jq -f release-audits/baselines/ruleset-put.jq"
REPOSITORY = "armelhbobdad/bmad-module-ultracode-goal"
RULESET = "main-protection"

# The guard release.yaml's Wait step uses: any answer but a list of
# rulesets, or a list without main-protection, gives nothing.
GUARD = """jq -r 'if type=="array" then (map(select(.name=="main-protection")) | .[0].id // empty) else empty end'"""
# Fields of a ruleset GET that a PUT does not take.
READ_ONLY = {"id", "source_type", "source", "node_id", "created_at", "updated_at", "current_user_can_bypass", "_links"}

needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="runs the lookup's own jq filter")
needs_shell = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None or shutil.which("jq") is None,
    reason="runs the restore snippet under bash with jq and a stub gh",
)


def text() -> str:
    return RELEASING.read_text(encoding="utf-8")


def section(heading: str) -> str:
    """The body of the section whose heading starts with `heading`, up to the
    next heading of the same or a higher level. A `#` line inside a fenced
    block is a shell comment, not a heading."""
    lines = text().splitlines(keepends=True)
    fenced = False
    level = None
    body: list[str] = []
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        heading_match = None if fenced else re.match(r"^(#+) (.*)", line)
        if level is None:
            if heading_match and heading_match.group(2).startswith(heading):
                level = len(heading_match.group(1))
            continue
        if heading_match and len(heading_match.group(1)) <= level:
            break
        body.append(line)
    assert level is not None, heading
    return "".join(body)


def headings(level: str = "#+") -> list[str]:
    """Every heading of the runbook at `level`, outside fenced blocks."""
    found = []
    fenced = False
    for line in text().splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else re.match(rf"^({level}) (.*)$", line)
        if match:
            found.append(match.group(2).strip())
    return found


def code_blocks(body: str) -> list[str]:
    return re.findall(r"^\s*```bash\n(.*?)^\s*```", body, re.MULTILINE | re.DOTALL)


# --------------------------------------------------------------------------
# Preconditions, ids, guarded lookups, baselines
# --------------------------------------------------------------------------


def test_preconditions_come_first_with_a_check_for_each_tool():
    body = text()
    assert body.index("## Preconditions\n") < body.index("## Branch Protection on `main`\n")
    checks = "\n".join(code_blocks(section("Preconditions")))
    for command in (
        "gh auth status",
        f"gh api repos/{REPOSITORY} --jq .permissions.admin",
        "jq --version",
        "node --version",
        "npm whoami",
        "npm owner ls bmad-module-ultracode-goal",
        "npm --version",
        'npm profile get "two-factor auth"',
    ):
        assert command in checks, command
    prose = section("Preconditions")
    for need in ("admin rights", "`jq`", "publish rights", "11.15.0", "2FA"):
        assert need in prose, need


def test_no_command_names_a_ruleset_or_environment_id():
    for block in code_blocks(text()):
        assert not re.search(r"rulesets/\d", block), block
        assert not re.search(r"environments/\d", block), block
    ruleset = json.loads(RULESET_BASELINE.read_text(encoding="utf-8"))
    environment = json.loads(ENV_BASELINE.read_text(encoding="utf-8"))
    for recorded in (str(ruleset["id"]), str(environment["id"])):
        lines = [line for line in text().splitlines() if recorded in line]
        assert lines, recorded
        assert all("at the time of writing" in line for line in lines), lines


def test_every_ruleset_lookup_is_guarded_before_the_id_is_used():
    blocks = [block for block in code_blocks(text()) if "RULESET_ID" in block]
    assert len(blocks) >= 3
    for block in blocks:
        assign = block.index("RULESET_ID=$(")
        lookup = block[assign : block.index("\n", block.index("\n", assign) + 1)]
        assert "2>/dev/null \\\n  | " + GUARD + ")" in lookup, lookup
        guard = block.index('if [ -z "$RULESET_ID" ]; then', assign)
        # Nothing reads the id between the lookup and its empty-id check.
        assert "$RULESET_ID" not in block[assign + len("RULESET_ID=$(") : guard], block
        assert "--jq" not in lookup


def test_the_lookup_is_the_one_release_yaml_and_the_tools_use():
    assert GUARD.removeprefix("jq -r ") in RELEASE_YAML.read_text(encoding="utf-8")
    assert f"const RULESET_NAME = '{RULESET}';" in RELEASE_STATE.read_text(encoding="utf-8")
    assert f"const RULESET = '{RULESET}';" in CHECK_REQUIRED.read_text(encoding="utf-8")
    # The runbook names no other ruleset in a lookup.
    for block in code_blocks(text()):
        if "/rulesets" in block:
            assert set(re.findall(r'select\(\.name=="([^"]+)"\)', block)) <= {RULESET}, block


@needs_jq
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param([{"id": 7, "name": "Other"}, {"id": 13, "name": RULESET}], "13", id="list with main-protection"),
        pytest.param([{"id": 7, "name": "Other"}], "", id="list without main-protection"),
        pytest.param({"message": "Not Found", "status": "404"}, "", id="error body"),
    ],
)
def test_the_lookup_gives_nothing_unless_a_ruleset_is_named_main_protection(answer, expected):
    program = GUARD.removeprefix("jq -r ").strip("'")
    proc = subprocess.run(["jq", "-r", program], input=json.dumps(answer), capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == expected


def test_the_baselines_are_committed_where_the_capture_writes_and_the_restore_reads():
    ruleset = json.loads(RULESET_BASELINE.read_text(encoding="utf-8"))
    environment = json.loads(ENV_BASELINE.read_text(encoding="utf-8"))
    assert (ruleset["name"], ruleset["target"]) == (RULESET, "branch")
    assert environment["name"] == "release"
    body = text()
    capture = code_blocks(body[body.index("**Capture.**") :])[0]
    assert "DIR=release-audits/baselines" in capture
    for path in (RULESET_BASELINE, ENV_BASELINE, POLICIES_BASELINE):
        assert f" {path.name}\n" in capture, path.name
    restore = code_blocks(section("Restore from a saved baseline"))[0]
    assert f"release-audits/baselines/{RULESET_BASELINE.name}" in restore
    assert "_bmad-output" not in body
    assert "ls -t" not in body


def test_the_branch_policies_baseline_exists_exactly_when_the_environment_has_a_branch_policy():
    environment = json.loads(ENV_BASELINE.read_text(encoding="utf-8"))
    policy = environment["deployment_branch_policy"]
    assert POLICIES_BASELINE.is_file() == (policy is not None)
    snapshots = section("Baseline snapshots")
    if policy is None:
        # The runbook says why there is no file, and when there will be one.
        assert "There is no branch-policies baseline while the environment has no branch policy" in snapshots
        assert "`deployment_branch_policy` | `null`" in section("Release Environment")
    else:
        policies = json.loads(POLICIES_BASELINE.read_text(encoding="utf-8"))
        assert [p["name"] for p in policies["branch_policies"]] == ["main"]


# --------------------------------------------------------------------------
# The restore drill, the required-checks list, Scenario C, Scenario F
# --------------------------------------------------------------------------


def test_every_restore_snippet_uses_the_one_filter():
    assert PUT_FILTER.is_file()
    restores = [
        block
        for block in code_blocks(text())
        if ("--method PUT" in block or "--method POST" in block) and "/rulesets" in block
    ]
    assert len(restores) >= 2
    for block in restores:
        assert PUT_FILTER_RUN in block, block
    # One copy of the filter: none written out in the runbook.
    assert "FILTER=" not in text()
    assert "jq '{name, target" not in text()


def test_the_restore_asks_before_its_put():
    restore = code_blocks(section("Restore from a saved baseline"))[0]
    diff = restore.index("| diff - /tmp/restore.json")
    ask = restore.index("read -r ok")
    put = restore.index('[ "$ok" = y ] && gh api --method PUT')
    assert diff < ask < put, restore
    assert restore.count("--method PUT") == 1


@needs_shell
@pytest.mark.parametrize(
    ("answer", "sends"),
    [
        pytest.param("y", True, id="yes"),
        pytest.param("n", False, id="no"),
        pytest.param("", False, id="enter"),
    ],
)
def test_the_restore_sends_the_put_only_on_yes(tmp_path, answer, sends):
    body = tmp_path / "restore.json"
    restore = code_blocks(section("Restore from a saved baseline"))[0].replace("/tmp/restore.json", body.as_posix())
    script = tmp_path / "restore.sh"
    script.write_text(restore, encoding="utf-8")
    log = tmp_path / "gh.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # The live ruleset is the baseline, so the diff prints nothing.
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{log.as_posix()}"\n'
        'case "$*" in\n'
        "  *'--method PUT'*) echo '{}' ;;\n"
        f"  */rulesets/*) cat '{RULESET_BASELINE.as_posix()}' ;;\n"
        f"""  */rulesets) echo '[{{"id": 13, "name": "{RULESET}"}}]' ;;\n"""
        "esac\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    proc = subprocess.run(
        ["bash", str(script)], input=answer + "\n", cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60
    )
    assert "PUT " + body.as_posix() + " to ruleset 13? [y/N]" in proc.stdout, proc.stdout + proc.stderr
    assert not proc.stdout.startswith("<") and "---" not in proc.stdout, proc.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    puts = [call for call in calls if "--method PUT" in call]
    assert puts == ([f"api --method PUT repos/{REPOSITORY}/rulesets/13 --input {body.as_posix()}"] if sends else [])


@needs_jq
def test_the_filter_keeps_every_field_a_put_takes_minus_what_a_put_refused():
    proc = subprocess.run(
        ["jq", "-f", str(PUT_FILTER), str(RULESET_BASELINE)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    ruleset = json.loads(RULESET_BASELINE.read_text(encoding="utf-8"))
    assert set(body) == set(ruleset) - READ_ONLY
    assert [rule["type"] for rule in body["rules"]] == [rule["type"] for rule in ruleset["rules"]]
    for kept, saved in zip(body["rules"], ruleset["rules"]):
        if saved["type"] != "required_status_checks":
            assert kept == saved
            continue
        # Every parameter but the checks is kept: a PUT takes
        # do_not_enforce_on_create, so a restore sends its saved value.
        assert {key: value for key, value in kept["parameters"].items() if key != "required_status_checks"} == {
            key: value for key, value in saved["parameters"].items() if key != "required_status_checks"
        }
        checks = kept["parameters"]["required_status_checks"]
        assert [c["context"] for c in checks] == [c["context"] for c in saved["parameters"]["required_status_checks"]]
        assert all(value is not None for check in checks for value in check.values())
    assert body["bypass_actors"] == ruleset["bypass_actors"]


@needs_jq
def test_the_filter_drops_only_a_checks_null_keys():
    # The baseline has no null key, so a ruleset that has one shows the drop.
    ruleset = {
        "name": RULESET,
        "target": "branch",
        "enforcement": "active",
        "conditions": {},
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": False,
                    "do_not_enforce_on_create": True,
                    "required_status_checks": [
                        {"context": "a", "integration_id": None},
                        {"context": "b", "integration_id": 15368},
                    ],
                },
            }
        ],
        "bypass_actors": [],
    }
    proc = subprocess.run(
        ["jq", "-f", str(PUT_FILTER)], input=json.dumps(ruleset), capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    parameters = json.loads(proc.stdout)["rules"][0]["parameters"]
    assert parameters["do_not_enforce_on_create"] is True
    assert parameters["required_status_checks"] == [{"context": "a"}, {"context": "b", "integration_id": 15368}]


def test_the_restore_drill_has_a_record_that_names_its_filter():
    body = text()
    drill = body[body.index("**Restore drill.**") :]
    table = re.search(r"^\| Date \| Target \| Filter \| Result \|\n\| -.*\n((?:\|.*\n)+)", drill, re.MULTILINE)
    assert table, "no drill record table"
    rows = [row.strip("|").split("|") for row in table.group(1).splitlines()]
    assert rows
    for cells in rows:
        assert "`release-audits/baselines/ruleset-put.jq`" in cells[2], cells
        # A row is a dated run, or says plainly that none has run.
        date = cells[0].strip()
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or date == "not run yet", cells


def test_the_environment_restore_agrees_with_its_baseline():
    restore = code_blocks(section("Restore / re-apply"))[0]
    put = json.loads(re.search(r"<<'JSON'\n(.*?)\nJSON", restore, re.DOTALL).group(1))
    environment = json.loads(ENV_BASELINE.read_text(encoding="utf-8"))
    reviewers = next(rule for rule in environment["protection_rules"] if rule["type"] == "required_reviewers")
    timers = [rule["wait_timer"] for rule in environment["protection_rules"] if rule["type"] == "wait_timer"]
    assert put["wait_timer"] == (timers[0] if timers else 0)
    assert put["prevent_self_review"] == reviewers["prevent_self_review"]
    assert put["reviewers"] == [{"type": r["type"], "id": r["reviewer"]["id"]} for r in reviewers["reviewers"]]
    assert put["deployment_branch_policy"] == environment["deployment_branch_policy"]
    posted = re.findall(r'\{ "name": "([^"]+)" \}', restore)
    if POLICIES_BASELINE.is_file():
        policies = json.loads(POLICIES_BASELINE.read_text(encoding="utf-8"))
        assert posted == [p["name"] for p in policies["branch_policies"]]
    else:
        assert posted == []
    # The runbook leaves this comparison to this test, not to a check by hand.
    assert "`test/test-releasing-runbook.py` checks on every pull request" in section("Baseline snapshots")
    assert "check that their JSON still matches" not in text()


def test_the_recommended_branch_policy_is_marked_as_not_applied_while_it_is_not():
    environment = json.loads(ENV_BASELINE.read_text(encoding="utf-8"))
    hardening = section("Restricting deployments to `main`")
    if environment["deployment_branch_policy"] is None:
        assert hardening.startswith("\n**Recommended, not applied yet.**")
    blocks = code_blocks(hardening)
    assert '"custom_branch_policies": true' in blocks[0]
    assert '{ "name": "main" }' in blocks[0]


def test_the_required_checks_list_sits_in_the_section_the_tool_names():
    tool = CHECK_REQUIRED.read_text(encoding="utf-8")
    named = re.search(r"const SECTION = `\$\{RELEASING\}, ([^`]+)`;", tool).group(1)
    body = section(named)
    start = body.index("<!-- required-checks:start -->")
    end = body.index("<!-- required-checks:end -->")
    items = re.findall(r"^- `([^`]+)`$", body[start:end], re.MULTILINE)
    assert "em-dash" in items
    assert len(items) == len(set(items))


def test_scenario_c_is_retired_and_the_matrix_lists_every_scenario_left():
    body = text()
    scenarios = set(re.findall(r"^### Scenario ([A-Z])\b", body, re.MULTILINE))
    assert scenarios == {"A", "B", "D", "E", "F", "G", "H"}
    assert "**Scenario C (unpublish) is retired.**" in body
    matrix = section("Cross-reference matrix")
    rows = set(re.findall(r"^\| ([A-Z])\s+\|", matrix, re.MULTILINE))
    assert rows == scenarios
    assert "time.modified" not in body


# The pointers the workflows and tools give into the runbook.
POINTER_FILES = sorted(
    [*(REPO_ROOT / ".github" / "workflows").glob("*.y*ml"), *(REPO_ROOT / "tools").glob("*.js")]
)


def flat(path: Path) -> str:
    """The file's text with each line break and the comment marker or
    indent after it read as one space, so a pointer wrapped across comment
    lines reads as one, and shell-escaped quotes as plain ones."""
    joined = re.sub(r"\s*\n\s*(?:#|//|\*)?\s*", " ", path.read_text(encoding="utf-8"))
    return joined.replace('\\"', '"')


def test_every_named_pointer_lands_on_exactly_one_heading():
    names = set()
    for path in POINTER_FILES:
        names |= set(re.findall(r'RELEASING\.md, "([^"]+)"', flat(path)))
    assert {
        "Bot PR merged, but the version was not published",
        "Tag exists but npm publish failed",
        "npm publish succeeded but GitHub Release / tag push failed",
    } <= names
    third = headings("###")
    for name in sorted(names):
        holding = [heading for heading in third if f'"{name}"' in heading]
        assert len(holding) == 1, (name, holding)


def test_every_section_pointer_lands_on_a_heading():
    all_headings = headings()
    sections = set()
    for path in POINTER_FILES:
        text_ = flat(path)
        for at in re.finditer(r"RELEASING\.md", text_):
            window = text_[at.end() : at.end() + 120]
            # "§ <section>", one or several ("§ A and § B"), up to the end of the clause.
            if window.startswith(" §"):
                sections |= set(re.findall(r"§ ([A-Za-z][^.,§()]*?)(?= and §|[.,)]| Paired)", window))
            # ", <Section>)" without quotes: a heading that starts with it.
            plain = re.match(r", ([A-Z][a-z]+(?: [a-z]+)*)\)", window)
            if plain:
                sections.add(plain.group(1))
    assert {"npm Trusted Publisher", "The docs site", "After the publish", "Repo settings"} <= sections, sections
    for name in sorted(sections):
        assert any(heading.startswith(name) for heading in all_headings), name
    # install-smoke.yaml also points to the dist-tag policy.
    assert "§ Dist-tag policy" in flat(INSTALL_SMOKE)
    assert "Dist-tag policy" in all_headings


def test_scenario_f_revokes_with_npm_trust_and_says_what_to_do_without_a_login():
    scenario = section("Scenario F")
    assert "npm trust list bmad-module-ultracode-goal" in scenario
    assert "npm trust revoke bmad-module-ultracode-goal --id=<id>" in scenario
    assert "**No maintainer can sign in to npm**" in scenario
    assert "Contact npm support" in scenario
    assert "11.15.0" in scenario and "2FA" in scenario


def test_the_trusted_publisher_section_inspects_with_npm_trust_list():
    publisher = section("npm Trusted Publisher")
    assert "npm trust list bmad-module-ultracode-goal --json" in publisher
    assert "npm 11.15.0 or later" in publisher
    for field in ('"type": "github"', '"file": "release.yaml"', '"environment": "release"'):
        assert field in publisher, field
    assert "UI-only" not in publisher
    assert "self-approval" in publisher
    assert "admin-bypass merge" in publisher
    # The slot for the last check: a date once one ran, never an invented one.
    last = re.search(r"^\*\*Last checked with `npm trust list`:\*\* (.*)$", publisher, re.MULTILINE)
    assert last, "no slot for the last npm trust list check"
    assert last.group(1).startswith("not yet checked") or re.match(r"\d{4}-\d{2}-\d{2}", last.group(1))
    # The publisher binds on these four fields, exactly.
    for cell in ("`armelhbobdad`", "`bmad-module-ultracode-goal`", "`release.yaml`", "`release`"):
        assert cell in publisher, cell


# --------------------------------------------------------------------------
# Planning labels, outside references, future tense
# --------------------------------------------------------------------------

LABEL = re.compile(r"\b(?:Story \d|NFR\d|FR\d|Epic \d|AC #?\d)")


def test_no_planning_label_and_no_issue_number():
    body = text()
    assert not LABEL.findall(body), sorted(set(LABEL.findall(body)))
    # No issue or pull request number: they would cite another tracker.
    assert not re.search(r"(?<![\w&])#\d{2,}(?![\dA-Fa-f])", body)


def test_no_reference_outside_the_repository():
    body = text()
    assert "_bmad-output" not in body
    assert "research doc" not in body
    assert "release-audits/v" not in body


def test_nothing_is_described_as_future_or_pending():
    body = text()
    for stale in ("The future `release.yaml`", "will use to push", "conventional-changelog", "RELEASE_RULESET_ID --body"):
        assert stale not in body, stale


# --------------------------------------------------------------------------
# Dist-tag policy, install smoke dispatch and record
# --------------------------------------------------------------------------


def test_the_dist_tag_policy_and_its_post_publish_step():
    policy = section("Dist-tag policy")
    assert "`latest` is the only permanent dist-tag." in policy
    assert "`alpha`, `beta` and `rc` exist only while a prerelease line is open" in policy
    # The registry's stale tags are an observation with its date, not a fact.
    assert re.search(r"On \d{4}-\d{2}-\d{2} npm still carried `alpha`", policy), policy
    after = section("After the publish")
    assert "npm dist-tag rm bmad-module-ultracode-goal" in after
    assert '# expected: {"latest":"<version>"}' in after
    for block in code_blocks(text()):
        for line in block.splitlines():
            if "expected" in line:
                assert not re.search(r'"(alpha|rc)"\s*:', line), line


def load_run_name() -> str:
    return yaml.safe_load(INSTALL_SMOKE.read_text(encoding="utf-8"))["run-name"]


def test_the_install_smoke_test_is_dispatched_with_an_exact_version():
    after = section("After the publish")
    assert "gh workflow run install-smoke.yaml --ref main -f version=<version>" in after
    # The run is found by its title (the workflow's run-name), and the watch
    # waits for it to be listed: the newest run can still be the previous one.
    dispatch = next(block for block in code_blocks(after) if "install-smoke.yaml" in block)
    assert """select(.displayTitle=="Install smoke <version>")""" in dispatch
    assert 'if [ -z "$RUN_ID" ]; then' in dispatch
    assert "--limit 1" not in dispatch
    assert load_run_name() == "Install smoke ${{ inputs.version }}"
    assert "version=latest" not in text()
    assert "install-smoke.json" in after
    assert "gh release download v<version> --pattern install-smoke.json" in after
    workflow = yaml.safe_load(INSTALL_SMOKE.read_text(encoding="utf-8"))
    # PyYAML reads the bare `on` key as the boolean True.
    assert "version" in workflow[True]["workflow_dispatch"]["inputs"]

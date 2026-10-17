#!/usr/bin/env python3
"""The GitHub Actions workflows: release.yaml's npm version floor, and the
action pins of every workflow, with their check and Dependabot.

The main-dispatch path of .github/workflows/release.yaml only runs for real
on a `--ref main` dispatch, which is also a real npm publish, so these tests
run the steps' own `run:` scripts instead. Each script is read from the
workflow with PyYAML and run under `bash -e`, the runner's default shell,
with stub `gh`, `git`, `npm` and `sleep` commands (and `node`, where a test
says so) first on PATH. A stub answers from a list of rules the test gives
(first matching rule wins, each rule answers its calls in order and repeats
its last answer) and logs every call, so a test can assert what the step
asked GitHub or npm to do.

Covers:
  - Verify npm version floor for OIDC trusted publishing: it runs on every
    dispatch right after Setup Node.js (which reads .nvmrc), prints Node and
    its bundled npm, passes from 11.5.1 up (a two-digit minor compared as a
    number) and fails below it naming .nvmrc as the fix; no step installs
    npm or writes $GITHUB_PATH, and release.yaml names no npm@latest
  - Action pins: every `uses:` of every workflow names a 40-character
    commit SHA and its exact version (`# vX.Y.Z`), the lines read as text
    are exactly the uses: YAML runs, each action has one pin, and
    actions/checkout stays on v5 with the reason on the line above each pin.
    The pin check, a Linux step of quality.yaml's validate job, passes on
    this repository naming every workflow it read, and on fixture workflows
    names each uses: it refuses and fails when it finds none.
    .github/dependabot.yaml has one monthly github-actions entry whose group
    lists every action the workflows use and that ignores only the major
    updates of actions/checkout.

The step scripts and the pin check run under bash, as on the Ubuntu
runner, so their behaviour tests are skipped on Windows.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "release.yaml"
QUALITY = WORKFLOWS / "quality.yaml"
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yaml"

REPOSITORY = "owner/repo"
RUN_ID = "42"
RUN_ATTEMPT = "2"

NPM_FLOOR = "Verify npm version floor for OIDC trusted publishing"

needs_shell = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="the step scripts run under bash, as on the Ubuntu runner",
)

# One stub for gh, git and npm, called with the tool's name first: its rules
# are in <STUB_DIR>/<name>.json. A rule matches when its `match` is a
# substring of the joined arguments. An answer may remove files in STUB_DIR,
# and an answer with `stdout_if` prints its stdout only while that file
# exists.
STUB = """\
import json, os, sys
d = os.environ["STUB_DIR"]
name = sys.argv[1]
args = sys.argv[2:]
with open(os.path.join(d, "calls.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps([name] + args) + "\\n")
line = " ".join(args)
with open(os.path.join(d, name + ".json"), encoding="utf-8") as f:
    rules = json.load(f)
for i, rule in enumerate(rules):
    if rule["match"] not in line:
        continue
    count_file = os.path.join(d, "%s.%d.count" % (name, i))
    n = int(open(count_file).read()) if os.path.exists(count_file) else 0
    with open(count_file, "w") as f:
        f.write(str(n + 1))
    answer = rule["answers"][min(n, len(rule["answers"]) - 1)]
    out = answer.get("stdout", "")
    if "stdout_if" in answer and not os.path.exists(os.path.join(d, answer["stdout_if"])):
        out = ""
    for path in answer.get("remove", []):
        if os.path.exists(os.path.join(d, path)):
            os.remove(os.path.join(d, path))
    sys.stdout.write(out)
    sys.stderr.write(answer.get("stderr", ""))
    sys.exit(answer.get("exit", 0))
sys.stderr.write("stub %s: no rule for: %s\\n" % (name, line))
sys.exit(97)
"""


def load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps() -> list[dict]:
    return load_workflow()["jobs"]["release"]["steps"]


def step(name: str) -> dict:
    matches = [s for s in steps() if s.get("name") == name]
    assert len(matches) == 1, f"expected one step named {name!r}, found {len(matches)}"
    return matches[0]


class Result:
    def __init__(self, proc: subprocess.CompletedProcess, stub_dir: Path):
        self.code = proc.returncode
        self.out = proc.stdout + proc.stderr
        log = stub_dir / "calls.jsonl"
        self.calls = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
        summary = stub_dir / "summary.md"
        self.summary = summary.read_text() if summary.exists() else ""
        output = stub_dir / "output.txt"
        self.output = output.read_text() if output.exists() else ""

    def called(self, name: str, *parts: str) -> list[list[str]]:
        """Calls of `name` whose joined arguments contain every part."""
        return [c for c in self.calls if c[0] == name and all(p in " ".join(c[1:]) for p in parts)]

    def slept(self, seconds: int) -> int:
        """How many times the step ran `sleep <seconds>`."""
        return self.calls.count(["sleep", str(seconds)])


def run_step(
    tmp_path: Path,
    name: str,
    env: dict[str, str],
    gh: list[dict] | None = None,
    git: list[dict] | None = None,
    npm: list[dict] | None = None,
    node: list[dict] | None = None,
    cwd: Path | None = None,
) -> Result:
    stub_dir = tmp_path / "stub"
    bin_dir = tmp_path / "bin"
    stub_dir.mkdir()
    bin_dir.mkdir()
    stub_py = stub_dir / "stub.py"
    stub_py.write_text(STUB, encoding="utf-8")
    # node is stubbed only when a test gives it rules.
    stubbed = [("gh", gh), ("git", git), ("npm", npm)] + ([("node", node)] if node is not None else [])
    for tool, rules in stubbed:
        exe = bin_dir / tool
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub_py}" {tool} "$@"\n', encoding="utf-8")
        exe.chmod(0o755)
        (stub_dir / f"{tool}.json").write_text(json.dumps(rules or []), encoding="utf-8")
    # sleep returns at once and logs its call, so a test can count the waits.
    sleep = bin_dir / "sleep"
    sleep.write_text('#!/bin/sh\necho "[\\"sleep\\", \\"$1\\"]" >> "$STUB_DIR/calls.jsonl"\n', encoding="utf-8")
    sleep.chmod(0o755)

    script = tmp_path / "step.sh"
    script.write_text(step(name)["run"], encoding="utf-8")
    full_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(tmp_path),
        "STUB_DIR": str(stub_dir),
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_RUN_ID": RUN_ID,
        "GITHUB_RUN_ATTEMPT": RUN_ATTEMPT,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_OUTPUT": str(stub_dir / "output.txt"),
        "GITHUB_STEP_SUMMARY": str(stub_dir / "summary.md"),
        **env,
    }
    proc = subprocess.run(
        ["bash", "-e", str(script)],
        cwd=cwd or tmp_path,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return Result(proc, stub_dir)


def ok(stdout: str) -> dict:
    return {"stdout": stdout}


# --------------------------------------------------------------------------
# Verify npm version floor for OIDC trusted publishing
# --------------------------------------------------------------------------


def floor_tools(node_version: str, npm_version: str) -> dict[str, list[dict]]:
    """node and npm answering `--version` as setup-node's Node and its bundled npm would."""
    return {
        "node": [{"match": "--version", "answers": [ok(node_version + "\n")]}],
        "npm": [{"match": "--version", "answers": [ok(npm_version + "\n")]}],
    }


@needs_shell
@pytest.mark.parametrize(
    "npm_version",
    [
        pytest.param("11.5.1", id="at the floor"),
        # A string compare would put 11.10.0 below 11.5.1.
        pytest.param("11.10.0", id="two-digit minor"),
        pytest.param("11.19.0", id="Node 24"),
        pytest.param("12.0.2", id="next major"),
    ],
)
def test_the_floor_check_prints_node_and_its_bundled_npm_and_passes_from_11_5_1(tmp_path, npm_version):
    result = run_step(tmp_path, NPM_FLOOR, {}, **floor_tools("v24.21.0", npm_version))
    assert result.code == 0, result.out
    assert f"Node: v24.21.0; bundled npm: {npm_version}" in result.out
    assert "::error::" not in result.out
    assert result.called("npm") == [["npm", "--version"]]


@needs_shell
@pytest.mark.parametrize(
    ("node_version", "npm_version"),
    [
        pytest.param("v24.0.0", "11.5.0", id="just below"),
        pytest.param("v22.22.2", "10.9.7", id="Node 22 npm"),
    ],
)
def test_the_floor_check_fails_below_11_5_1_and_names_nvmrc_as_the_fix(tmp_path, node_version, npm_version):
    result = run_step(tmp_path, NPM_FLOOR, {}, **floor_tools(node_version, npm_version))
    assert result.code == 1, result.out
    assert f"Node: {node_version}; bundled npm: {npm_version}" in result.out
    message = (
        f"::error::npm {npm_version}, the one bundled with Node {node_version}, is below the OIDC "
        "trusted-publishing floor (11.5.1), so the run stopped before anything was committed, tagged or "
        "published. Fix .nvmrc: in a pull request, move it to a Node version whose bundled npm is 11.5.1 or later"
    )
    assert message in result.out
    # The npm that ships with Node is the only one: nothing to blame on PATH.
    assert "PATH" not in result.out


def test_the_floor_check_runs_on_every_dispatch_right_after_setup_node():
    names = [s["name"] for s in steps()]
    assert names[:3] == ["Checkout", "Setup Node.js", NPM_FLOOR]
    assert "if" not in step(NPM_FLOOR)
    assert step("Setup Node.js")["with"]["node-version-file"] == ".nvmrc"
    assert names.index(NPM_FLOOR) < names.index("Install dependencies") < names.index("Publish to npm via OIDC trusted publishing")


def test_no_step_installs_npm_so_the_publish_uses_the_one_node_ships():
    # npm@latest put a major nobody chose on the publish. A step that installs
    # npm must pin one exact version; none is needed while Node 24 ships an
    # npm above the floor.
    assert "npm@latest" not in WORKFLOW.read_text(encoding="utf-8")
    for s in steps():
        run = s.get("run", "")
        assert not re.search(r"\bnpm\s+(?:install|i|add|update|up)\b", run), s["name"]
        assert "GITHUB_PATH" not in run, s["name"]
    assert "side-prefix" not in WORKFLOW.read_text(encoding="utf-8").lower()


# --------------------------------------------------------------------------
# Action pins and Dependabot
# --------------------------------------------------------------------------

PIN_CHECK = "Check that every action is pinned to a commit SHA"
# A `uses:` key opens its line, after the indent and an optional list dash,
# as the pin check reads it.
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:(.*)$")
PIN = re.compile(r"^(?P<action>[^\s@]+)@(?P<sha>[0-9a-f]{40}) # (?P<version>v\d+\.\d+\.\d+)$")
CHECKOUT_HOLD = "# Held on v5: v6 changes how it stores the git credentials, and release.yaml pushes with them."


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOWS.glob("*.yaml"), *WORKFLOWS.glob("*.yml")])


def uses_lines(path: Path) -> list[tuple[int, str]]:
    """(line number, value with its comment) of every `uses:` key of a workflow, read as text."""
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = USES_LINE.match(line)
        if match:
            found.append((number, match.group(1).strip()))
    return found


def parsed_uses(path: Path) -> list[str]:
    """Every `uses:` value YAML reads in a workflow: its steps' and its reusable-workflow jobs'."""
    values = []
    for job in yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"].values():
        if "uses" in job:
            values.append(job["uses"])
        values.extend(s["uses"] for s in job.get("steps", []) if "uses" in s)
    return values


def pins() -> list[tuple[str, int, re.Match | None]]:
    """(workflow name, line number, PIN match) of every `uses:` that names an action."""
    found = []
    for path in workflow_files():
        for number, value in uses_lines(path):
            if not value.startswith("./"):
                found.append((path.name, number, PIN.match(value)))
    return found


def test_every_action_is_pinned_to_a_commit_sha_with_its_exact_version():
    names = [path.name for path in workflow_files()]
    for name in ("quality.yaml", "release.yaml", "docs.yaml", "install-smoke.yaml", "health-check-dedup.yaml"):
        assert name in names
    for path in workflow_files():
        # The text the pin check reads holds exactly the uses: YAML runs.
        assert [value.split(" #")[0] for _, value in uses_lines(path)] == parsed_uses(path), path.name
        # No uses: names a version tag.
        assert not re.search(r"uses: [^ ]+@v[0-9]", path.read_text(encoding="utf-8")), path.name
    unpinned = [f"{name}:{number}" for name, number, match in pins() if match is None]
    assert unpinned == []


def test_each_action_has_one_pin_across_the_workflows():
    # A partial update would run two commits of one action.
    seen: dict[str, set[tuple[str, str]]] = {}
    for _, _, match in pins():
        if match:
            seen.setdefault(match["action"], set()).add((match["sha"], match["version"]))
    assert {action: len(shas) for action, shas in seen.items() if len(shas) != 1} == {}


def test_install_smoke_pins_its_action():
    pinned = {match["action"] for name, _, match in pins() if name == "install-smoke.yaml" and match}
    assert pinned == {"actions/setup-node"}


def test_checkout_stays_on_v5_with_the_reason_beside_each_pin():
    checkouts = []
    for path in workflow_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, value in uses_lines(path):
            if not value.startswith("actions/checkout@"):
                continue
            checkouts.append(path.name)
            match = PIN.match(value)
            assert match and match["version"].startswith("v5."), f"{path.name}:{number}"
            assert lines[number - 2].strip() == CHECKOUT_HOLD, f"{path.name}:{number}"
    # release.yaml pushes with the credentials of its own checkout.
    assert "release.yaml" in checkouts


def pin_check_step() -> dict:
    found = [
        (job_id, s)
        for job_id, job in yaml.safe_load(QUALITY.read_text(encoding="utf-8"))["jobs"].items()
        for s in job.get("steps", [])
        if s.get("name") == PIN_CHECK
    ]
    assert [job_id for job_id, _ in found] == ["validate"]
    return found[0][1]


def test_the_pin_check_is_a_step_of_the_validate_job_on_linux():
    # A step of a required job, not a new required job.
    s = pin_check_step()
    assert s["if"] == "runner.os == 'Linux'"
    assert "shell" not in s
    validate = yaml.safe_load(QUALITY.read_text(encoding="utf-8"))["jobs"]["validate"]
    assert "ubuntu-latest" in validate["strategy"]["matrix"]["os"]


def run_pin_check(tmp_path: Path, cwd: Path) -> subprocess.CompletedProcess:
    script = tmp_path / "pin-check.sh"
    script.write_text(pin_check_step()["run"], encoding="utf-8")
    return subprocess.run(["bash", "-e", str(script)], cwd=cwd, capture_output=True, text=True, timeout=60)


@needs_shell
def test_the_pin_check_passes_on_this_repository_and_reads_every_workflow(tmp_path):
    proc = run_pin_check(tmp_path, REPO_ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    total = 0
    for path in workflow_files():
        count = len(uses_lines(path))
        assert f"Checked {count} uses: in .github/workflows/{path.name}\n" in proc.stdout
        total += count
    assert "Checked 1 uses: in .github/workflows/install-smoke.yaml\n" in proc.stdout
    assert f"All {total} uses: in .github/workflows/ name a commit SHA and its version." in proc.stdout


SAMPLE_SHA = "1234567890abcdef1234567890abcdef12345678"
PINNED = f"actions/checkout@{SAMPLE_SHA} # v5.1.0"
# Line by line: the ones the check refuses are marked.
PIN_FIXTURE = [
    ("jobs:", False),
    ("  a:", False),
    ("    steps:", False),
    ("      - uses: actions/checkout@v5", True),
    ("      - uses: actions/checkout@main", True),
    ("      - uses: actions/checkout@fbc6f39 # v5.1.0", True),
    (f"      - uses: actions/checkout@{SAMPLE_SHA}", True),
    (f"      - uses: actions/checkout@{SAMPLE_SHA} # v5", True),
    (f"      - uses: actions/checkout@{SAMPLE_SHA.upper()} # v5.1.0", True),
    (f'      - uses: "{PINNED}"', True),
    (f"      - uses: {PINNED}", False),
    ("      - name: Local", False),
    ("        uses: ./.github/actions/local", False),
    ("      # uses: actions/checkout@v5", False),
    ("      - run: |", False),
    ('          echo "the publish below uses: it"', False),
    ("  b:", False),
    ("    uses: owner/repo/.github/workflows/build.yaml@v1", True),
]


@needs_shell
def test_the_pin_check_names_each_uses_that_is_not_pinned(tmp_path):
    workflows = tmp_path / "repo" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yaml").write_text("\n".join(line for line, _ in PIN_FIXTURE) + "\n", encoding="utf-8")
    # A .yml workflow is read as well.
    (workflows / "b.yml").write_text("jobs:\n  c:\n    steps:\n      - uses: actions/setup-node@v6\n", encoding="utf-8")
    proc = run_pin_check(tmp_path, tmp_path / "repo")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    refused = [n for n, (_, bad) in enumerate(PIN_FIXTURE, start=1) if bad]
    reported = [int(m) for m in re.findall(r"::error file=\.github/workflows/a\.yaml,line=(\d+)::", proc.stdout)]
    assert reported == refused
    assert "::error file=.github/workflows/b.yml,line=4::Not pinned to a commit SHA with its version: " in proc.stdout
    assert "uses: actions/setup-node@v6\n" in proc.stdout
    uses = sum(1 for line, _ in PIN_FIXTURE if USES_LINE.match(line)) + 1
    assert f"::error::{len(refused) + 1} of the {uses} uses: in .github/workflows/ are not pinned." in proc.stdout
    assert "gh api repos/<owner>/<repo>/commits/<tag> --jq .sha" in proc.stdout


@needs_shell
def test_the_pin_check_fails_when_it_finds_nothing_to_check(tmp_path):
    (tmp_path / "repo" / ".github" / "workflows").mkdir(parents=True)
    proc = run_pin_check(tmp_path, tmp_path / "repo")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "::error::No uses: found in .github/workflows/, so nothing was checked." in proc.stdout


def dependabot_actions() -> dict:
    config = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
    assert config["version"] == 2
    entries = [u for u in config["updates"] if u["package-ecosystem"] == "github-actions"]
    assert len(entries) == 1
    return entries[0]


def test_dependabot_proposes_every_pinned_action_monthly_in_one_group():
    entry = dependabot_actions()
    assert entry["directory"] == "/"
    assert entry["schedule"]["interval"] == "monthly"
    assert entry["commit-message"]["prefix"] == "ci"
    groups = entry["groups"]
    assert len(groups) == 1
    group = next(iter(groups.values()))
    used = {match["action"] for _, _, match in pins() if match}
    # A new action goes on the list, so its updates join the group.
    assert sorted(group["patterns"]) == sorted(used)
    assert sorted(group["update-types"]) == ["minor", "patch"]
    # One file: GitHub reads dependabot.yml or dependabot.yaml, not both.
    assert not (REPO_ROOT / ".github" / "dependabot.yml").exists()


def test_dependabot_never_proposes_a_checkout_major():
    ignored = [i for i in dependabot_actions()["ignore"] if i["dependency-name"] == "actions/checkout"]
    # Only the major is ignored: checkout still gets its v5 minor and patch updates.
    assert ignored == [{"dependency-name": "actions/checkout", "update-types": ["version-update:semver-major"]}]


def test_every_setup_uv_keys_its_cache_on_package_json():
    # setup-uv's default cache globs match no file here, so each run would warn.
    for path in workflow_files():
        for job in yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"].values():
            for s in job.get("steps", []):
                if s.get("uses", "").startswith("astral-sh/setup-uv@"):
                    assert s["with"]["cache-dependency-glob"] == "package.json", path.name


def test_ci_runs_node_24_while_the_supported_floor_stays_22():
    assert (REPO_ROOT / ".nvmrc").read_text(encoding="utf-8").strip() == "24"
    package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["engines"]["node"] == ">=22.0.0"
    # The smoke test pins the floor, so the minimum supported Node keeps a run.
    smoke = yaml.safe_load((WORKFLOWS / "install-smoke.yaml").read_text(encoding="utf-8"))
    node = [s for s in smoke["jobs"]["smoke"]["steps"] if s.get("uses", "").startswith("actions/setup-node@")]
    assert [s["with"]["node-version"] for s in node] == ["22"]

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""Tests for health_check_fp.py.

Covers the fingerprint byte-format (fp and the keyless legacy_fp, locked against
golden sha1s computed in the test), the fp regex contract and the severity,
stage, slug and defect-key validation; the section heading, defect name and
short description read from --stdin, with the slug and key rules, the title
and its character rule and the body header; `queue`'s naming, counter,
byte-for-byte copy and the submit commands it prints, read from the draft's body
header and quoted for a shell; the `seen` verdict table and its opening line, including the
legacy-fingerprint demotions and the issue-state check it runs through `gh`
(a fake gh on PATH that answers, fails, prints junk or hangs, and a gh planted
in the current folder that must never run); `record`'s validation, merge,
resolved guard, lock, fsync-and-rename write and corrupt-cache set-aside; and
`version`, read from UCG's own root (the script copied into a checkout's, a
plugin's and a CLI install's layout) and then the CLI install's VERSION, never
from the user's project's package.json or marketplace.json.

The script is exercised via subprocess (sys.executable + absolute path) to test
the real CLI surface, mirroring test_preflight_check.py. Every subprocess gets a
PATH that holds no gh, so no test reaches a gh the developer installed. Tests
that need a time limit shorter than the script's own, a patched clock or a
failing rename load the script as a module and call main() in-process. The fake
gh is a POSIX shell script, so the tests that need it skip on Windows.

Run: uv run --with pytest pytest test_health_check_fp.py -v
"""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "health_check_fp.py"
HEALTH_CHECK_MD = Path(__file__).resolve().parents[2] / "references" / "health-check.md"

# A folder that does not exist, so it holds no gh: the PATH of every CLI call.
NO_GH_PATH = str(Path(__file__).resolve().parent / "no-gh-here")

URL = "https://github.com/o/r/issues/1"
FP, LEGACY, OTHER = "fp-abc1234", "fp-1234abc", "fp-7654321"
DAY = "2026-11-14"

needs_posix = pytest.mark.skipif(os.name == "nt", reason="the fake gh is a POSIX shell script")


def _env(path: str = NO_GH_PATH, **extra: str) -> dict:
    env = dict(os.environ)
    env["PATH"] = path
    env.update(extra)
    return env


def _run(*args: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=_env() if env is None else env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def _load():
    """The script as a fresh module, so a constant patched in one test never leaks into another."""
    spec = importlib.util.spec_from_file_location("health_check_fp_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mod():
    return _load()


def _main(module, capsys, *args: str) -> tuple[int, dict]:
    code = module.main(list(args))
    out = capsys.readouterr().out
    return code, json.loads(out)


def _fingerprint(severity: str, stage: str, slug: str, key: str = "staging-path") -> subprocess.CompletedProcess[str]:
    # The `=` form, so a value that starts with a dash reaches the script's own check.
    return _run(
        "fingerprint",
        "--severity",
        severity,
        "--stage",
        stage,
        f"--section-slug={slug}",
        f"--defect-key={key}",
    )


def _expected_fp(severity: str, stage: str, slug: str, key: str) -> tuple[str, str, str]:
    """Recompute both fingerprints independently to lock the byte format."""
    step_file = f"skills/ultracode-goal/references/{stage}.md"
    legacy = f"{severity}|ultracode-goal/{stage}|{step_file}|{slug}"
    keyed = f"{legacy}|{key}"

    def sha7(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:7]

    return f"fp-{sha7(keyed)}", f"fp-{sha7(legacy)}", keyed


def _write_cache(path: Path, data) -> Path:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _live(action: str = "created", url: str | None = URL) -> dict:
    record = {"action": action, "date": "2026-10-01"}
    if url is not None:
        record["issue_url"] = url
    return record


def _seen(cache: Path, fp: str = FP, legacy: str = LEGACY, env: dict | None = None,
          cwd: Path | None = None, repo: str | None = None) -> dict:
    scope = () if repo is None else (f"--repo={repo}",)
    proc = _run("seen", "--fp", fp, "--legacy-fp", legacy, "--cache", str(cache), *scope, env=env, cwd=cwd)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def _record(cache: Path, *extra: str, fp: str = FP, action: str = "created", url: str = URL,
            day: str = DAY) -> subprocess.CompletedProcess[str]:
    return _run("record", "--fp", fp, "--cache", str(cache), f"--issue-url={url}", "--action", action,
                "--date", day, *extra)


# --- Fingerprint: golden byte-format lock ----------------------------------


def test_fingerprint_matches_independent_golden():
    proc = _fingerprint("bug", "preflight", "missing-staging-path", "staging-path")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    expected_fp, expected_legacy, expected_tuple = _expected_fp(
        "bug", "preflight", "missing-staging-path", "staging-path"
    )
    # Without a short_description there is no title and no body header.
    assert payload == {
        "fp": expected_fp,
        "legacy_fp": expected_legacy,
        "tuple": expected_tuple,
        "section_slug": "missing-staging-path",
        "defect_key": "staging-path",
        "title": None,
        "regression_title": None,
        "body_header": None,
    }
    # The exact tuple the script hashes: install-mode-invariant step_file form, then the defect key.
    assert payload["tuple"] == (
        "bug|ultracode-goal/preflight|"
        "skills/ultracode-goal/references/preflight.md|missing-staging-path|staging-path"
    )


def test_the_keyed_fingerprint_and_its_legacy_twin():
    proc = _fingerprint("bug", "gate", "verdict-mapping", "gate-status")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert set(payload) == {"fp", "legacy_fp", "tuple", "section_slug", "defect_key", "title", "regression_title",
                            "body_header"}
    assert payload["tuple"].endswith("|verdict-mapping|gate-status")
    assert (payload["fp"], payload["legacy_fp"]) == _expected_fp("bug", "gate", "verdict-mapping", "gate-status")[:2]
    # Literal goldens. fp-3d74222 is what the keyless script (91f0e02) printed as the fingerprint
    # of this finding: issues and records made before the defect key carry it.
    assert payload["fp"] == "fp-4e6fb0f"
    assert payload["legacy_fp"] == "fp-3d74222"


def test_fingerprint_matches_fp_regex():
    payload = json.loads(_fingerprint("friction", "execute", "ambiguous-budget").stdout)
    assert re.fullmatch(r"fp-[0-9a-f]{7}", payload["fp"])
    assert re.fullmatch(r"fp-[0-9a-f]{7}", payload["legacy_fp"])


# --- Fingerprint: determinism + sensitivity --------------------------------


def _fps(severity: str, stage: str, slug: str, key: str = "gate-status") -> dict:
    proc = _fingerprint(severity, stage, slug, key)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_fingerprint_is_deterministic_for_identical_inputs():
    assert _fps("gap", "gate", "verdict-mapping") == _fps("gap", "gate", "verdict-mapping")


def test_changing_severity_changes_fp():
    assert _fps("bug", "gate", "verdict-mapping")["fp"] != _fps("friction", "gate", "verdict-mapping")["fp"]


def test_changing_stage_changes_fp():
    assert _fps("bug", "gate", "verdict-mapping")["fp"] != _fps("bug", "finalize", "verdict-mapping")["fp"]


def test_changing_section_slug_changes_fp():
    assert _fps("bug", "gate", "verdict-mapping")["fp"] != _fps("bug", "gate", "reloop-budget")["fp"]


def test_two_defects_in_one_section_share_only_the_legacy_fp():
    a = _fps("bug", "gate", "verdict-mapping", "gate-status")
    b = _fps("bug", "gate", "verdict-mapping", "nfr-status")
    assert a["fp"] != b["fp"], "two defect keys in one section must get two fingerprints"
    assert a["legacy_fp"] == b["legacy_fp"], "the section fingerprint ignores the key"


# --- Fingerprint: validation -----------------------------------------------


def test_invalid_stage_exits_one_with_json_error():
    proc = _fingerprint("bug", "not-a-stage", "some-slug")
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


def test_invalid_severity_exits_one():
    proc = _fingerprint("critical", "preflight", "some-slug")
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


@pytest.mark.parametrize("slug", ["Some-Slug", "some_slug", "some-slug\n", "", "-some"])
def test_invalid_slug_exits_one(slug):
    proc = _fingerprint("bug", "preflight", slug)
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


@pytest.mark.parametrize(
    "key",
    ["a-b-c-d-e", "Gate-Status", "gate_status", "gate-status\n", "", "-gate", "gate--status", "gate status"],
)
def test_a_defect_key_that_is_not_one_to_four_kebab_words_exits_one(key):
    proc = _fingerprint("bug", "gate", "verdict-mapping", key)
    assert proc.returncode == 1
    assert "defect-key" in json.loads(proc.stdout)["error"]


@pytest.mark.parametrize("key", ["gate", "gate-status", "a-b-c-d", "cycle-profile-2"])
def test_a_defect_key_of_one_to_four_words_is_accepted(key):
    assert _fingerprint("bug", "gate", "verdict-mapping", key).returncode == 0


def test_the_defect_key_is_required():
    proc = _run("fingerprint", "--severity", "bug", "--stage", "gate", "--section-slug", "verdict-mapping")
    assert proc.returncode == 2, "an argparse usage error exits 2"


# --- Fingerprint: the heading and the name on stdin ---------------------------


def _fingerprint_stdin(severity: str, stage: str, names, *flags: str) -> tuple[int, dict]:
    """fingerprint --stdin, fed `names` as UTF-8 JSON (or as given when it is bytes)."""
    data = names if isinstance(names, bytes) else json.dumps(names, ensure_ascii=False).encode("utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "fingerprint", "--severity", severity, "--stage", stage, "--stdin", *flags],
        capture_output=True, env=_env(), input=data, timeout=120,
    )
    return proc.returncode, json.loads(proc.stdout.decode("utf-8"))


@pytest.mark.parametrize(
    "heading",
    ["1b. Run the formalize readiness check", "## 1b. Run the formalize readiness check", "  1b. Run the formalize readiness check  "],
)
def test_a_heading_of_the_stage_file_gives_its_slug(heading):
    code, payload = _fingerprint_stdin("bug", "preflight", {"section_heading": heading, "defect_name": "gate_status"})
    assert code == 0, payload
    assert payload["section_slug"] == "run-the-formalize-readiness-check"
    assert payload["defect_key"] == "gate-status"
    # The fingerprints hash the derived slug, exactly as if it had been given with --section-slug.
    assert (payload["fp"], payload["legacy_fp"], payload["tuple"]) == _expected_fp(
        "bug", "preflight", "run-the-formalize-readiness-check", "gate-status"
    )
    assert payload == json.loads(_fingerprint("bug", "preflight", "run-the-formalize-readiness-check",
                                              "gate-status").stdout)


@pytest.mark.parametrize(
    "stage, heading, slug",
    [
        ("preflight", "3. Semantic intervention scan (the part the script cannot do)",
         "semantic-intervention-scan-the-part-the-script-cannot-do"),
        ("execute", "The per-invocation work bound (`--max-stories N`)", "the-per-invocation-work-bound-max-stories-n"),
        ("define-done", "Stage 3 \u2014 Define Done", "stage-3-define-done"),
        ("gate", "Non-web stack: the red phase by hand, and the trace artifacts where trace cannot run",
         "non-web-stack-the-red-phase-by-hand-and-the-trace-artifacts-where-trace-cannot-run"),
    ],
)
def test_real_stage_headings_give_their_slugs(stage, heading, slug):
    code, payload = _fingerprint_stdin("friction", stage, {"section_heading": heading}, "--defect-key=x")
    assert code == 0, payload
    assert payload["section_slug"] == slug


@pytest.mark.parametrize(
    "heading, slug",
    [
        ("1b. Run the formalize readiness check", "run-the-formalize-readiness-check"),
        ("### 5a-ii. If no matching open issue exists", "if-no-matching-open-issue-exists"),
        ("### 4-headless. Unattended routing (no human at the gate)", "unattended-routing-no-human-at-the-gate"),
        ("## 0.5. Enabled gate", "enabled-gate"),
        ("## 5. Severity routing (attended [Y] and [A])", "severity-routing-attended-y-and-a"),
        ("## Step 2.5 is not numbering", "step-2-5-is-not-numbering"),
        ("## 3.5 GHz is not numbering", "3-5-ghz-is-not-numbering"),
        ("## Closing hashes ##", "closing-hashes"),
        # An accented letter gives its base letter, and NFKD (not NFD) turns a superscript or a ligature into its
        # plain characters.
        ("Résumé du run", "resume-du-run"),
        ("## 2. État Ünïcode", "etat-unicode"),
        ("Phase ² ﬁnal", "phase-2-final"),
        # A letter NFKD cannot split stays, so it is one of the other characters.
        ("Straße", "stra-e"),
        # Folded before the numbering is read: a full-width `１.` is the numbering `1.`.
        ("１. Run the gate", "run-the-gate"),
    ],
)
def test_the_slug_rule(mod, heading, slug):
    assert mod.section_slug(heading) == slug


@pytest.mark.parametrize("stage", ["ingest-and-scope", "preflight", "define-done", "execute", "gate", "finalize",
                                   "health-check"])
def test_every_heading_of_every_stage_file_gives_a_slug(mod, stage):
    headings = mod._stage_headings(mod.REFERENCES_DIR / f"{stage}.md")
    assert headings, stage
    slugs = [mod.section_slug(heading) for heading in headings]
    assert all(slugs), [h for h, slug in zip(headings, slugs) if not slug]
    # Two sections of one stage file never share a slug, so a slug names one section.
    assert len(set(slugs)) == len(slugs), sorted(slug for slug in slugs if slugs.count(slug) > 1)


def test_a_stage_file_that_is_not_utf8_exits_one(tmp_path, mod, monkeypatch, capsys):
    (tmp_path / "gate.md").write_bytes(b"# Stage 5\n\xff\xfe\n")
    monkeypatch.setattr(mod, "REFERENCES_DIR", tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"section_heading": "Stage 5"})))
    code, payload = _main(mod, capsys, "fingerprint", "--severity", "bug", "--stage", "gate", "--stdin", "--defect-key=x")
    assert code == 1
    assert "could not read" in payload["error"]


@pytest.mark.parametrize("heading", ["Run the formalize readiness check (missing)", "verdict-mapping", "1b."])
def test_a_heading_that_is_no_heading_of_the_stage_file_exits_one(heading):
    code, payload = _fingerprint_stdin("bug", "preflight", {"section_heading": heading}, "--defect-key=x")
    assert code == 1
    assert "no heading of references/preflight.md" in payload["error"]


def test_a_heading_line_in_fenced_code_or_frontmatter_is_no_heading(tmp_path, mod, monkeypatch, capsys):
    (tmp_path / "gate.md").write_text(
        "---\n# front: matter\n---\n# Stage 5\n\n```markdown\n# Deferred Work\n```\n\n~~~~\n## In tildes\n~~~~\n"
        "## Route on the verdict ##\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "REFERENCES_DIR", tmp_path)
    for heading, ok in (("Stage 5", True), ("Route on the verdict", True), ("Deferred Work", False),
                        ("In tildes", False), ("front: matter", False)):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"section_heading": heading})))
        code, payload = _main(mod, capsys, "fingerprint", "--severity", "bug", "--stage", "gate", "--stdin",
                              "--defect-key=x")
        assert (code == 0) is ok, (heading, payload)


@pytest.mark.parametrize(
    "name, key",
    [
        ("gate_status", "gate-status"),
        ("--cycle-profile", "cycle-profile"),
        ("operator's own evidence", "operators-own-evidence"),
        ("gate_eval.py", "gate-eval"),
        ("composeStories", "compose-stories"),
        ("one two three four five", "two-three-four-five"),
        ("_private_helper", "private-helper"),
        ("formalize_check.py ready", "formalize-check-py-ready"),
        ("story moved criteria", "story-moved-criteria"),
        ("buildHeadlessEnvelope", "build-headless-envelope"),
        # A path keeps its last component, and a line suffix goes with the extension.
        ("scripts/gate_eval.py", "gate-eval"),
        ("skills\\ultracode-goal\\scripts\\gate_eval.py", "gate-eval"),
        ("gate_eval.py:42", "gate-eval"),
        ("scripts/gate_eval.py:42-50", "gate-eval"),
        # A `:N:M` suffix, a line number then a column number, goes as `:N` and `:N-M` do.
        ("gate_eval.py:42:7", "gate-eval"),
        ("C:\\work\\gate_eval.py:10:2", "gate-eval"),
        # A name copied from Markdown or a log keeps no backticks or quotes around it.
        ("`gate_eval.py`", "gate-eval"),
        ("'gate_eval.py'", "gate-eval"),
        ('"gate_eval.py"', "gate-eval"),
        ("  `scripts/gate_eval.py:42:7`  ", "gate-eval"),
        ("`composeStories`", "compose-stories"),
        # A wrapper that closes before the location, and wrappers and whitespace in layers.
        ("`gate_eval.py`:42", "gate-eval"),
        ('"scripts/gate_eval.py":42:7', "gate-eval"),
        ("` 'gate_eval.py' `", "gate-eval"),
        ("**`gate_eval.py`**", "gate-eval"),
        # Curly quotes, brackets, emphasis and the punctuation of a sentence: each edge character trails some name.
        ("“gate_eval.py”", "gate-eval"),
        ("‘gate_eval.py’", "gate-eval"),
        ("(gate_eval.py)", "gate-eval"),
        ("[gate_eval.py]", "gate-eval"),
        ("{gate_eval.py}", "gate-eval"),
        ("<gate_eval.py>", "gate-eval"),
        ("*gate_eval.py*", "gate-eval"),
        ("gate_eval.py.", "gate-eval"),
        ("gate_eval.py,", "gate-eval"),
        ("gate_eval.py;", "gate-eval"),
        ("gate_eval.py?!", "gate-eval"),
        ("composeStories()", "compose-stories"),
        # An opening bracket or quote is an edge at the end of a name too.
        ("gate_eval.py ([{<‘“", "gate-eval"),
        # A compiler's or an editor's location, and a GitHub anchor.
        ("gate_eval.py:42:7:", "gate-eval"),
        ("gate_eval.py:42:7-12", "gate-eval"),
        ("gate_eval.py:42-", "gate-eval"),
        ("gate_eval.py:", "gate-eval"),
        ("gate_eval.py#L42", "gate-eval"),
        ("gate_eval.py#L42-L50", "gate-eval"),
        ("gate_eval.py#L42-50", "gate-eval"),
        ("gate_eval.py#L42C7", "gate-eval"),
        ("gate_eval.py#L42-L50C3", "gate-eval"),
        ("gate_eval.py#L42C7-L50C3", "gate-eval"),
        ("gate.md?plain=1#L42", "gate"),
        # The longest anchors: a search that started any later would miss their `?plain=1`.
        ("gate.md?plain=1#L42-L50", "gate"),
        ("gate.md?plain=1#L42C7-L50C3", "gate"),
        # A location inside a wrapper, then more: the location and the edges go until the name stops changing.
        ("`gate_eval.py:42`:", "gate-eval"),
        ("(gate_eval.py:42):", "gate-eval"),
        ("gate_eval.py:1:2:3:4", "gate-eval"),
        # Up to two more numbers follow the first, and only a `:` starts a location: a fourth joined by `-` makes none.
        ("gate_eval.py:42-50-60", "gate-eval"),
        ("gate_eval.py:42-50-60-70", "py42-50-60-70"),
        # An accented letter gives its base letter, and NFKD (not NFD) a ligature its plain letters.
        ("ÉtatMachine", "etat-machine"),
        ("Ünïcode", "unicode"),
        ("ﬁleLoader", "file-loader"),
        # A letter NFKD cannot split stays, and is dropped as any character that is not an ASCII letter or digit.
        ("Øresund", "resund"),
        ("Straße", "strae"),
        # Only a lower-case letter followed by an upper-case one splits, so an acronym stays one word, and a letter
        # and a digit stay together.
        ("getHTTPResponse", "get-httpresponse"),
        ("HTTP2Client", "http2client"),
    ],
)
def test_a_name_gives_its_defect_key(name, key):
    code, payload = _fingerprint_stdin("bug", "gate", {"defect_name": name}, "--section-slug=verdict-mapping")
    assert code == 0, payload
    assert payload["defect_key"] == key
    assert payload["fp"] == _expected_fp("bug", "gate", "verdict-mapping", key)[0]


@pytest.mark.parametrize(
    "name",
    # A name in an alphabet other than the Latin one folds to no ASCII letter, so it yields no word.
    ["--__", "...", "'", "`", '""', "` `", "**", "(“”)", "#L42", ":42:7",
     "Проверка"],
)
def test_a_name_that_yields_no_word_exits_one(name):
    code, payload = _fingerprint_stdin("bug", "gate", {"defect_name": name}, "--section-slug=verdict-mapping")
    assert code == 1
    assert "yields no word" in payload["error"]


def test_the_longest_location_holds_the_most_non_digits_the_search_reads(mod):
    """The location search starts no further back than _NAME_LOCATION_NON_DIGITS characters that are not digits, so
    no location may hold more: the longest form holds exactly that many."""
    longest = "?plain=1#L42C7-L50C3"
    assert mod._NAME_LOCATION_RE.fullmatch(longest)
    assert sum(ch not in "0123456789" for ch in longest) == mod._NAME_LOCATION_NON_DIGITS


@pytest.mark.parametrize(
    "name, key",
    [
        ("x" + ":1" * 50_000, "x"),  # one location after another, each dropped in its own round
        ("x" + ":1`" * 33_334, "x"),  # a location, then an edge, then a location, and so on
        ("x" + ":`" * 50_000, "x"),
        ("x" + (":" + "1" * 999) * 100, "x"),  # long numbers, each searched again by the rounds after it
        ("x:" + "1" * 100_000 + "y", "x" + "1" * 100_000 + "y"),  # no location, however long its number
        ("a" + " " * 100_000 + "b", "a-b"),  # a run of edges that does not end the name
        ("(" * 50_000 + "x" + ")" * 50_000, "x"),
    ],
    ids=["locations", "locations-and-edges", "lone-colons-and-edges", "long-numbers", "long-number", "spaces",
         "brackets"],
)
def test_a_long_name_gives_its_key_in_linear_time(mod, name, key):
    """A 100,000-character name: a search for each location from the start, or a backtracking edge pattern, would
    take minutes."""
    assert len(name) >= 100_000
    started = time.perf_counter()
    assert mod.defect_key(name) == key
    assert time.perf_counter() - started < 2


@pytest.mark.parametrize(
    "names, flags",
    [
        ({"section_heading": "Route on the verdict", "defect_name": "x"}, ("--section-slug=verdict-mapping",)),
        ({"section_heading": "Route on the verdict", "defect_name": "x"}, ("--defect-key=x",)),
        ({"section_heading": "Route on the verdict"}, ()),
        ({"defect_name": "x"}, ()),
        ({}, ()),
    ],
    ids=["slug-twice", "key-twice", "no-key", "no-slug", "neither"],
)
def test_each_pair_takes_exactly_one_form(names, flags):
    code, payload = _fingerprint_stdin("bug", "gate", names, *flags)
    assert code == 1
    assert "--section-slug" in payload["error"] or "--defect-key" in payload["error"]


@pytest.mark.parametrize(
    "raw",
    [b"", b"not json", b"[1]", b'{"section": "x"}', b'{"section_heading": 1, "defect_name": "x"}',
     b'{"section_heading": " ", "defect_name": "x"}', b"\xff\xfe"],
    ids=["empty", "junk", "list", "unknown-key", "not-a-string", "blank", "not-utf8"],
)
def test_stdin_that_is_not_the_names_object_exits_one(raw):
    code, payload = _fingerprint_stdin("bug", "gate", raw)
    assert code == 1
    assert "error" in payload


def test_the_flags_alone_still_need_both_without_stdin():
    proc = _run("fingerprint", "--severity", "bug", "--stage", "gate", "--defect-key", "gate-status")
    assert proc.returncode == 2, "an argparse usage error exits 2"


# --- Fingerprint: the title and the body header ---------------------------------

GATE_NAMES = {"section_heading": "Route on the verdict", "defect_name": "gate_status"}


def test_a_short_description_gives_the_title_and_its_regression_twin():
    code, payload = _fingerprint_stdin("bug", "gate", {**GATE_NAMES, "short_description": "the gate reads a stale trace"})
    assert code == 0, payload
    fp = payload["fp"]
    assert payload["title"] == f"[health-check][bug][{fp}] ultracode-goal/gate: the gate reads a stale trace"
    assert payload["regression_title"] == (
        f"[health-check][bug][{fp}] ultracode-goal/gate: REGRESSION: the gate reads a stale trace"
    )
    # The description changes no fingerprint.
    _, bare = _fingerprint_stdin("bug", "gate", GATE_NAMES)
    assert {k: payload[k] for k in ("fp", "legacy_fp", "tuple", "section_slug", "defect_key")} == {
        k: bare[k] for k in ("fp", "legacy_fp", "tuple", "section_slug", "defect_key")
    }


def test_the_description_is_trimmed_and_works_beside_the_flags():
    code, payload = _fingerprint_stdin("friction", "execute", {"short_description": "  a budget left unsaid  "},
                                       "--section-slug=ambiguous-budget", "--defect-key=budget")
    assert code == 0, payload
    assert payload["title"] == f"[health-check][friction][{payload['fp']}] ultracode-goal/execute: a budget left unsaid"


def test_the_body_header_carries_the_machine_read_sections():
    code, payload = _fingerprint_stdin("gap", "gate", {**GATE_NAMES, "short_description": "x"})
    assert code == 0, payload
    assert payload["body_header"] == (
        "## Workflow\n`ultracode-goal/gate`\n\n"
        "## Step File\n`skills/ultracode-goal/references/gate.md`\n\n"
        "## Section\n`route-on-the-verdict`\n\n"
        "## Severity\n`gap`\n\n"
        f"## Fingerprint\n`{payload['fp']}`\n\n"
        f"Section fingerprint: `{payload['legacy_fp']}`\n\n"
        "## Defect Key\n`gate-status`\n"
    )


@pytest.mark.parametrize(
    "description",
    ["the `gate` reads", "costs $5", 'a "quoted" word', "a back\\slash", "two\nlines", "carriage\rreturn", "", "  ",
     "it fails!", "a\ttab", "line\N{LINE SEPARATOR}separator", "paragraph\N{PARAGRAPH SEPARATOR}separator",
     "next\N{NEL}line", "vertical\vtab", "form\ffeed", "nul\x00byte"],
    ids=["backtick", "dollar", "double-quote", "backslash", "newline", "carriage-return", "empty", "blank", "bang",
         "tab", "u2028", "u2029", "u0085", "vt", "ff", "nul"],
)
def test_a_description_the_command_line_cannot_carry_exits_one(description):
    code, payload = _fingerprint_stdin("bug", "gate", {**GATE_NAMES, "short_description": description})
    assert code == 1
    assert "short_description" in payload["error"]
    assert set(payload) == {"error"}, "nothing is printed but the error"


@pytest.mark.parametrize("description", ["it's 'single' quoted", "50% of #3 (a & b) <c>", "naïve défaut"])
def test_a_description_safe_inside_double_quotes_is_kept_as_written(description):
    code, payload = _fingerprint_stdin("bug", "gate", {**GATE_NAMES, "short_description": description})
    assert code == 0, payload
    assert payload["title"].endswith(f"ultracode-goal/gate: {description}")


def test_a_non_ascii_title_is_printed_as_itself_in_utf8():
    """The title is used exactly as printed, so it must not reach the run as a \\uXXXX escape, whatever the locale."""
    data = json.dumps({**GATE_NAMES, "short_description": "naïve défaut"}).encode("utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "fingerprint", "--severity", "bug", "--stage", "gate", "--stdin"],
        capture_output=True, env=_env(PYTHONIOENCODING="latin-1"), input=data, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ultracode-goal/gate: naïve défaut".encode("utf-8") in proc.stdout
    assert b"\\u00e9" not in proc.stdout


def test_the_regression_title_is_capped_at_githubs_256_characters():
    _, payload = _fingerprint_stdin("friction", "gate", {**GATE_NAMES, "short_description": "x"})
    room = 256 - len(payload["regression_title"]) + 1
    code, payload = _fingerprint_stdin("friction", "gate", {**GATE_NAMES, "short_description": "x" * room})
    assert code == 0, payload
    assert len(payload["regression_title"]) == 256
    code, payload = _fingerprint_stdin("friction", "gate", {**GATE_NAMES, "short_description": "x" * (room + 1)})
    assert code == 1
    assert "257 characters long; GitHub takes at most 256" in payload["error"]


# --- queue ---------------------------------------------------------------------------


def _finding(severity: str = "bug", stage: str = "gate", description: str = "a defect") -> dict:
    """A real fingerprint payload: the title a queued draft is filed under and the body_header it opens with."""
    code, payload = _fingerprint_stdin(severity, stage, {"short_description": description},
                                       "--section-slug=route-on-the-verdict", "--defect-key=gate-status")
    assert code == 0, payload
    return payload


def _draft(path: Path, finding: dict, rest: bytes = b"\n## Finding\nOne sentence.\n") -> Path:
    path.write_bytes(finding["body_header"].encode("utf-8") + rest)
    return path


def _queue(mod, capsys, queue_dir: Path, body: Path, title: str, repo: str = "o/r") -> tuple[int, dict]:
    # The `=` forms, so a value that starts with a dash reaches the script's own check.
    return _main(mod, capsys, "queue", "--queue-dir", str(queue_dir), "--body-file", str(body),
                 f"--title={title}", f"--repo={repo}")


def test_two_queued_findings_in_the_same_second_get_a_counter(tmp_path, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_queue_stamp", lambda: "20261114-093012")
    finding = _finding()
    body = _draft(tmp_path / "hc-body-fp-abc1234.md", finding, b"\r\n## Finding\r\n\xe2\x9c\x93\n")
    queue_dir = tmp_path / "out" / "improvement-queue"
    paths = []
    for _ in range(3):
        code, result = _queue(mod, capsys, queue_dir, body, finding["title"])
        assert code == 0, result
        paths.append(Path(result["path"]))
    assert [p.name for p in paths] == [
        "hc-ultracode-goal-gate-20261114-093012.md",
        "hc-ultracode-goal-gate-20261114-093012-2.md",
        "hc-ultracode-goal-gate-20261114-093012-3.md",
    ]
    assert all(p.is_absolute() and p.parent == queue_dir.resolve() for p in paths)
    # The body, byte for byte: no frontmatter, line endings and characters as written.
    assert all(p.read_bytes() == body.read_bytes() for p in paths)


def test_a_file_already_there_is_never_overwritten(tmp_path, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_queue_stamp", lambda: "20261114-093012")
    (tmp_path / "hc-ultracode-goal-execute-20261114-093012.md").write_text("earlier", encoding="utf-8")
    finding = _finding(stage="execute")
    body = _draft(tmp_path / "body.md", finding)
    code, result = _queue(mod, capsys, tmp_path, body, finding["title"])
    assert code == 0
    assert Path(result["path"]).name == "hc-ultracode-goal-execute-20261114-093012-2.md"
    assert (tmp_path / "hc-ultracode-goal-execute-20261114-093012.md").read_text(encoding="utf-8") == "earlier"


def test_the_queue_name_is_the_utc_time(tmp_path, mod, monkeypatch):
    from datetime import datetime, timedelta, timezone

    instant = datetime(2026, 11, 14, 9, 30, 12, tzinfo=timezone.utc)

    class Clock:
        """A host four hours east of UTC: its wall clock differs from the UTC instant."""

        @staticmethod
        def now(tz=None):
            if tz is None:
                return (instant + timedelta(hours=4)).replace(tzinfo=None)
            return instant.astimezone(tz)

    monkeypatch.setattr(mod, "datetime", Clock)
    assert mod._queue_stamp() == "20261114-093012"
    monkeypatch.undo()
    finding = _finding(stage="preflight")
    body = _draft(tmp_path / "body.md", finding)
    proc = _run("queue", "--queue-dir", str(tmp_path / "q"), "--body-file", str(body),
                "--title", finding["title"], "--repo", "o/r")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert re.fullmatch(r"hc-ultracode-goal-preflight-[0-9]{8}-[0-9]{6}\.md", Path(json.loads(proc.stdout)["path"]).name)


def test_a_failed_write_leaves_no_partial_queue_file(tmp_path, mod, monkeypatch, capsys):
    finding = _finding()
    body = _draft(tmp_path / "body.md", finding, b"x" * 4096)
    queue_dir = tmp_path / "q"

    def disk_full(fd, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(mod.os, "write", disk_full)
    code, result = _queue(mod, capsys, queue_dir, body, finding["title"])
    monkeypatch.undo()
    assert code == 1
    assert "could not write" in result["error"]
    assert queue_dir.is_dir() and list(queue_dir.iterdir()) == []


def test_a_missing_body_file_exits_one_and_creates_nothing(tmp_path):
    proc = _run("queue", "--queue-dir", str(tmp_path / "q"), "--body-file", str(tmp_path / "nope.md"),
                "--title", _finding()["title"], "--repo", "o/r")
    assert proc.returncode == 1
    assert "body file" in json.loads(proc.stdout)["error"]
    assert not (tmp_path / "q").exists()


def test_queue_takes_no_stage_argument(tmp_path):
    """The draft's header gives the stage, and the title check proves it, so --stage could only fail (leanness-4)."""
    finding = _finding()
    body = _draft(tmp_path / "body.md", finding)
    proc = _run("queue", "--queue-dir", str(tmp_path / "q"), "--stage", "gate", "--body-file", str(body),
                "--title", finding["title"], "--repo", "o/r")
    assert proc.returncode == 2 and "--stage" in proc.stderr
    assert not (tmp_path / "q").exists()


@pytest.mark.parametrize("stage", ["gate", "ingest-and-scope", "finalize"])
def test_the_queue_file_is_named_after_the_drafts_own_stage(tmp_path, mod, monkeypatch, capsys, stage):
    monkeypatch.setattr(mod, "_queue_stamp", lambda: "20261114-093012")
    finding = _finding(stage=stage)
    code, result = _queue(mod, capsys, tmp_path / "q", _draft(tmp_path / "hc-body.md", finding), finding["title"])
    assert code == 0, result
    assert Path(result["path"]).name == f"hc-ultracode-goal-{stage}-20261114-093012.md"


def test_queue_needs_all_four_arguments(tmp_path):
    full = {"--queue-dir": str(tmp_path), "--body-file": str(tmp_path / "b.md"), "--title": "t", "--repo": "o/r"}
    for missing in full:
        argv = [arg for flag, value in full.items() if flag != missing for arg in (flag, value)]
        assert _run("queue", *argv).returncode == 2, missing


def _expected_commands(finding: dict, severity: str, repo: str, title: str, path: str) -> list[list[str]]:
    """The argv of the label create, the create and the create without labels, as the shell must read them."""
    fp = finding["fp"]
    return [
        ["gh", "label", "create", "--repo", repo, fp, "--color", "ededed",
         "--description", "Health-check fingerprint dedup key"],
        ["gh", "issue", "create", "--repo", repo, "--title", title,
         "--label", f"health-check,workflow-improvement,{severity},{fp}", "--body-file", path],
        ["gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", path],
    ]


def test_queue_prints_the_three_submit_commands_every_argument_quoted(tmp_path, mod, capsys):
    """The model no longer fills in the commands: the script prints them, quoted for a shell (determinism-2)."""
    finding = _finding("bug", "gate", "it's a 'quoted' title (50% & more) <here> naïve")
    queue_dir = tmp_path / "My Projects" / "improvement queue"
    body = _draft(tmp_path / "hc-body.md", finding)
    code, result = _queue(mod, capsys, queue_dir, body, finding["title"], repo="o/r")
    assert code == 0, result
    assert set(result) == {"path", "commands"}
    path = result["path"]
    assert " " in path and Path(path).parent == queue_dir.resolve()
    assert all("\n" not in command for command in result["commands"]), "each command is one line"
    # The shell gets every argument back exactly as given, the path with its spaces and the title with its quotes;
    # no redirect or `||` that a POSIX-only shell or an allow rule would trip on.
    assert [shlex.split(c) for c in result["commands"]] == _expected_commands(finding, "bug", "o/r", finding["title"], path)
    assert not [c for c in result["commands"] if "2>" in c or "||" in c]
    assert f"--body-file {shlex.quote(path)}" in result["commands"][1] and shlex.quote(path) != path
    # `--repo` follows the subcommand, so an allow rule scoped to the repository matches each of them.
    for command, prefix in zip(result["commands"], ("gh label create --repo o/r ", "gh issue create --repo o/r ",
                                                     "gh issue create --repo o/r ")):
        assert command.startswith(prefix), command


@pytest.mark.parametrize("severity", ["bug", "friction", "gap"])
def test_queue_reads_the_severity_and_fp_from_a_regression_draft_with_crlf(tmp_path, mod, capsys, severity):
    finding = _finding(severity, "execute")
    opened = "Regression of https://github.com/o/r/issues/1 (resolved 2026-07-19).\n\n" + finding["body_header"]
    body = tmp_path / "hc-body.md"
    body.write_bytes(("\ufeff" + opened + "\n## Finding\nx\n").replace("\n", "\r\n").encode("utf-8"))
    repo = "ghe.example.com/team/internal-repo"
    code, result = _queue(mod, capsys, tmp_path / "q", body, finding["regression_title"], repo=repo)
    assert code == 0, result
    assert [shlex.split(c) for c in result["commands"]] == _expected_commands(
        finding, severity, repo, finding["regression_title"], result["path"])


def test_a_draft_that_is_a_bom_then_the_body_header_is_read(tmp_path, mod, capsys):
    finding = _finding("friction")
    raw = b"\xef\xbb\xbf" + finding["body_header"].encode("utf-8") + b"\n## Finding\nx\n"
    assert mod._draft_keys(raw) == ("gate", "friction", finding["fp"])
    body = tmp_path / "hc-body.md"
    body.write_bytes(raw)
    code, result = _queue(mod, capsys, tmp_path / "q", body, finding["title"])
    assert code == 0, result
    assert Path(result["path"]).read_bytes() == raw


def test_queue_prints_a_non_ascii_title_as_itself_in_utf8(tmp_path):
    """The commands are shown as printed, so a title must not reach the run as a \\uXXXX escape, whatever the locale."""
    finding = _finding("bug", "gate", "naïve défaut")
    body = _draft(tmp_path / "hc-body.md", finding)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "queue", "--queue-dir", str(tmp_path / "q"),
         "--body-file", str(body), "--title", finding["title"], "--repo", "o/r"],
        capture_output=True, env=_env(PYTHONIOENCODING="latin-1"), timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ultracode-goal/gate: naïve défaut".encode("utf-8") in proc.stdout
    assert b"\\u00" not in proc.stdout


@needs_posix
def test_the_printed_commands_run_in_a_shell_as_printed(tmp_path, mod, capsys):
    """The matrix row run for real: a shell reads each command and gh receives each argument unchanged."""
    folder = tmp_path / "fake-bin"
    folder.mkdir()
    gh = folder / "gh"
    gh.write_text('#!/bin/sh\nfor arg in "$@"; do printf \'%s\\0\' "$arg"; done >> "$ARGV_LOG"\n'
                  'printf \'\\n\' >> "$ARGV_LOG"\nexit 1\n', encoding="utf-8")
    gh.chmod(0o755)
    finding = _finding("gap", "gate", "it's 'here' & (there)")
    body = _draft(tmp_path / "hc-body.md", finding)
    code, result = _queue(mod, capsys, tmp_path / "a queue dir", body, finding["title"])
    assert code == 0, result
    log = tmp_path / "argv.log"
    proc = subprocess.run(["sh", "-c", "\n".join(result["commands"])], capture_output=True, text=True, timeout=60,
                          env=_env(f"{folder}{os.pathsep}/usr/bin{os.pathsep}/bin", ARGV_LOG=str(log)))
    # A failed label create does not stop the create that follows it.
    assert proc.returncode == 1 and proc.stderr == ""
    calls = [line.split("\0")[:-1] for line in log.read_text(encoding="utf-8").splitlines()]
    assert calls == [argv[1:] for argv in _expected_commands(finding, "gap", "o/r", finding["title"], result["path"])]


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"## Finding\nno header at all\n",
        # The template's placeholders, or a header cut short, are no body_header.
        b"## Workflow\n`ultracode-goal/gate`\n\n## Severity\n`bug`\n\n## Fingerprint\n`fp-abc1234`\n",
        None,
        # The header must open the draft, under one opening line at most.
        b"Regression of x.\n\nA second line.\n\n",
        b"## Finding\nx\n\n",
    ],
    ids=["empty", "no-header", "partial-header", "template-placeholder", "two-opening-lines", "header-not-first"],
)
def test_a_draft_with_no_body_header_exits_one_and_writes_no_file(tmp_path, mod, capsys, body):
    finding = _finding()
    if body is None:
        body = finding["body_header"].replace(finding["fp"], "fp-XXXXXXX").encode("utf-8")
    elif body.endswith(b"\n\n"):
        body += finding["body_header"].encode("utf-8")
    path = tmp_path / "hc-body.md"
    path.write_bytes(body)
    code, result = _queue(mod, capsys, tmp_path / "q", path, finding["title"])
    assert code == 1
    assert set(result) == {"error"} and "holds no body_header" in result["error"]
    assert not (tmp_path / "q").exists()


@pytest.mark.parametrize("which", ["fp", "severity", "stage", "bare"])
def test_a_title_that_is_not_the_drafts_exits_one_and_writes_no_file(tmp_path, mod, capsys, which):
    finding = _finding("bug")
    other = {"fp": finding["title"].replace(finding["fp"], "fp-0000000"),
             "severity": _finding("friction")["title"],
             "stage": finding["title"].replace("ultracode-goal/gate:", "ultracode-goal/execute:"),
             "bare": "a defect"}[which]
    code, result = _queue(mod, capsys, tmp_path / "q", _draft(tmp_path / "hc-body.md", finding), other)
    assert code == 1
    assert "is not this draft's" in result["error"]
    assert f"[health-check][bug][{finding['fp']}] ultracode-goal/gate: " in result["error"]
    assert not (tmp_path / "q").exists()


@pytest.mark.parametrize(
    "tail",
    ["x" * 256, "two\nlines", "a\ttab", "costs $5", "the `gate`", 'a "quoted" word', "it fails!", "back\\slash"],
    ids=["too-long", "newline", "tab", "dollar", "backtick", "double-quote", "bang", "backslash"],
)
def test_a_title_fingerprint_would_refuse_exits_one_and_writes_no_file(tmp_path, mod, capsys, tail):
    finding = _finding("bug")
    code, result = _queue(mod, capsys, tmp_path / "q", _draft(tmp_path / "hc-body.md", finding),
                          finding["title"] + tail)
    assert code == 1
    assert ("GitHub takes at most 256" if tail.startswith("x") else "not printable") in result["error"]
    assert not (tmp_path / "q").exists()


@pytest.mark.parametrize("repo", ["", "o", "o/r/x/y", "o/r x", "-o/r", "o/r;rm", "https://github.com/o/r", "o//r"])
def test_a_repo_that_is_not_owner_slash_repo_exits_one_and_writes_no_file(tmp_path, mod, capsys, repo):
    finding = _finding("bug")
    code, result = _queue(mod, capsys, tmp_path / "q", _draft(tmp_path / "hc-body.md", finding), finding["title"],
                          repo=repo)
    assert code == 1
    assert "invalid repo" in result["error"] and "[HOST/]OWNER/REPO" in result["error"]
    assert not (tmp_path / "q").exists()


@pytest.mark.parametrize("repo", ["armelhbobdad/bmad-module-ultracode-goal", "o/r.js", "ghe.example.com/team/repo_1"])
def test_a_repo_of_owner_slash_repo_with_an_optional_host_is_taken(tmp_path, mod, capsys, repo):
    finding = _finding("bug")
    code, result = _queue(mod, capsys, tmp_path / "q", _draft(tmp_path / "hc-body.md", finding), finding["title"],
                          repo=repo)
    assert code == 0, result
    assert shlex.split(result["commands"][1])[4] == repo


@pytest.mark.parametrize("severity", ["bug", "friction", "gap"])
@pytest.mark.parametrize("stage", ["ingest-and-scope", "define-done", "finalize"])
def test_every_body_header_the_script_prints_is_read_back(mod, severity, stage):
    fp, legacy_fp, _ = mod._compute_fp(severity, stage, "a-section", "a-key")
    header = mod.body_header(severity, stage, "a-section", "a-key", fp, legacy_fp)
    assert mod._draft_keys(header.encode("utf-8")) == (stage, severity, fp)
    assert mod._draft_keys(header.replace("\n", "\r\n").encode("utf-8")) == (stage, severity, fp)
    # The section fingerprint is never read as the defect's own.
    assert mod._draft_keys(header.replace(f"`{fp}`", "`fp-XXXXXXX`").encode("utf-8")) is None


# --- seen: the verdict table -------------------------------------------------


def test_seen_missing_cache_is_unseen(tmp_path):
    assert _seen(tmp_path / "nope.json") == {
        "seen": False,
        "status": "unseen",
        "record": None,
        "matched_on": None,
        "opening_line": None,
    }


@pytest.mark.parametrize("flag", ["--fp", "--legacy-fp"])
def test_seen_invalid_fingerprint_exits_one(tmp_path, flag):
    values = {"--fp": FP, "--legacy-fp": LEGACY, flag: "fp-XYZ"}
    proc = _run("seen", "--fp", values["--fp"], "--legacy-fp", values["--legacy-fp"],
                "--cache", str(tmp_path / "c.json"))
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)


def test_seen_requires_the_legacy_fp(tmp_path):
    proc = _run("seen", "--fp", FP, "--cache", str(tmp_path / "c.json"))
    assert proc.returncode == 2


def test_record_then_seen_round_trip(tmp_path):
    cache = tmp_path / "seen.json"
    rec = _record(cache)
    assert rec.returncode == 0, rec.stdout
    new = {"issue_url": URL, "action": "created", "date": DAY}
    assert json.loads(rec.stdout) == {"written": True, "fp": FP, "record": new, "set_aside": None}

    # No gh on PATH: the issue-state check cannot run, so the record stays handled.
    assert _seen(cache) == {"seen": True, "status": "handled", "record": new, "matched_on": "fp", "opening_line": None}


@pytest.mark.parametrize("action", ["created", "reacted", "commented"])
@pytest.mark.parametrize("url", ["", None])
def test_a_written_action_with_no_url_is_handled(tmp_path, action, url):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live(action, url)})
    payload = _seen(cache)
    assert (payload["seen"], payload["status"], payload["matched_on"]) == (True, "handled", "fp")


def test_seen_resolved_does_not_suppress(tmp_path):
    # The fail-open this closes: a fixed finding used to keep suppressing
    # forever, so a REGRESSION of the same defect was silently swallowed.
    cache = _write_cache(tmp_path / "seen.json", {FP: {"action": "resolved", "issue_url": "", "date": "2026-07-19"}})
    payload = _seen(cache)
    assert payload["seen"] is False, "a resolved fingerprint must not suppress"
    assert payload["status"] == "regression"
    # The record RIDES ALONG so the caller can link the original rather than
    # file the recurrence as a first sighting.
    assert payload["record"] == {"action": "resolved", "issue_url": "", "date": "2026-07-19"}
    assert payload["matched_on"] == "fp"


@pytest.mark.parametrize(
    "record",
    [
        {"action": "queued", "issue_url": "", "date": "2026-07-19"},
        {"action": "teleported", "issue_url": "", "date": "2026-07-19"},
        {"issue_url": URL, "date": "2026-07-19"},
        ["not", "an", "object"],
        "created",
    ],
    ids=["old-queued", "unknown-action", "no-action", "a-list", "a-string"],
)
def test_a_record_this_version_does_not_write_is_unrecognized(tmp_path, record):
    # An old `queued` record, a hand-edit or a newer module's record cannot be
    # confirmed handled, so it reports: a duplicate is closed by the dedup Action,
    # a silenced regression is caught by nothing.
    cache = _write_cache(tmp_path / "seen.json", {FP: record})
    payload = _seen(cache)
    assert payload == {"seen": False, "status": "unrecognized", "record": record, "matched_on": "fp",
                       "opening_line": None}


def test_a_queued_bug_never_suppresses_a_later_attended_report(tmp_path):
    """A headless run with autosubmit off used to record `queued`, which suppressed the [Y] filing later."""
    cache = tmp_path / "seen.json"
    refused = _record(cache, action="queued", url="")
    assert refused.returncode == 1, "nothing records a queued finding any more"
    assert not cache.exists()
    assert _seen(cache)["seen"] is False


# --- seen: the legacy (section) fingerprint ------------------------------------


@pytest.mark.parametrize("action", ["created", "reacted", "commented"])
def test_a_legacy_record_that_would_suppress_is_unseen(tmp_path, action):
    record = _live(action, "")
    cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
    assert _seen(cache) == {"seen": False, "status": "unseen", "record": record, "matched_on": "legacy_fp",
                            "opening_line": None}


def test_a_resolved_legacy_record_is_a_possible_regression(tmp_path):
    record = {"action": "resolved", "issue_url": URL, "date": "2026-07-19"}
    cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
    assert _seen(cache) == {
        "seen": False,
        "status": "possible-regression",
        "record": record,
        "matched_on": "legacy_fp",
        "opening_line": f"Possibly a regression of {URL} (resolved 2026-07-19): that report's fingerprint has no "
                        "defect key, so it may be another defect in this section.",
    }


def test_an_unrecognized_legacy_record_stays_unrecognized(tmp_path):
    record = {"action": "queued", "issue_url": "", "date": "2026-07-19"}
    cache = _write_cache(tmp_path / "seen.json", {LEGACY: record})
    payload = _seen(cache)
    assert (payload["status"], payload["matched_on"]) == ("unrecognized", "legacy_fp")


def test_the_record_under_fp_decides_over_the_legacy_one(tmp_path):
    cache = _write_cache(
        tmp_path / "seen.json",
        {FP: _live("created", ""), LEGACY: {"action": "resolved", "issue_url": "", "date": "2026-01-01"}},
    )
    payload = _seen(cache)
    assert (payload["status"], payload["matched_on"]) == ("handled", "fp")
    assert payload["record"] == _live("created", "")


# --- seen: the opening line ------------------------------------------------------

LOCAL_REGRESSION = "Regression of a previously resolved local finding (resolved 2026-07-19)."
LOCAL_POSSIBLE = "Possibly a regression of a previously resolved local finding in this section (resolved 2026-07-19)."


@pytest.mark.parametrize(
    "under, url, line",
    [
        (FP, URL, f"Regression of {URL} (resolved 2026-07-19)."),
        (FP, "", LOCAL_REGRESSION),
        (LEGACY, URL, f"Possibly a regression of {URL} (resolved 2026-07-19): that report's fingerprint has no defect "
                      "key, so it may be another defect in this section."),
        (LEGACY, "", LOCAL_POSSIBLE),
    ],
    ids=["fp-url", "fp-local", "legacy-url", "legacy-local"],
)
def test_a_resolved_record_gives_one_of_the_four_opening_lines(tmp_path, under, url, line):
    cache = _write_cache(tmp_path / "seen.json", {under: {"action": "resolved", "issue_url": url, "date": "2026-07-19"}})
    payload = _seen(cache)
    assert payload["status"] == ("regression" if under == FP else "possible-regression")
    assert payload["opening_line"] == line


@pytest.mark.parametrize(
    "record",
    [
        {"action": "resolved", "date": "2026-07-19"},
        {"action": "resolved", "issue_url": "http://example.invalid/1", "date": "2026-07-19"},
        {"action": "resolved", "issue_url": "https://x/1\n## Fingerprint", "date": "2026-07-19"},
        {"action": "resolved", "issue_url": 7, "date": "2026-07-19"},
    ],
    ids=["no-url", "not-https", "whitespace", "not-a-string"],
)
def test_a_url_a_body_should_not_carry_reads_as_a_local_finding(tmp_path, record):
    """The line goes into a public issue body verbatim, so only a plain https:// URL is written into it."""
    payload = _seen(_write_cache(tmp_path / "seen.json", {FP: record}))
    assert payload["opening_line"] == LOCAL_REGRESSION


@pytest.mark.parametrize("day", [None, "", "yesterday", "2026-07-19\n## Severity", 20260719])
def test_a_date_that_is_not_yyyy_mm_dd_is_unrecorded(tmp_path, day):
    record = {"action": "resolved", "issue_url": ""}
    if day is not None:
        record["date"] = day
    payload = _seen(_write_cache(tmp_path / "seen.json", {FP: record}))
    assert payload["opening_line"] == "Regression of a previously resolved local finding (resolved on an unrecorded date)."


@pytest.mark.parametrize(
    "cache_data",
    [{}, {FP: _live("created", "")}, {FP: {"action": "queued", "issue_url": "", "date": "2026-07-19"}},
     {LEGACY: _live("created", "")}],
    ids=["unseen", "handled", "unrecognized", "legacy-unseen"],
)
def test_every_other_verdict_has_no_opening_line(tmp_path, cache_data):
    assert _seen(_write_cache(tmp_path / "seen.json", cache_data))["opening_line"] is None


# --- seen: the issue-state check through gh -------------------------------------

FAKE_GH = """#!/bin/sh
PATH=/usr/bin:/bin
export PATH
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
case "$FAKE_GH_MODE" in
  fail) echo "gh: could not resolve to an issue" >&2; exit 1 ;;
  junk) echo "this is not json" ;;
  hang) sleep 60 & echo $! > "$FAKE_GH_CHILD"; wait ;;
  *) printf '%s\\n' "$FAKE_GH_MODE" ;;
esac
"""


def _plant_gh(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    gh = folder / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    return gh


@pytest.fixture
def fake_gh(tmp_path):
    """A fake gh in its own folder; returns (folder, log). Its mode is the env var FAKE_GH_MODE."""
    folder = tmp_path / "fake-bin"
    _plant_gh(folder)
    return folder, tmp_path / "gh.log"


def _gh_env(fake, mode: str) -> dict:
    folder, log = fake
    return _env(str(folder), FAKE_GH_LOG=str(log), FAKE_GH_MODE=mode)


def _gh_calls(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _answer(state: str, reason: str = "") -> str:
    return json.dumps({"state": state, "stateReason": reason})


@needs_posix
@pytest.mark.parametrize(
    "mode, status",
    [
        (_answer("OPEN"), "handled"),
        (_answer("CLOSED", "NOT_PLANNED"), "handled"),
        (_answer("CLOSED", "DUPLICATE"), "handled"),
        ("fail", "handled"),
        ("junk", "handled"),
        ("[]", "handled"),
        (json.dumps({"stateReason": "COMPLETED"}), "handled"),
        (_answer("CLOSED", "COMPLETED"), "regression"),
        (_answer("MERGED"), "regression"),
    ],
    ids=["open", "not-planned", "duplicate", "fail", "junk", "a-list", "no-state", "completed", "merged"],
)
def test_the_issue_state_decides_a_keyed_record(tmp_path, fake_gh, mode, status):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    payload = _seen(cache, env=_gh_env(fake_gh, mode))
    # The record dates the report, not the fix: only the issue's own state says it was fixed.
    opening = None
    if status == "regression":
        how = "merged" if mode == _answer("MERGED") else "closed as completed"
        opening = f"Regression of {URL}, {how} since its report on 2026-10-01."
    assert payload == {"seen": status == "handled", "status": status, "record": _live("created"), "matched_on": "fp",
                       "opening_line": opening}
    assert _gh_calls(fake_gh[1]) == [f"issue view {URL} --json state,stateReason"]


@needs_posix
def test_a_completed_close_under_the_legacy_fp_is_a_possible_regression(tmp_path, fake_gh):
    cache = _write_cache(tmp_path / "seen.json", {LEGACY: _live("created")})
    payload = _seen(cache, env=_gh_env(fake_gh, _answer("CLOSED", "COMPLETED")))
    assert (payload["status"], payload["matched_on"]) == ("possible-regression", "legacy_fp")
    assert payload["opening_line"] == (
        f"Possibly a regression of {URL}, closed as completed since its report on 2026-10-01: that report's "
        "fingerprint has no defect key, so it may be another defect in this section."
    )


def test_an_absent_gh_keeps_a_keyed_record_handled(tmp_path):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    assert _seen(cache)["status"] == "handled"


@needs_posix
@pytest.mark.parametrize(
    "url",
    ["http://github.com/o/r/issues/1", "--web", "https://github.com/o/r/issues/1 --web", "github.com/o/r/issues/1",
     "https://github.com/o/r/issues/1\n"],
    ids=["http", "a-flag", "whitespace", "no-scheme", "newline"],
)
def test_gh_never_runs_for_a_url_that_is_not_plain_https(tmp_path, fake_gh, url):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created", url)})
    payload = _seen(cache, env=_gh_env(fake_gh, _answer("CLOSED", "COMPLETED")))
    assert payload["status"] == "handled"
    assert _gh_calls(fake_gh[1]) == []


@needs_posix
def test_gh_never_runs_for_a_resolved_or_unrecognized_record(tmp_path, fake_gh):
    cache = _write_cache(
        tmp_path / "seen.json",
        {FP: {"action": "resolved", "issue_url": URL, "date": DAY}, OTHER: {"action": "queued", "issue_url": URL}},
    )
    env = _gh_env(fake_gh, _answer("OPEN"))
    assert _seen(cache, env=env)["status"] == "regression"
    assert _seen(cache, fp=OTHER, env=env)["status"] == "unrecognized"
    assert _gh_calls(fake_gh[1]) == []


@needs_posix
@pytest.mark.parametrize("path_form", [".", "empty-entry", "absolute"])
def test_a_gh_planted_in_the_current_folder_never_runs(tmp_path, path_form):
    """The current folder is the user's project: a gh planted there reads as no gh, and nothing is started."""
    project = tmp_path / "project"
    _plant_gh(project)
    log = tmp_path / "planted.log"
    path = {
        ".": ".",
        "empty-entry": os.pathsep + NO_GH_PATH,
        "absolute": str(project),
    }[path_form]
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    env = _env(path, FAKE_GH_LOG=str(log), FAKE_GH_MODE=_answer("CLOSED", "COMPLETED"))
    payload = _seen(cache, env=env, cwd=project)
    assert payload["status"] == "handled"
    assert not log.exists(), "the gh in the current folder ran"


# --- seen: the repository scope -----------------------------------------------------
# The cache serves every project on the machine, and a project may file to another repository (customization-1).

ABSENT = {"seen": False, "status": "unseen", "record": None, "matched_on": None, "opening_line": None}
OTHER_URL = "https://github.com/other/repo/issues/3"


@needs_posix
@pytest.mark.parametrize("under", [FP, LEGACY])
@pytest.mark.parametrize("record", [_live("created", OTHER_URL), _live("commented", OTHER_URL),
                                    {"action": "resolved", "issue_url": OTHER_URL, "date": "2026-07-19"}],
                         ids=["created", "commented", "resolved"])
def test_a_record_of_another_repositorys_issue_counts_as_none(tmp_path, fake_gh, under, record):
    """Neither suppressed by another tracker's record nor linked to its issue, and gh is never asked about it."""
    cache = _write_cache(tmp_path / "seen.json", {under: record})
    assert _seen(cache, env=_gh_env(fake_gh, _answer("CLOSED", "COMPLETED")), repo="me/repo") == ABSENT
    assert _gh_calls(fake_gh[1]) == []


@needs_posix
@pytest.mark.parametrize(
    "mode, status, opening",
    [(_answer("OPEN"), "handled", None),
     (_answer("CLOSED", "COMPLETED"), "regression", "Regression of {url}, closed as completed since its report on "
                                                    "2026-10-01.")],
    ids=["open", "completed"],
)
@pytest.mark.parametrize("repo", ["me/repo", "Me/Repo"], ids=["same-case", "other-case"])
def test_a_record_of_the_repositorys_own_issue_decides_as_before(tmp_path, fake_gh, mode, status, opening, repo):
    url = "https://github.com/me/repo/issues/7"
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created", url)})
    payload = _seen(cache, env=_gh_env(fake_gh, mode), repo=repo)
    assert payload == {"seen": status == "handled", "status": status, "record": _live("created", url),
                       "matched_on": "fp", "opening_line": opening and opening.format(url=url)}
    assert _gh_calls(fake_gh[1]) == [f"issue view {url} --json state,stateReason"]


@pytest.mark.parametrize(
    "record, status",
    [(_live("created", ""), "handled"), (_live("reacted", None), "handled"),
     ({"action": "resolved", "issue_url": "", "date": "2026-07-19"}, "regression"),
     ({"action": "queued", "issue_url": "", "date": "2026-07-19"}, "unrecognized"), ("created", "unrecognized")],
    ids=["created-empty-url", "reacted-no-url", "resolved-empty-url", "old-queued", "not-an-object"],
)
def test_a_record_that_names_no_repository_decides_as_without_repo(tmp_path, record, status):
    cache = _write_cache(tmp_path / "seen.json", {FP: record})
    assert _seen(cache, repo="me/repo") == _seen(cache)
    assert _seen(cache, repo="me/repo")["status"] == status


def test_without_repo_another_repositorys_record_still_decides(tmp_path):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created", OTHER_URL)})
    assert _seen(cache)["status"] == "handled"


def test_an_other_repository_record_under_fp_leaves_the_legacy_one_to_decide(tmp_path):
    own = {"action": "resolved", "issue_url": "https://github.com/me/repo/issues/2", "date": "2026-07-19"}
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created", OTHER_URL), LEGACY: own})
    payload = _seen(cache, repo="me/repo")
    assert (payload["status"], payload["record"], payload["matched_on"]) == ("possible-regression", own, "legacy_fp")


@pytest.mark.parametrize(
    "repo, url, counts",
    [("me/repo", "https://github.com/me/repo-two/issues/1", False),
     ("me/repo", "https://github.com/me/repo/pull/4", True),
     ("me/repo", "http://github.com/me/repo/issues/1", False),
     ("me/repo", "https://github.com/me/repo", False),
     ("ghe.example.com/team/repo", "https://ghe.example.com/team/repo/issues/1", True),
     ("ghe.example.com/team/repo", "https://github.com/team/repo/issues/1", False)],
    ids=["longer-name", "pull-request", "http", "repository-page", "host-form", "host-form-on-github"],
)
def test_a_record_counts_only_under_the_repositorys_own_url(tmp_path, repo, url, counts):
    cache = _write_cache(tmp_path / "seen.json", {FP: {"action": "resolved", "issue_url": url, "date": "2026-07-19"}})
    assert _seen(cache, repo=repo)["status"] == ("regression" if counts else "unseen")


@pytest.mark.parametrize("repo", ["", "o", "o/r/x/y", "o/r x", "-o/r", "https://github.com/o/r"])
def test_seen_refuses_a_repo_that_is_not_owner_slash_repo(tmp_path, repo):
    proc = _run("seen", "--fp", FP, "--legacy-fp", LEGACY, "--cache", str(tmp_path / "c.json"), f"--repo={repo}")
    assert proc.returncode == 1
    assert json.loads(proc.stdout) == {"error": f"invalid repo {repo!r}; expected [HOST/]OWNER/REPO"}


HEARTBEAT = """
import pathlib, subprocess, sys
beat = pathlib.Path(sys.argv[1])
child = (
    "import pathlib, sys, time\\n"
    "beat = pathlib.Path(sys.argv[1])\\n"
    "while True:\\n"
    "    beat.write_text(str(time.monotonic()))\\n"
    "    time.sleep(0.1)\\n"
)
subprocess.Popen([sys.executable, "-c", child, str(beat)])
import time
time.sleep(60)
"""


def test_run_stops_a_call_and_everything_it_started_at_the_limit(tmp_path, mod):
    """Runs on every platform: killpg on POSIX, taskkill /T on Windows. The child's heartbeat stops."""
    beat = tmp_path / "beat"
    start = time.monotonic()
    returncode, _out, _err = mod._run([sys.executable, "-c", HEARTBEAT, str(beat)], 1.0)
    assert returncode is None, "a call stopped at the limit has no exit code"
    assert time.monotonic() - start < 1.0 + 3 * mod.KILL_WAIT_SEC + 5
    assert beat.exists(), "the child never started"
    time.sleep(0.5)
    settled = beat.read_text()
    time.sleep(1.0)
    assert beat.read_text() == settled, "the process the call started outlived the time limit"


def test_replace_is_retried_while_windows_holds_the_target_open(tmp_path, mod, monkeypatch):
    """Windows refuses a rename over a file another process has open; the write lands once it is let go."""
    target = tmp_path / "seen.json"
    target.write_text("{}\n", encoding="utf-8")
    real_replace = os.replace
    refusals = []

    def busy_twice(src, dst):
        if len(refusals) < 2:
            refusals.append(dst)
            raise PermissionError(13, "The process cannot access the file")
        real_replace(src, dst)

    monkeypatch.setattr(mod, "_IS_WINDOWS", True)
    monkeypatch.setattr(mod.os, "replace", busy_twice)
    mod._atomic_write(target, '{"fp-abc1234": {}}\n')
    assert len(refusals) == 2
    assert target.read_text(encoding="utf-8") == '{"fp-abc1234": {}}\n'
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json"], "no temp file is left"


def test_the_time_limit_is_ten_seconds(mod):
    assert mod.GH_TIMEOUT_SEC == 10.0


def test_seen_hands_gh_the_ten_second_limit(tmp_path, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_resolve_outside_cwd", lambda name: "/fake/gh" if name == "gh" else None)
    limits = []

    def fake_run(argv, timeout):
        limits.append((argv, timeout))
        return 0, _answer("OPEN").encode("utf-8"), b""

    monkeypatch.setattr(mod, "_run", fake_run)
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    code, payload = _main(mod, capsys, "seen", "--fp", FP, "--legacy-fp", LEGACY, "--cache", str(cache))
    assert code == 0 and payload["status"] == "handled"
    assert limits == [(["/fake/gh", "issue", "view", URL, "--json", "state,stateReason"], 10.0)]


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    try:
        return stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"  # a zombie has ended
    except (OSError, IndexError):
        return False


@needs_posix
def test_a_hanging_gh_is_stopped_with_everything_it_started(tmp_path, fake_gh, mod, monkeypatch, capsys):
    folder, log = fake_gh
    child = tmp_path / "child.pid"
    monkeypatch.setenv("PATH", str(folder))
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_MODE", "hang")
    monkeypatch.setenv("FAKE_GH_CHILD", str(child))
    monkeypatch.setattr(mod, "GH_TIMEOUT_SEC", 1.0)
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})

    start = time.monotonic()
    code, payload = _main(mod, capsys, "seen", "--fp", FP, "--legacy-fp", LEGACY, "--cache", str(cache))
    elapsed = time.monotonic() - start

    assert code == 0
    assert (payload["seen"], payload["status"]) == (True, "handled")
    assert elapsed < 1.0 + 3 * mod.KILL_WAIT_SEC + 5
    pid = int(child.read_text(encoding="utf-8").strip())
    deadline = time.monotonic() + 5
    while not _gone(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _gone(pid), "the process gh started outlived the time limit"


# --- record --------------------------------------------------------------------


def test_record_creates_nested_parent_dirs(tmp_path):
    cache = tmp_path / "deep" / "nested" / "tree" / "seen.json"
    rec = _record(cache)
    assert rec.returncode == 0, rec.stdout
    assert cache.is_file()


def test_record_merges_distinct_fps_and_keeps_every_other_key(tmp_path):
    others = {
        LEGACY: {"action": "resolved", "issue_url": "", "date": "2026-01-01"},
        "not-a-fingerprint": [1, 2, 3],
        OTHER: {"action": "queued", "issue_url": "", "date": "2026-02-02"},
    }
    cache = _write_cache(tmp_path / "seen.json", others)
    assert _record(cache, action="reacted").returncode == 0

    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data[FP] == {"issue_url": URL, "action": "reacted", "date": DAY}
    assert {k: v for k, v in data.items() if k != FP} == others, "a legacy record is never rewritten"


def test_record_overwrites_same_fp_in_place(tmp_path):
    cache = tmp_path / "seen.json"
    assert _record(cache, action="created", day="2026-06-04").returncode == 0
    assert _record(cache, action="commented", day="2026-06-05").returncode == 0
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert list(data.keys()) == [FP]
    assert data[FP] == {"issue_url": URL, "action": "commented", "date": "2026-06-05"}


@pytest.mark.parametrize(
    "over",
    [
        {"action": "queued", "url": ""},
        {"action": "upvoted"},
        {"action": "created", "url": ""},
        {"action": "reacted", "url": "http://github.com/o/r/issues/1"},
        {"action": "commented", "url": "--web"},
        {"action": "created", "url": "https://github.com/o/r/issues/1 x"},
        {"action": "resolved", "url": "http://github.com/o/r/pull/2"},
        {"day": "2026-13-01"},
        {"day": "2026-02-30"},
        {"day": "20261114"},
        {"day": DAY + "\n"},
        {"fp": "fp-XYZ"},
        {"fp": FP + "\n"},
    ],
    ids=["queued", "unknown-action", "created-empty-url", "http", "a-flag", "whitespace", "resolved-http",
         "month-13", "feb-30", "no-dashes", "date-newline", "bad-fp", "fp-newline"],
)
def test_a_record_that_breaks_its_rule_exits_one_and_writes_nothing(tmp_path, over):
    cache = tmp_path / "seen.json"
    proc = _record(cache, **over)
    assert proc.returncode == 1
    assert "error" in json.loads(proc.stdout)
    assert not cache.exists()
    assert list(tmp_path.iterdir()) == [], "a refused record takes no lock and writes no file"


@pytest.mark.parametrize("url", ["", "https://github.com/o/r/pull/2"])
def test_resolved_takes_an_empty_or_https_url(tmp_path, url):
    cache = tmp_path / "seen.json"
    proc = _record(cache, action="resolved", url=url)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["record"] == {"issue_url": url, "action": "resolved", "date": DAY}


def _resolved_cache(tmp_path: Path) -> tuple[Path, dict]:
    resolved = {"action": "resolved", "issue_url": URL, "date": "2026-10-02"}
    return _write_cache(tmp_path / "seen.json", {FP: resolved, OTHER: _live()}), resolved


@pytest.mark.parametrize("action", ["created", "reacted", "commented"])
def test_a_resolved_record_is_never_downgraded(tmp_path, action):
    cache, resolved = _resolved_cache(tmp_path)
    before = cache.read_bytes()
    proc = _record(cache, action=action, url="https://github.com/o/r/issues/5")
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout) == {"written": False, "fp": FP, "record": resolved, "set_aside": None}
    assert cache.read_bytes() == before


def test_the_regression_issue_replaces_a_resolved_record(tmp_path):
    cache, _ = _resolved_cache(tmp_path)
    new_url = "https://github.com/o/r/issues/5"
    proc = _record(cache, "--regression", url=new_url)
    assert proc.returncode == 0, proc.stdout
    new = {"issue_url": new_url, "action": "created", "date": DAY}
    assert json.loads(proc.stdout) == {"written": True, "fp": FP, "record": new, "set_aside": None}
    assert json.loads(cache.read_text(encoding="utf-8")) == {FP: new, OTHER: _live()}


def test_regression_on_a_record_that_is_not_resolved_writes_as_usual(tmp_path):
    cache = _write_cache(tmp_path / "seen.json", {FP: _live("created")})
    proc = _record(cache, "--regression", action="reacted")
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["written"] is True


def test_a_resolved_record_can_be_resolved_again(tmp_path):
    # The resolve recipe re-run with the resolving PR's URL: not a downgrade.
    cache, _ = _resolved_cache(tmp_path)
    proc = _record(cache, action="resolved", url="https://github.com/o/r/pull/9")
    assert json.loads(proc.stdout)["written"] is True
    assert json.loads(cache.read_text(encoding="utf-8"))[FP]["issue_url"] == "https://github.com/o/r/pull/9"


def test_a_seeded_defect_slug_carries_over_a_resolved_replace(tmp_path):
    """A record written by 7854e70's `record --defect-slug` keeps its slug when the resolve recipe replaces it."""
    seeded = {"action": "created", "issue_url": URL, "date": "2026-08-01", "defect_slug": "wrong-event-guard"}
    cache = _write_cache(tmp_path / "seen.json", {FP: seeded})
    proc = _record(cache, action="resolved", url="", day="2026-08-04")
    assert proc.returncode == 0, proc.stdout
    expected = {"issue_url": "", "action": "resolved", "date": "2026-08-04", "defect_slug": "wrong-event-guard"}
    assert json.loads(proc.stdout)["record"] == expected
    assert json.loads(cache.read_text(encoding="utf-8"))[FP] == expected


def test_record_no_longer_takes_a_defect_slug(tmp_path):
    proc = _record(tmp_path / "seen.json", "--defect-slug", "some-defect")
    assert proc.returncode == 2


# --- record: the corrupt cache ----------------------------------------------------

STAMPED = re.compile(r"seen\.json\.corrupt-\d{8}T\d{6}Z")


@pytest.mark.parametrize(
    "content",
    [b"\x00\xff garbage not json {{{", b"{bad", b"[]", b'"text"', b"\xff\xfe{}", b"[" * 200_000],
    ids=["garbage", "truncated", "a-list", "a-string", "not-utf8", "nested-past-the-parsers-depth"],
)
def test_a_corrupt_cache_is_set_aside_not_erased(tmp_path, content):
    cache = tmp_path / "seen.json"
    cache.write_bytes(content)
    proc = _record(cache)
    assert proc.returncode == 0, proc.stdout
    result = json.loads(proc.stdout)

    aside = Path(result["set_aside"])
    assert aside.parent == tmp_path and STAMPED.fullmatch(aside.name), aside
    assert aside.read_bytes() == content, "the corrupt records stay on disk for a hand repair"
    assert json.loads(cache.read_text(encoding="utf-8")) == {FP: {"issue_url": URL, "action": "created",
                                                                  "date": DAY}}
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["seen.json", "seen.json.lock", aside.name])


def test_seen_reads_a_corrupt_cache_as_unseen(tmp_path):
    cache = tmp_path / "seen.json"
    cache.write_bytes(b"\x00\xff not json at all {{{")
    assert _seen(cache)["status"] == "unseen"
    assert cache.read_bytes() == b"\x00\xff not json at all {{{", "seen never moves or rewrites the cache"


@pytest.mark.parametrize("content", [b"", b"  \n"])
def test_an_empty_cache_is_not_set_aside(tmp_path, content):
    cache = tmp_path / "seen.json"
    cache.write_bytes(content)
    proc = _record(cache)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["set_aside"] is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json", "seen.json.lock"]


def test_a_bom_cache_is_read(tmp_path):
    cache = tmp_path / "seen.json"
    cache.write_bytes(b"\xef\xbb\xbf" + json.dumps({OTHER: _live()}).encode("utf-8"))
    proc = _record(cache)
    assert json.loads(proc.stdout)["set_aside"] is None
    assert set(json.loads(cache.read_text(encoding="utf-8"))) == {OTHER, FP}


def test_a_second_set_aside_in_the_same_second_counts_up(tmp_path, mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_corrupt_stamp", lambda: "20261114T093012Z")
    cache = tmp_path / "seen.json"
    names = []
    for garbage in (b"{one", b"{two", b"{three"):
        cache.write_bytes(garbage)
        code, result = _main(mod, capsys, "record", "--fp", FP, "--cache", str(cache), "--issue-url", URL,
                             "--action", "created", "--date", DAY)
        assert code == 0
        names.append(Path(result["set_aside"]).name)
    assert names == [
        "seen.json.corrupt-20261114T093012Z",
        "seen.json.corrupt-20261114T093012Z-2",
        "seen.json.corrupt-20261114T093012Z-3",
    ]
    assert (tmp_path / names[0]).read_bytes() == b"{one"
    assert (tmp_path / names[2]).read_bytes() == b"{three"


def test_a_failed_set_aside_exits_one_and_writes_nothing(tmp_path, mod, monkeypatch, capsys):
    real_replace = mod._replace

    def refuse_set_aside(src, dst):
        if ".corrupt-" in str(dst):
            raise PermissionError(13, "Permission denied")
        real_replace(src, dst)

    monkeypatch.setattr(mod, "_replace", refuse_set_aside)
    cache = tmp_path / "seen.json"
    cache.write_bytes(b"{corrupt")
    code, result = _main(mod, capsys, "record", "--fp", FP, "--cache", str(cache), "--issue-url", URL,
                         "--action", "created", "--date", DAY)
    assert code == 1
    assert "nothing was written" in result["error"]
    assert cache.read_bytes() == b"{corrupt"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json", "seen.json.lock"]


# --- record: the lock ---------------------------------------------------------------


def test_eight_parallel_records_all_land(tmp_path):
    cache = tmp_path / "seen.json"
    fps = [f"fp-{i:07x}" for i in range(8)]
    procs = [
        subprocess.Popen(
            [sys.executable, str(SCRIPT), "record", "--fp", fp, "--cache", str(cache), "--issue-url",
             f"{URL}{i}", "--action", "created", "--date", DAY],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(), stdin=subprocess.DEVNULL,
        )
        for i, fp in enumerate(fps)
    ]
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, out + err
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert sorted(data) == fps
    assert all(data[fp]["issue_url"] == f"{URL}{i}" for i, fp in enumerate(fps))


HOLDER = """
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("holder", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fd = mod._acquire(mod.Path(sys.argv[2]), 5)
print("locked", flush=True)
time.sleep(30)
"""


def test_a_lock_held_past_the_wait_exits_one_and_writes_nothing(tmp_path, mod, monkeypatch, capsys):
    cache = _write_cache(tmp_path / "seen.json", {OTHER: _live()})
    before = cache.read_bytes()
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(SCRIPT), str(tmp_path / "seen.json.lock")],
        stdout=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL,
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        monkeypatch.setattr(mod, "LOCK_WAIT_SEC", 0.5)
        start = time.monotonic()
        code, result = _main(mod, capsys, "record", "--fp", FP, "--cache", str(cache), "--issue-url", URL,
                             "--action", "created", "--date", DAY)
        waited = time.monotonic() - start
    finally:
        holder.kill()
        holder.wait(timeout=30)
    assert code == 1
    assert "nothing was written" in result["error"]
    assert waited >= 0.4, "the call gives up only at the end of its wait"
    assert cache.read_bytes() == before


def test_the_lock_is_released_when_its_holder_dies(tmp_path):
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(SCRIPT), str(tmp_path / "seen.json.lock")],
        stdout=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL,
    )
    assert holder.stdout.readline().strip() == "locked"
    holder.kill()
    holder.wait(timeout=30)
    proc = _record(tmp_path / "seen.json")
    assert proc.returncode == 0, proc.stdout
    assert (tmp_path / "seen.json.lock").exists(), "the lock file is never deleted"


def test_the_lock_wait_is_ten_seconds(mod):
    assert mod.LOCK_WAIT_SEC == 10.0


def test_record_leaves_no_temp_file(tmp_path):
    cache = tmp_path / "seen.json"
    for action in ("created", "reacted"):
        assert _record(cache, action=action).returncode == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seen.json", "seen.json.lock"]


# --- the action vocabulary -----------------------------------------------------


def test_suppressing_actions_is_not_derived_from_actions():
    """`resolved` must be opted OUT of suppression by construction.

    SUPPRESSING_ACTIONS is a literal tuple rather than `ACTIONS` minus
    `resolved`, so a disposition added later defaults to NOT suppressing until
    someone opts it in. Deriving it would silently re-arm suppression for every
    future action, which is the exact defect this disposition exists to fix.
    """
    src = SCRIPT.read_text(encoding="utf-8")

    # A literal tuple, not `tuple(a for a in ACTIONS if ...)` or a set-difference.
    match = re.search(r"^SUPPRESSING_ACTIONS = \(([^)]*)\)", src, re.MULTILINE)
    assert match, "SUPPRESSING_ACTIONS must be a module-level literal tuple"
    suppressing = re.findall(r'"([a-z]+)"', match.group(1))
    assert "resolved" not in suppressing
    # A queued finding is not an issue: it neither suppresses nor is recordable.
    assert "queued" not in suppressing

    actions = re.search(r"^ACTIONS = \(([^)]*)\)", src, re.MULTILINE)
    assert actions, "ACTIONS must be a module-level literal tuple"
    valid = re.findall(r'"([a-z]+)"', actions.group(1))
    assert "resolved" in valid, "resolved must be a recordable action"
    assert "queued" not in valid
    # No drift: every suppressing action is still a valid action.
    assert set(suppressing) < set(valid)


# --- the stage reference that drives the script --------------------------------


def _reference() -> str:
    return HEALTH_CHECK_MD.read_text(encoding="utf-8")


def _flow(text: str) -> str:
    return " ".join(text.split())


def _section(start: str, end: str | None = None) -> str:
    """The reference from `start` to `end`, or to the end of the file when `end` is None."""
    text = _reference()
    assert text.count(start) == 1, start
    i = text.index(start)
    j = len(text) if end is None else text.index(end, i + len(start))
    return text[i:j]


def _fenced_blocks(text: str) -> list[str]:
    return re.findall(r"^```[^\n]*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)


QUEUE = "### 5c. Local queue"


def test_the_script_not_the_prose_reads_the_issue_state():
    """`CLOSED` alone cannot tell a fix from an auto-closed duplicate, and the script owns that check.

    The dedup Action closes duplicates with `state_reason: 'not_planned'`, so `seen` reads stateReason. The stage
    reference only acts on the verdict, so it no longer restates which issue states give which status.
    """
    assert '"state,stateReason"' in SCRIPT.read_text(encoding="utf-8")
    seen = _flow(_section("**1. Check the seen-cache via the script:**", "**Opening line**"))
    assert "the script reads that issue's state itself: never run that check yourself" in seen
    for status in ("`handled`, the only verdict that suppresses", "`unseen` or `unrecognized`",
                   "`regression` or `possible-regression`"):
        assert status in seen, status
    # A failure is logged: a health_check_repo that `seen --repo` refuses would otherwise fail every call silently.
    assert "If the call fails or prints no JSON, log its error and treat it as `unseen`." in seen


def test_no_instruction_runs_timeout_or_puts_a_cached_url_into_a_shell_command():
    """`timeout` is not on stock macOS, and a recorded URL pasted into a shell is a command the cache wrote."""
    body = _reference()
    assert not re.search(r"\btimeout\b", body), "the issue-state check is the script's, bounded there"
    blocks = _fenced_blocks(body)
    commands = blocks + re.findall(r"`([^`\n]*gh [^`\n]*)`", body)
    assert blocks
    for command in commands:
        assert "record." not in command, command
    for block in blocks:
        assert "gh issue view" not in block, block
    assert not re.search(r"gh issue view \{", body), "the stage never hands gh a placeholder to view"


def test_every_call_passes_the_new_arguments():
    blocks = _fenced_blocks(_reference())
    fingerprint = [b for b in blocks if "health_check_fp.py fingerprint" in b]
    seen = [b for b in blocks if "health_check_fp.py seen" in b]
    # The names go through a file on stdin, so no quote in a heading or a name ever meets the shell.
    assert len(fingerprint) == 1
    assert '--stdin < "<run folder>/hc-name-{n}.json"' in fingerprint[0]
    assert "--section-slug" not in fingerprint[0] and "--defect-key" not in fingerprint[0]
    assert len(seen) == 1 and "--legacy-fp {legacy_fp}" in seen[0]
    # A record of an issue on another repository counts as none (customization-1).
    assert '--repo "{workflow.health_check_repo}"' in seen[0]
    body = _reference()
    assert ('`{"section_heading": "<the heading>", "defect_name": "<the name>", '
            '"short_description": "<the description>"}`') in body
    for retired in ("--queue-path", "--defect-slug", "--action queued", "defect_slug"):
        assert retired not in body, retired


def test_the_regression_records_and_treatments_are_described():
    """The opening line and the regression title come from the script: the prose only says where they go."""
    body = _flow(_reference())
    assert "add `--regression`" in body
    assert '→ `{"seen", "status", "record", "matched_on", "opening_line"}`' in body
    opening = _flow(_section("**Opening line**", "**2. Check GitHub CLI**"))
    assert ("Write `opening_line` exactly as printed at the top of the finding's draft, above `## Workflow`, with a "
            "blank line after it.") in opening
    assert "A `regression` takes `{regression_title}` in place of `{title}`" in opening
    assert "A `possible-regression` keeps `{title}`" in opening
    # The four sentences live in the script alone.
    for sentence in ("Regression of {record.issue_url}", "Possibly a regression of {record.issue_url}",
                     "a previously resolved local finding", "REGRESSION: {short description}"):
        assert sentence not in body, sentence


def test_the_section_and_defect_naming_rule_is_stated():
    body = _flow(_reference())
    assert "**Name the section and the defect.**" in body
    assert "copied exactly as that file writes it, numbering included" in body
    assert "Never use the section's own subject alone" in body
    # The script derives the key, and names a script by its stem.
    assert "one to four lower-case ASCII words joined by hyphens (`gate_eval.py` gives `gate-eval`" in body
    assert "Never use a path, a line number, a severity or words from this run's own story" in body
    # The slug and key rules themselves live in the script, not in the prose.
    assert "split it at spaces" not in body
    # Every finding has a heading the script accepts, and a refused one is retried once, never in a loop.
    assert "A bold run-in label (`**Foo.**`) is no heading: take the heading that encloses it." in body
    assert ("A defect in an instruction of `SKILL.md` or of a script takes the heading of the stage-file section that "
            "was running when it bit, or the file's H1 when none fits; one that bit before any stage file was running "
            "(On Activation, the resume routing) takes the stage `ingest-and-scope` and that file's H1.") in body
    # The friction entry such a defect logs names the same file, so the check finds a heading there.
    skill = _flow((Path(__file__).resolve().parents[2] / "SKILL.md").read_text(encoding="utf-8"))
    assert ("An entry for a defect hit before any stage file was running (On Activation, the resume routing) names "
            "`ingest-and-scope.md` and its H1.") in skill
    assert "when it refuses the heading, take the heading that encloses that one" in body
    assert ("Never loop: when that second call fails too, or a call prints no JSON at all (uv or Python could not "
            "run), log it, naming the finding, and drop that finding.") in body


def test_every_failure_after_drafting_has_a_route():
    body = _flow(_reference())
    assert "write `N/A` when it is `null`, or when the call fails or prints no JSON" in body
    assert ('If adding the opening line to the draft fails, log its error and write the finding to the local '
            'queue (§5c) with the reason "Posting these to GitHub failed."') in body
    # The comment is written at the dedup gate, so it is shown before it is posted.
    assert "show the user its text, and run `gh issue comment" in body
    # A configured path with a space in it stays one argument.
    blocks = _fenced_blocks(_reference())
    assert all('--cache "{workflow.health_check_seen_cache}"' in b for b in blocks if "--cache" in b)
    assert all('--queue-dir "{workflow.health_check_queue_path}"' in b for b in blocks if "--queue-dir" in b)


def test_the_second_search_offers_possible_matches_and_n_rekeys_an_exact_one():
    body = _flow(_reference())
    assert '"{legacy_fp} in:title,body"' in body
    assert "Possible match: #{match_number}: {match_title}" in body
    assert "choose a more specific defect name" in body
    # A re-keyed finding gets a new draft and is checked again: the old verdict's treatment never carries over.
    assert "run §3's call again with it and write the draft anew under the new `{fp}`, without a line the old verdict added" in body
    assert "run steps 1 to 3 again for the new fingerprints" in body
    assert "the new `seen` verdict alone decides the opening line, the title and `--regression`" in body
    # A failed search is not a search that found nothing.
    assert ('If either search exits non-zero, it has not shown that no issue matches: log its error and send the '
            'finding to the local queue (§5c) with the reason "Posting these to GitHub failed."') in body


def test_the_enabled_gate_comes_first_and_headless_announces_nothing():
    body = _reference()
    assert not body.startswith("---"), "the stage reference carries no frontmatter aliases"
    first = re.search(r"^## [0-9]", body, re.MULTILINE)
    assert first and body[first.start():].startswith("## 1. Enabled gate")
    gate = _flow(_section("## 1. Enabled gate", "## 2."))
    assert gate.index("If `{workflow.health_check_repo}` is empty, the check is off") < gate.index("in an attended run")
    assert "touching nothing but that marker line" in gate
    assert "arrival announcement" not in body


def test_one_name_per_setting():
    """The body reads each setting by its {workflow.*} name: no frontmatter alias, none that nothing reads."""
    body = _reference()
    for alias in ("{healthCheckRepo}", "{seenCachePath}", "liveSubmitSeverities", "localFallbackFolder", "autosubmit:"):
        assert alias not in body, alias
    for name in ("{workflow.health_check_repo}", "{workflow.health_check_seen_cache}",
                 "{workflow.health_check_queue_path}", "{workflow.health_check_autosubmit}"):
        assert name in body, name


def test_reflection_reads_the_friction_entries_no_health_check_reported():
    """Every entry after the last marker, whichever invocation logged it: a run that blocked early, or whose health
    check never finished, has its entries reported by the next one (architecture-2, determinism-3)."""
    find = _flow(_section("## 2. Find the findings", "## 3."))
    assert find.startswith(
        "## 2. Find the findings First read the `friction:` entries no health check has reported yet: search "
        "`.decision-log.md` with the Grep tool, with line numbers, for the regex `" + _READ_PATTERN + "`, which finds "
        "an entry or a marker only at the start of its line (after a list bullet at most), never one quoted inside "
        "another entry. Take the `friction:` entries after the last marker (all of them when there is none)."
    )
    # An upgrade between the run that logged an entry and this check can retire its instruction.
    assert ("Drop an entry whose section heading or instruction the current stage file no longer carries: an upgrade "
            "may sit between the run that logged it and this check.") in find
    # The reason for the Grep tool holds: the default allowlist runs no shell grep (leanness-5).
    assert ("Use the Grep tool, not a shell grep: it reads a log too large to Read, and a shell grep is outside the "
            "headless allowlist.") in find
    skill_root = Path(__file__).resolve().parents[2]
    allow = re.search(r"^allowlist_commands = \[(.*)\]$", (skill_root / "customize.toml").read_text(encoding="utf-8"),
                      re.MULTILINE)
    assert allow and not [c for c in re.findall(r'"([^"]+)"', allow.group(1)) if c.split()[0] in ("grep", "rg")]
    for gone in ("this invocation", "dlog-slice", "grep -n"):
        assert gone not in find, gone
    # Only what was actually hit is reported: stated once, in the anti-fabrication rules (leanness-2).
    assert "Report only what a logged entry or the live context shows." not in find
    assert "Report only friction that was **actually hit**" in _section("## Anti-fabrication rules", "## 1.")
    skill = _flow((skill_root / "SKILL.md").read_text(encoding="utf-8"))
    assert ('and, without stopping, a one-line `friction: <stage>.md "<section heading, exactly as the file writes it, '
            'numbering included>": <what was unclear, contradictory or missing>` entry whenever an instruction is '
            "unclear, contradictory or silent on the case in hand") in skill
    # SKILL.md names no marker mechanics: the stage that appends and reads the markers states them (leanness-1).
    assert "`health-check:` line" not in skill


def test_finalize_hands_friction_to_the_health_check_only_when_it_is_on():
    """An entry left for a check that is off would reach no report: the audit lists it instead (architecture-4).

    The `disabled` marker closes every entry after the last marker, whichever invocation logged it, so the audit
    lists all of those, found the way §2 finds them, not only this invocation's.
    """
    skill_root = Path(__file__).resolve().parents[2]
    finalize = _flow((skill_root / "references" / "finalize.md").read_text(encoding="utf-8"))
    assert ("A `friction:` entry is left for the health check when `{workflow.health_check_repo}` is set, since the "
            "check reports it. When that is empty, the check is off, and the `disabled` marker it appends closes every "
            "`friction:` entry after the log's last `health-check:` marker unreported, so list each of those in the "
            "addendum: search `.decision-log.md` with the Grep tool for the regex `" + _READ_PATTERN + "` and take the "
            "`friction:` entries after the last marker it finds (all of them when there is none).") in finalize
    assert "A `friction:` entry is left for the health check, which reports it." not in finalize
    skill = _flow((skill_root / "SKILL.md").read_text(encoding="utf-8"))
    assert "(the next health check reports it, or Finalize lists it in the run's addendum when the check is off)" in skill
    assert "closes it unreported" not in skill


def _markers() -> list[str]:
    """Every `health-check: ...` line the stage reference appends, in the order it names them."""
    return re.findall(r"append (?:the one line )?`(health-check: [^`]+)`", _flow(_reference()))


def test_every_exit_appends_exactly_one_marker_line():
    """Each exit's marker, pinned where that exit is."""
    assert [m.split(",")[0] for m in _markers()] == [
        "health-check: disabled", "health-check: clean", "health-check: discarded", "health-check: done"
    ]
    gate = _flow(_section("## 1. Enabled gate", "## 2."))
    assert "append `health-check: disabled` to `.decision-log.md` and return, touching nothing but that marker line" in gate
    assert ("Every exit of this check appends exactly one `health-check: <outcome>` line to `.decision-log.md`, in "
            "place of any other line about how it ended: `disabled` (above), `clean` (§2), `discarded` (§4a **[N]**) "
            "or `done` with its counts (§6).") in gate
    find = _flow(_section("## 2. Find the findings", "## 3."))
    assert ('If there is none, append `health-check: clean` (§1), display "Health Check: clean run. No workflow '
            'issues to report." in an attended run, and return.') in find
    draft = _flow(_section("## 3. Fingerprint and draft each finding", "## 4."))
    assert "When no finding survives this step, go straight to §6, with no gate." in draft
    attended = _flow(_section("### 4a. Attended routing", "### 4-headless."))
    # Every exit returns: the check is the run's last step, so no exit shouts a harder stop (leanness-6).
    assert ('**[N]** → append `health-check: discarded` (§1), display "Findings discarded. Workflow complete." and '
            "return.") in attended
    assert "STOP" not in _reference()
    close = _flow(_section("## 6. Close"))
    assert close == (
        "## 6. Close Once every finding is routed, or none survived §3, append the one line `health-check: done, <n> "
        "filed, <n> upvoted, <n> queued, <n> already handled, <n> dropped` (§1), each count being the findings that "
        "took that route (an issue created; **R** or **C**; the local queue; a `handled` verdict; dropped in §3). Only "
        'then show the lines §5a-ii and §5c kept, in that order, followed by "Workflow complete.": display them in an '
        "attended run; in an unattended one, display nothing and wait for nothing, and log the kept lines alone. Then "
        "return."
    )
    body = _flow(_reference())
    for stale in ("health-check disabled (", "clean run, no findings"):
        assert stale not in body, stale


def test_the_done_marker_comes_before_anything_the_close_shows():
    """A session that stops after any line the routed exits show must already hold its marker, or the next check
    re-reports every entry this one filed or queued (architecture-2). So §5a-ii and §5c only keep their lines, and
    §6 appends the marker before it shows or logs them, and "Workflow complete." after them."""
    body = _flow(_reference())
    # The closing line is shown by the [N] exit and by §6 alone, never by a route that §6 still follows.
    assert body.count("Workflow complete.") == 2
    created = _flow(_section("**5a-ii. If no matching open issue exists**", "### 5b."))
    queued = _flow(_section(QUEUE, "## 6. Close"))
    for route in (created, queued):
        assert "Workflow complete." not in route
        assert "keep for §6" in route
        assert not re.search(r"\b(display|show|log) (these|this|the same) (lines|block)\b", route), route
    assert ('After creating all issues, keep for §6 the line "{N} issue(s) created on {workflow.health_check_repo}:" '
            "and each URL.") in created
    assert "After writing the files, keep for §6 this block, once per reason" in queued
    attended = _flow(_section("### 4a. Attended routing", "### 4-headless."))
    assert attended.index("append `health-check: discarded`") < attended.index("Workflow complete.")
    close = _flow(_section("## 6. Close"))
    marker = close.index("append the one line `health-check: done")
    # Nothing is shown or logged before the marker, and no "Workflow complete." follows a log instruction.
    assert not re.search(r"\b(show|display|log)\b", close[:marker])
    assert marker < close.index("Only then show the lines §5a-ii and §5c kept") < close.index('"Workflow complete."')
    for log in re.finditer(r"\blog\b", close):
        assert "Workflow complete." not in close[log.start():], close[log.start():]


def test_the_stage_states_how_it_appends_to_the_log():
    """The check runs last, when compaction has most likely dropped SKILL.md, so it carries the append rule itself
    (architecture-3), with a slice named for Stage 7 that Finalize's `dlog-slice-*.md` audit glob covers."""
    gate = _flow(_section("## 1. Enabled gate", "## 2."))
    assert ("**Appending to the log.** The marker, and every line this file says to log, is appended to "
            "`.decision-log.md` with Write or Edit, never a Bash heredoc.") in gate
    assert ("Once the log is too large to Read affordably, do not Read it: Write the line to a new file beside the "
            "log, `<log folder>/dlog-slice-stage7-<n>.md`, where `<log folder>` is the run folder's full path and "
            "`<n>` is one past the highest number a `dlog-slice-stage7-*.md` there already carries, then append it in "
            'one Bash call, `cat "<log folder>/dlog-slice-stage7-<n>.md" >> "<log folder>/.decision-log.md"`, and keep '
            "the slice.") in gate
    assert "the way SKILL.md appends" not in _reference()
    [command] = re.findall(r"`(cat [^`]+)`", gate)
    words = shlex.split(command.replace("<log folder>", "/my project/run"))
    assert words == ["cat", "/my project/run/dlog-slice-stage7-<n>.md", ">>", "/my project/run/.decision-log.md"]


# §2's Grep pattern: an entry or a marker at the start of its line, after a list bullet at most.
_READ_PATTERN = r"^\s*([-*]\s+)?(friction:|health-check: (disabled|clean|discarded|done)\b)"


def _friction_read(log: str) -> list[str]:
    """§2's read with the pattern the stage reference gives: the `friction:` entries after the last marker."""
    [pattern] = re.findall(r"for the regex `([^`]+)`", _reference())
    assert pattern == _READ_PATTERN
    read = re.compile(pattern)
    hits = [(n, line) for n, line in enumerate(log.splitlines(), 1) if read.search(line)]
    last = max((n for n, line in hits if read.search(line).group(2).startswith("health-check:")), default=0)
    return [line for n, line in hits if n > last and read.search(line).group(2) == "friction:"]


def test_the_friction_read_takes_only_the_entries_after_the_last_marker():
    def entry(k: int, bullet: str = "") -> str:
        return f'{bullet}friction: gate.md "Route on the verdict": case {k}'

    assert _friction_read("\n".join(["# Session 1", entry(1), entry(2)])) == [entry(1), entry(2)], "no marker yet"
    for marker in _markers():
        line = marker.replace("<n>", "1")
        assert not re.search(r"\bfriction:", line), "a marker is never read as an entry"
        log = "\n".join(["# Session 1", entry(1), line, "# Session 2", entry(2, "- "), "- gate: advance", entry(3)])
        assert _friction_read(log) == [entry(2, "- "), entry(3)], marker
        # A later marker closes those too, and an earlier one never reopens them.
        assert _friction_read(log + "\n- " + line) == []


def test_an_entry_that_quotes_a_marker_neither_closes_itself_nor_the_entries_before_it():
    quoting = 'friction: finalize.md "Workflow health check (terminal)": it says to log health-check: done, then?'
    earlier = 'friction: gate.md "Route on the verdict": silent on a reloop'
    log = "\n".join(["- health-check: clean", earlier, quoting, "- gate: advance, see friction: above"])
    assert _friction_read(log) == [earlier, quoting]


def test_every_finding_is_drafted_before_the_gate_and_routed_unchanged():
    body = _reference()
    assert body.index("## 3. Fingerprint and draft each finding") < body.index("### 4a. Attended routing")
    draft = _flow(_section("## 3. Fingerprint and draft each finding", "## 4."))
    assert "Write each finding's issue body with the Write tool to `hc-body-{fp}.md` in the run folder" in draft
    assert "Every route uses that file as it stands" in draft
    assert ("After the gate the draft changes only by a regression's opening line (§5a step 1) or an **[N]** re-key "
            "at the dedup gate (§5a-i).") in draft
    # A file an earlier invocation left is Read before it is overwritten, and a failed Write drops the finding.
    assert "Read a file of that name an earlier invocation left" in draft
    assert "If either Write fails, log its error, naming the finding, and drop that finding" in draft
    assert "Two findings that get one `{fp}` are one defect: merge them into one finding before drafting." in draft
    # The draft opens with the script's body header, which the dedup Action reads: no machine-read line by hand.
    assert ("Write each finding's issue body with the Write tool to `hc-body-{fp}.md` in the run folder, opening with "
            "the call's `body_header` exactly as printed.") in draft
    # The draft copies the header as printed, so the prose lists none of its sections (leanness-4).
    assert "**Issue body**: the `body_header`, then these `## ` headings in order" in draft
    assert "which the dedup Action reads" not in draft
    for by_hand in ("`## Fingerprint` with", "`## Severity` (`{severity}`)", "Section fingerprint:"):
        assert by_hand not in draft, by_hand
    # The live create and the queue both take that draft as their body file.
    create = [b for b in _fenced_blocks(_section("**5a-ii. If no matching open issue exists**", "### 5b."))
              if "gh issue create" in b]
    assert len(create) == 1 and '--body-file "<run folder>/hc-body-{fp}.md"' in create[0]
    queue = [b for b in _fenced_blocks(_section(QUEUE)) if "health_check_fp.py queue" in b]
    assert len(queue) == 1 and '--body-file "<run folder>/hc-body-{fp}.md"' in queue[0]


def test_the_gate_shows_each_title_and_body_and_y_submits_only_bugs():
    gate = _flow(_section("### 4a. Attended routing", "### 4-headless."))
    assert ("Show every finding: for each one, its `{title}` (§3), the path of its draft and the draft's full "
            "text.") in gate
    assert "then HALT" not in gate, "the gate halts once"
    assert "**[Y]** Yes: submit the bug findings; friction and gap findings stay local" in gate
    assert "**[A]** All: submit every finding, friction and gap included" in gate
    assert gate.index("the draft's full text") < gate.index("**HALT and wait for input.**")
    assert "write the draft anew as `hc-body-{fp}.md` under the new `{fp}`" in gate, "[E] edits the drafts"
    assert "a confirmed regression's title gains `REGRESSION: `" in gate
    routing = _flow(_section("## 5. Severity routing", "### 5a."))
    assert ("Each `friction` and `gap` finding, the most subjective kinds and the ones that draw the most "
            "near-duplicates, goes to the local queue (§5c) with the reason "
            '"Friction and gap findings stay local unless you choose [A]."') in routing
    assert "**[A]**: every finding but a `health-check` one live-submits (§5a)." in routing
    # One prompt, not two: no second friction/gap question after the gate.
    assert "[y/N]" not in _reference()


def test_the_gate_names_where_the_issues_go():
    """The only consent point says what [Y] does: issues on the configured repo, under the user's account (enhancement-4)."""
    gate = _flow(_section("### 4a. Attended routing", "### 4-headless."))
    # Public on the default whatever its letter case, and a note for any other repository, a public fork included.
    assert ('Then ask, saying "public issues" for "issues" when `{workflow.health_check_repo}` is the default, '
            '`armelhbobdad/bmad-module-ultracode-goal` in any letter case, and for any other repository adding '
            '"(public if that repository is public)" after its name: "Submit these findings as issues on '
            '{workflow.health_check_repo}, filed with your GitHub account?') in gate
    skill_root = Path(__file__).resolve().parents[2]
    assert 'health_check_repo = "armelhbobdad/bmad-module-ultracode-goal"' in (
        skill_root / "customize.toml").read_text(encoding="utf-8"), "the default the gate names is the shipped one"
    docs = _flow((Path(__file__).resolve().parents[4] / "docs" / "health-check.md").read_text(encoding="utf-8"))
    assert ('asks "Submit these findings as issues on `<health_check_repo>`, filed with your GitHub account?", saying '
            "public issues on the default and, for any other repository, that they are public if it is.") in docs


def test_the_dedup_gate_names_the_matched_issue_apart_from_the_findings_title():
    """`{title}` is the finding's script-built title alone, so a new issue after [N] never takes the match's title."""
    menu = _section("**5a-i. If a matching open issue exists**", "**5a-ii.")
    assert ("present, `{match_number}` and `{match_title}` being that issue's `number` and `title` from the "
            "search:") in _flow(menu)
    assert '"Matching report found: #{match_number}: {match_title}' in menu
    assert "Possible match: #{match_number}: {match_title}" in menu
    assert "/issues/{match_number}/reactions" in menu and "gh issue comment {match_number} " in menu
    assert "{N}" not in menu and "{title}" not in menu
    # Everywhere else `{title}` is the finding's own, and the commands that file it use it.
    assert _reference().count('--title "{title}"') == 2


def test_a_null_title_or_header_is_never_written():
    draft = _flow(_section("## 3. Fingerprint and draft each finding", "## 4."))
    assert ("A null `title` or `body_header` means the description was missing from the file: write it there and run "
            "the call again, and never write `null` into a title or a draft.") in draft
    assert ("the description may hold no backtick, `$`, double quote, backslash, `!`, tab, line break or other "
            "character that is not printable, since the title goes on a command line, and may not make "
            "`regression_title` longer than 256 characters") in draft


def test_the_attended_gate_offers_queue_locally():
    gate = _flow(_section("### 4a. Attended routing", "### 4-headless."))
    assert "**[Q]** Queue locally" in gate
    # [Q] routes to the queue alone, which makes no GitHub call, so nothing restates that (leanness-2).
    assert "Make no GitHub call" not in gate
    assert '"The review gate queued these locally."' in gate


def test_the_never_block_rule_is_stated_once_with_its_reason():
    body = _flow(_reference())
    assert body.count("block or delay") == 1
    headless = _flow(_section("### 4-headless.", "## 5. Severity routing"))
    assert ("Never block or delay the final headless JSON emit: Finalize emits it only after this step returns, and "
            "an automator is waiting on it.") in headless
    assert "## Terminal step" not in _reference()
    skill_root = Path(__file__).resolve().parents[2]
    for path in (skill_root / "SKILL.md", skill_root / "references" / "finalize.md"):
        text = path.read_text(encoding="utf-8")
        for stale in ("queue-only", "queues findings locally"):
            assert stale not in text, (path.name, stale)
    finalize = _flow((skill_root / "references" / "finalize.md").read_text(encoding="utf-8"))
    assert "It routes its own headless mode and **never blocks the emit**." in finalize
    # The rule keeps its place, with the failure it guards against in place of a bare order (leanness-6).
    assert ("Take no other action between this section and the health check: a turn that ends on the run report "
            "skips the check.") in finalize
    assert "Do not perform any other action" not in finalize


def test_an_unattended_match_takes_skip_and_posts_nothing():
    headless = _flow(_section("### 4-headless.", "## 5. Severity routing"))
    assert "A match takes **[S]** (§5a-i)." in headless
    menu = _flow(_section("**5a-i. If a matching open issue exists**", "**5a-ii."))
    assert "**Unattended default: [S].**" in menu
    # Stated once, where it is decided, with the reason only it gives.
    assert ('takes **[S]** at an exact or a possible match, so the finding goes to the local queue (§5c) with the '
            'reason "These may match an open issue on {workflow.health_check_repo}; review them before submitting.", '
            "and nothing is posted on a guess.") in menu
    assert "(the Unattended default's reason when nobody was asked)" in menu
    assert _flow(_reference()).count("nothing is posted") == 1


def test_a_queued_finding_records_nothing():
    """Stated once, in §5b, with the reason only it gives; each route names the record it makes (leanness-2)."""
    assert "health_check_fp.py record" not in _section(QUEUE)
    record = _flow(_section("### 5b. Record the outcome", QUEUE))
    assert ("Nothing else is recorded: not a queued finding, not **[S]**, not a failed call. A queued finding is not "
            "an issue, and a record for it would suppress the same defect when a later attended run approves it.") in record
    assert "record nothing" not in _reference().lower()


def test_the_queue_step_writes_into_the_configured_queue_path():
    """#228's rewrite dropped the folder from the one step that writes queued files (customization-1)."""
    queue = _section(QUEUE)
    assert "{workflow.health_check_queue_path}" in queue
    [block] = [b for b in _fenced_blocks(queue) if "health_check_fp.py queue" in b]
    assert 'queue --queue-dir "{workflow.health_check_queue_path}"' in _flow(block.replace("\\\n", " "))
    # The script names the file after the stage the draft's header gives (leanness-4).
    assert "--stage" not in block
    assert '--title "{title}" --repo "{workflow.health_check_repo}"' in block


def test_a_queued_file_is_the_draft_with_no_frontmatter():
    # The script copies the draft byte for byte (the queue tests above), so the prose does not describe it.
    assert "copies the draft unchanged" not in _section(QUEUE)
    for gone in ("section_fingerprint:", "type: workflow-health-finding", "```yaml"):
        assert gone not in _section(QUEUE), gone


def test_every_local_outcome_shows_its_paths_reason_and_the_printed_commands():
    queue = _flow(_section(QUEUE))
    assert '"{N} finding(s) saved locally:" then each path, each followed by its three `commands`, exactly as printed.' in queue
    assert ('"{reason sentence} Run a finding\'s first two commands to submit it as an issue (the first fails, '
            "harmlessly, when its label exists)") in queue
    assert "In an unattended run" not in queue
    assert "in an unattended one, display nothing and wait for nothing, and log the kept lines alone." in _flow(
        _section("## 6. Close"))
    # The script prints the commands, quoted; the prose fills in none by hand (determinism-2).
    # The script quotes the commands and the display sentence names each one, so the result is not described twice.
    assert '→ `{"path", "commands"}`: the file it wrote and the three commands that submit it.' in queue
    assert "each on one line with every argument quoted" not in queue
    assert "{file-path}" not in _reference()
    assert not [b for b in _fenced_blocks(_section(QUEUE)) if "gh " in b], "no command template left in §5c"
    [block] = [b for b in _fenced_blocks(_section(QUEUE)) if "health_check_fp.py queue" in b]
    # {title} is defined for every finding, one that never reached §5a included.
    assert '--title "{title}"' in block
    assert ("`{title}` being the finding's `title`, or its `regression_title` only after a `regression` verdict whose "
            "opening line was added") in queue
    assert "the title §5a-ii would use" not in queue
    # A failed call leaves the draft to list, pointed at the manual route rather than at commands it lacks.
    assert ("If the call fails or prints no JSON, log its error and list the draft itself in that file's place (it "
            'holds the same text), followed, in place of commands, by "Submit it as '
            "<https://armelhbobdad.github.io/bmad-module-ultracode-goal/health-check/#submitting-a-queued-finding-manually> "
            'says."') in queue
    assert "## Submitting a queued finding manually" in _docs()
    assert "[title]" not in queue
    # Each routing step quotes its own reason, one of a fixed set, and §5c keeps no copy of them (leanness-2).
    assert set(re.findall(r'with the reason "([^"]+)"', _flow(_reference()))) == {
        "The review gate queued these locally.",
        "Headless runs queue every finding while health_check_autosubmit is off.",
        "Headless runs never submit friction or gap findings.",
        "Friction and gap findings stay local unless you choose [A].",
        "You declined a gh call; nothing was posted.",
        "GitHub CLI is not available.",
        "You skipped these at the dedup gate.",
        "These may match an open issue on {workflow.health_check_repo}; review them before submitting.",
        "Posting these to GitHub failed.",
        "Found in the health check's own instructions; review it before submitting.",
    }
    # A refused gh call gives one of two reasons, by run mode: the unattended one tells how to allow the calls.
    assert set(re.findall(r'with the reason "([^"]+)" in an attended run', _flow(_reference()))) == {
        "You declined a gh call; nothing was posted."}
    assert set(re.findall(r'and "([^"]+)" in an unattended one', _flow(_reference()))) == {
        "A gh call was refused in this session; allow the health check's gh commands (see health_check_autosubmit) "
        "to submit unattended."}
    assert "Each finding here carries the reason sentence its routing step gave it." in queue
    assert not re.search(r"^\|", _section(QUEUE), re.MULTILINE), "no reason table"


def test_the_created_issues_are_logged_not_displayed_in_an_unattended_run():
    """§5a-ii's lines follow §5c's rule: on screen when attended, in the log when not (architecture-6), both shown
    or logged by §6 once the marker is in."""
    create = _flow(_section("**5a-ii. If no matching open issue exists**", "### 5b. Record the outcome"))
    assert ('After creating all issues, keep for §6 the line "{N} issue(s) created on {workflow.health_check_repo}:" '
            "and each URL.") in create
    close = _flow(_section("## 6. Close"))
    assert ("show the lines §5a-ii and §5c kept, in that order, followed by \"Workflow complete.\": display them in an "
            "attended run; in an unattended one, display nothing and wait for nothing, and log the kept lines "
            "alone.") in close


def test_a_failed_create_is_retried_once_without_labels():
    """A reporter without push access can create no label and set none (#227).

    A failed `gh label create` is no error, so `gh issue create --label {fp}` runs and fails on the missing label,
    and the first report of every defect was only ever queued. The retry files it bare, and the
    dedup Action labels it from its title.
    """
    section = _section("**5a-ii. If no matching open issue exists**", "### 5b. Record the outcome")
    create = _flow(section)
    # The first run still passes --label, so a collaborator's filing is unchanged.
    [block] = [b for b in _fenced_blocks(section) if "gh issue create" in b]
    assert '--label "health-check,workflow-improvement,{severity},{fp}"' in block
    # The title is the script's, for the first run, the retry and a regression alike.
    assert '--title "{title}"' in block
    assert "After a `regression` verdict, `{regression_title}` takes the place of `{title}` (§5a step 1)." in create
    assert ("**If `gh issue create` exits non-zero, run it once more without the `--label` line**, with the same "
            "title and body file: a reporter without push access can set no label, and the dedup Action labels the "
            "issue from its title.") in create
    # One clause of why for each command, the label mechanics stated once (leanness-2).
    assert "**First, create the `{fp}` label**, which `--label {fp}` needs:" in create
    for gone in ("It is per-fingerprint", "pre-created repo labels", "the first run fails on the missing"):
        assert gone not in create, gone
    # The outcome is recorded and queued as before: created after either run, queued after the second failure.
    assert "After the issue is created, by the first run or the retry, record it (§5b)" in create
    assert ('If `gh issue create` fails on its retry too, log its error and write the finding to the local queue '
            '(§5c) with the reason "Posting these to GitHub failed."') in create
    record = _flow(_section("### 5b. Record the outcome", QUEUE))
    assert "`created` after `gh issue create` succeeded, on its first run or its retry without `--label`" in record


def test_the_queue_tells_a_reporter_without_push_access_to_run_the_create_without_labels():
    queue = _flow(_section(QUEUE))
    # The script prints that create, so nobody cuts `--label` out of a quoted line by hand.
    assert ("Without push access to {workflow.health_check_repo}, run its third command alone instead: you can "
            "neither create a label nor set one, and the dedup Action labels the issue from its title.") in queue


def test_a_failed_label_create_is_no_error_and_no_command_is_compound():
    """`2>/dev/null || true` is a compound an allow rule may not cover, and its redirect breaks on Windows."""
    body = _reference()
    assert "|| true" not in body and "2>/dev/null" not in body
    create = _flow(_section("**5a-ii. If no matching open issue exists**", "### 5b. Record the outcome"))
    assert ("If it exits non-zero (the label exists already, or you have no push access), that is no error: go on to "
            "the create.") in create
    # `--repo` right after the subcommand, so an allow rule scoped to the repository matches each live call.
    for block in _fenced_blocks(body):
        flowed = _flow(block.replace("\\\n", " "))
        for sub in ("gh label create", "gh search issues", "gh issue create"):
            if sub in flowed:
                assert f"{sub} --repo {{workflow.health_check_repo}} " in flowed, block
    docs = _docs()
    assert "|| true" not in docs and "2>/dev/null" not in docs


def test_a_refused_gh_call_stops_every_gh_call_of_the_check():
    """Each refusal is a blocked call (under Auto Mode, consecutive blocks count against the session), and an
    attended user who declined a prompt is not told to configure unattended allow rules."""
    refused = _flow(_section("**A refused `gh` call.**", "**3. Remote dedup search**"))
    assert ("When the session refuses `gh auth status` or any later `gh` call of §5a, so that the command never ran, "
            "make no further `gh` call in this check: write this finding and every live-submit finding not yet "
            'submitted to the local queue (§5c), with the reason "You declined a gh call; nothing was posted." in an '
            "attended run, and \"A gh call was refused in this session; allow the health check's gh commands (see "
            'health_check_autosubmit) to submit unattended." in an unattended one.') in refused


def test_evidence_cites_only_module_files():
    assert "**Cite only this module's files.**" in _reference()


# --- the contributor docs --------------------------------------------------------


def test_the_flag_mode_says_it_skips_the_heading_check_and_prints_no_title():
    """--section-slug and --defect-key stay for manual filers and old calls, but say what they skip (leanness-5)."""
    proc = _run("fingerprint", "--help")
    assert proc.returncode == 0
    flowed = _flow(proc.stdout)
    assert "it skips the check that the heading is one of the stage file's own" in flowed
    assert flowed.count("Without --stdin, title, regression_title and body_header print null.") == 2
    doc = _flow(_load().__doc__)
    assert ("The two flags stay for tests and old calls: --section-slug skips the check that the heading is one of "
            "the stage file's own, and without --stdin the flags print a null title, regression_title and "
            "body_header.") in doc
    # Under --repo, every issue_url but an empty or missing one must sit under the prefix.
    assert ("any other record whose issue_url is not a string under https://github.com/OWNER/REPO/ "
            "(https://HOST/OWNER/REPO/ for a REPO that names a host), compared in any letter case, counts as no "
            "record") in doc
    # And the docstring documents the commands as they are now.
    assert "seen --fp FP --legacy-fp FP --cache PATH [--repo REPO]" in doc
    assert "queue --queue-dir DIR --body-file F --title TITLE --repo REPO" in doc


_DIRECT_RUN = ("To report a run's friction now, without waiting for a later run, ask the conductor to run the health "
               "check for that run: it reads that run folder's `.decision-log.md`, with no other stage, and reports "
               "from the log's `friction:` lines alone.")


def test_an_operator_can_run_the_health_check_for_a_run_directly():
    """CONTRIBUTING promised a direct run, and the run that completes an Epic has no later run to report its
    friction (enhancement-4): SKILL.md routes the request, and the stage says how such a run differs."""
    root = Path(__file__).resolve().parents[4]
    skill = (root / "skills" / "ultracode-goal" / "SKILL.md").read_text(encoding="utf-8")
    [row] = [line for line in skill.splitlines() if line.startswith("| 7 | Health Check |")]
    assert ("Finalize's close-out loads it, and an operator's request to run the health check for a run loads it "
            "against that run folder's `.decision-log.md`, with no other stage and no resume prompt") in row
    assert "\u2014" not in row
    opening = _flow(_section("# Health Check: Workflow Self-Improvement", "## Anti-fabrication rules"))
    assert ("A direct run, the one an operator asks for against a run folder, reports from the `friction:` entries "
            "of that folder's `.decision-log.md` alone (§2), since nothing of that run is in context, and routes by "
            "its run mode like any run (§4).") in opening
    assert "is attended" not in opening
    find = _flow(_section("## 2. Find the findings", "## 3."))
    assert ("Then find each point where a stage instruction you were following was wrong or contradictory (`bug`), "
            "worked but left you guessing or going back and forth (`friction`), or was silent on a case you hit "
            "(`gap`): in a direct run from those entries alone, in any other from them, the rest of the log and what "
            "is still in context.") in find
    # On Activation's Resume routes the request: no resume offer, and a named folder that holds a log.
    resume = _flow(skill)
    assert ("An operator's request to run the health check for a run skips the resume offer and creates nothing: the "
            "operator names the Epic or its run folder (ask in an attended run when they name neither, and refuse in "
            "a headless one), refuse a folder that holds no `.decision-log.md`, and otherwise load "
            "`references/health-check.md` against that folder's log (Stages row 7).") in resume
    assert resume.index("An operator's request to run the health check") < resume.index("If one exists for the Epic")
    # The docs and CONTRIBUTING give the same sentence.
    assert _DIRECT_RUN in _flow(_docs())
    assert _DIRECT_RUN in _flow((root / "CONTRIBUTING.md").read_text(encoding="utf-8"))


_REPO_LABELS = ("`health-check`, `workflow-improvement`, `bug`, `friction`, `gap`, `duplicate` and "
                "`possible-duplicate`")


def test_a_redirected_repository_is_told_what_it_needs():
    """A project that points health_check_repo elsewhere needs the labels and the dedup Action there, and a shared
    seen-cache reads only that repository's records (customization-2)."""
    customize = (Path(__file__).resolve().parents[2] / "customize.toml").read_text(encoding="utf-8")
    comment = customize[customize.index("# Set health_check_repo"):customize.index("\nhealth_check_repo =")]
    comment = " ".join(re.sub(r"^#\s*", "", comment, flags=re.MULTILINE).split())
    assert ("To send findings to another repository, create these labels there: health-check, workflow-improvement, "
            "bug, friction, gap, duplicate and possible-duplicate, and copy two files into it unchanged: the issue "
            "template,") in comment
    # An install has no .github folder, so the comment names both files by their URL.
    blob = "https://github.com/armelhbobdad/bmad-module-ultracode-goal/blob/main/"
    for name in (".github/ISSUE_TEMPLATE/workflow-health-check.md", ".github/workflows/health-check-dedup.yaml"):
        assert blob + name in comment, name
    assert "A repository on a host other than github.com is given as HOST/OWNER/REPO." in comment
    # `record` keys the cache by fingerprint alone, so a shared cache cannot serve two repositories.
    assert ("Such a project must also set its own health_check_seen_cache: the cache keys each record by fingerprint "
            "alone, so two projects filing to different repositories would block or overwrite each other's records. "
            "The check only keeps another repository's record from suppressing or linking a finding.") in comment
    cache = customize[customize.index("\nhealth_check_repo ="):customize.index("\nhealth_check_seen_cache =")]
    cache = " ".join(re.sub(r"^#\s*", "", cache, flags=re.MULTILINE).split())
    assert ("dedup must span the projects that file to one repository: the same defect met in two of them is still "
            "one report.") in cache
    docs = _flow(_docs())
    assert ("**To send findings to another repository**, set `health_check_repo` to it under the same header "
            "(`OWNER/REPO`, or `HOST/OWNER/REPO` on a host other than github.com), and set that repository up as the "
            "default one is: create the labels " + _REPO_LABELS + " there, and copy two files into it unchanged, the "
            "issue template [`.github/ISSUE_TEMPLATE/workflow-health-check.md`](" + blob + ".github/ISSUE_TEMPLATE/"
            "workflow-health-check.md) and the dedup Action [`.github/workflows/health-check-dedup.yaml`](" + blob +
            ".github/workflows/health-check-dedup.yaml), which reads its repository from the run.") in docs
    assert ("Set the project's own `health_check_seen_cache` too: the cache keys each record by fingerprint alone, so "
            "two projects that share it and file to different repositories would block or overwrite each other's "
            "records.") in docs
    assert ("`seen` is given the configured `health_check_repo` and reads a record of an issue on another repository "
            "as no record, so that record neither suppresses a finding nor links its body to that issue; `record` "
            "still keys the cache by fingerprint alone, so a project that files to another repository sets its own "
            "`health_check_seen_cache`.") in docs
    for gone in ("one cache serves", "gets in your way", "reads only its records"):
        assert gone not in docs and gone not in comment, gone
    # The labels named are the ones CONTRIBUTING has maintainers pre-create.
    contributing = (Path(__file__).resolve().parents[4] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert ("`health-check`, `workflow-improvement`, `bug`, `friction`, `gap`, `duplicate`, and `possible-duplicate`"
            in contributing)


def test_the_boundary_sentence_does_not_restate_what_is_sent():
    """"Exactly what gets sent" owns that topic; a partial copy read as if only the table left the machine
    (leanness-6)."""
    docs = _flow(_docs())
    assert ("The gate that admits anything to the right of the boundary is the `[Y]` or `[A]` approval on an attended "
            "run, or the autosubmit opt-in restricted to `bug`-severity findings on a headless run.") in docs
    assert "is all that travels with a filed issue" not in docs


def test_the_issue_template_explains_only_what_the_filer_chooses():
    """The first comment says to paste the body_header over the machine-read sections, so only the Severity and
    Defect Key comments, which guide --severity and defect_name, stay (leanness-8)."""
    template = (Path(__file__).resolve().parents[4] / ".github" / "ISSUE_TEMPLATE" / "workflow-health-check.md")
    text = template.read_text(encoding="utf-8")
    for heading, placeholder in (("## Step File", "`skills/ultracode-goal/references/{stage}.md`"),
                                 ("## Section", ""),
                                 ("## Fingerprint", "<!-- The `Section fingerprint:` line below is never a label. -->\n"
                                                    "`fp-XXXXXXX`")):
        assert f"{heading}\n{placeholder}\n" in text, heading
    assert "`fp-XXXXXXX`\n\nSection fingerprint: `fp-XXXXXXX`\n" in text
    comments = [" ".join(c.split()) for c in re.findall(r"<!--(.*?)-->", text, re.DOTALL)]
    for gone in ("the body_header gives it", "sha1(", "the deterministic dedup key"):
        assert not [c for c in comments if gone in c.lower()], gone
    assert [c for c in comments if c.startswith("Pick one, and pass it to the command as --severity")]
    assert [c for c in comments if c.startswith("Give as `defect_name` the most specific script")]


def test_contributing_does_not_promise_a_bare_closed_counts_as_fixed():
    """The contributor-facing note must not contradict the stage.

    It is the doc that tells a maintainer how to close a finding out, so if it
    implies any close counts, the stage's narrower rule reads as a bug.
    """
    body = (Path(__file__).resolve().parents[4] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "not planned" in body.lower(), "CONTRIBUTING must say a not-planned close does not count as a fix"


def test_the_issue_template_gives_the_stdin_fingerprint_command():
    """A manual filer runs the script with the heading and the name in a file, never hashing by hand."""
    template = (Path(__file__).resolve().parents[4] / ".github" / "ISSUE_TEMPLATE" / "workflow-health-check.md")
    lines = template.read_text(encoding="utf-8").splitlines()
    [command] = [line.strip() for line in lines if "health_check_fp.py fingerprint" in line]
    assert re.search(r"health_check_fp\.py fingerprint .*--stdin < names\.json$", command), command
    [names] = [line.strip() for line in lines if line.strip().startswith('{"section_heading"')]
    assert set(json.loads(names)) == {"section_heading", "defect_name", "short_description"}
    flowed = " ".join(" ".join(lines).split())
    assert "use its `title` as this issue's title" in flowed
    # The filer's first instruction is to paste the printed header whole, never field by field, so fp and
    # legacy_fp cannot swap (determinism-3).
    comments = re.findall(r"<!--(.*?)-->", template.read_text(encoding="utf-8"), re.DOTALL)
    assert " ".join(comments[0].split()).startswith(
        "Filing by hand: replace everything from this `## Workflow` line through the end of the Defect Key section "
        "with the `body_header` the health check's script prints for your finding, and use its `title` as this "
        "issue's title.")
    # Printing it as text: jq is named as needed, with a python3 alternative, and a null is caught.
    assert "add `| jq -r .body_header` to the command (jq needed)" in flowed
    assert """`| python3 -c "import json, sys; print(json.load(sys.stdin)['body_header'])"`""" in flowed
    assert "Neither may print `null`: that means names.json had no short_description." in flowed
    for gone in ("Paste its `fp` here", "its `legacy_fp` on the Section fingerprint line", "paste the `defect_key`",
                 "through the Defect Key value"):
        assert gone not in flowed, gone


def test_a_run_blocked_at_stage_1_or_2_has_its_friction_reported_by_the_next_run():
    """No health check at an early block, and no reason that says there is nothing to report (architecture-2).

    Only a later run that reaches Finalize reports it, and an `already-complete` exit or an abandoned Epic has none.
    """
    root = Path(__file__).resolve().parents[4]
    skill = _flow((root / "skills" / "ultracode-goal" / "SKILL.md").read_text(encoding="utf-8"))
    # SKILL.md no longer restates when the check runs: Finalize and the Stages table carry it (leanness-1).
    assert "Runs that reach Stage 6" not in skill and "Runs that block at Stage 1 or Stage 2" not in skill
    docs = _flow((root / "docs" / "health-check.md").read_text(encoding="utf-8"))
    assert ("It does **not** run on an early block, a Stage 1 or Stage 2 stop: the next run of that Epic that reaches "
            "Finalize, if one does, reports the friction the blocked run logged.") in docs
    contributing = _flow((root / "CONTRIBUTING.md").read_text(encoding="utf-8"))
    assert "so the next run of that Epic that reaches Finalize, if one does, reports what such a run logged" in contributing
    for text in (skill, docs, contributing):
        for gone in ("no executed workflow surface", "nothing to audit"):
            assert gone not in text, gone


def test_the_docs_say_the_off_switch_closes_pending_friction_and_draw_the_markers():
    docs = (Path(__file__).resolve().parents[4] / "docs" / "health-check.md").read_text(encoding="utf-8")
    assert ("Each run it skips still logs its `disabled` marker, which closes the `friction:` entries logged so far: "
            "turning the check back on reports only friction logged after that. Finalize lists those entries in the "
            "run's addendum first, so they are still on record.") in _flow(docs)
    [chart] = re.findall(r"```mermaid\n(.*?)```", docs, re.DOTALL)
    for node in ('Off["Log the disabled marker and exit.', 'Reflect["Read the friction logged since the last marker',
                 'Done["Clean run. Log the clean marker and exit"]', 'Discard["Discard the findings. Log the discarded',
                 'Create["Create or react on an issue on health_check_repo"]',
                 'Close["Log the done marker with its counts"]', "Queue --> Close", "Create --> Close"):
        assert node in chart, node
    assert "public issue" not in chart and "Reflect on this run" not in chart


_AUTOSUBMIT_ALLOW = 'allowlist_commands = ["gh auth status", "gh search issues", "gh label create", "gh issue create"]'


def _docs() -> str:
    return (Path(__file__).resolve().parents[4] / "docs" / "health-check.md").read_text(encoding="utf-8")


def test_autosubmit_names_the_gh_calls_to_allow_and_a_refusal_has_its_own_reason():
    """Unattended, a gh call no allow rule covers is refused, so the opt-in says which to allow (architecture-1,
    customization-1); none is shipped, and a refusal is not reported as a missing CLI."""
    skill_root = Path(__file__).resolve().parents[2]
    customize = (skill_root / "customize.toml").read_text(encoding="utf-8")
    comment = customize[customize.index("# In unattended/headless runs"):customize.index("health_check_autosubmit =")]
    assert _AUTOSUBMIT_ALLOW in comment
    assert "under [workflow] in" in comment and "{project-root}/_bmad/custom/ultracode-goal.toml (or .user.toml)" in comment
    assert "Arrays append" in comment
    shipped = tomllib.loads(customize)["workflow"]["allowlist_commands"]
    assert not [c for c in shipped if c.split()[0] == "gh"], "no gh allow rule is shipped"
    # Each of the four is a gh call a headless submit makes, and a headless match never reacts or comments.
    body = _reference()
    for command in json.loads(_AUTOSUBMIT_ALLOW.split(" = ", 1)[1]):
        assert command in body, command
    step = _flow(_section("**2. Check GitHub CLI**", "**A refused `gh` call.**"))
    assert ('If it runs and fails, fall through to §5c with the reason "GitHub CLI is not available."') in step
    docs = _flow(_docs())
    assert "**To let autosubmit post unattended**, allow the four `gh` commands a submission runs." in docs
    assert "Arrays append to the shipped list" in docs
    assert _AUTOSUBMIT_ALLOW in _docs()


def test_the_gh_allow_rules_say_they_persist_how_to_scope_them_and_how_to_remove_them():
    """The rules outlast the run and cover every repository, so the opt-in says so and how to narrow and undo them."""
    customize = (Path(__file__).resolve().parents[2] / "customize.toml").read_text(encoding="utf-8")
    comment = " ".join(re.sub(r"^#\s*", "", customize[customize.index("# In unattended/headless runs"):
                                                       customize.index("health_check_autosubmit =")],
                              flags=re.MULTILINE).split())
    assert ".claude/settings.local.json, where it stays for every later session in the project" in comment
    assert ('"gh search issues --repo <repo>", "gh label create --repo <repo>" and "gh issue create --repo <repo>", '
            "<repo> being health_check_repo") in comment
    assert "When you turn autosubmit off, drop the entries and delete their Bash(gh ...) rules" in comment
    docs = _flow(_docs())
    assert ("These rules outlast the run: they stay in `.claude/settings.local.json` and apply to every later session "
            "in the project, so any agent working there can then create issues and labels on any repository without "
            "asking.") in docs
    assert ('allowlist_commands = ["gh auth status", "gh search issues --repo <health_check_repo>", '
            '"gh label create --repo <health_check_repo>", "gh issue create --repo <health_check_repo>"]') in _docs()
    assert ("When you turn autosubmit off, remove the entries, then delete the rules preflight wrote for them, such as "
            "`Bash(gh issue create:*)`, from `.claude/settings.local.json` yourself: preflight only adds rules.") in docs
    assert "POSIX shell (bash, zsh, Git Bash or WSL)" in docs


def test_every_override_the_docs_show_sits_under_workflow():
    """A bare top-level key is discarded by the resolver, so a copied block must carry its table (architecture-5)."""
    docs = _docs()
    blocks = re.findall(r"```toml\n(.*?)```", docs, re.DOTALL)
    assert len(blocks) == 3
    keys = set()
    for block in blocks:
        parsed = tomllib.loads(block)
        assert list(parsed) == ["workflow"], block
        keys |= set(parsed["workflow"])
    assert keys == {"health_check_repo", "health_check_autosubmit", "allowlist_commands"}
    assert ("The `[workflow]` table header matters: the resolver extracts the `workflow` block from the merged "
            "files, so a bare top-level line is silently discarded and the knob keeps its default.") in _flow(docs)
    assert "(set in `{project-root}/_bmad/custom/ultracode-goal.toml`) change this" not in docs


def test_the_docs_name_the_configured_repositorys_chooser():
    """An override that keeps findings off the public default must not be undone by the docs' link (customization-2)."""
    docs = _flow(_docs())
    assert ("You can also open one through the issue chooser of `<health-check-repo>`, "
            "`https://github.com/<health-check-repo>/issues/new/choose` (on the default, "
            "<https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/new/choose>).") in docs
    assert "through the repository's issue chooser at" not in docs
    # A filing through the chooser pastes the body_header too, never fills in its sections one by one.
    assert ("so replace its sections from Workflow through Defect Key with the `body_header` that the "
            "`health_check_fp.py fingerprint` command in the template's comments prints") in docs
    assert "fill in its Fingerprint and Severity sections" not in docs


def test_the_interactive_briefing_does_not_describe_headless_routing():
    """Only an attended operator reads the briefing (leanness-5)."""
    preflight = (Path(__file__).resolve().parents[2] / "references" / "preflight.md").read_text(encoding="utf-8")
    [line] = [ln for ln in preflight.splitlines() if ln.startswith("- **How the run ends:**")]
    assert line.endswith('so "unattended" ends there rather than at the last story.')
    assert "Headless" not in line


def test_contributing_points_at_the_actions_header_for_the_dedup_rules():
    """One maintainer-facing statement of the Action's rules, its header; CONTRIBUTING keeps what a maintainer
    acts on (leanness-7)."""
    contributing = (Path(__file__).resolve().parents[4] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    [bullet] = [ln for ln in contributing.splitlines() if ln.startswith("- **Deduplication is automatic.**")]
    assert "its header comment gives the rules. **Re-reporting is safe.**" in bullet
    assert "[dedup Action](.github/workflows/health-check-dedup.yaml)" in bullet
    for gone in ("lowest-numbered", "runs once at a time per issue", "One limit:"):
        assert gone not in bullet, gone


def test_contributing_records_a_fix_in_the_configured_seen_cache():
    """customization-1: an overridden health_check_seen_cache must get the `resolved` record the next run reads."""
    contributing = (Path(__file__).resolve().parents[4] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    [command] = [b for b in _fenced_blocks(contributing.replace("\n  ", "\n")) if "health_check_fp.py record" in b]
    assert "--cache <health_check_seen_cache>" in command
    assert "~/" not in command
    assert "(the configured `health_check_seen_cache`, by default `~/.ultracode-goal/health-check-seen.json`)" in contributing


# --- version: UCG's own root, then the CLI install's VERSION ------------------------------------

UCG = "bmad-module-ultracode-goal"
# What a user's project may hold: its own package.json and, for a project that is a plugin, its own marketplace.
USER_PACKAGE = {"name": "my-web-app", "version": "0.3.1"}
USER_MARKETPLACE = {"name": "my-plugins", "plugins": [{"name": "my-plugin", "version": "4.0.0"}]}


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _marketplace(root: Path, *plugins: dict, name: str = UCG) -> None:
    _write_json(root / ".claude-plugin" / "marketplace.json", {"name": name, "plugins": list(plugins)})


def _package(root: Path, name: str = UCG, version: str = "7.1.0") -> None:
    _write_json(root / "package.json", {"name": name, "version": version})


def _install_version(project: Path, text: str) -> None:
    (project / "_bmad" / "ucg").mkdir(parents=True, exist_ok=True)
    (project / "_bmad" / "ucg" / "VERSION").write_text(text, encoding="utf-8")


def _user_project(project: Path) -> Path:
    """A user's project holding its own package.json and its own plugin marketplace, neither of them UCG's."""
    _write_json(project / "package.json", USER_PACKAGE)
    _write_json(project / ".claude-plugin" / "marketplace.json", USER_MARKETPLACE)
    return project


def _copy_script(folder: Path) -> Path:
    """The script copied into folder, which is created: it runs from there, as an install runs it."""
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / SCRIPT.name
    copy.write_bytes(SCRIPT.read_bytes())
    return copy


def _ucg_checkout(root: Path) -> Path:
    """The script at <root>/skills/ultracode-goal/scripts/, as a checkout and a plugin hold it."""
    return _copy_script(root / "skills" / "ultracode-goal" / "scripts")


def _version(script: Path, project: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(script), "version", "--project-root", str(project)],
        capture_output=True, text=True, env=_env(), stdin=subprocess.DEVNULL, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def test_version_reads_the_marketplace_entry_named_ucg_first(tmp_path):
    root = tmp_path / "ucg"
    _marketplace(root, {"name": "another-plugin", "version": "1.0.0"}, {"name": UCG, "version": " 7.1.0 "})
    _package(root, version="7.0.9")
    assert _version(_ucg_checkout(root), tmp_path / "proj") == {
        "version": "7.1.0", "source": ".claude-plugin/marketplace.json"}


def test_version_reads_ucg_package_json_without_a_marketplace(tmp_path):
    root = tmp_path / "ucg"
    _package(root)
    assert _version(_ucg_checkout(root), tmp_path / "proj") == {"version": "7.1.0", "source": "package.json"}


@pytest.mark.parametrize(
    "marketplace",
    [
        {"name": UCG, "plugins": [{"name": "another-plugin", "version": "9.9.9"}]},
        {"name": UCG, "plugins": [{"version": "9.9.9"}]},
        {"name": UCG, "plugins": [{"name": UCG}]},
        {"name": UCG, "plugins": [{"name": UCG, "version": "  "}]},
        {"name": UCG, "plugins": [{"name": UCG, "version": 7}]},
        {"name": UCG, "plugins": {"name": UCG, "version": "9.9.9"}},
        {"name": UCG, "plugins": ["9.9.9"]},
        ["not", "an", "object"],
        "{ this is not valid json {{{",
    ],
    ids=["another-plugin", "unnamed-entry", "no-version", "blank-version", "number-version", "plugins-not-a-list",
         "entry-not-an-object", "not-an-object", "malformed"],
)
def test_a_marketplace_with_no_ucg_version_falls_through_to_package_json(tmp_path, marketplace):
    root = tmp_path / "ucg"
    path = root / ".claude-plugin" / "marketplace.json"
    if isinstance(marketplace, str):
        path.parent.mkdir(parents=True)
        path.write_text(marketplace, encoding="utf-8")
    else:
        _write_json(path, marketplace)
    _package(root, version="7.0.9")
    assert _version(_ucg_checkout(root), tmp_path / "proj") == {"version": "7.0.9", "source": "package.json"}


@pytest.mark.parametrize(
    "package",
    [
        USER_PACKAGE,
        {"version": "0.3.1"},
        {"name": UCG.upper(), "version": "0.3.1"},
        {"name": UCG, "version": ""},
        {"name": UCG},
        "not json at all }{",
    ],
    ids=["another-name", "no-name", "name-in-another-case", "empty-version", "no-version", "malformed"],
)
def test_a_package_json_with_no_ucg_version_falls_through_to_the_install_version(tmp_path, package):
    """A foreign file at UCG's root falls through: the install's VERSION, then null."""
    root = tmp_path / "ucg"
    if isinstance(package, str):
        root.mkdir()
        (root / "package.json").write_text(package, encoding="utf-8")
    else:
        _write_json(root / "package.json", package)
    script = _ucg_checkout(root)
    project = tmp_path / "proj"
    assert _version(script, project) == {"version": None, "source": "N/A"}
    _install_version(project, "7.1.0\n")
    assert _version(script, project) == {"version": "7.1.0", "source": "_bmad/ucg/VERSION"}


def test_a_stale_install_version_never_masks_the_roots(tmp_path):
    """A checkout's own `_bmad/ucg/VERSION`, left by an old install (this checkout's says 2.2.0), loses to its root."""
    root = tmp_path / "ucg"
    _marketplace(root, {"name": UCG, "version": "7.1.0"})
    _package(root)
    _install_version(root, "2.2.0\n")
    assert _version(_ucg_checkout(root), root) == {"version": "7.1.0", "source": ".claude-plugin/marketplace.json"}


def test_this_checkout_reports_its_own_version():
    """The checkout's marketplace answers first: its plugin entry named bmad-module-ultracode-goal."""
    root = SCRIPT.resolve().parents[3]
    marketplace = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    [expected] = [entry["version"] for entry in marketplace["plugins"] if entry["name"] == UCG]
    assert _load().UCG_ROOT == root
    assert _version(SCRIPT, root) == {"version": expected, "source": ".claude-plugin/marketplace.json"}


@pytest.mark.parametrize("skills", [".claude/skills", "_bmad/ucg"])
def test_a_cli_install_reads_the_install_version_never_the_users_package_json(tmp_path, skills):
    """The CLI installer copies the skill under .claude/skills/ and _bmad/ucg/ and writes _bmad/ucg/VERSION.

    Neither copy has a root of its own: UCG_ROOT is proj/.claude or proj/_bmad, which hold no package.json or
    marketplace.json, so the user's own, in proj, are never read.
    """
    project = _user_project(tmp_path / "proj")
    script = _copy_script(project / skills / "ultracode-goal" / "scripts")
    assert _version(script, project) == {"version": None, "source": "N/A"}
    _install_version(project, "7.1.0\n")
    assert _version(script, project) == {"version": "7.1.0", "source": "_bmad/ucg/VERSION"}


def test_a_plugin_install_reads_the_plugins_root_never_the_users_project(tmp_path):
    """#234: the user's package.json and marketplace.json are the project's, never UCG's version."""
    plugin = tmp_path / "plugins" / "cache" / UCG / UCG / "7.1.0"
    _marketplace(plugin, {"name": UCG, "version": "7.1.0"})
    _package(plugin)
    project = _user_project(tmp_path / "proj")
    assert _version(_ucg_checkout(plugin), project) == {"version": "7.1.0", "source": ".claude-plugin/marketplace.json"}


def test_a_plugin_without_its_version_files_is_null_never_the_users_version(tmp_path):
    project = _user_project(tmp_path / "proj")
    assert _version(_ucg_checkout(tmp_path / "plugin"), project) == {"version": None, "source": "N/A"}


def test_an_install_version_saved_with_a_byte_order_mark_gives_the_bare_version(tmp_path):
    project = tmp_path / "proj"
    (project / "_bmad" / "ucg").mkdir(parents=True)
    (project / "_bmad" / "ucg" / "VERSION").write_bytes(b"\xef\xbb\xbf7.1.0\n")
    assert _version(_ucg_checkout(tmp_path / "ucg"), project) == {"version": "7.1.0", "source": "_bmad/ucg/VERSION"}


def test_an_empty_install_version_is_null(tmp_path):
    project = tmp_path / "proj"
    _install_version(project, "   \n  ")
    assert _version(_ucg_checkout(tmp_path / "ucg"), project) == {"version": None, "source": "N/A"}


def _module_at(fake_path: str):
    """The script's source run as a module whose __file__ is fake_path, which need not exist."""
    module = types.ModuleType("health_check_fp_at_a_fake_path")
    module.__file__ = fake_path
    exec(compile(SCRIPT.read_text(encoding="utf-8"), fake_path, "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_a_shallow_script_has_no_root_rungs(tmp_path, capsys, depth):
    """Copied to a folder with fewer than four parents, the script has no root of its own: no crash, no root rung."""
    fake = Path(Path.cwd().anchor, *["d"] * depth, SCRIPT.name)
    module = _module_at(str(fake))
    assert module.UCG_ROOT is None
    project = tmp_path / "proj"
    _user_project(project)
    code, payload = _main(module, capsys, "version", "--project-root", str(project))
    assert (code, payload) == (0, {"version": None, "source": "N/A"})
    _install_version(project, "7.1.0")
    code, payload = _main(module, capsys, "version", "--project-root", str(project))
    assert (code, payload) == (0, {"version": "7.1.0", "source": "_bmad/ucg/VERSION"})


def test_a_test_points_the_root_elsewhere_through_the_module_constant(tmp_path, mod, monkeypatch, capsys):
    root = tmp_path / "ucg"
    _package(root, version="6.0.0")
    monkeypatch.setattr(mod, "UCG_ROOT", root)
    assert _main(mod, capsys, "version", "--project-root", str(tmp_path / "proj")) == (
        0, {"version": "6.0.0", "source": "package.json"})


def test_version_takes_no_skill_root(tmp_path):
    """The {skill-root}/VERSION rung is gone, and with it the flag."""
    proc = _run("version", "--project-root", str(tmp_path), "--skill-root", str(tmp_path))
    assert proc.returncode == 2
    blocks = [b for b in _fenced_blocks(_reference()) if "health_check_fp.py version" in b]
    assert blocks == ["uv run {skill-root}/scripts/health_check_fp.py version --project-root {project-root}\n"]


# --- the health check's own stage -----------------------------------------------


def _own_stage_finding(heading: str = "5c. Local queue (every finding that stays local)") -> dict:
    code, payload = _fingerprint_stdin("bug", "health-check", {
        "section_heading": heading,
        "defect_name": "queue",
        "short_description": "the queue step names no folder",
    })
    assert code == 0, payload
    return payload


def test_health_check_is_a_stage_of_its_own():
    """A defect in the health check's own instructions is fingerprinted under its own stage file."""
    payload = _own_stage_finding()
    assert payload["section_slug"] == "local-queue-every-finding-that-stays-local"
    assert payload["tuple"].startswith(
        "bug|ultracode-goal/health-check|skills/ultracode-goal/references/health-check.md|"
        "local-queue-every-finding-that-stays-local|")
    assert payload["title"].startswith(f"[health-check][bug][{payload['fp']}] ultracode-goal/health-check: ")
    assert "`ultracode-goal/health-check`" in payload["body_header"]


def test_a_heading_the_health_check_file_lacks_is_refused_under_its_stage():
    code, payload = _fingerprint_stdin("bug", "health-check", {
        "section_heading": "Route on the verdict",
        "defect_name": "queue",
        "short_description": "a defect",
    })
    assert code == 1
    assert "no heading of references/health-check.md" in payload["error"]


def test_a_health_check_finding_is_queued_under_its_own_stage(tmp_path, mod, monkeypatch, capsys):
    """A real heading of health-check.md, through fingerprint and then queue."""
    monkeypatch.setattr(mod, "_queue_stamp", lambda: "20261114-093012")
    finding = _own_stage_finding("6. Close")
    body = _draft(tmp_path / "hc-body.md", finding)
    code, result = _queue(mod, capsys, tmp_path / "q", body, finding["title"])
    assert code == 0, result
    assert Path(result["path"]).name == "hc-ultracode-goal-health-check-20261114-093012.md"


def test_a_finding_about_the_health_check_itself_is_never_posted():
    """#230: every submitting or queueing route queues it with its own reason; [N] discards it."""
    route = _flow(_section("## 4. Route by run mode", "### 4a. Attended routing"))
    assert "A finding whose stage is `health-check` is never posted." in route
    assert ("Every route that submits or queues (**[Y]**, **[A]**, **[Q]** and headless) writes it to the local "
            "queue (§5c) with the reason \"Found in the health check's own instructions; review it before "
            "submitting.\", which replaces any reason its route would give; **[N]** discards it with the rest.") in route
    # The routing bullets an agent follows carry the exception themselves.
    headless = _flow(_section("### 4-headless.", "## 5. Severity routing"))
    assert "(a `health-check` finding takes §4's)" in headless
    assert "live-submit the `bug` findings but a `health-check` one (§5a)" in headless
    severity = _flow(_section("## 5. Severity routing", "### 5a. Live-submit"))
    assert "each `bug` finding but a `health-check` one live-submits (§5a)" in severity
    assert "every finding but a `health-check` one live-submits (§5a)" in severity
    assert "A `health-check` finding, under either, goes to the local queue with §4's reason." in severity
    gate = _flow(_section("### 4a. Attended routing", "### 4-headless."))
    assert ("a finding about the health check itself (stage `health-check`) is queued, never posted, whatever you "
            "choose but **[N]** (§4)") in gate
    assert ("When every finding's stage is `health-check`, ask instead \"Queue these findings locally?\" with "
            "**[Q]**, **[N]** and **[E]** only.") in gate
    assert "a stage moved into or out of `health-check` changes its route (§4)" in gate
    find = _flow(_section("## 2. Find the findings", "## 3. Fingerprint"))
    assert "or `health-check` when the instruction is this file's own or belongs to a script or command it runs" in find


def test_a_defect_in_the_check_itself_is_queued_once_or_logged_for_the_next_check():
    """#230: the rule sits before §3, so §3's jump to §6 cannot skip it, and covers §6 through the friction read."""
    enabled = _flow(_section("## 1. Enabled gate", "## 2. Find the findings"))
    assert ("A defect in this file's instructions, or in a script or command it runs, that bites while the check "
            "runs §3 to §6 is a finding of the stage `health-check` (§4).") in enabled
    assert ("Until §6 appends its marker, fingerprint and draft it (§3) and queue it as §4 says. Take at most one "
            "per check: append any further one, and one that bites once the marker is in, as a "
            "`friction: health-check.md \"<section heading>\": <what bit>` line after the marker, which the next "
            "health check reads.") in enabled
    # A friction line after the marker is exactly what the next check's read takes.
    log = ("- health-check: done, 0 filed, 0 upvoted, 1 queued, 0 already handled, 0 dropped\n"
           "- friction: health-check.md \"6. Close\": the counts left out a merged finding\n")
    assert _friction_read(log) == ["- friction: health-check.md \"6. Close\": the counts left out a merged finding"]


def test_the_docs_say_a_finding_about_the_health_check_is_never_posted():
    docs = _flow(_docs())
    assert ("or `health-check` for a defect in the health check's own instructions or in a script or command it "
            "runs, which is never posted: it goes to the local queue unless you discard it") in docs
    assert ("A finding about the health check itself (stage `health-check`) is queued, never posted, whatever you "
            "choose but no.") in docs
    assert "they always queue regardless of this setting, as does a finding about the health check itself." in docs
    assert "a finding about the health check itself, no GitHub CLI" in docs


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

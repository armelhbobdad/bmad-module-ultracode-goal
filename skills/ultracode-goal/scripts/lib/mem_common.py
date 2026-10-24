#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Shared primitives for ultracode-goal Cross-Session Recall.

This is the shared internal library — NOT a CLI entrypoint (no argparse, no
main). It lives under scripts/lib/ (out of the CLI-entrypoint scope) and is
imported as ``from lib import mem_common as mc`` by mem_recall.py and
mem_observation.py (and their tests). The PreToolUse hook (guard_pretooluse.py)
deliberately does NOT import this module — it stays self-contained so the
gating path has zero shared surface with the advisory path.

Cross-Session Recall leverages the third-party claude-mem plugin in an
advisory-only capacity: it NEVER sits in the gate/completion path, it is
voice-never-vote, it fails closed during a run, control flow is identical when
absent, and it is OFF by default. Everything here is deterministic, stdlib-only,
no network.

Contents:
  - UCG_SCHEMA_VERSION / UCG_MARKER       payload tagging
  - TAXONOMY                              the 12 root-cause classes
  - canonical_class()                     unknown -> "other"
  - repo_fingerprint(cwd)                 stable per-repo identity
  - redact(text)                          high-precision secret scrubbing
  - neutralize(text)                      bidi/code-fence strip + 80cp clamp
  - state_path / read_state / write_state machine latch plumbing
  - carries_marker / extract_payload      legacy claude-mem payload parsing
  - valid_run_id                          the run_id check both scripts share
  - is_store_unset / resolve_store_root / store_unset_note   the cross_session_recall_store key
  - fingerprint_dir / runs_dir / run_file_path   store layout
  - ensure_store_root                     store root plus its self-ignoring .gitignore
  - validate_record / classify_record     per-record validation
  - write_run_record                      the immutable per-run writer
  - iter_store_records / read_store       the reader over a list of roots
  - probe_store                           the write probe the latch runs
  - is_legacy_payload / legacy_payload_to_record   outbox migration
  - build_latch_v2 / measure_latch_v2 / latch_view   latch v2

The state file is the machine latch the hook reads to decide whether claude-mem
MCP calls are permitted during a run. Its schema (v1) is documented at
write_state() and shared verbatim with the hook's gating predicate.

The local run store (the "Local run store" section below) is the backend that
replaces claude-mem: ``<store>/<fingerprint-dir>/runs/<run_id>.jsonl``, one
immutable JSON line per run, written and read only through this module by
mem_observation.py and mem_recall.py. The v2 latch certifies that the store can
be written; its helpers sit beside the v1 ones, which are unchanged.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import unicodedata
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

UCG_SCHEMA_VERSION = 1
UCG_MARKER = "[ucg-payload:v1]"

# Exactly 12 root-cause classes. "other" is the catch-all and is NOT eligible to
# be treated as a recurring signal (see mem_recall recurrence). Frozen tuple so
# callers can rely on ordering and immutability.
TAXONOMY: tuple[str, ...] = (
    "test-flake",
    "test-failure",
    "build-error",
    "lint-error",
    "dependency",
    "environment-config",
    "race-condition",
    "fixture-isolation",
    "integration-contract",
    "performance",
    "security",
    "other",
)

_TAXONOMY_SET = frozenset(TAXONOMY)


def canonical_class(value: str | None) -> str:
    """Map an arbitrary class string onto TAXONOMY; unknown -> "other"."""
    if value is None:
        return "other"
    candidate = value.strip()
    return candidate if candidate in _TAXONOMY_SET else "other"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with a trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Repo fingerprint
# ---------------------------------------------------------------------------

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    """Run git in cwd, returning (returncode, stdout-stripped). Never raises."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def normalize_remote(url: str) -> str:
    """Normalize a git remote URL so ssh and https forms collapse to one key.

    Strips the scheme, any user@ prefix, a trailing .git, and a trailing slash,
    converts the ``host:org/repo`` scp-like form to ``host/org/repo``, and
    lowercases the result. Purely lexical — no network.
    """
    text = url.strip()
    # Drop an explicit scheme (https://, ssh://, git://, ...).
    text = _SCHEME_RE.sub("", text)
    # Drop a leading user@ (git@github.com:..., user@host/...).
    if "@" in text:
        text = text.split("@", 1)[1]
    # scp-like "host:org/repo" -> "host/org/repo". Only treat the FIRST colon as
    # the host/path separator, and only when it is not a "host:port" number.
    if ":" in text:
        host, _, rest = text.partition(":")
        if not rest.split("/", 1)[0].isdigit():
            text = f"{host}/{rest}"
    # Drop trailing slash, then a trailing .git.
    text = text.rstrip("/")
    if text.endswith(".git"):
        text = text[: -len(".git")]
    return text.lower()


def _select_remote(cwd: Path) -> str | None:
    """Return the chosen remote URL: origin pinned, else lexicographically first."""
    code, out = _git(cwd, "remote")
    if code != 0 or not out:
        return None
    names = sorted(n for n in out.splitlines() if n.strip())
    if not names:
        return None
    chosen = "origin" if "origin" in names else names[0]
    code, url = _git(cwd, "remote", "get-url", chosen)
    if code != 0 or not url:
        return None
    return url


def repo_fingerprint(cwd: str | os.PathLike[str]) -> dict:
    """Compute a stable per-repo fingerprint.

    Returns {"basis": <str|None>, "value": <str|None>}:
      - "remote+root"  full normal case: sha1(normalized_remote + "|" + root_sha)
      - "remote-only"  shallow repo: sha1(normalized_remote)[:16]
      - "local"        no remote: "local:" + root_sha[:16]
      - None/None      zero commits or not a git repo (callers => recall off)

    The fingerprint pins a UCG payload to the repo that produced it so recall
    never bleeds advisories across unrelated checkouts.
    """
    root = Path(cwd)

    # Not a git work tree at all -> no fingerprint.
    code, inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0 or inside != "true":
        return {"basis": None, "value": None}

    # Root commit (oldest). Empty repo -> no commits -> no fingerprint.
    code, root_out = _git(root, "rev-list", "--max-parents=0", "HEAD")
    if code != 0 or not root_out:
        return {"basis": None, "value": None}
    root_sha = root_out.splitlines()[0].strip()
    if not root_sha:
        return {"basis": None, "value": None}

    remote_url = _select_remote(root)

    # Shallow clone: history is truncated so the root commit is unreliable; pin
    # to the remote alone.
    code, shallow = _git(root, "rev-parse", "--is-shallow-repository")
    is_shallow = code == 0 and shallow == "true"

    if is_shallow:
        if remote_url is None:
            # Shallow with no remote: nothing stable to pin to.
            return {"basis": None, "value": None}
        normalized = normalize_remote(remote_url)
        value = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
        return {"basis": "remote-only", "value": value}

    if remote_url is None:
        value = "local:" + root_sha[:16]
        return {"basis": "local", "value": value}

    normalized = normalize_remote(remote_url)
    basis_input = f"{normalized}|{root_sha}"
    value = hashlib.sha1(basis_input.encode("utf-8")).hexdigest()[:16]
    return {"basis": "remote+root", "value": value}


# ---------------------------------------------------------------------------
# Redaction — high-precision secret scrubbing
# ---------------------------------------------------------------------------

_REDACTION = "[redacted]"

# High-precision patterns: each is specific enough that a match is almost
# certainly a real secret, so false positives are rare. Order matters only in
# that the value-bearing key=value patterns run last.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # AWS access key id.
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # GitHub personal/oauth tokens (ghp_, gho_, ghu_, ghs_, ghr_).
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    # OpenAI / Anthropic style sk- keys (sk-, sk-ant-...).
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    # PEM block opener.
    re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----"),
    # Bearer tokens in an Authorization context.
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
    # password= / token= / api_key= / apikey= / secret= value assignments.
    re.compile(
        r"(?i)\b(?:password|passwd|pwd|token|api[_-]?key|apikey|secret)\s*[=:]\s*"
        r"['\"]?[^\s'\"]{4,}['\"]?"
    ),
)


def redact(text: str | None) -> str:
    """Replace high-precision secret patterns with ``[redacted]``.

    Conservative on purpose: matches only well-known credential shapes so we do
    not mangle ordinary prose. Returns "" for None.
    """
    if not text:
        return ""
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_REDACTION, out)
    return out


# ---------------------------------------------------------------------------
# Neutralization — defang untrusted free text for storage/recall
# ---------------------------------------------------------------------------

# Bidi control codepoints that can visually reorder text (Trojan Source style).
_BIDI_CONTROLS = {
    "‪",
    "‫",
    "‬",
    "‭",
    "‮",
    "⁦",
    "⁧",
    "⁨",
    "⁩",
}

_CLAMP = 80


def _clamp_codepoints(text: str, limit: int) -> str:
    """Clamp to ``limit`` codepoints on a codepoint boundary (never mid-char)."""
    # Iterating the str yields whole codepoints, so slicing the list is always
    # boundary-safe regardless of multibyte UTF-8 encoding.
    chars = list(text)
    if len(chars) <= limit:
        return text
    return "".join(chars[:limit])


def neutralize(text: str | None) -> str:
    """Defang untrusted free text into a single short, plain phrase.

    Strips bidi controls, removes backticks / code-fence markers, collapses all
    whitespace runs (including newlines/tabs) to single spaces, drops other
    control characters, and clamps to 80 codepoints on a boundary. Idempotent.
    Returns "" for None.
    """
    if not text:
        return ""
    out_chars = []
    for ch in text:
        if ch in _BIDI_CONTROLS:
            continue
        if ch == "`":
            continue
        category = unicodedata.category(ch)
        # Cc = control, Cf = format (other invisible formatting); drop them, but
        # keep ordinary whitespace which we normalize below by mapping to space.
        if category in ("Cc", "Cf"):
            # Preserve word separation for whitespace-like controls.
            out_chars.append(" ")
            continue
        out_chars.append(ch)
    collapsed = re.sub(r"\s+", " ", "".join(out_chars)).strip()
    return _clamp_codepoints(collapsed, _CLAMP)


# ---------------------------------------------------------------------------
# State file (machine latch) plumbing
# ---------------------------------------------------------------------------

LATCH_VERSION = 1
_STATE_FILENAME = ".mem-state.json"


def state_path(impl_artifacts: str | os.PathLike[str]) -> Path:
    """Return the latch path: ``<impl_artifacts>/.mem-state.json``."""
    return Path(impl_artifacts) / _STATE_FILENAME


def read_state(impl_artifacts: str | os.PathLike[str]) -> dict | None:
    """Read and JSON-parse the latch. Missing/empty/corrupt -> None (never raises)."""
    path = state_path(impl_artifacts)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def write_state(impl_artifacts: str | os.PathLike[str], state: dict) -> Path:
    """Atomically write the latch (tmp file + os.replace) and return its path.

    Schema v1 (exact keys), written ONCE per run by mem_recall latch:
      {"latch_version":1, "run_id":str, "claude_mem":"present"|"absent",
       "schema_ok":bool, "recall":"on"|"off", "tool_form":"plugin"|"bare"|null,
       "fingerprint":str|null, "created_at":ISO}
    """
    impl = Path(impl_artifacts)
    impl.mkdir(parents=True, exist_ok=True)
    path = state_path(impl)
    fd, tmp_name = tempfile.mkstemp(dir=str(impl), prefix=".mem-state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, str(path))
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def remove_state(impl_artifacts: str | os.PathLike[str]) -> bool:
    """Remove the latch (Stage 6 close-out). Returns True if a file was removed."""
    path = state_path(impl_artifacts)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Legacy claude-mem payload parsing (shared by mem_recall and mem_observation)
# ---------------------------------------------------------------------------


def carries_marker(record: object) -> bool:
    """True if the record's ``text`` field carries our payload marker.

    A title that merely starts with "UCG run" is not proof of ownership, so only
    the marker counts.
    """
    if not isinstance(record, dict):
        return False
    text = record.get("text")
    return isinstance(text, str) and UCG_MARKER in text


def extract_payload(record: dict) -> dict | None:
    """Pull our embedded JSON payload out of a record's text. Defensive.

    The text field is one human line, then the marker, then a fenced json block.
    We locate the first ``{`` after the marker and JSON-decode from there using a
    raw decoder so trailing fence characters do not break parsing. Never raises;
    returns None when nothing parseable is present. Moved here from mem_recall,
    whose ``_extract_payload`` keeps the same behaviour for dict records.
    """
    if not isinstance(record, dict):
        return None
    text = record.get("text")
    if not isinstance(text, str):
        return None
    marker_at = text.find(UCG_MARKER)
    if marker_at == -1:
        return None  # no marker -> not our payload; never scan from position 0
    brace_at = text.find("{", marker_at + len(UCG_MARKER))
    if brace_at == -1:
        return None
    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(text[brace_at:])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


# ---------------------------------------------------------------------------
# Local run store (cross_session_recall_store)
# ---------------------------------------------------------------------------
#
# Layout: <store>/<fingerprint-dir>/runs/<run_id>.jsonl, one JSON line per run.
# The store root carries a create-only ``.gitignore`` holding ``*`` so a store
# inside a workspace ignores itself. Run files are immutable: created once
# (temp file, fsync, os.link; O_EXCL only where links are unsupported) and never
# replaced, renamed or copied over. Only mem_observation.py and mem_recall.py
# reach the store, through the functions below; the PreToolUse guard keeps its
# own reader of the latch v2 ``store`` field and mirrors latch_view().

STORE_KEY = "cross_session_recall_store"
STORE_BACKEND = "jsonl"
STORE_RUNS_DIRNAME = "runs"
STORE_GITIGNORE = ".gitignore"
STORE_GITIGNORE_BODY = b"*\n"

# write_run_record() outcomes.
WRITE_WRITTEN = "written"
WRITE_SKIPPED_EXISTING = "skipped-existing"
WRITE_FOREIGN_TARGET = "foreign-target"

# Per-record validation outcomes (the filter's dropped categories).
RECORD_OK = "ok"
RECORD_INVALID = "invalid"
RECORD_CROSS_SCHEMA = "cross_schema"
RECORD_FOREIGN = "foreign"

# Pinned NOTE and WARN tokens the two scripts print (and the prose logs).
NOTE_RECALL_STORE_UNSET = "NOTE recall-store-unset"
NOTE_MEM_TARGET_FOREIGN = "NOTE mem-target-foreign"
NOTE_MEM_RUN_ID_INVALID = "NOTE mem-run-id-invalid"
NOTE_MEM_LEGACY_UNCONVERTIBLE = "NOTE mem-legacy-unconvertible"
WARN_MEM_WRITE_DEFERRED = "WARN mem-write-deferred"

# A run file larger than this is never a record of ours: dropped as invalid
# without decoding it.
_MAX_RUN_FILE_BYTES = 1 << 20

_RUN_ID_RE = re.compile(r"^epic-[A-Za-z0-9._-]+-\d{8}T\d{6}Z$", re.ASCII)


def _is_int(value: object) -> bool:
    """True for a real int (bool is an int subclass and is not one here)."""
    return isinstance(value, int) and not isinstance(value, bool)


def valid_run_id(value: object) -> bool:
    """The run_id check both scripts apply before any write.

    ``re.fullmatch`` under ``re.ASCII`` against
    ``^epic-[A-Za-z0-9._-]+-\\d{8}T\\d{6}Z$``, and no ``..`` anywhere: the bare
    pattern accepts ``..``, ``re.match`` with ``$`` accepts a trailing newline,
    and a Unicode ``\\d`` matches non-ASCII digits. A run_id that passes is a
    safe single path component on every OS (no separator, no ``..``).
    """
    if not isinstance(value, str) or ".." in value:
        return False
    return _RUN_ID_RE.fullmatch(value) is not None


# ---------------------------------------------------------------------------
# Store path resolution
# ---------------------------------------------------------------------------

_PROJECT_ROOT_TOKEN = "{project-root}"
_BRACE_TOKEN_RE = re.compile(r"\{[^{}]*\}")
# A literal $NAME / ${NAME}, or a Windows %NAME% (ProgramFiles(x86) included),
# opening a path component: never expanded here, so it would become a folder
# named after the variable. A "$" or "%" inside a name (my$proj, C$, 50%) is
# part of that name.
_DOLLAR_VAR_RE = re.compile(r"(?:^|[/\\])\$(?:[A-Za-z_][A-Za-z0-9_]*|\{)")
_PERCENT_VAR_RE = re.compile(r"(?:^|[/\\])%[A-Za-z_][A-Za-z0-9_()]*%")


def is_store_unset(value: object) -> bool:
    """True when a cross_session_recall_store value counts as unset.

    Unset: not a string (None, a missing key), empty or whitespace only, an
    unresolved ``{...}`` token, a literal ``$VAR`` / ``${VAR}`` or ``%VAR%``
    opening a path component, or a NUL character. Checked on the raw text
    before any expansion, because ``Path("").expanduser()`` is the cwd and a
    literal ``$HOME`` would become a directory named ``$HOME``. A ``$`` or
    ``%`` inside a name (``my$proj``, a ``C$`` share) is part of that name.
    ``{project-root}`` is a token here too:
    resolve_store_root() substitutes it first when it is given a project root.
    A value this accepts can still resolve to nothing: resolve_store_root()
    also refuses one that is not absolute once expanded.
    """
    if not isinstance(value, str):
        return True
    text = value.strip()
    if not text or "\0" in text:
        return True
    if _BRACE_TOKEN_RE.search(text) or _PERCENT_VAR_RE.search(text):
        return True
    return _DOLLAR_VAR_RE.search(text) is not None


def store_unset_note(consequence: str) -> str:
    """The ``NOTE recall-store-unset`` line, naming the key and its accepted forms."""
    return (
        f"{NOTE_RECALL_STORE_UNSET}: {STORE_KEY} is not set to a usable folder, so "
        f"{consequence} (set it to a ~ path, an absolute path or a {_PROJECT_ROOT_TOKEN} "
        f"path, for example ~/.ultracode-goal/recall)"
    )


def resolve_store_root(
    value: object,
    *,
    project_root: str | os.PathLike[str] | None = None,
) -> Path | None:
    """Resolve a cross_session_recall_store value to an absolute store root.

    Returns None when the value counts as unset (is_store_unset) or does not
    resolve to an absolute path. Accepted forms, and the only ones:
    ``~``-relative (``Path.expanduser``, like health_check_seen_cache, so HOME on
    POSIX and USERPROFILE on Windows), absolute, and ``{project-root}/...`` when
    ``project_root`` is given (made absolute first; without it the token stays
    unresolved and the value counts as unset). A relative value is refused, so
    one value never names two stores from two working directories. The result
    is ``os.path.abspath`` of the expanded path: normalized, symlinks not
    resolved. A ``~`` that cannot be expanded counts as unset.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    substitute = project_root is not None and _PROJECT_ROOT_TOKEN in text
    # Checked before substituting, so a brace or "$" inside the project root's
    # own path never reads as an unresolved token.
    if is_store_unset(text.replace(_PROJECT_ROOT_TOKEN, "p") if substitute else text):
        return None
    try:
        if substitute:
            text = text.replace(_PROJECT_ROOT_TOKEN, os.path.abspath(os.fspath(project_root)))
        path = Path(text).expanduser()
        if str(path).startswith("~") or not path.is_absolute():
            return None
        return Path(os.path.abspath(path))
    except (RuntimeError, ValueError):  # no home to expand against; a NUL byte
        return None


# Characters a Windows path component cannot hold (plus anything non-ASCII).
_FP_DIR_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]", re.ASCII)
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def fingerprint_dir(fingerprint: object) -> str | None:
    """The Windows-legal directory name for a repo fingerprint, or None.

    Every character outside ``[A-Za-z0-9._-]`` becomes ``-`` (so the no-remote
    ``local:<16 hex>`` becomes ``local-<16 hex>``), trailing dots and spaces are
    stripped, and a reserved device name gains a leading ``_``. A 16-hex remote
    fingerprint is unchanged. The raw fingerprint stays inside each record, and
    the foreign check compares that raw value, so two fingerprints that map to
    one directory never read as each other's.
    """
    if not isinstance(fingerprint, str):
        return None
    name = _FP_DIR_UNSAFE_RE.sub("-", fingerprint.strip()).rstrip(". ")
    if not name.strip(".-"):
        return None
    if name.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        name = "_" + name
    return name


def runs_dir(store_root: str | os.PathLike[str], fingerprint: object) -> Path:
    """``<store>/<fingerprint-dir>/runs``. ValueError when no fingerprint dir."""
    name = fingerprint_dir(fingerprint)
    if name is None:
        raise ValueError("no usable repo fingerprint for the store layout")
    return Path(store_root) / name / STORE_RUNS_DIRNAME


def run_file_path(
    store_root: str | os.PathLike[str], fingerprint: object, run_id: object
) -> Path:
    """``<store>/<fingerprint-dir>/runs/<run_id>.jsonl``.

    ValueError when the run_id fails valid_run_id() or the fingerprint has no
    directory name, so no path is ever built from a bad value.
    """
    if not valid_run_id(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    return runs_dir(store_root, fingerprint) / f"{run_id}.jsonl"


def _create_exclusive(path: Path, data: bytes) -> None:
    """Create ``path`` with ``data`` only if it does not exist (O_EXCL).

    FileExistsError when it does. A partial file this call created is removed
    before the error propagates.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(str(path), flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        try:
            os.unlink(str(path))
        except OSError:
            pass
        raise


def ensure_store_root(store_root: str | os.PathLike[str]) -> bool:
    """Create the store root if missing; return True when this call created it.

    A root this call creates gets ``<store>/.gitignore`` holding ``*``,
    create-only (an existing file is never overwritten), so a store inside a
    git workspace leaves ``git status --porcelain`` empty. A root that already
    exists is left as it is, with no ``.gitignore`` written. If the
    ``.gitignore`` cannot be written, the empty root is removed again and the
    OSError propagates, so no root this module made ever lacks it. Raises
    OSError (NotADirectoryError when the path is a file) on any failure.
    """
    root = Path(store_root)
    try:
        root.mkdir(parents=True)
    except FileExistsError:
        if root.is_dir():
            return False
        if os.path.lexists(root):
            raise NotADirectoryError(
                errno.ENOTDIR, "store root is not a directory", str(root)
            ) from None
        raise  # a parent is a file (Windows reports that as FileExistsError)
    try:
        _create_exclusive(root / STORE_GITIGNORE, STORE_GITIGNORE_BODY)
    except FileExistsError:
        pass
    except OSError:
        try:
            root.rmdir()
        except OSError:
            pass
        raise
    return True


def main_worktree_name(cwd: str | os.PathLike[str]) -> str | None:
    """The main worktree's directory name (the record's display-only ``project``).

    Taken from ``git rev-parse --git-common-dir``, so every worktree of one repo
    reports the main checkout's name. A bare repo reports its own name without
    ``.git``. None outside git. Never compared: the foreign check uses the
    fingerprint only.
    """
    root = Path(cwd)
    code, out = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    lines = out.splitlines() if code == 0 else []
    common_text = lines[-1].strip() if lines else ""
    if not common_text or common_text.startswith("--"):
        # A git older than --path-format echoes the flag; ask without it.
        code, out = _git(root, "rev-parse", "--git-common-dir")
        lines = out.splitlines() if code == 0 else []
        common_text = lines[-1].strip() if lines else ""
        if not common_text:
            return None
    common = Path(common_text)
    if not common.is_absolute():
        common = root / common
    common = Path(os.path.abspath(common))
    if common.name == ".git":
        return common.parent.name or None
    name = common.name
    if name.endswith(".git") and len(name) > len(".git"):
        name = name[: -len(".git")]
    return name or None


# ---------------------------------------------------------------------------
# Record shape and validation
# ---------------------------------------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def utc_now_epoch_ms() -> int:
    """Current UTC time as integer milliseconds since the Unix epoch."""
    return time.time_ns() // 1_000_000


def iso_to_epoch_ms(stamp: object) -> int | None:
    """Parse an ISO-8601 stamp (``...Z`` or an offset) to integer UTC ms.

    A stamp with no offset is read as UTC. None when it does not parse.
    """
    if not isinstance(stamp, str) or not stamp.strip():
        return None
    text = stamp.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed - _EPOCH) // timedelta(milliseconds=1)


def store_record(payload: dict, *, created_at_epoch: int, project: str) -> dict:
    """A store record: the ``build`` payload plus ``created_at_epoch`` and ``project``.

    ``payload`` is the dict ``mem_observation.py build`` embeds today (without
    the claude-mem ``{text,title,project}`` wrapper). ``created_at_epoch`` is
    integer UTC ms, stamped when the payload is built; ``project`` is display
    only ("" when unknown). Returns a new dict; ``payload`` is not modified.
    """
    record = dict(payload)
    record["created_at_epoch"] = created_at_epoch
    record["project"] = project
    return record


def _str_or_none(value: object) -> bool:
    return value is None or isinstance(value, str)


def _list_of_str_dicts(value: object, keys: tuple[str, ...]) -> bool:
    if not isinstance(value, list):
        return False
    for entry in value:
        if not isinstance(entry, dict):
            return False
        for key in keys:
            if not isinstance(entry.get(key), str):
                return False
    return True


def _record_shape_ok(record: dict) -> bool:
    """The v1 record shape. Unknown extra fields are tolerated."""
    if not _is_int(record.get("ucg")) or record.get("ucg") != 1:
        return False
    for key in ("kind", "epic", "gate_status", "verdict", "project"):
        if not isinstance(record.get(key), str):
            return False
    if not valid_run_id(record.get("run_id")):
        return False
    # The fingerprint names the record's folder, so one with no directory name
    # (".", "-", ":") can never be written or read back: wrong shape.
    if fingerprint_dir(record.get("fingerprint")) is None:
        return False
    for key in ("created_at_epoch", "deferred_count"):
        value = record.get(key)
        if not _is_int(value) or value < 0:
            return False
    valid_until = record.get("valid_until")
    if not isinstance(valid_until, dict):
        return False
    if not (_str_or_none(valid_until.get("sha")) and _str_or_none(valid_until.get("date"))):
        return False
    if not _list_of_str_dicts(record.get("signatures"), ("class", "path", "sig")):
        return False
    return _list_of_str_dicts(record.get("advisories"), ("sig", "recurred"))


def validate_record(record: object) -> str:
    """Validate one store record on its own: RECORD_OK, RECORD_INVALID or RECORD_CROSS_SCHEMA.

    Not an object, or a ``schema_version`` that is not an int of at least 1:
    invalid. A ``schema_version`` newer than ``UCG_SCHEMA_VERSION`` (read at call
    time, so a test can patch it): cross_schema, whatever its shape. Every
    version up to the current one is checked against the record shape and
    accepted when it fits, so a schema bump never discards earlier history.
    """
    if not isinstance(record, dict):
        return RECORD_INVALID
    version = record.get("schema_version")
    if not _is_int(version) or version < 1:
        return RECORD_INVALID
    if version > UCG_SCHEMA_VERSION:
        return RECORD_CROSS_SCHEMA
    return RECORD_OK if _record_shape_ok(record) else RECORD_INVALID


def classify_record(record: object, fingerprint: str | None) -> str:
    """validate_record(), then RECORD_FOREIGN when the raw fingerprint is not ``fingerprint``.

    The foreign check compares the fingerprint only, never ``project``, so
    worktrees and clones of one repo read each other's records.
    """
    status = validate_record(record)
    if status != RECORD_OK:
        return status
    if not isinstance(fingerprint, str) or record["fingerprint"] != fingerprint:
        return RECORD_FOREIGN
    return RECORD_OK


def _parse_run_file_bytes(raw: bytes) -> dict | None:
    """Decode one run file's bytes to its JSON object, or None (unparseable).

    A leading UTF-8 byte order mark (an editor such as Notepad can add one) is
    not part of the record.
    """
    if len(raw) > _MAX_RUN_FILE_BYTES:
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _read_run_file(path: Path) -> bytes:
    """Read at most _MAX_RUN_FILE_BYTES + 1 bytes. OSError propagates."""
    with open(path, "rb") as handle:
        return handle.read(_MAX_RUN_FILE_BYTES + 1)


# ---------------------------------------------------------------------------
# The immutable per-run writer
# ---------------------------------------------------------------------------


class WriteResult(NamedTuple):
    """Outcome of write_run_record(): ``status`` is a WRITE_* constant."""

    status: str
    path: Path


# os.link failures that mean "this filesystem does not support hard links", so
# the writer falls back to O_EXCL. Any other OSError propagates (the caller
# spills), and FileExistsError is the existing-target path, never a fallback.
_LINK_UNSUPPORTED_ERRNOS = frozenset(
    code
    for code in (
        getattr(errno, name, None)
        for name in ("EPERM", "EOPNOTSUPP", "ENOTSUP", "ENOSYS", "EXDEV", "EMLINK")
    )
    if code is not None
)
# ERROR_INVALID_FUNCTION, ERROR_NOT_SAME_DEVICE, ERROR_NOT_SUPPORTED (FAT32,
# exFAT and some network shares).
_LINK_UNSUPPORTED_WINERRORS = frozenset({1, 17, 50})


def _link_unsupported(exc: OSError) -> bool:
    if isinstance(exc, FileExistsError):
        return False
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return winerror in _LINK_UNSUPPORTED_WINERRORS
    return exc.errno in _LINK_UNSUPPORTED_ERRNOS


def _link_into_place(tmp_name: str, target: Path, data: bytes) -> None:
    """Create ``target`` from the temp file; FileExistsError when it exists.

    os.link is atomic and never replaces an existing name. Only when the
    filesystem has no hard links does it fall back to an O_EXCL create of the
    same bytes.
    """
    link = getattr(os, "link", None)
    if link is not None:
        try:
            link(tmp_name, str(target))
            return
        except OSError as exc:
            if not _link_unsupported(exc):
                raise
    _create_exclusive(target, data)


def _existing_target_status(target: Path, run_id: str, fingerprint: str) -> str:
    """Classify a run file that already exists, without touching it.

    WRITE_SKIPPED_EXISTING when it holds one JSON object with this run_id and
    this fingerprint that validate_record() does not reject as invalid;
    otherwise (a directory, unparseable bytes, another run or another repo)
    WRITE_FOREIGN_TARGET. An OSError reading it propagates (the caller spills).
    """
    if os.path.isdir(target):
        return WRITE_FOREIGN_TARGET
    existing = _parse_run_file_bytes(_read_run_file(target))
    if (
        existing is not None
        and existing.get("run_id") == run_id
        and existing.get("fingerprint") == fingerprint
        and validate_record(existing) != RECORD_INVALID
    ):
        return WRITE_SKIPPED_EXISTING
    return WRITE_FOREIGN_TARGET


def write_run_record(store_root: str | os.PathLike[str] | None, record: dict) -> WriteResult:
    """Create ``<store>/<fingerprint-dir>/runs/<run_id>.jsonl`` once, immutably.

    ``record`` must pass validate_record() as RECORD_OK (build it with
    store_record()); its ``run_id`` and raw ``fingerprint`` name the file. The
    store root is created through ensure_store_root() (with its ``.gitignore``).
    The record is written as one sorted-keys JSON line to a temp file in the runs
    directory (``.tmp`` suffix, outside the reader's ``*.jsonl``), fsynced, then
    os.link-ed into place; O_EXCL is used only where links are unsupported. An
    existing run file is never replaced, renamed or copied over. The temp is
    unlinked in a ``finally`` that ignores errors (a Windows scanner can hold it).

    Returns WriteResult(status, path) with status:
      - WRITE_WRITTEN           the file was created by this call
      - WRITE_SKIPPED_EXISTING  this run's record is already there (left byte-identical)
      - WRITE_FOREIGN_TARGET    something else occupies the path (left untouched;
                                the caller dead-letters with NOTE mem-target-foreign)
    Raises ValueError (unset store root, invalid record or run_id) before
    touching the filesystem, and OSError when the store cannot be written (the
    caller spills with WARN mem-write-deferred).
    """
    if store_root is None:
        raise ValueError(f"{STORE_KEY} is unset")
    status = validate_record(record)
    if status != RECORD_OK:
        raise ValueError(f"record is not writable: {status}")
    run_id = record["run_id"]
    fingerprint = record["fingerprint"]
    target = run_file_path(store_root, fingerprint, run_id)

    ensure_store_root(store_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(target):
        return WriteResult(_existing_target_status(target, run_id, fingerprint), target)

    data = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{run_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            _link_into_place(tmp_name, target, data)
        except FileExistsError:
            # Another writer landed it between the check and the link.
            return WriteResult(_existing_target_status(target, run_id, fingerprint), target)
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
    return WriteResult(WRITE_WRITTEN, target)


# ---------------------------------------------------------------------------
# The reader over a list of roots
# ---------------------------------------------------------------------------


class StoreItem(NamedTuple):
    """One run file seen by iter_store_records().

    ``status`` is a RECORD_* constant; ``record`` is the parsed object, or None
    when the file did not parse to a JSON object.
    """

    status: str
    record: dict | None
    path: Path


def iter_store_records(
    roots: Iterable[str | os.PathLike[str] | None], fingerprint: str | None
) -> Iterator[StoreItem]:
    """Yield every run file of this repo across ``roots``, validated one by one.

    For each root in order (None entries are skipped), reads
    ``<root>/<fingerprint-dir>/runs/`` in sorted name order. Names not ending in
    ``.jsonl`` are skipped, a file that raises OSError on read is skipped (one
    bad file never stops the read), and a root whose runs directory cannot be
    listed contributes nothing. Each yielded item carries RECORD_OK,
    RECORD_INVALID (unparseable or wrong shape), RECORD_CROSS_SCHEMA or
    RECORD_FOREIGN (classify_record). An OK record whose run_id an earlier OK
    record already had (the same run seen through two roots) is not yielded
    again. Yields nothing when ``fingerprint`` has no directory name.
    """
    name = fingerprint_dir(fingerprint)
    if name is None:
        return
    seen_run_ids: set[str] = set()
    for root in roots:
        if root is None:
            continue
        runs = Path(root) / name / STORE_RUNS_DIRNAME
        try:
            with os.scandir(runs) as entries:
                names = sorted(entry.name for entry in entries)
        except OSError:
            continue
        for file_name in names:
            if not file_name.endswith(".jsonl"):
                continue
            path = runs / file_name
            try:
                raw = _read_run_file(path)
            except OSError:
                continue
            record = _parse_run_file_bytes(raw)
            status = RECORD_INVALID if record is None else classify_record(record, fingerprint)
            if status == RECORD_OK:
                if record["run_id"] in seen_run_ids:
                    continue
                seen_run_ids.add(record["run_id"])
            yield StoreItem(status, record, path)


def read_store(
    roots: Iterable[str | os.PathLike[str] | None], fingerprint: str | None
) -> tuple[list[dict], dict[str, int]]:
    """Collect iter_store_records(): (OK records in read order, dropped counts).

    The counts dict always has the keys ``invalid``, ``cross_schema`` and
    ``foreign``. Only the OK records may feed recurrence or horizon immunity.
    """
    records: list[dict] = []
    dropped = {RECORD_INVALID: 0, RECORD_CROSS_SCHEMA: 0, RECORD_FOREIGN: 0}
    for item in iter_store_records(roots, fingerprint):
        if item.status == RECORD_OK:
            records.append(item.record)
        else:
            dropped[item.status] += 1
    return records, dropped


# ---------------------------------------------------------------------------
# Health: the latch's write probe
# ---------------------------------------------------------------------------


def _probe_link(src: str, dst: str) -> None:
    """Hard-link the probe file as write_run_record() links a run file.

    Returns when the link works or links are unsupported (the writer then
    falls back to O_EXCL, which the probe's mkstemp already exercised). Any
    other OSError propagates: the writer would raise it too, and spill every
    write while the latch read green.
    """
    link = getattr(os, "link", None)
    if link is None:
        return
    try:
        link(src, dst)
    except OSError as exc:
        if not _link_unsupported(exc):
            raise


def probe_store(
    store_root: str | os.PathLike[str] | None, fingerprint: str | None
) -> tuple[bool, str | None]:
    """Check the store can be created and written, as the latch requires.

    Returns (True, None) when ``<store>/<fingerprint-dir>/runs`` exists or was
    created (the root through ensure_store_root(), so it gets its
    ``.gitignore``), a mkstemp file could be created there, and it could be
    hard-linked the way the writer links a run file (or links are unsupported,
    so the writer falls back to O_EXCL). Both probe files carry a ``.tmp``
    suffix, outside the reader's ``*.jsonl``, and are then unlinked; a failure
    to unlink one (a Windows scanner holding it) is ignored. Otherwise
    (False, reason) with reason ``"store-unset"``, ``"no-fingerprint"``
    (nothing is created then) or ``"store-unwritable: <error>"``. Never raises.
    """
    if store_root is None:
        return False, "store-unset"
    if fingerprint_dir(fingerprint) is None:
        return False, "no-fingerprint"
    runs = runs_dir(store_root, fingerprint)
    try:
        ensure_store_root(store_root)
        runs.mkdir(parents=True, exist_ok=True)
        fd, probe_name = tempfile.mkstemp(dir=str(runs), prefix=".probe-", suffix=".tmp")
        os.close(fd)
    except OSError as exc:
        return False, f"store-unwritable: {exc}"
    link_name = probe_name[: -len(".tmp")] + ".link.tmp"
    try:
        _probe_link(probe_name, link_name)
    except OSError as exc:
        return False, f"store-unwritable: {exc}"
    finally:
        for name in (link_name, probe_name):
            try:
                os.unlink(name)
            except OSError:
                pass
    return True, None


# ---------------------------------------------------------------------------
# Legacy outbox migration
# ---------------------------------------------------------------------------

_LEGACY_KEYS = ("text", "title", "project")


def is_legacy_payload(payload: object) -> bool:
    """True for a claude-mem era outbox payload: ``{text,title,project}`` with the marker.

    An object with those keys but no ``[ucg-payload:v1]`` marker in ``text`` is
    not legacy by this definition (the caller decides what to do with it).
    """
    if not isinstance(payload, dict):
        return False
    if any(key not in payload for key in _LEGACY_KEYS):
        return False
    return carries_marker(payload)


def legacy_payload_to_record(payload: object) -> dict | None:
    """Convert a legacy outbox payload into a store record, or None (unconvertible).

    The embedded payload comes from extract_payload(); ``created_at_epoch`` is
    its own build time, ``valid_until.date`` (not the drain time); ``project`` is
    the wrapper's ``project`` ("" when not a string). None when the payload is
    not legacy, the fenced JSON does not parse, the date does not parse, or the
    result does not pass validate_record() as RECORD_OK (for example a missing
    or invalid run_id, or no fingerprint): the caller dead-letters it with
    NOTE mem-legacy-unconvertible.
    """
    if not is_legacy_payload(payload):
        return None
    inner = extract_payload(payload)
    if inner is None:
        return None
    valid_until = inner.get("valid_until")
    date = valid_until.get("date") if isinstance(valid_until, dict) else None
    created_at_epoch = iso_to_epoch_ms(date)
    if created_at_epoch is None:
        return None
    project = payload.get("project")
    record = store_record(
        inner,
        created_at_epoch=created_at_epoch,
        project=project if isinstance(project, str) else "",
    )
    return record if validate_record(record) == RECORD_OK else None


# ---------------------------------------------------------------------------
# Latch v2 (the v1 helpers above are unchanged)
# ---------------------------------------------------------------------------

LATCH_VERSION_V2 = 2


def build_latch_v2(
    *,
    run_id: str,
    recall: str,
    store: str | os.PathLike[str] | None,
    store_ok: bool,
    fingerprint: str | None,
    created_at: str | None = None,
) -> dict:
    """The v2 latch object, exact keys, ready for write_state().

    {"latch_version":2, "run_id":str, "backend":"jsonl", "store_ok":bool,
     "recall":"on"|"off", "store":str|null, "fingerprint":str|null,
     "created_at":ISO}

    ``store`` is the resolved absolute store root (resolve_store_root), or None
    when unset; latch_view() reads it back as written. ValueError for an
    invalid run_id or a recall value other than "on" / "off".
    """
    if not valid_run_id(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    if recall not in ("on", "off"):
        raise ValueError(f"recall must be 'on' or 'off', not {recall!r}")
    return {
        "latch_version": LATCH_VERSION_V2,
        "run_id": run_id,
        "backend": STORE_BACKEND,
        "store_ok": bool(store_ok),
        "recall": recall,
        "store": None if store is None else os.fspath(store),
        "fingerprint": fingerprint,
        "created_at": created_at or utc_now_iso(),
    }


class LatchMeasure(NamedTuple):
    """Outcome of measure_latch_v2().

    ``state`` is the build_latch_v2() object to write; ``notes`` holds the lines
    to print (``NOTE recall-store-unset ...`` only); ``reason`` is None when the
    latch is green, else ``"recall-off"``, ``"store-unset"``,
    ``"no-fingerprint"`` or ``"store-unwritable: <error>"``.
    """

    state: dict
    notes: list[str]
    reason: str | None


def measure_latch_v2(
    *,
    run_id: str,
    recall: str,
    store_value: object,
    cwd: str | os.PathLike[str] | None = None,
    project_root: str | os.PathLike[str] | None = None,
) -> LatchMeasure:
    """Measure everything latch v2 certifies, with no MCP call and no probe input.

    Validates run_id and recall first (ValueError, nothing created). Takes the
    fingerprint of ``cwd`` (default "."), resolves ``store_value`` with
    resolve_store_root(project_root=...), and only when ``recall`` is "on"
    probes the store (probe_store, which creates the root with its
    ``.gitignore``). ``store_ok`` is True only for "on" with a set, writable
    store and a fingerprint. "on" with an unset store adds the
    ``NOTE recall-store-unset`` line naming the key; "off" never probes and
    never notes, but still carries the resolved ``store`` so the guard gates by
    path like any other present latch.
    """
    if not valid_run_id(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    if recall not in ("on", "off"):
        raise ValueError(f"recall must be 'on' or 'off', not {recall!r}")
    base = cwd if cwd is not None else "."
    fingerprint = repo_fingerprint(base).get("value")
    store = resolve_store_root(store_value, project_root=project_root)
    notes: list[str] = []
    store_ok = False
    if recall != "on":
        reason: str | None = "recall-off"
    elif store is None:
        reason = "store-unset"
        notes.append(store_unset_note("recall is off for this run"))
    else:
        store_ok, reason = probe_store(store, fingerprint)
    state = build_latch_v2(
        run_id=run_id,
        recall=recall,
        store=store,
        store_ok=store_ok,
        fingerprint=fingerprint,
    )
    return LatchMeasure(state, notes, reason)


def latch_version(state: object) -> int | None:
    """The latch's ``latch_version`` when it is a real int, else None."""
    if not isinstance(state, dict):
        return None
    version = state.get("latch_version")
    return version if _is_int(version) else None


def _latch_store_path(value: object) -> Path | None:
    """A latch's ``store`` field as an absolute path, or None.

    The latch already holds the resolved root (resolve_store_root), so the
    value is taken as written: no token check, since a resolved root may hold
    a ``$`` or braces of its own (a project root named ``my$proj``). Only a
    leading ``~`` (a hand-written latch) is expanded. Anything that is not then
    an absolute path, a string with a NUL, or a non-string, reads as no store.
    """
    if not isinstance(value, str) or not value or "\0" in value:
        return None
    try:
        path = Path(value).expanduser() if value.startswith("~") else Path(value)
        if not path.is_absolute():
            return None
        return Path(os.path.abspath(path))
    except (RuntimeError, ValueError):
        return None


def latch_view(state: object) -> dict:
    """How a latch object reads, for preflight reporting and guard parity.

    Returns {"latch_version": int|None, "store_ok": bool, "store": str|None,
    "run_id": object, "recall": object}:
      - ``store`` is the latch's ``store`` as an absolute path for a v2 latch
        (taken as written, a leading ``~`` expanded), and None for any other
        version or when the value is not an absolute path;
      - ``store_ok`` is the derived colour: True only for a v2 latch whose
        ``store_ok`` is literally true, ``backend`` is "jsonl", ``recall`` is
        "on" and ``store`` is an absolute path. A v1 latch, any other version, a
        non-object and None read as red.
    The PreToolUse guard keeps its own reader and must read a latch the same way.
    """
    if not isinstance(state, dict):
        return {
            "latch_version": None,
            "store_ok": False,
            "store": None,
            "run_id": None,
            "recall": None,
        }
    version = latch_version(state)
    store: Path | None = None
    green = False
    if version == LATCH_VERSION_V2:
        store = _latch_store_path(state.get("store"))
        green = (
            state.get("store_ok") is True
            and state.get("backend") == STORE_BACKEND
            and state.get("recall") == "on"
            and store is not None
        )
    return {
        "latch_version": version,
        "store_ok": green,
        "store": None if store is None else str(store),
        "run_id": state.get("run_id"),
        "recall": state.get("recall"),
    }

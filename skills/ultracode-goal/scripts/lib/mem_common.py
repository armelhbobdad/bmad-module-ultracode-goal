#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Shared primitives for ultracode-goal Cross-Session Recall (D12).

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

The state file is the machine latch the hook reads to decide whether claude-mem
MCP calls are permitted during a run. Its schema (v1) is documented at
write_state() and shared verbatim with the hook's gating predicate.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

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

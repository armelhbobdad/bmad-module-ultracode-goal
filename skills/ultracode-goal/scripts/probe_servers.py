#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Report which of the URLs a test runner may reuse already have a server.

A runner that attaches to a server already answering at its URL, instead of
starting one (Playwright's `webServer` with `reuseExistingServer`), runs a gate
worktree's tests against the tree that server was started from, usually the
main tree (references/gate.md, "A server the gate set reuses does not follow
the commit"). The gate checks those URLs before its first run in the worktree
and again after the rebuild. `ss`, `lsof` and `curl` are not on the run's
allowlist; this script runs under `uv run`, which is.

What it checks. For each `--url`, a TCP connection to every address the URL's
host resolves to, at the URL's port (80 or 443 when the URL names none): the
URL answers when any address accepts. `localhost` resolves to `::1` as well as
`127.0.0.1`, and a dev server may listen on only one of them. A connection is
all it makes: it sends no request, so a server that answers it with an error
page still answers here.

Which folder. For a URL that answers, the folder the listening process runs
from, read from /proc on Linux when the process is the caller's own; `null`
on another system, or when /proc does not say. A server whose folder has since
been removed (one started from a gate worktree the rebuild replaced) reads
with the ` (deleted)` suffix Linux gives it.

Usage:
    uv run probe_servers.py --url <url> [--url <url> ...]

Output: JSON on stdout, `{"answering": [{"url", "port", "cwd"}], "free":
[<url>, ...]}`. Exit 0 when no URL answers, 1 when any does, and 2 when a URL
has no host, or a port that is not a number from 0 to 65535.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
# The `st` column of /proc/net/tcp for a listening socket.
_LISTEN = "0A"
_TIMEOUT = 1.0


def _host_and_port(url: str) -> tuple[str, int]:
    parts = urlsplit(url if "://" in url else f"http://{url}")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"{url}: {exc}") from exc
    if not parts.hostname:
        raise ValueError(f"{url}: no host")
    return parts.hostname, port if port is not None else _DEFAULT_PORTS.get(parts.scheme, 80)


def _answers(host: str, port: int) -> bool:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, kind, proto, _, address in infos:
        try:
            with socket.socket(family, kind, proto) as sock:
                sock.settimeout(_TIMEOUT)
                if sock.connect_ex(address) == 0:
                    return True
        except OSError:
            # An address family this system cannot open (IPv6 switched off).
            continue
    return False


def _listening_inodes(port: int, proc: Path) -> set[str]:
    inodes: set[str] = set()
    for table in ("tcp", "tcp6"):
        try:
            lines = (proc / "net" / table).read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) > 9 and fields[3] == _LISTEN and int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(fields[9])
    return inodes


def _holds(pid: Path, sockets: set[str]) -> bool:
    """Whether the process holds one of `sockets` among its open files."""
    for fd in (pid / "fd").iterdir():
        try:
            if os.readlink(fd) in sockets:
                return True
        except OSError:
            # Closed since the listing.
            continue
    return False


def _cwd_of_listener(port: int, proc: Path = Path("/proc")) -> str | None:
    """The folder the process listening on `port` runs from, or None."""
    sockets = {f"socket:[{inode}]" for inode in _listening_inodes(port, proc)}
    if not sockets:
        return None
    for pid in (entry for entry in proc.iterdir() if entry.name.isdigit()):
        try:
            if _holds(pid, sockets):
                return os.readlink(pid / "cwd")
        except OSError:
            # Another user's process, or one that has exited.
            continue
    return None


def probe(urls: list[str]) -> dict:
    answering, free = [], []
    for url in urls:
        host, port = _host_and_port(url)
        if _answers(host, port):
            answering.append({"url": url, "port": port, "cwd": _cwd_of_listener(port)})
        else:
            free.append(url)
    return {"answering": answering, "free": free}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report which URLs already have a server answering.")
    parser.add_argument("--url", action="append", required=True, help="A URL a runner may reuse; repeatable.")
    args = parser.parse_args(argv)
    try:
        result = probe(args.url)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["answering"] else 0


if __name__ == "__main__":
    sys.exit(main())

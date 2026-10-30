#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Report which of the URLs a test runner may reuse already have a server.

A runner that attaches to a server already answering at its URL, instead of
starting one (Playwright's `webServer` with `reuseExistingServer`), runs a
gate worktree's tests against the tree that server was started from, usually
the main tree (references/gate.md, "A server the gate set reuses does not
follow the commit"). The gate checks those URLs before its first run in the
worktree and again after the rebuild. Automate checks them before and after
each mutation table it runs, since a server one of the worktree's own runs
starts can outlive that run (a launcher such as turbo runs it in a process
group of its own), and with reuse on every later run reuses it while it serves
the files as they were when it started. When a scratch runner config gives the
worktree's runs a server of their own, the gate also checks that config's URLs
before each assessor runs under it, since a server an earlier run left up can
hold the port. `ss`, `lsof` and `curl` are not on the run's allowlist; this
script runs under `uv run`, which is.

What it checks. For each `--url`, a TCP connection to every address the URL's
host resolves to, at the URL's port (80 or 443 when the URL names none): the
URL answers when any address accepts. `localhost` resolves to `::1` as well as
`127.0.0.1`, and a dev server may listen on only one of them. A connection is
all it makes: it sends no request, so a server that answers it with an error
page still answers here.

Which folder. For a URL that answers, the folder the process listening where
the connection landed runs from, read from /proc on Linux when the process is
the caller's own. Two servers can listen on one port, a stale worktree's on
`::1` beside the main tree's on `127.0.0.1`, say, so only a socket that could
have taken that connection counts: one at the address it reached, or at that
family's wildcard address (`0.0.0.0`, or `::`, which takes IPv4 connections
too). The folder is `null` on another system, when /proc does not say, or
when those sockets are not all held from one folder by processes it can read,
since it cannot tell then which of them took the connection. A server whose
folder has since been removed (one started from a gate worktree the rebuild
replaced) reads with the ` (deleted)` suffix Linux gives it.

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
import struct
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


def _reached(host: str, port: int) -> tuple[int, bytes] | None:
    """The family and packed address of the first of the host's addresses that
    accepts a connection at `port`, or None when none does."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return None
    for family, kind, proto, _, address in infos:
        try:
            with socket.socket(family, kind, proto) as sock:
                sock.settimeout(_TIMEOUT)
                if sock.connect_ex(address) == 0:
                    # An IPv6 address can carry a zone (`fe80::1%lo`), which is no part of it.
                    return family, socket.inet_pton(family, address[0].split("%", 1)[0])
        except OSError:
            # An address family this system cannot open (IPv6 switched off).
            continue
    return None


def _proc_address(hex_address: str) -> bytes:
    """An address as /proc/net/tcp or tcp6 prints it, packed as the socket
    module packs one: the kernel prints each 32-bit word of it as a number in
    the host's own byte order."""
    return b"".join(
        struct.pack("=I", int(hex_address[start : start + 8], 16)) for start in range(0, len(hex_address), 8)
    )


def _could_take(local: bytes, reached: tuple[int, bytes]) -> bool:
    """Whether a socket listening at `local` could have taken a connection to
    `reached`: one at that address, or at its family's wildcard, which for
    IPv4 includes `::` and the IPv4-mapped form of the address."""
    family, address = reached
    if len(local) == 4:
        return family == socket.AF_INET and local in (address, bytes(4))
    if family == socket.AF_INET6:
        return local in (address, bytes(16))
    return local in (bytes(10) + b"\xff\xff" + address, bytes(16))


def _listening_inodes(port: int, proc: Path, reached: tuple[int, bytes] | None = None) -> set[str]:
    """The inodes of the sockets listening on `port`: every one, or with
    `reached`, the ones that could have taken a connection to it."""
    inodes: set[str] = set()
    for table in ("tcp", "tcp6"):
        try:
            lines = (proc / "net" / table).read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) <= 9 or fields[3] != _LISTEN:
                continue
            local, _, local_port = fields[1].rpartition(":")
            if int(local_port, 16) == port and (reached is None or _could_take(_proc_address(local), reached)):
                inodes.add(fields[9])
    return inodes


def _held(pid: Path, sockets: set[str]) -> set[str]:
    """Which of `sockets` the process holds among its open files."""
    held: set[str] = set()
    for fd in (pid / "fd").iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            # Closed since the listing.
            continue
        if target in sockets:
            held.add(target)
    return held


def _cwd_of_listener(port: int, proc: Path = Path("/proc"), reached: tuple[int, bytes] | None = None) -> str | None:
    """The folder the process listening on `port` runs from (with `reached`,
    the one listening where a connection to it lands), or None unless every
    socket that could have taken it is held from one folder by a process this
    one can read."""
    sockets = {f"socket:[{inode}]" for inode in _listening_inodes(port, proc, reached)}
    if not sockets:
        return None
    held: set[str] = set()
    cwds: set[str] = set()
    for pid in (entry for entry in proc.iterdir() if entry.name.isdigit()):
        try:
            found = _held(pid, sockets)
            if found:
                cwds.add(os.readlink(pid / "cwd"))
                held |= found
        except OSError:
            # Another user's process, or one that has exited.
            continue
    # A second folder, or a socket with no holder it can read, leaves it unable to say which one answered.
    return next(iter(cwds)) if len(cwds) == 1 and held == sockets else None


def probe(urls: list[str]) -> dict:
    answering, free = [], []
    for url in urls:
        host, port = _host_and_port(url)
        reached = _reached(host, port)
        if reached is None:
            free.append(url)
        else:
            answering.append({"url": url, "port": port, "cwd": _cwd_of_listener(port, reached=reached)})
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

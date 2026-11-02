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
have taken that connection counts, in the order Linux looks for one: at the
address it reached (for IPv4, an IPv4 socket before an IPv4-mapped one), then
at that family's wildcard address (`0.0.0.0`, `::`), then, for IPv4, at `::`,
which takes IPv4 connections unless it sets IPV6_V6ONLY. /proc does not show
that flag, but a `::` socket that takes IPv4 connections shares a port with an
IPv4 socket only under SO_REUSEPORT, and then the IPv4 one at the address or
at `0.0.0.0` takes the connection, so `::` counts for IPv4 only when no
socket listens at the address, its IPv4-mapped form or `0.0.0.0`. A `::`
socket set IPV6_V6ONLY still counts then, though the connection reached no
socket /proc lists (a NAT rule sent it elsewhere, say). A connection to the
unspecified address (`0.0.0.0`, `::`) reaches the family's loopback address,
and one to an IPv4-mapped address (`::ffff:127.0.0.1`) the IPv4 address it
maps, as Linux routes them, so the probe reads it there. The folder is `null`
on another system, when the
address the connection reached is not one of this host's own (a container's,
say), since no socket here took it, when /proc does not say, or when those
sockets are not all held from one folder by processes it can read, since it
cannot tell then which of them took the connection. It tells an address of this host's
own by listening on it, at a port the system picks, and taking a connection it
makes there, and it does so only when /proc lists a socket that could have
taken the URL's connection and the answer counts: for a folder /proc names,
or with the stop flags below. So on a system with no /proc it opens no
listening socket. A server whose folder has since been removed (one started
from a gate worktree the rebuild replaced) reads with the ` (deleted)` suffix
Linux gives it.

Stopping a server the run started. A server the run's own runs started can
stay up after them: Execute's step 5 sweep runs the full suite, browser tests
included, in the main tree right before the gate, and a server its runner
started through a launcher answers there at the gate's first check, so the
gate's worktree runs would reuse it (#190). Under a scratch runner config
whose only start command is a launcher, each run leaves one up on the config's
port (#186). The gate runs every check above with `--stop-since <file>` and
`--root`, and once more before each gate cycle's verdict, so those servers
neither serve the worktree's runs nor pile up over an Epic. With them the
probe stops each server that answers when what /proc shows of it matches a
server the run left up, and leaves every other one up. A server counts as the
run's only when every process in its process group belongs to this user, has
no controlling terminal and started after `<file>` was last written (the gate
passes the story's baseline marker, which Execute writes before any of the
story's work and a resume keeps, so a server an earlier session started still
counts); when the process that led its session no longer runs; when no
other process that still runs in that session started before `<file>` was
written or is the parent of one of the group's processes (a watcher or
supervisor, which can start it again: watchexec and cargo-watch run their
server in a group of their own and start it in a new one when a file
changes, as the run's own edits make them do); and when the folder it runs
from is inside a `--root`. A runner starts its server's command in a session
of its own, which has no controlling terminal, and ends that command when it
ends, so a server a launcher ran in a group of its own lives on without the
process that led its session. A server started from a terminal has a
controlling terminal while that terminal's shell runs, and the shell leads
its session. Measured with turbo 2.11.9 and Claude Code 2.1.316 on Linux: the
server turbo left up had no terminal, its session's first process was gone,
its parent was `systemd --user`, which leads a session of its own and adopted
it, and every process of its session had started during the sweep; a server
started from a terminal had one. These are signs, not proof: a server started
with `nohup ... &` from a terminal that is closed afterwards, or in the
background by a command that has since exited, with no terminal, reads as the
run's too when it started after the marker, as did everything else that still
runs in its session, and runs from inside a root. So does one that a watcher
started that way restarts after the marker, when the watcher started after
the marker too and runs in the server's process group, or when it starts the
server through a command that then exits, so that it is no longer the
server's parent, and either started after the marker or had that command give
the server a session of its own. The marker can be days old, since a resume
keeps it. The probe never stops its own process group, or one that holds a
process that started it, and it stops nothing for a URL whose
connection no process here took: /proc lists no socket here that could have
taken it, or it reached an address that is not one of this host's own (a
container's, say). It sends the group SIGTERM, then SIGKILL to what is left
after a few seconds, and checks the URL again: a URL that still answers is
read as above, once more, until a bounded number of stops. A process still
running after the SIGKILL (one that left its group on the SIGTERM, say)
leaves the server stopped only in part: the probe names the processes that
exited and the ones still running, and signals those no more, for this URL
or another. It reads the URL once more: it leaves the URL up when one of
those processes holds a socket that could have taken the connection, and
otherwise reads it as above, so a server that answers it now, at another of
its host's addresses say, gets a verdict of its own. A URL read before a
later URL's stop is read again after it, since that stop can end the server
that answered it. On a system with no /proc to read it stops nothing.

Usage:
    uv run probe_servers.py --url <url> [--url <url> ...]
    uv run probe_servers.py --url <url> [--url <url> ...] --stop-since <file> --root <dir> [--root <dir> ...]

Output: JSON on stdout, `{"answering": [{"url", "port", "cwd"}], "free":
[<url>, ...]}`. With `--stop-since`, `answering` and `free` say what answers
once it has stopped what it could, and two keys are added: `stopped`, each
server it stopped, in whole or in part (`{"url", "port", "cwd",
"process_groups", "pids", "partial", "running"}`: the groups it signalled, the
processes that exited, whether any of its processes still ran after the
SIGKILL, and the ones that did), and `left`, each URL that still answers with
the reason it left that server up (`{"url", "port", "cwd", "reason"}`). After
a stop that leaves some of a server's processes running, the server is listed
under `stopped` when some of its processes exited or the ones still running
no longer answer its URL, and a URL they still answer is listed under `left`,
its reason, which any other URL that reaches them gives too, naming the
groups signalled and the processes still running. It reads the
groups' processes again right before each signal and right after it, and
names each one it finds in them, so a process it signals goes unnamed only
when it joins a group after the read before a signal and is out of that
group, reaped or moved to another, by the read after it. Exit 0 when no
URL answers, 1 when any does, and 2 when a URL has no host, a host the lookup
cannot encode (an empty label, or one over 63 characters), or a port that is
not a number from 0 to 65535, or when the `--stop-since` file cannot be read:
every URL and the file are read before anything is stopped, so a refusal
stops nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import struct
import sys
import time
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
# The `st` column of /proc/net/tcp for a listening socket.
_LISTEN = "0A"
_TIMEOUT = 1.0
_PROC = Path("/proc")
# A process's start time is read to the second (/proc/stat's boot time is a
# whole second), so one that started within this long after the marker was
# written is not counted as started after it.
_CLOCK_SLACK = 2.0
# How long a process group has to exit after SIGTERM, and again after SIGKILL.
_GRACE = 5.0
# How many times one URL's server is stopped before the probe leaves it up:
# something that starts it again is not this run's to fight.
_STOPS = 3
# The state letters of a process that has exited (a zombie nobody has reaped yet, or a dead one).
_EXITED = ("Z", "X")


class _Address(NamedTuple):
    """The address a connection landed at: its family, the address packed as
    the socket module packs one, and for an IPv6 address the scope id of the
    link it is on (the `eth0` of `fe80::1%eth0`, as the link's index), 0 when
    it names none."""

    family: int
    packed: bytes
    scope: int = 0


# The first twelve bytes of an IPv4-mapped IPv6 address (`::ffff:127.0.0.1`), and each family's loopback address.
_MAPPED = bytes(10) + b"\xff\xff"
_LOOPBACK = {socket.AF_INET: b"\x7f\x00\x00\x01", socket.AF_INET6: bytes(15) + b"\x01"}


def _landing(family: int, packed: bytes, scope: int) -> _Address:
    """Where a connection to the address lands, as Linux routes one: one to an
    IPv4-mapped IPv6 address is made over IPv4, to the address it maps, and
    one to the unspecified address (`0.0.0.0`, `::`) to the family's loopback
    address."""
    if family == socket.AF_INET6 and packed.startswith(_MAPPED):
        family, packed, scope = socket.AF_INET, packed[len(_MAPPED) :], 0
    if not any(packed):
        packed = _LOOPBACK[family]
    return _Address(family, packed, scope)


def _host_and_port(url: str) -> tuple[str, int]:
    parts = urlsplit(url if "://" in url else f"http://{url}")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"{url}: {exc}") from exc
    if not parts.hostname:
        raise ValueError(f"{url}: no host")
    try:
        # socket.getaddrinfo encodes the host with this codec before it resolves it, and raises for one it cannot
        # encode (an empty label, or one over 63 characters): found only there, the host would be refused after an
        # earlier URL's server was stopped.
        parts.hostname.encode("idna")
    except UnicodeError as exc:
        raise ValueError(f"{url}: {exc}") from exc
    return parts.hostname, port if port is not None else _DEFAULT_PORTS.get(parts.scheme, 80)


def _reached(host: str, port: int) -> _Address | None:
    """Where a connection lands at the first of the host's addresses that
    accepts one at `port`, or None when none does."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        # No address for it (socket.gaierror, an OSError), or a host the lookup cannot encode, which
        # `_host_and_port` refuses first: an error raised here would end the probe after a stop it then never reports.
        return None
    for family, kind, proto, _, address in infos:
        try:
            with socket.socket(family, kind, proto) as sock:
                sock.settimeout(_TIMEOUT)
                if sock.connect_ex(address) == 0:
                    # An IPv6 address can carry a zone (`fe80::1%eth0`), which is no part of it: the lookup gives its
                    # link as the scope id, which a socket bound to a link-local address needs.
                    scope = address[3] if family == socket.AF_INET6 else 0
                    return _landing(family, socket.inet_pton(family, address[0].split("%", 1)[0]), scope)
        except OSError:
            # An address family this system cannot open (IPv6 switched off).
            continue
    return None


def _lands_here(reached: _Address) -> bool:
    """Whether a connection to the reached address lands on this host: a
    socket bound to it here takes one made to it. Only an address of this
    host's own can be bound, unless Linux's `ip_nonlocal_bind` lets any one be,
    so the bound socket must also take the connection. A link-local IPv6
    address is bound on its link, as Linux requires."""
    family, host = reached.family, socket.inet_ntop(reached.family, reached.packed)
    try:
        with socket.socket(family, socket.SOCK_STREAM) as server, socket.socket(family, socket.SOCK_STREAM) as client:
            server.bind((host, 0, 0, reached.scope) if family == socket.AF_INET6 else (host, 0))
            server.listen(1)
            server.settimeout(_TIMEOUT)
            client.settimeout(_TIMEOUT)
            client.connect(server.getsockname())
            # Taken by the bound socket: a connection to another host's address leaves this one. The peer it names
            # is not compared with the client's address, which a NAT rule can rewrite (Docker's MASQUERADE does for a
            # connection to its bridge's address).
            server.accept()[0].close()
            return True
    except OSError:
        # Another host's address (EADDRNOTAVAIL), a link-local one with no link (EINVAL), or one a connection to never
        # reached the socket bound to it.
        return False


def _proc_address(hex_address: str) -> bytes:
    """An address as /proc/net/tcp or tcp6 prints it, packed as the socket
    module packs one: the kernel prints each 32-bit word of it as a number in
    the host's own byte order."""
    return b"".join(
        struct.pack("=I", int(hex_address[start : start + 8], 16)) for start in range(0, len(hex_address), 8)
    )


def _lookup_order(reached: _Address) -> tuple[tuple[bytes, ...], ...]:
    """The addresses a socket listens at that Linux looks for, in turn, to give
    a connection to `reached`: the address itself, then its family's wildcard,
    and at each an IPv4 socket before an IPv6 one (an IPv4-mapped address). So
    for IPv4 `127.0.0.1`, `::ffff:127.0.0.1`, `0.0.0.0`, then `::` with
    `::ffff:0.0.0.0`, and for IPv6 `::1`, then `::`."""
    if reached.family == socket.AF_INET6:
        return (reached.packed,), (bytes(16),)
    return (reached.packed,), (_MAPPED + reached.packed,), (bytes(4),), (bytes(16), _MAPPED + bytes(4))


def _listening_inodes(port: int, proc: Path, reached: _Address | None = None) -> set[str]:
    """The inodes of the sockets listening on `port`: every one, or with
    `reached`, the ones that could have taken a connection to it: those at the
    first addresses in `_lookup_order` that any socket listens at. A `::`
    socket set IPV6_V6ONLY takes no IPv4 connection, and /proc does not show
    the flag, but one that takes them shares its port with an IPv4 socket only
    under SO_REUSEPORT, and then an IPv4 socket at the address or `0.0.0.0`
    comes first either way: so a `::` socket counts for IPv4 only when no
    socket listens at the address, its IPv4-mapped form or `0.0.0.0`. One set
    IPV6_V6ONLY still counts then, though it took no part: the connection
    reached no socket /proc lists (a NAT rule sent it elsewhere, say)."""
    listening: list[tuple[bytes, str]] = []
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
            if int(local_port, 16) == port:
                listening.append((_proc_address(local), fields[9]))
    if reached is None:
        return {inode for _, inode in listening}
    for addresses in _lookup_order(reached):
        found = {inode for local, inode in listening if local in addresses}
        if found:
            return found
    return set()


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


def _holders(port: int, proc: Path, reached: _Address | None = None) -> tuple[dict[int, str], bool]:
    """The processes holding a socket listening on `port` (with `reached`,
    one that could have taken a connection to it), each with the folder it
    runs from, and whether every such socket has a holder this one can read."""
    sockets = {f"socket:[{inode}]" for inode in _listening_inodes(port, proc, reached)}
    if not sockets:
        return {}, False
    held: set[str] = set()
    holders: dict[int, str] = {}
    for pid in (entry for entry in proc.iterdir() if entry.name.isdigit()):
        try:
            found = _held(pid, sockets)
            if found:
                holders[int(pid.name)] = os.readlink(pid / "cwd")
                held |= found
        except OSError:
            # Another user's process, or one that has exited.
            continue
    return holders, held == sockets


def _cwd_of_listener(port: int, proc: Path = Path("/proc"), reached: _Address | None = None) -> str | None:
    """The folder the process listening on `port` runs from (with `reached`,
    the one listening where a connection to it lands), or None unless every
    socket that could have taken it is held from one folder by a process this
    one can read."""
    holders, complete = _holders(port, proc, reached)
    cwds = set(holders.values())
    # A second folder, or a socket with no holder it can read, leaves it unable to say which one answered.
    return next(iter(cwds)) if len(cwds) == 1 and complete else None


# --- stopping a server the run started -------------------------------------------


class _Process(NamedTuple):
    pid: int
    state: str
    ppid: int
    pgrp: int
    session: int
    tty: int
    # Clock ticks after boot.
    start: int


class _Caller(NamedTuple):
    """The process that runs the probe: whose processes it may stop, and which it must not."""

    uid: int
    pgrp: int
    session: int
    # This process and every process that started it.
    lineage: frozenset[int]


class _Stop(NamedTuple):
    """What `--stop-since` and `--root` ask for."""

    marker: Path
    since: float
    roots: tuple[str, ...]


def _process(proc: Path, pid: int) -> _Process | None:
    """A process as /proc/<pid>/stat gives it, or None once it has gone. The
    name in parentheses can hold spaces and parentheses, so the fields are
    read after its last `)`."""
    try:
        raw = (proc / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
        fields = raw[raw.rindex(")") + 2 :].split()
        return _Process(pid, fields[0], int(fields[1]), int(fields[2]), int(fields[3]), int(fields[4]), int(fields[19]))
    except (OSError, ValueError, IndexError):
        return None


def _running(proc: Path, pid: int) -> _Process | None:
    found = _process(proc, pid)
    return None if found is None or found.state in _EXITED else found


def _uid(proc: Path, pid: int) -> int | None:
    """The process's user, when its real and effective users are one."""
    try:
        for line in (proc / str(pid) / "status").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Uid:"):
                ids = line.split()[1:3]
                return int(ids[0]) if len(ids) == 2 and ids[0] == ids[1] else None
    except (OSError, ValueError):
        return None
    return None


def _boot_time(proc: Path) -> float | None:
    try:
        for line in (proc / "stat").read_text(encoding="ascii").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except (OSError, ValueError):
        return None
    return None


def _processes(proc: Path) -> list[_Process]:
    found = (_running(proc, int(entry.name)) for entry in proc.iterdir() if entry.name.isdigit())
    return sorted((process for process in found if process is not None), key=lambda process: process.pid)


def _caller(proc: Path) -> _Caller:
    lineage, pid = set(), os.getpid()
    while pid > 0 and pid not in lineage:
        lineage.add(pid)
        parent = _process(proc, pid)
        pid = parent.ppid if parent is not None else 0
    return _Caller(os.getuid(), os.getpgrp(), os.getsid(0), frozenset(lineage))


def _inside(cwd: str, roots: tuple[str, ...]) -> bool:
    # A folder removed since the process started from it (an old gate worktree) reads with this suffix.
    path = cwd.removesuffix(" (deleted)")
    for root in roots:
        try:
            # commonpath gives the system's own separators, so the root is compared in that form.
            if os.path.commonpath([path, root]) == os.path.normpath(root):
                return True
        except ValueError:
            # Paths on two drives, or one relative and one absolute.
            continue
    return False


def _not_the_runs(
    proc: Path, port: int, reached: _Address, stop: _Stop, caller: _Caller, ticks: float
) -> tuple[str | None, list[_Process]]:
    """Why the server listening where a connection to `reached` lands is not
    one the run can be shown to have started, or None and the processes of
    its process groups when it is. Past its own groups, it reads the session
    they are in: a process that still runs there outside them as the parent
    of one of their processes is a watcher or supervisor that started it (a
    process in another session is a parent only by adopting it, as `systemd
    --user` adopts the server a runner's launcher left up), and one that
    started there before the marker is one a run could not have started."""
    holders, complete = _holders(port, proc, reached)
    if not complete:
        return (
            "a socket that could have taken the connection has no holder this probe can read (another user's "
            "server, or /proc does not say)"
        ), []
    outside = sorted(cwd for cwd in holders.values() if not _inside(cwd, stop.roots))
    if outside:
        return f"it runs from {outside[0]}, outside every --root", []
    boot = _boot_time(proc)
    if boot is None:
        return "/proc gives no boot time to read a process's start time against", []
    processes = _processes(proc)
    if {process.pid for process in processes if process.pid in holders} != set(holders):
        return "a process that holds its socket has exited", []
    groups = {process.pgrp for process in processes if process.pid in holders}
    members = [process for process in processes if process.pgrp in groups]
    for group in sorted(groups):
        if group <= 1 or group == caller.pgrp:
            return f"process group {group} is this probe's own", []
    for member in members:
        if member.pid in caller.lineage or member.session == caller.session:
            return f"process {member.pid} in its process group is this probe, one that started it or in its session", []
        if _uid(proc, member.pid) != caller.uid:
            return f"process {member.pid} in its process group is not this user's", []
        if member.tty != 0:
            return f"process {member.pid} in its process group has a controlling terminal", []
        if boot + member.start / ticks < stop.since + _CLOCK_SLACK:
            return f"process {member.pid} in its process group started before {stop.marker} was written", []
    sessions = {member.session for member in members}
    for session in sorted(sessions):
        leader = _running(proc, session)
        if leader is not None and leader.session == session:
            return f"process {session}, which leads its session, still runs", []
    # A watcher (watchexec, cargo-watch) runs its server in a process group of its own and starts it again in a new
    # one when a file changes, as the run's own edits make it do: the new group then passes every check above.
    outside = {
        process.pid: process for process in processes if process.session in sessions and process.pgrp not in groups
    }
    for member in members:
        parent = outside.get(member.ppid)
        if parent is not None and parent.session == member.session:
            return (
                f"process {parent.pid}, outside its process group, still runs in its session as the parent of process "
                f"{member.pid}: a watcher or supervisor that can start it again"
            ), []
    for process in outside.values():
        if boot + process.start / ticks < stop.since + _CLOCK_SLACK:
            return f"process {process.pid} in its session started before {stop.marker} was written", []
    return None, members


def _in_groups(proc: Path, groups: set[int]) -> list[_Process]:
    """Every process /proc lists in one of `groups`, one that has exited and
    is not reaped yet included."""
    try:
        pids = [int(entry.name) for entry in proc.iterdir() if entry.name.isdigit()]
    except OSError:
        return []
    found = (_process(proc, pid) for pid in pids)
    return [process for process in found if process is not None and process.pgrp in groups]


def _stop_groups(proc: Path, members: list[_Process], kill=None) -> tuple[list[_Process], list[_Process]]:
    """SIGTERM to each process group of `members`, then SIGKILL to what is
    left of it after a grace period. Gives every process it found in those
    groups, and which of them still run after both signals, none when every
    one has exited. A signal reaches each process in the group when it is
    sent, a worker forked since `members` were read included, so it reads the
    groups again right before each signal and right after it, and adds each
    process it finds in them. A process is known by its start time as well as
    its pid, so a pid the system has given to a new process since does not
    count as one still running."""
    kill = kill or os.killpg
    groups = {member.pgrp for member in members}
    found = list(members)

    def alive() -> list[_Process]:
        left = []
        for member in found:
            now = _running(proc, member.pid)
            if now is not None and now.start == member.start:
                left.append(member)
        return left

    def join(targets: set[int]) -> None:
        known = {(process.pid, process.start) for process in found}
        found.extend(process for process in _in_groups(proc, targets) if (process.pid, process.start) not in known)

    for sig in (signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)):
        # Only a group one of its processes still runs in: the id of a group none is left in can name a new one.
        targets = {member.pgrp for member in alive()} & groups
        join(targets)
        for group in sorted(targets):
            try:
                kill(group, sig)
            except OSError:
                # Gone since (ProcessLookupError), or one it may not signal: what is left is reported below.
                continue
        # One forked between that read and the signal, which the signal reached, shows here until it is reaped.
        join(targets)
        deadline = time.monotonic() + _GRACE
        while alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not alive():
            return found, []
    # A process that left its group after the SIGTERM (or one SIGKILL cannot end yet), which the SIGKILL missed.
    return found, alive()


def _reads_processes(proc: Path) -> bool:
    return sys.platform.startswith("linux") and (proc / "stat").is_file() and hasattr(os, "killpg")


def _clock_ticks() -> float:
    """The clock ticks per second /proc/<pid>/stat counts a start time in."""
    return float(os.sysconf("SC_CLK_TCK"))


def _read(url: str, port: int, reached: _Address, proc: Path, readable: bool) -> tuple[dict, bool | None]:
    """The URL's entry, its folder the one of the process listening where the
    connection landed, and whether the address it reached is one of this
    host's own: None when the probe had no cause to ask. It asks by listening
    on that address (`_lands_here`), which a firewall on macOS or Windows can
    ask the user about, so only where the answer counts: for a folder /proc
    names, and, where it may stop a server (`readable`), when /proc lists a
    socket here that could have taken the connection."""
    cwd = _cwd_of_listener(port, proc, reached)
    if cwd is None and not (readable and _listening_inodes(port, proc, reached)):
        return {"url": url, "port": port, "cwd": None}, None
    # A connection that reached another host's address (a container's, say) was taken by no socket here, though one
    # here listens on every address at that port.
    here = _lands_here(reached)
    return {"url": url, "port": port, "cwd": cwd if here else None}, here


def _numbered(noun: str, numbers: list[int]) -> str:
    """`pid 41`, or `pids 40, 41`."""
    return f"{noun}{'s' if len(numbers) > 1 else ''} {', '.join(map(str, numbers))}"


def probe(urls: list[str], stop: _Stop | None = None, proc: Path | None = None, kill=None) -> dict:
    proc = proc or _PROC
    readable = stop is not None and _reads_processes(proc)
    caller = _caller(proc) if readable else None
    ticks = _clock_ticks() if readable else 0.0
    # Every URL is read, its host encoded as the lookup encodes it, before the first stop: a refusal prints no JSON,
    # so a server stopped before it would be named nowhere.
    targets = [(url, *_host_and_port(url)) for url in urls]
    stopped: list[dict] = []
    # How many stops the reads of each URL made.
    stops = [0] * len(targets)
    # Each process a stop left running, by its pid and start time, with the reason a server it is in is left up: the
    # probe signals it no more.
    spent: dict[tuple[int, int], str] = {}
    # The URLs that processes a stop left running still answer: no later stop can free them, since none signals those.
    kept: set[int] = set()

    def verdict(index: int) -> tuple[dict, str | None] | None:
        """The URL's entry and, with the stop flags, the reason the server that
        answers it is left up, once the probe has stopped what it could; None
        once nothing answers it."""
        url, host, port = targets[index]
        while True:
            reached = _reached(host, port)
            if reached is None:
                return None
            entry, here = _read(url, port, reached, proc, readable)
            if stop is None:
                return entry, None
            members: list[_Process] = []
            if not readable:
                reason = "this system has no Linux /proc to read the server's processes from, so it stops nothing"
            elif here is None:
                reason = (
                    "/proc lists no socket here that could have taken the connection at "
                    f"{socket.inet_ntop(reached.family, reached.packed)}"
                )
            elif not here:
                reason = (
                    f"it answered at {socket.inet_ntop(reached.family, reached.packed)}, which is not an address of "
                    "this host, so no process here took the connection"
                )
            elif stops[index] == _STOPS:
                reason = f"it answered again after {_STOPS} stops, so something keeps starting it"
            else:
                reason, members = _not_the_runs(proc, port, reached, stop, caller, ticks)
                if reason is None:
                    keys = ((member.pid, member.start) for member in members)
                    reason = next((spent[key] for key in keys if key in spent), None)
            if reason is not None:
                return entry, reason
            stops[index] += 1
            groups = sorted({member.pgrp for member in members})
            found, running = _stop_groups(proc, members, kill)
            still = sorted(process.pid for process in running)
            exited = sorted(process.pid for process in found if process not in running)
            record = {**entry, "process_groups": groups, "pids": exited, "partial": bool(running), "running": still}
            if running:
                # Stopped only in part: the processes still running are signalled no more, by this URL or another.
                # The URL is read once more. When one of them holds a socket that could have taken the connection,
                # the URL is left up, and the server is listed under `stopped` only when a process of it exited, so
                # the reason names the groups signalled and the processes still running. Otherwise the server is
                # listed under `stopped`, and the URL read as before: another server that answers it now, at another
                # of its host's addresses say, gets a verdict of its own.
                reason = (
                    f"{'some of its' if exited else 'its'} processes still ran after SIGTERM and SIGKILL to "
                    f"{_numbered('process group', groups)} ({_numbered('pid', still)})"
                )
                spent.update(((process.pid, process.start), reason) for process in running)
                after = _reached(host, port)
                if after is not None:
                    entry, here = _read(url, port, after, proc, readable)
                    if here and set(still) & set(_holders(port, proc, after)[0]):
                        if exited:
                            stopped.append(record)
                        kept.add(index)
                        return entry, reason
            stopped.append(record)

    verdicts: list[tuple[dict, str | None] | None] = [None] * len(targets)
    # How many stops had been made when each URL was last read.
    seen = [0] * len(targets)
    pending = list(range(len(targets)))
    while pending:
        for index in pending:
            verdicts[index] = verdict(index)
            seen[index] = sum(stops)
        # A later URL's stop can end the server that answered a URL read before it (one it reached at another address,
        # say), so that URL is read again, until a round of reads stops nothing: each URL's stops are bounded.
        pending = [
            index
            for index, found in enumerate(verdicts)
            if found is not None and index not in kept and seen[index] < sum(stops)
        ]
    answering, free, left = [], [], []
    for (url, _, _), found in zip(targets, verdicts):
        if found is None:
            free.append(url)
            continue
        entry, reason = found
        answering.append(entry)
        if reason is not None:
            left.append({**entry, "reason": reason})
    result = {"answering": answering, "free": free}
    if stop is not None:
        result.update(stopped=stopped, left=left)
    return result


def _stop_request(marker: str | None, roots: list[str] | None) -> _Stop | None:
    if marker is None:
        return None
    try:
        since = Path(marker).stat().st_mtime
    except OSError as exc:
        raise ValueError(f"--stop-since {marker}: {exc.strerror or exc}") from exc
    return _Stop(Path(marker), since, tuple(os.path.realpath(root) for root in roots or ()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report which URLs already have a server answering.")
    parser.add_argument("--url", action="append", required=True, help="A URL a runner may reuse; repeatable.")
    parser.add_argument(
        "--stop-since",
        metavar="FILE",
        help="Stop each answering server that reads as one the run left up after FILE was last written.",
    )
    parser.add_argument(
        "--root",
        action="append",
        metavar="DIR",
        help="With --stop-since: a folder a server it stops may run from; repeatable.",
    )
    args = parser.parse_args(argv)
    if (args.stop_since is None) != (args.root is None):
        parser.error("--stop-since and --root go together")
    try:
        result = probe(args.url, _stop_request(args.stop_since, args.root))
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["answering"] else 0


if __name__ == "__main__":
    sys.exit(main())

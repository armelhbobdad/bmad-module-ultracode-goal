#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
"""probe_servers.py: which URLs a runner may reuse already answer (issue #182).

A Playwright config with `reuseExistingServer` attached a gate worktree's runs
to a dev server started from the main tree, so the worktree's browser runs
measured the main tree's source, and a mutation written into the worktree
never reached them. The last test here reproduces that with mutate_check.py:
a mutant the server never loads reads GREEN.

Stdlib + pytest only.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import importlib.util
import json
import os
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe_servers = _load("probe_servers")


def _listener(family: int = socket.AF_INET, host: str = "127.0.0.1") -> socket.socket:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.bind((host, 0))
    sock.listen()
    return sock


def _free_port() -> int:
    with _listener() as sock:
        return sock.getsockname()[1]


@functools.cache
def _ipv6_loopback() -> bool:
    """Whether a connection to `::1` reaches a socket listening there. IPv6
    can be built in (`socket.has_ipv6`) and `::` bound while `::1` takes no
    connection: a container with IPv6 switched off on its loopback device
    (`disable_ipv6`) has it so."""
    if not socket.has_ipv6:
        return False
    try:
        with _listener(socket.AF_INET6, "::1") as server, socket.socket(socket.AF_INET6) as client:
            client.settimeout(probe_servers._TIMEOUT)
            client.connect(server.getsockname()[:2])
            return True
    except OSError:
        return False


def test_a_url_with_a_listener_answers_and_names_its_folder(capsys):
    with _listener() as sock:
        port = sock.getsockname()[1]
        code = probe_servers.main(["--url", f"http://127.0.0.1:{port}"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert [entry["port"] for entry in out["answering"]] == [port]
    assert out["free"] == []
    if sys.platform.startswith("linux"):
        # The listener is this process, so its folder is this process's.
        assert out["answering"][0]["cwd"] == os.getcwd()


def test_a_url_with_no_listener_is_free(capsys):
    port = _free_port()
    assert probe_servers.main(["--url", f"http://localhost:{port}"]) == 0
    assert json.loads(capsys.readouterr().out) == {"answering": [], "free": [f"http://localhost:{port}"]}


def test_each_url_is_reported_answering_or_free(capsys):
    """`--url` repeats, and an answering URL does not hide a free one."""
    free = _free_port()
    with _listener() as sock:
        port = sock.getsockname()[1]
        code = probe_servers.main(["--url", f"http://127.0.0.1:{port}", "--url", f"127.0.0.1:{free}"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert [entry["url"] for entry in out["answering"]] == [f"http://127.0.0.1:{port}"]
    assert out["free"] == [f"127.0.0.1:{free}"]


@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6")
def test_localhost_answers_when_the_server_listens_on_ipv6_only(capsys):
    """The main tree's vite server in #182 listened on [::1]:3001 alone."""
    try:
        sock = _listener(socket.AF_INET6, "::1")
    except OSError:
        pytest.skip("::1 cannot be bound here")
    with sock:
        port = sock.getsockname()[1]
        if not any(info[0] == socket.AF_INET6 for info in socket.getaddrinfo("localhost", port)):
            pytest.skip("localhost does not resolve to ::1 here")
        assert probe_servers.main(["--url", f"http://localhost:{port}"]) == 1
    assert json.loads(capsys.readouterr().out)["answering"][0]["port"] == port


# Hosts the lookup cannot encode (Python encodes a host with the `idna` codec before it resolves it): an empty
# label, at either end or inside, and a label over 63 characters.
_UNENCODABLE_HOSTS = ["http://localhost..:3000", "http://.localhost:3000", "http://" + "a" * 64 + ".test"]


@pytest.mark.parametrize(
    "url", ["http://", "http://localhost:notaport", "http://localhost:70000", *_UNENCODABLE_HOSTS]
)
def test_a_url_with_no_host_or_a_bad_port_is_refused(url, capsys):
    assert probe_servers.main(["--url", url]) == 2
    assert f"REFUSED: {url}: " in capsys.readouterr().err


def test_a_host_with_a_trailing_dot_is_no_refusal(capsys):
    """The twin: `localhost.` is a full name, not an empty label."""
    port = _free_port()
    assert probe_servers.main(["--url", f"http://localhost.:{port}"]) in (0, 1)
    assert "REFUSED" not in capsys.readouterr().err


def test_a_host_the_lookup_cannot_encode_reads_as_free():
    """`_reached` raises nothing: an error it let through would end the probe after an earlier URL's stop."""
    assert probe_servers._reached("a" * 64 + ".test", 80) is None


# The checks gate.md's fourth caveat makes with this script. Its docstring said
# the gate checks before the first run and after the rebuild, and otherwise only
# under a scratch config; but a server one of the worktree's own runs starts
# through turbo outlives that run, and with reuse on every later row of a
# mutation table ran through it, so automate checks after each table too.
_DOC_CHECKS = (
    "The gate checks those URLs before its first run in the worktree and again after the rebuild.",
    "Automate checks them before and after each mutation table it runs, since a server one of the worktree's own "
    "runs starts can outlive that run",
)


def _doc_check_gaps(doc: str) -> list[str]:
    flat = " ".join(doc.split())
    return [phrase for phrase in _DOC_CHECKS if phrase not in flat]


def test_the_docstring_names_each_check_the_gate_makes():
    assert _doc_check_gaps(probe_servers.__doc__) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("before and after each mutation table", "before each mutation table"),
        ("Automate checks them before and after each mutation table it runs, since a server one of the worktree's "
         "own runs starts can outlive that run", "A server one of the worktree's own runs starts can outlive that run"),
    ],
)
def test_docstring_predicate_rejects_a_check_left_out(old, new):
    doc = " ".join(probe_servers.__doc__.split())
    mutant = doc.replace(old, new)
    assert mutant != doc, "the mutant must actually change the text"
    assert _doc_check_gaps(mutant)


def test_the_folder_is_read_only_from_a_listening_socket(tmp_path):
    """A /proc laid out as Linux lays it out: the process holding the
    listening socket on the port names the folder, and one holding a socket
    that only connects on that port does not."""
    proc = tmp_path / "proc"
    (proc / "net").mkdir(parents=True)
    header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    (proc / "net" / "tcp").write_text(
        header
        # 127.0.0.1:3001 connected (01) to a client, inode 111.
        + "   0: 0100007F:0BB9 0100007F:D431 01 00000000:00000000 00:00000000 00000000  1000        0 111\n"
        # 127.0.0.1:3001 listening (0A), inode 222.
        + "   1: 0100007F:0BB9 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 222\n",
        encoding="ascii",
    )
    for pid, inode, cwd in (("10", "111", "/elsewhere"), ("20", "222", "/main/tree")):
        (proc / pid / "fd").mkdir(parents=True)
        try:
            os.symlink(f"socket:[{inode}]", proc / pid / "fd" / "3")
            os.symlink(cwd, proc / pid / "cwd")
        except OSError:
            pytest.skip("these symlinks cannot be made here")
    assert probe_servers._cwd_of_listener(3001, proc) == os.readlink(proc / "20" / "cwd")
    assert probe_servers._cwd_of_listener(3002, proc) is None


def _proc_hex(family: int, address: str) -> str:
    """An address as /proc/net/tcp or tcp6 prints it on this host: each 32-bit
    word as a number in the host's own byte order."""
    packed = socket.inet_pton(family, address)
    return "".join(f"{struct.unpack('=I', packed[at : at + 4])[0]:08X}" for at in range(0, len(packed), 4))


def _fake_proc(tmp_path: Path, listeners: list[tuple[int, str, int, str, str | None]]) -> Path:
    """A /proc whose tcp and tcp6 tables list each (family, address, port,
    inode, holder folder) as a listening socket, each held by a process of
    its own that runs from that folder, or by none when the folder is None."""
    proc = tmp_path / "proc"
    (proc / "net").mkdir(parents=True)
    header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    tables = {"tcp": [header], "tcp6": [header]}
    for pid, (family, address, port, inode, cwd) in enumerate(listeners, start=10):
        table = tables["tcp" if family == socket.AF_INET else "tcp6"]
        remote = "0" * len(_proc_hex(family, address))
        table.append(
            f"   {len(table) - 1}: {_proc_hex(family, address)}:{port:04X} {remote}:0000 0A 00000000:00000000 "
            f"00:00000000 00000000  1000        0 {inode}\n"
        )
        if cwd is None:
            continue
        (proc / str(pid) / "fd").mkdir(parents=True)
        try:
            os.symlink(f"socket:[{inode}]", proc / str(pid) / "fd" / "3")
            os.symlink(cwd, proc / str(pid) / "cwd")
        except OSError:
            pytest.skip("these symlinks cannot be made here")
    for name, rows in tables.items():
        (proc / "net" / name).write_text("".join(rows), encoding="ascii")
    return proc


_V4 = probe_servers._Address(socket.AF_INET, socket.inet_pton(socket.AF_INET, "127.0.0.1"))
_V6 = probe_servers._Address(socket.AF_INET6, socket.inet_pton(socket.AF_INET6, "::1"))


def test_the_folder_is_the_one_of_the_socket_the_connection_reached(tmp_path):
    """Two servers on one port, one per address family: a stale gate
    worktree's on `::1` beside the main tree's on `127.0.0.1`. Each address
    names its own server's folder; the folder of whichever process came first
    in /proc was named for both, so the probe could vouch for the main tree
    while the stale worktree's server answered (#182)."""
    proc = _fake_proc(
        tmp_path,
        [
            (socket.AF_INET6, "::1", 3001, "333", "/stale/worktree"),
            (socket.AF_INET, "127.0.0.1", 3001, "222", "/main/tree"),
        ],
    )
    assert probe_servers._cwd_of_listener(3001, proc, _V4) == "/main/tree"
    assert probe_servers._cwd_of_listener(3001, proc, _V6) == "/stale/worktree"
    # With no address to match, two folders on the port are no answer at all.
    assert probe_servers._cwd_of_listener(3001, proc) is None


@pytest.mark.parametrize(
    ("listeners", "reached", "expected"),
    [
        # `::` takes IPv4 connections too, unless a socket sets IPV6_V6ONLY.
        ([(socket.AF_INET6, "::", 3002, "444", "/dual")], _V4, "/dual"),
        ([(socket.AF_INET6, "::ffff:127.0.0.1", 3002, "444", "/mapped")], _V4, "/mapped"),
        ([(socket.AF_INET, "0.0.0.0", 3002, "444", "/any")], _V4, "/any"),
        # 0.0.0.0 takes no IPv6 connection, and 127.0.0.2 none for 127.0.0.1.
        ([(socket.AF_INET, "0.0.0.0", 3002, "444", "/any")], _V6, None),
        ([(socket.AF_INET, "127.0.0.2", 3002, "444", "/other")], _V4, None),
        # Two sockets that could both have taken it (SO_REUSEPORT), from two folders.
        ([(socket.AF_INET, "127.0.0.1", 3002, "444", "/a"), (socket.AF_INET, "127.0.0.1", 3002, "555", "/b")],
         _V4, None),
        ([(socket.AF_INET, "0.0.0.0", 3002, "444", "/a"), (socket.AF_INET, "0.0.0.0", 3002, "555", "/b")],
         _V4, None),
        # The same, from one folder: a server's forked workers.
        ([(socket.AF_INET, "127.0.0.1", 3002, "444", "/a"), (socket.AF_INET, "127.0.0.1", 3002, "555", "/a")],
         _V4, "/a"),
        # A socket no readable process holds (another user's server) could be the one that answered.
        ([(socket.AF_INET, "127.0.0.1", 3002, "444", "/a"), (socket.AF_INET, "127.0.0.1", 3002, "555", None)],
         _V4, None),
        ([(socket.AF_INET6, "::", 3002, "444", "/a"), (socket.AF_INET6, "::", 3002, "555", None)], _V4, None),
    ],
    ids=["v6-wildcard", "v4-mapped", "v4-wildcard", "v4-wildcard-for-v6", "other-address", "two-folders",
         "two-folders-at-the-wildcard", "one-folder", "unread-holder", "unread-holder-at-the-v6-wildcard"],
)
def test_a_folder_is_named_only_when_every_socket_that_could_answer_shares_it(tmp_path, listeners, reached, expected):
    proc = _fake_proc(tmp_path, listeners)
    assert probe_servers._cwd_of_listener(3002, proc, reached) == expected


# Which socket Linux gives a connection to, measured on Linux 6.12 with real sockets, with
# net.ipv6.bindv6only 0 and 1, SO_REUSEPORT and SO_INCOMING_CPU: a socket at the address itself before any
# wildcard, an IPv4 socket before an IPv6 one at the same address (an IPv4-mapped one), so for IPv4
# `127.0.0.1`, then `::ffff:127.0.0.1`, then `0.0.0.0`, then `::` (or `::ffff:0.0.0.0`), and for IPv6
# `::1`, then `::`. A `::` socket set IPV6_V6ONLY (nginx's `listen [::]`, Go's `tcp6`, asyncio's per-family
# sockets, or any `::` socket under bindv6only 1) takes no IPv4 connection, and one that takes them shares
# its port with an IPv4 socket only under SO_REUSEPORT, so an IPv4 socket at the address or 0.0.0.0 takes
# the connection first either way. /proc does not show IPV6_V6ONLY: counting every `::` socket for IPv4,
# the probe named no folder for, stopped, or left up with its reason, a `::` server that never took the
# connection.
_ORDER = [
    # (listeners as (host, folder), reached, the folder of the socket Linux gives the connection to)
    ([("127.0.0.1", "/v4"), ("::", "/v6only")], _V4, "/v4"),
    ([("0.0.0.0", "/v4"), ("::", "/v6only")], _V4, "/v4"),
    ([("127.0.0.1", "/exact"), ("0.0.0.0", "/any")], _V4, "/exact"),
    ([("::ffff:127.0.0.1", "/mapped"), ("0.0.0.0", "/any")], _V4, "/mapped"),
    ([("127.0.0.1", "/v4"), ("::ffff:127.0.0.1", "/mapped")], _V4, "/v4"),
    ([("0.0.0.0", "/v4"), ("::ffff:0.0.0.0", "/mapped")], _V4, "/v4"),
    # The IPv4 socket at another address, which takes no connection to 127.0.0.1: `::` does (SO_REUSEPORT).
    ([("127.0.0.2", "/other"), ("::", "/dual")], _V4, "/dual"),
    ([("::1", "/exact"), ("::", "/any")], _V6, "/exact"),
    ([("0.0.0.0", "/v4"), ("::", "/v6")], _V6, "/v6"),
]
_ORDER_IDS = ["v4-beside-v6only-wildcard", "v4-wildcard-beside-v6only-wildcard", "v4-beside-v4-wildcard",
              "v4-mapped-beside-v4-wildcard", "v4-beside-v4-mapped", "v4-wildcard-beside-v4-mapped-wildcard",
              "v6-wildcard-beside-v4-at-another-address", "v6-beside-v6-wildcard", "v6-wildcard-for-v6"]


@pytest.mark.parametrize(("listeners", "reached", "expected"), _ORDER, ids=_ORDER_IDS)
def test_the_folder_is_the_one_of_the_socket_linux_gives_the_connection_to(tmp_path, listeners, reached, expected):
    proc = _fake_proc(
        tmp_path,
        [
            (socket.AF_INET6 if ":" in host else socket.AF_INET, host, 3002, str(400 + at), folder)
            for at, (host, folder) in enumerate(listeners)
        ],
    )
    assert probe_servers._cwd_of_listener(3002, proc, reached) == expected


def _bound(host: str, port: int, v6only: bool) -> socket.socket:
    """A socket listening at `host` and `port`, with SO_REUSEPORT so that it can share the port as `_ORDER` lays
    one out, and for IPv6 with IPV6_V6ONLY as `v6only` says, whatever the system's default."""
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        if ":" in host:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, int(v6only))
        sock.bind((host, port))
        sock.listen()
    except (OSError, AttributeError) as exc:
        sock.close()
        pytest.skip(f"{host}:{port} cannot be bound here: {exc}")
    return sock


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or not socket.has_ipv6,
    reason="Linux's lookup order, with sockets read from its /proc",
)
@pytest.mark.parametrize(("listeners", "reached", "expected"), _ORDER, ids=_ORDER_IDS)
def test_the_sockets_counted_are_the_ones_linux_gives_the_connection_to(listeners, reached, expected):
    """The same layouts on real sockets: the probe counts exactly the socket
    Linux gave its connection to, which this test reads from the listener that
    has it waiting to be accepted."""
    if reached.family == socket.AF_INET6 and not _ipv6_loopback():
        pytest.skip("no connection to ::1 reaches a socket here")
    port = _free_port()
    with contextlib.ExitStack() as stack:
        socks = {
            folder: stack.enter_context(_bound(host, port, v6only=folder == "/v6only"))
            for host, folder in listeners
        }
        target = socket.inet_ntop(reached.family, reached.packed)
        landed = probe_servers._reached(target, port)
        assert landed == reached
        ready, _, _ = select.select(list(socks.values()), [], [], 2)
        assert [folder for folder, sock in socks.items() if sock in ready] == [expected]
        counted = probe_servers._listening_inodes(port, Path("/proc"), landed)
        assert counted == {str(os.fstat(socks[expected].fileno()).st_ino)}


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or not socket.has_ipv6,
    reason="Linux's lookup order, with sockets read from its /proc",
)
def test_a_v6only_socket_beside_the_v4_mapped_wildcard_still_counts_as_the_docstring_says():
    """A layout the docstring names, measured: a `::` socket set IPV6_V6ONLY
    shares a port with one at `::ffff:0.0.0.0` (with or without SO_REUSEPORT),
    which takes every IPv4 connection, and both sit at the last address in
    Linux's order. /proc shows no IPV6_V6ONLY, so the probe counts both."""
    port = _free_port()
    with contextlib.ExitStack() as stack:
        socks = {
            folder: stack.enter_context(_bound(host, port, v6only=folder == "/v6only"))
            for host, folder in [("::", "/v6only"), ("::ffff:0.0.0.0", "/mapped")]
        }
        landed = probe_servers._reached("127.0.0.1", port)
        assert landed == _V4
        ready, _, _ = select.select(list(socks.values()), [], [], 2)
        assert [folder for folder, sock in socks.items() if sock in ready] == ["/mapped"]
        counted = probe_servers._listening_inodes(port, Path("/proc"), landed)
        assert counted == {str(os.fstat(sock.fileno()).st_ino) for sock in socks.values()}


# What the docstring says of the cases its reads cannot tell apart. It named one layout in which a socket that took
# no part in the connection still counts (a `::` socket set IPV6_V6ONLY, with no socket at the address, its mapped
# form or `0.0.0.0`), though a review measured three on real sockets: that one, the same socket beside the one at `::`
# or `::ffff:0.0.0.0` that took the connection, and a socket bound to a device the connection did not arrive on. And
# it said a watcher that starts its server through a command that then exits is no longer the server's parent, though
# a subreaper adopts it back: from another session, once that command gave the server one, which counts for nothing.
_DOC_LIMITS = (
    "a socket that took no part in the connection still counts in three layouts:",
    "a `::` socket set IPV6_V6ONLY counts for IPv4 when no socket listens at those addresses",
    "and when the socket that took it listens at `::` too (without the flag, under SO_REUSEPORT) or at "
    "`::ffff:0.0.0.0`;",
    "a socket bound to a device with SO_BINDTODEVICE, which takes only a connection that arrives on that device, "
    "counts at its address in place of, or beside, the one that took it.",
    "the probe can stop a server that took no part, though only one that reads as the run's itself,",
    "starts the server through a command that then exits and is not its parent afterwards (a subreaper adopts it "
    "back), or, whenever the watcher started, when that command gave the server a session of its own, since a parent "
    "in another session, a subreaper included, counts for nothing.",
)
_DOC_NEVER_SAYS = ("so that it is no longer the server's parent",)


def _doc_limit_gaps(doc: str) -> list[str]:
    flat = " ".join(doc.split())
    return [phrase for phrase in _DOC_LIMITS if phrase not in flat] + [
        phrase for phrase in _DOC_NEVER_SAYS if phrase in flat
    ]


def test_the_docstring_names_what_its_reads_cannot_tell_apart():
    assert _doc_limit_gaps(probe_servers.__doc__) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        # The first wording: the one layout of a connection no listed socket took.
        ("still counts in three layouts:", "still counts in one layout:"),
        (" and when the socket that took it listens at `::` too (without the flag, under SO_REUSEPORT) or at "
         "`::ffff:0.0.0.0`;", ";"),
        ("; and a socket bound to a device with SO_BINDTODEVICE, which takes only a connection that arrives on that "
         "device, counts at its address in place of, or beside, the one that took it.", "."),
        (", though only one that reads as the run's itself,", ","),
        # The first watcher wording, which a subreaper that adopts its server back from another session breaks.
        ("exits and is not its parent afterwards (a subreaper adopts it back), or,",
         "exits, so that it is no longer the server's parent, or,"),
        (", since a parent in another session, a subreaper included, counts for nothing.", "."),
    ],
)
def test_doc_limit_predicate_rejects_a_case_left_unsaid(old, new):
    doc = " ".join(probe_servers.__doc__.split())
    mutant = doc.replace(old, new)
    assert mutant != doc, "the mutant must actually change the text"
    assert _doc_limit_gaps(mutant)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the folder is read from Linux's /proc")
@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6")
def test_two_real_servers_on_one_port_are_told_apart(tmp_path, capsys):
    """The same on real sockets: this process listens on 127.0.0.1, a process
    started from another folder on [::1] at the same port, and each URL names
    the folder of the server that answered it."""
    stale = tmp_path / "stale-worktree"
    stale.mkdir()
    with _listener() as sock:
        port = sock.getsockname()[1]
        other = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import socket, sys\n"
                "s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)\n"
                "s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)\n"
                f"s.bind(('::1', {port}))\n"
                "s.listen()\n"
                "print('ready', flush=True)\n"
                "sys.stdin.read()\n",
            ],
            cwd=stale,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            if other.stdout.readline().strip() != "ready":
                pytest.skip(f"[::1]:{port} cannot be bound here: {other.stderr.read()}")
            code = probe_servers.main(["--url", f"http://127.0.0.1:{port}", "--url", f"http://[::1]:{port}"])
        finally:
            other.stdin.close()
            other.wait(timeout=10)
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert [entry["cwd"] for entry in out["answering"]] == [os.getcwd(), str(stale)]


# --- a server the run itself left up (#190, #186) ------------------------------
#
# Measured with turbo 2.11.9: Playwright starts its `webServer` command in a
# session of its own (Node's `detached`) and its teardown kills that command's
# process group. turbo runs the task (`bun run dev`, the server under it) in a
# process group of its own in that session, so the server outlives the run,
# reparented to `systemd --user`, with no controlling terminal, while the
# command that led its session is gone, and turbo's strict env mode drops the
# variables Claude Code sets, so no variable marks it as the run's. Execute's
# step 5 sweep left one so in the main tree right before the gate (#190), and
# each run under a scratch runner config whose only start command is a
# launcher leaves one on its port (#186). These tests make that server with
# real processes: a start command that leads a session of its own runs the
# server through a launcher in a process group of its own, and is then killed
# with its group, as Playwright's teardown kills it.

def _serving(host: str, v6only: bool = False) -> str:
    """A server that listens on `host`, at the port its first argument gives,
    with IPV6_V6ONLY set when `v6only` says so."""
    return (
        "import socket, sys, time\n"
        f"s = socket.socket(socket.{'AF_INET6' if ':' in host else 'AF_INET'})\n"
        + ("s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)\n" if v6only else "")
        + f"s.bind(({host!r}, int(sys.argv[1])))\n"
        "s.listen()\n"
        "print('ready', flush=True)\n"
        "time.sleep(600)\n"
    )


_SERVE = _serving("127.0.0.1")
_LAUNCHER = (
    "import subprocess, sys\n"
    "server = subprocess.Popen(\n"
    "    [sys.executable, '-c', sys.argv[1], sys.argv[2]], process_group=0, stdin=subprocess.DEVNULL,\n"
    "    stdout=subprocess.PIPE, text=True,\n"
    ")\n"
    "print(server.pid, server.stdout.readline().strip(), flush=True)\n"
    "server.wait()\n"
)


def _gone(pid: int) -> bool:
    """Whether the process has exited: no /proc entry, or a zombie nobody has reaped yet."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return True
    return stat[stat.rindex(")") + 2 :].split()[0] in ("Z", "X")


@contextlib.contextmanager
def _left_up(cwd: Path, port: int, serve: str = _SERVE):
    """A server a runner left up, from `cwd`: its pid, which is its process
    group's, then each pid `serve` prints after `ready`."""
    start = subprocess.Popen(
        [sys.executable, "-c", _LAUNCHER, serve, str(port)],
        cwd=cwd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=True,
    )
    pids: list[int] = []
    try:
        line = start.stdout.readline().split()
        if len(line) < 2 or line[1] != "ready":
            pytest.skip(f"no server started on 127.0.0.1:{port}")
        pids = [int(line[0]), *(int(pid) for pid in line[2:])]
        # The runner's teardown: the start command's process group, with SIGKILL.
        os.killpg(start.pid, signal.SIGKILL)
        start.wait(timeout=10)
        yield tuple(pids)
    finally:
        if start.poll() is None:
            os.killpg(start.pid, signal.SIGKILL)
            start.wait(timeout=10)
        if pids and not _gone(pids[0]):
            os.killpg(pids[0], signal.SIGKILL)
        for pid in pids[1:]:
            if not _gone(pid):
                os.kill(pid, signal.SIGKILL)


def _baseline(tmp_path: Path, age: float = 60.0) -> Path:
    """The story's baseline marker, written `age` seconds ago."""
    marker = tmp_path / ".baseline-1-1"
    marker.write_text("0" * 40 + "\n", encoding="utf-8")
    then = time.time() - age
    os.utime(marker, (then, then))
    return marker


_LINUX_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="the probe reads a server's processes from Linux's /proc"
)


@_LINUX_ONLY
def test_a_server_the_run_left_up_in_the_main_tree_is_stopped(tmp_path, capsys):
    """#190: the server step 5's sweep left up answers from the main tree, so
    the gate's worktree run would reuse it and measure the main tree. With the
    stop flags the probe stops it, and the URL is free for the worktree's own."""
    main_tree = tmp_path / "main"
    main_tree.mkdir()
    marker = _baseline(tmp_path)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    with _left_up(main_tree, port) as (server,):
        found = probe_servers.probe([url])
        assert [os.path.realpath(entry["cwd"]) for entry in found["answering"]] == [os.path.realpath(main_tree)]
        code = probe_servers.main(["--url", url, "--stop-since", str(marker), "--root", str(main_tree)])
        out = json.loads(capsys.readouterr().out)
        assert _gone(server)
    assert code == 0
    assert out["answering"] == [] and out["free"] == [url] and out["left"] == []
    assert [(entry["url"], entry["pids"]) for entry in out["stopped"]] == [(url, [server])]
    assert os.path.realpath(out["stopped"][0]["cwd"]) == os.path.realpath(main_tree)


@_LINUX_ONLY
def test_a_server_from_a_folder_of_its_own_tree_is_stopped_once_that_folder_is_removed(tmp_path, capsys):
    """A server a run in an old gate worktree left up, whose folder the
    rebuild removed: Linux names its folder with a ` (deleted)` suffix, and it
    is still inside the worktree's root."""
    worktree = tmp_path / ".gate-worktree-1-1"
    worktree.mkdir()
    marker = _baseline(tmp_path)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    with _left_up(worktree, port) as (server,):
        worktree.rmdir()
        code = probe_servers.main(["--url", url, "--stop-since", str(marker), "--root", str(worktree)])
        out = json.loads(capsys.readouterr().out)
        assert _gone(server)
    assert code == 0
    assert out["stopped"][0]["cwd"].endswith(" (deleted)")


@_LINUX_ONLY
def test_a_host_the_lookup_cannot_encode_after_a_servers_url_stops_nothing(tmp_path, capsys):
    """The refusal prints no JSON, so it comes before any stop: the server the
    first URL reaches, one the probe would stop, still runs. Before, the
    probe stopped it, then refused the second URL when it resolved it."""
    main_tree = tmp_path / "main"
    main_tree.mkdir()
    marker = _baseline(tmp_path)
    port = _free_port()
    with _left_up(main_tree, port) as (server,):
        code = probe_servers.main(
            ["--url", f"http://127.0.0.1:{port}", "--url", _UNENCODABLE_HOSTS[-1], "--stop-since", str(marker),
             "--root", str(main_tree)]
        )
        assert not _gone(server)
    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == "" and f"REFUSED: {_UNENCODABLE_HOSTS[-1]}: " in captured.err


def _serve_with_a_worker_that_leaves(holds_the_socket: bool, host: str = "127.0.0.1") -> str:
    """A server on `host` whose forked worker, on SIGTERM, leaves the process
    group, so the SIGKILL sent to that group misses it. The worker shares the
    server's listening socket, or closes its copy, and sets its handler before
    the server says it is ready."""
    return (
        "import os, signal, socket, sys, time\n"
        f"s = socket.socket(socket.{'AF_INET6' if ':' in host else 'AF_INET'})\n"
        f"s.bind(({host!r}, int(sys.argv[1])))\n"
        "s.listen()\n"
        "r, w = os.pipe()\n"
        "worker = os.fork()\n"
        "if worker == 0:\n"
        + ("" if holds_the_socket else "    s.close()\n")
        + "    signal.signal(signal.SIGTERM, lambda *_: os.setpgid(0, 0))\n"
        "    os.write(w, b'1')\n"
        "    while True:\n"
        "        time.sleep(600)\n"
        "os.read(r, 1)\n"
        "print('ready', worker, flush=True)\n"
        "time.sleep(600)\n"
    )


@_LINUX_ONLY
@pytest.mark.parametrize("worker_answers", [True, False], ids=["worker-answers", "nothing-answers"])
def test_a_server_stopped_only_in_part_is_named_with_what_it_stopped(tmp_path, monkeypatch, capsys, worker_answers):
    """The SIGTERM ends the server and its worker leaves the group, so the
    SIGKILL misses it: the server it ended is listed under `stopped`, marked
    `partial`, with the worker as still running. The probe then reads the URL
    once more: the worker that holds the socket still answers it, so the URL
    is listed under `left`; the twin's worker holds none, so the URL is free.
    Before, a partial stop read as nothing stopped and the ended server was
    named nowhere, and then the URL kept its read from before the stop, so it
    read as answering, and the probe exited 1, with nothing listening."""
    main_tree = tmp_path / "main"
    main_tree.mkdir()
    marker = _baseline(tmp_path)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    monkeypatch.setattr(probe_servers, "_GRACE", 0.5)
    with _left_up(main_tree, port, _serve_with_a_worker_that_leaves(worker_answers)) as (server, worker):
        code = probe_servers.main(["--url", url, "--stop-since", str(marker), "--root", str(main_tree)])
        out = json.loads(capsys.readouterr().out)
        assert _gone(server) and not _gone(worker)
    assert [
        (entry["url"], entry["process_groups"], entry["pids"], entry["partial"], entry["running"])
        for entry in out["stopped"]
    ] == [(url, [server], [server], True, [worker])]
    if not worker_answers:
        assert code == 0
        assert out["answering"] == [] and out["free"] == [url] and out["left"] == []
        return
    assert code == 1
    assert [entry["url"] for entry in out["answering"]] == [url]
    assert [entry["reason"] for entry in out["left"]] == [
        f"some of its processes still ran after SIGTERM and SIGKILL to process group {server} (pid {worker})"
    ]


def _localhost_addresses(port: int) -> list[str]:
    """The addresses `localhost` resolves to, in the order a connection tries them."""
    infos = socket.getaddrinfo("localhost", port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


@_LINUX_ONLY
@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6")
def test_a_server_that_answers_once_another_is_stopped_in_part_gets_a_verdict_of_its_own(tmp_path, monkeypatch,
                                                                                         capsys):
    """`localhost` resolves to `::1` and `127.0.0.1`, and a server listens on
    each at one port. The probe stops the one the URL reaches first only in
    part, its worker, which holds no socket, outliving the SIGKILL, and the URL
    then answers from the other. That server never had a verdict: the probe
    gave the URL its folder and the first server's reason, and left it up,
    though it is one the run left up too. Now the probe reads it as it reads
    any server that answers, and stops it. The twin, the first server stopped
    in full, is the stop that reads the URL again."""
    port = _free_port()
    addresses = _localhost_addresses(port)
    if sorted(addresses) != ["127.0.0.1", "::1"]:
        pytest.skip(f"localhost resolves to {addresses} here, not to ::1 and 127.0.0.1")
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    marker = _baseline(tmp_path)
    url = f"http://localhost:{port}"
    monkeypatch.setattr(probe_servers, "_GRACE", 0.5)
    with (
        _left_up(first, port, _serve_with_a_worker_that_leaves(False, addresses[0])) as (server, worker),
        _left_up(second, port, _serving(addresses[1])) as (other,),
    ):
        code = probe_servers.main(["--url", url, "--stop-since", str(marker), "--root", str(tmp_path)])
        out = json.loads(capsys.readouterr().out)
        assert _gone(server) and _gone(other) and not _gone(worker)
    assert code == 0
    assert out["answering"] == [] and out["free"] == [url] and out["left"] == []
    assert [
        (os.path.realpath(entry["cwd"]), entry["process_groups"], entry["pids"], entry["partial"], entry["running"])
        for entry in out["stopped"]
    ] == [
        (os.path.realpath(first), [server], [server], True, [worker]),
        (os.path.realpath(second), [other], [other], False, []),
    ]


@_LINUX_ONLY
def test_a_process_a_partial_stop_left_running_is_signalled_no_more(tmp_path, monkeypatch, capsys):
    """Two URLs reach one server, `127.0.0.1` and `localhost` at its port. The
    first URL's stop ends the server, and its worker, which shares its socket,
    leaves the group and outlives the SIGKILL, so the probe stops it no more.
    The second URL then reaches that worker: before, the probe stopped it
    there, and still listed the first URL as answering, with nothing
    listening, and exited 1. Now the worker is left up for both URLs, each of
    which it still answers, with the first URL's reason."""
    main_tree = tmp_path / "main"
    main_tree.mkdir()
    marker = _baseline(tmp_path)
    port = _free_port()
    if "127.0.0.1" not in _localhost_addresses(port):
        pytest.skip("localhost does not resolve to 127.0.0.1 here")
    urls = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    monkeypatch.setattr(probe_servers, "_GRACE", 0.5)
    with _left_up(main_tree, port, _serve_with_a_worker_that_leaves(True)) as (server, worker):
        code = probe_servers.main(
            ["--url", urls[0], "--url", urls[1], "--stop-since", str(marker), "--root", str(main_tree)]
        )
        out = json.loads(capsys.readouterr().out)
        assert _gone(server) and not _gone(worker)
        # Each URL listed as answering still answers.
        assert [probe_servers._reached(*probe_servers._host_and_port(entry["url"])) is not None
                for entry in out["answering"]] == [True] * len(out["answering"])
    assert code == 1
    assert [(entry["pids"], entry["running"]) for entry in out["stopped"]] == [([server], [worker])]
    assert [entry["url"] for entry in out["answering"]] == urls
    assert [entry["reason"] for entry in out["left"]] == [
        f"some of its processes still ran after SIGTERM and SIGKILL to process group {server} (pid {worker})"
    ] * 2


@_LINUX_ONLY
@pytest.mark.parametrize(
    ("host", "listens_on"),
    [("0.0.0.0", "127.0.0.1"), ("[::ffff:127.0.0.1]", "127.0.0.1"), ("[::]", "::1"), ("127.0.0.1", "127.0.0.1")],
    ids=["v4-unspecified", "v4-mapped", "v6-unspecified", "the-address"],
)
def test_a_url_whose_connection_lands_on_another_address_is_read_where_it_lands(tmp_path, capsys, host, listens_on):
    """Linux sends a connection to the unspecified address (`0.0.0.0`, `::`)
    to the family's loopback address, and one to an IPv4-mapped IPv6 address
    over IPv4 to the address it maps. The probe looked for a socket at the
    address as the URL names it, so for a server that took such a connection
    it named no folder and, with the stop flags, gave the false reason that
    /proc lists no socket that could have taken it. The twin: the URL names
    the address itself."""
    marker = _baseline(tmp_path)
    try:
        sock = _listener(socket.AF_INET6 if ":" in listens_on else socket.AF_INET, listens_on)
    except OSError:
        pytest.skip(f"{listens_on} cannot be bound here")
    with sock:
        port = sock.getsockname()[1]
        url = f"http://{host}:{port}"
        if probe_servers._reached(host.strip("[]"), port) is None:
            pytest.skip(f"no connection to {host} reaches {listens_on} here")
        assert probe_servers.main(["--url", url]) == 1
        found = json.loads(capsys.readouterr().out)
        code, out = _left_up_reason(capsys, url, marker, Path(os.getcwd()))
    assert found["answering"] == [{"url": url, "port": port, "cwd": os.getcwd()}]
    assert code == 1
    assert out["left"][0]["reason"].endswith("is this probe's own")


@contextlib.contextmanager
def _leading_its_session(cwd: Path, port: int, serve: str):
    """A server from `cwd` that leads a session of its own and still runs, as one from a terminal does: its pid."""
    server = subprocess.Popen(
        [sys.executable, "-c", serve, str(port)],
        cwd=cwd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        if server.stdout.readline().strip() != "ready":
            pytest.skip(f"no server started on port {port}")
        yield server.pid
    finally:
        server.kill()
        server.wait(timeout=10)


@_LINUX_ONLY
@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6")
@pytest.mark.parametrize("v6only_server", ["the-runs", "the-operators"])
def test_a_v6only_server_on_the_v6_wildcard_is_neither_stopped_nor_named_for_an_ipv4_url(tmp_path, capsys,
                                                                                         v6only_server):
    """A server on `[::]` with IPV6_V6ONLY, which takes no IPv4 connection,
    beside the one on `127.0.0.1` that took the URL's, at one port. The probe
    counted it as one that could have taken the connection: one the run left
    up, from another folder, it stopped with the other and named no folder for
    them; an operator's, whose session's first process still runs, it gave as
    the reason it left the server on 127.0.0.1 up. Now it reads only the server
    Linux gave the connection to: it stops it and names its folder, and the
    server on `[::]` keeps running."""
    if not _ipv6_loopback():
        pytest.skip("no connection to ::1 reaches a socket here, to show the server on [::] still answers")
    project = tmp_path / "project"
    other = project / "sub"
    other.mkdir(parents=True)
    marker = _baseline(tmp_path)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    v6only = _serving("::", v6only=True)
    with contextlib.ExitStack() as stack:
        if v6only_server == "the-runs":
            (v6_server,) = stack.enter_context(_left_up(other, port, v6only))
        else:
            v6_server = stack.enter_context(_leading_its_session(other, port, v6only))
        (server,) = stack.enter_context(_left_up(project, port))
        code = probe_servers.main(["--url", url, "--stop-since", str(marker), "--root", str(project)])
        out = json.loads(capsys.readouterr().out)
        assert _gone(server) and not _gone(v6_server)
        assert probe_servers._reached("::1", port) is not None
    assert code == 0
    assert out["answering"] == [] and out["free"] == [url] and out["left"] == []
    assert [(entry["url"], entry["process_groups"], entry["pids"]) for entry in out["stopped"]] == [
        (url, [server], [server])
    ]
    assert os.path.realpath(out["stopped"][0]["cwd"]) == os.path.realpath(project)


@pytest.mark.parametrize(
    ("family", "address", "lands"),
    [
        (socket.AF_INET, "0.0.0.0", (socket.AF_INET, "127.0.0.1")),
        (socket.AF_INET6, "::", (socket.AF_INET6, "::1")),
        (socket.AF_INET6, "::ffff:192.0.2.1", (socket.AF_INET, "192.0.2.1")),
        (socket.AF_INET6, "::ffff:0.0.0.0", (socket.AF_INET, "127.0.0.1")),
        (socket.AF_INET, "192.0.2.1", (socket.AF_INET, "192.0.2.1")),
        (socket.AF_INET6, "2001:db8::1", (socket.AF_INET6, "2001:db8::1")),
    ],
    ids=["v4-unspecified", "v6-unspecified", "v4-mapped", "v4-mapped-unspecified", "v4", "v6"],
)
def test_the_address_a_connection_lands_at(family, address, lands):
    """The rule above on its own, on any system; an address that is neither
    unspecified nor IPv4-mapped is where the connection lands."""
    landed = probe_servers._landing(family, socket.inet_pton(family, address), 0)
    assert landed == probe_servers._Address(lands[0], socket.inet_pton(*lands))


def _left_up_reason(capsys, url: str, marker: Path, root: Path) -> tuple[int, dict]:
    code = probe_servers.main(["--url", url, "--stop-since", str(marker), "--root", str(root)])
    out = json.loads(capsys.readouterr().out)
    assert out["stopped"] == []
    assert [entry["url"] for entry in out["answering"]] == [url]
    assert [entry["url"] for entry in out["left"]] == [url]
    return code, out


@_LINUX_ONLY
def test_a_server_from_outside_every_root_is_left_up(tmp_path, capsys):
    """Another project's server on the port: the run never started a server there."""
    main_tree, elsewhere = tmp_path / "main", tmp_path / "elsewhere"
    main_tree.mkdir()
    elsewhere.mkdir()
    marker = _baseline(tmp_path)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    with _left_up(elsewhere, port) as (server,):
        code, out = _left_up_reason(capsys, url, marker, main_tree)
        assert not _gone(server)
    assert code == 1
    assert "outside every --root" in out["left"][0]["reason"]


@_LINUX_ONLY
def test_a_server_that_started_before_the_marker_is_left_up(tmp_path, capsys):
    """A dev server left running from before the story's work began, the
    operator's own: it started before the baseline marker was written."""
    main_tree = tmp_path / "main"
    main_tree.mkdir()
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    with _left_up(main_tree, port) as (server,):
        marker = _baseline(tmp_path, age=0.0)
        code, out = _left_up_reason(capsys, url, marker, main_tree)
        assert not _gone(server)
    assert code == 1
    assert f"process {server} in its process group started before {marker} was written" == out["left"][0]["reason"]


@_LINUX_ONLY
def test_a_server_whose_session_leader_still_runs_is_left_up(tmp_path, capsys):
    """A server whatever started it still runs beside: a shell, an IDE, a
    runner mid-run. Its session's first process runs, so it is not one a
    finished run left up."""
    main_tree = tmp_path / "main"
    main_tree.mkdir()
    marker = _baseline(tmp_path)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    start = subprocess.Popen(
        [sys.executable, "-c", _LAUNCHER, _SERVE, str(port)],
        cwd=main_tree,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        if start.stdout.readline().split()[1:] != ["ready"]:
            pytest.skip(f"no server started on 127.0.0.1:{port}")
        code, out = _left_up_reason(capsys, url, marker, main_tree)
        assert start.poll() is None
    finally:
        os.killpg(start.pid, signal.SIGKILL)
        start.wait(timeout=10)
        for entry in Path("/proc").iterdir():
            # The launcher's server, in a group of its own, outlives it: stop it too.
            if entry.name.isdigit() and not _gone(int(entry.name)):
                try:
                    stat = (entry / "stat").read_text(encoding="ascii")
                except OSError:
                    continue
                if int(stat[stat.rindex(")") + 2 :].split()[3]) == start.pid:
                    os.killpg(int(stat[stat.rindex(")") + 2 :].split()[2]), signal.SIGKILL)
    assert code == 1
    assert out["left"][0]["reason"] == f"process {start.pid}, which leads its session, still runs"


# A watcher (watchexec, cargo-watch) runs its server in a process group of its own and, when a file changes, as the
# run's own edits make one do, starts it again in a new group, while it runs on in the session it started in.
_WATCHER = (
    "import os, signal, subprocess, sys\n"
    "signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1})\n"
    "def start():\n"
    "    server = subprocess.Popen(\n"
    "        [sys.executable, '-c', sys.argv[1], sys.argv[2]], process_group=0, stdin=subprocess.DEVNULL,\n"
    "        stdout=subprocess.PIPE, text=True,\n"
    "    )\n"
    "    print(os.getpid(), server.pid, server.stdout.readline().strip(), flush=True)\n"
    "    return server\n"
    "server = start()\n"
    "while True:\n"
    "    signal.sigwait({signal.SIGUSR1})\n"
    "    os.killpg(server.pid, signal.SIGKILL)\n"
    "    server.wait()\n"
    "    server = start()\n"
)
# The watcher started in the background with no terminal, by a command that leads a session of its own and exits at
# once: `setsid sh -c 'watcher &'`, a `nohup watcher &` from a terminal then closed, or another agent session's.
_IN_THE_BACKGROUND = (
    "import subprocess, sys\n"
    "subprocess.Popen([sys.executable, '-c', *sys.argv[1:]], stdin=subprocess.DEVNULL)\n"
)


@contextlib.contextmanager
def _watched(cwd: Path, port: int):
    """A server a watcher runs from `cwd`: the watcher's pid and the server's, then a function that makes the
    watcher start the server again and gives the new pair."""
    start = subprocess.Popen(
        [sys.executable, "-c", _IN_THE_BACKGROUND, _WATCHER, _SERVE, str(port)],
        cwd=cwd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=True,
    )
    pairs: list[tuple[int, int]] = []

    def read() -> tuple[int, int]:
        line = start.stdout.readline().split()
        if len(line) < 3 or line[2] != "ready":
            pytest.skip(f"no watched server started on 127.0.0.1:{port}")
        pairs.append((int(line[0]), int(line[1])))
        return pairs[-1]

    def again() -> tuple[int, int]:
        os.kill(pairs[-1][0], signal.SIGUSR1)
        return read()

    try:
        first = read()
        start.wait(timeout=10)
        yield first, again
    finally:
        if start.poll() is None:
            start.kill()
            start.wait(timeout=10)
        # The watcher runs in the group the command that started it led; each server in a group of its own.
        for group in (start.pid, *(server for _, server in pairs)):
            with contextlib.suppress(OSError):
                os.killpg(group, signal.SIGKILL)


_WATCHER_REASON = (
    "process {watcher}, outside its process group, still runs in its session as the parent of process {server}: a "
    "watcher or supervisor that can start it again"
)


@_LINUX_ONLY
@pytest.mark.parametrize("began", ["before-the-story", "after-the-story"])
def test_a_server_a_watcher_of_the_operators_starts_is_left_up(tmp_path, capsys, began):
    """The operator starts a watcher in the background with no terminal, and
    it runs a dev server in a process group of its own. The probe left that
    server up while it had started before the story's marker, but once the
    run's edits made the watcher start it again, every process of its group
    had started after the marker, its session's first process was gone, and
    the probe stopped it, while the watcher, started before the story, ran on
    in that session and nothing examined it. A watcher started after the
    marker had its server stopped the same way. Now a process that still runs
    in the server's session as the parent of one of its processes, outside
    its group, keeps it up, and so does any process in that session that
    started before the marker."""
    main_tree = tmp_path / "main"
    main_tree.mkdir()
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    with _watched(main_tree, port) as ((watcher, server), again):
        if began == "before-the-story":
            # Written once the watcher and its first server had started, and the server started again more than the
            # probe's clock slack (two seconds after the marker) later, with a second for /proc's whole-second boot time.
            marker = _baseline(tmp_path, age=probe_servers._CLOCK_SLACK)
            time.sleep(1.5)
            watcher, server = again()
        else:
            marker = _baseline(tmp_path)
        code, out = _left_up_reason(capsys, url, marker, main_tree)
        assert not _gone(server) and not _gone(watcher)
    assert code == 1
    assert out["left"][0]["reason"] == _WATCHER_REASON.format(watcher=watcher, server=server)


@_LINUX_ONLY
def test_the_probes_own_server_is_left_up(tmp_path, capsys):
    """A listener in the process that runs the probe: never its own to stop."""
    marker = _baseline(tmp_path)
    with _listener() as sock:
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        code, out = _left_up_reason(capsys, url, marker, Path(os.getcwd()))
    assert code == 1
    assert "this probe's own" in out["left"][0]["reason"]


def test_without_a_linux_proc_it_stops_nothing(tmp_path):
    """macOS, Windows, or a /proc it cannot read: every answering URL is left
    up, and says why, so the gate falls back to its rule for a server it
    leaves."""
    marker = _baseline(tmp_path)
    with _listener() as sock:
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        stop = probe_servers._stop_request(str(marker), [str(tmp_path)])
        out = probe_servers.probe([url], stop, proc=tmp_path / "no-proc")
    assert out["stopped"] == []
    assert [entry["url"] for entry in out["answering"]] == [url]
    assert out["left"][0]["reason"].startswith("this system has no Linux /proc")


def test_the_stop_flags_go_together_and_need_a_marker_it_can_read(tmp_path, capsys):
    url = f"http://127.0.0.1:{_free_port()}"
    with pytest.raises(SystemExit) as exc:
        probe_servers.main(["--url", url, "--stop-since", str(_baseline(tmp_path))])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        probe_servers.main(["--url", url, "--root", str(tmp_path)])
    assert exc.value.code == 2
    assert probe_servers.main(["--url", url, "--stop-since", str(tmp_path / "absent"), "--root", str(tmp_path)]) == 2
    assert "REFUSED: --stop-since" in capsys.readouterr().err


_GATE = _SCRIPTS.parent / "references" / "gate.md"


def _gate_stop_flags() -> list[str]:
    """The stop flags gate.md's caveat adds to the probe, as one code span."""
    found = re.search(r"with the stop flags added: `(--stop-since [^`]+)`", _GATE.read_text(encoding="utf-8"))
    return found.group(1).split() if found else []


def test_the_stop_flags_the_gate_prescribes_are_the_ones_the_probe_takes(tmp_path, capsys):
    """The conductor copies the flags from gate.md: each one, with its
    placeholders filled as a run fills them, is one the probe accepts."""
    artifacts, project = tmp_path / "artifacts", tmp_path / "project"
    artifacts.mkdir()
    project.mkdir()
    _baseline(artifacts)
    filled = {
        "{workflow.implementation_artifacts}/.baseline-<story_id>": str(artifacts / ".baseline-1-1"),
        "{project-root}": str(project),
        "<tmp-path>": str(artifacts / ".gate-worktree-1-1"),
    }
    flags = [filled.get(word, word) for word in _gate_stop_flags()]
    assert flags[0::2] == ["--stop-since", "--root", "--root"], flags
    url = f"http://127.0.0.1:{_free_port()}"
    assert probe_servers.main(["--url", url, *flags]) == 0
    assert json.loads(capsys.readouterr().out) == {"answering": [], "free": [url], "stopped": [], "left": []}


def test_the_stop_flags_reader_misses_a_flag_the_gate_drops():
    """The twin: a caveat whose span lost a flag is not the probe's three."""
    flags = _gate_stop_flags()
    assert flags
    assert (flags[:2] + flags[4:])[0::2] != ["--stop-since", "--root", "--root"]


def test_without_the_stop_flags_the_output_keeps_its_two_keys(capsys):
    """Readers of the first output read `answering` and `free` only."""
    port = _free_port()
    assert probe_servers.main(["--url", f"http://127.0.0.1:{port}"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"answering", "free"}


# Each condition on its own, on a /proc laid out as Linux lays it out: one
# server whose every process passes, and the same server with one thing
# changed. The probe's caller is given, so these run on any system.

_BOOT = 1_000_000
_TICKS = 100.0
_SINCE = float(_BOOT + 100)
# The marker as the probe names it in a reason: `Path` writes it with backslashes on Windows.
_MARKER_NAMED = str(Path("/p/.baseline-1-1"))
_CALLER = probe_servers._Caller(uid=1000, pgrp=500, session=500, lineage=frozenset({500, 400, 1}))
# The server the run left up: `bun run dev` (40) leading its process group, the server under it (41) holding the
# socket, both in the session the runner's start command (30, gone) led, started 200 seconds after boot.
_RUN_LEFT_UP = (
    {"pid": 40, "ppid": 1, "pgrp": 40, "session": 30, "tty": 0, "start": 20_000, "uid": 1000, "cwd": "/p/apps/web"},
    {"pid": 41, "ppid": 40, "pgrp": 40, "session": 30, "tty": 0, "start": 20_100, "uid": 1000, "cwd": "/p/apps/web",
     "holds": True},
)


def _proc_with(tmp_path: Path, processes, listening: str = "0100007F") -> Path:
    """`processes` in a /proc whose one listening socket, port 3001 at `listening` (127.0.0.1 unless given, as
    /proc/net/tcp prints it), inode 777, the ones marked `holds` hold."""
    proc = tmp_path / "proc"
    (proc / "net").mkdir(parents=True)
    (proc / "stat").write_text(f"cpu  1 2 3\nbtime {_BOOT}\n", encoding="ascii")
    header = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    (proc / "net" / "tcp").write_text(
        header + f"   0: {listening}:0BB9 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 777\n",
        encoding="ascii",
    )
    (proc / "net" / "tcp6").write_text(header, encoding="ascii")
    for p in processes:
        _add_process(proc, p)
    return proc


def _add_process(proc: Path, p: dict) -> None:
    """Process `p` in a /proc laid out as Linux lays it out, holding socket 777 when marked `holds`, or the socket
    whose inode `holds` gives."""
    folder = proc / str(p["pid"])
    (folder / "fd").mkdir(parents=True)
    # minflt through itrealvalue: the twelve fields between flags and starttime, field 22.
    rest = " ".join(["0"] * 12)
    (folder / "stat").write_text(
        f"{p['pid']} (node (dev)) {p.get('state', 'S')} {p['ppid']} {p['pgrp']} {p['session']} {p['tty']} -1 0 "
        f"{rest} {p['start']} 0 0\n",
        encoding="ascii",
    )
    (folder / "status").write_text(f"Name:\tnode\nUid:\t{p['uid']}\t{p['uid']}\t{p['uid']}\t{p['uid']}\n")
    try:
        os.symlink(p["cwd"], folder / "cwd")
        if p.get("holds"):
            os.symlink(f"socket:[{'777' if p['holds'] is True else p['holds']}]", folder / "fd" / "3")
    except OSError:
        pytest.skip("these symlinks cannot be made here")


def _verdict(tmp_path: Path, processes, roots=("/p",)) -> str | None:
    proc = _proc_with(tmp_path, processes)
    stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, tuple(roots))
    reason, members = probe_servers._not_the_runs(proc, 3001, _V4, stop, _CALLER, _TICKS)
    assert (reason is None) == bool(members)
    return reason


def _changed(index: int, **fields) -> tuple[dict, ...]:
    return tuple({**p, **fields} if i == index else p for i, p in enumerate(_RUN_LEFT_UP))


def test_a_server_whose_every_process_passes_is_the_runs(tmp_path):
    proc = _proc_with(tmp_path, _RUN_LEFT_UP)
    stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
    reason, members = probe_servers._not_the_runs(proc, 3001, _V4, stop, _CALLER, _TICKS)
    assert reason is None
    assert sorted(member.pid for member in members) == [40, 41]


@pytest.mark.parametrize(
    ("processes", "roots", "reason"),
    [
        # Started from a terminal: the terminal's shell leads its session and is its controlling terminal.
        (_changed(0, tty=34817), ("/p",), "process 40 in its process group has a controlling terminal"),
        # Another user's process in the group.
        (_changed(0, uid=1001), ("/p",), "process 40 in its process group is not this user's"),
        # One process of the group started before the marker, within the clock's slack, or long before.
        (_changed(0, start=10_000), ("/p",), f"process 40 in its process group started before {_MARKER_NAMED} was "
         "written"),
        (_changed(1, start=10_150), ("/p",), f"process 41 in its process group started before {_MARKER_NAMED} was "
         "written"),
        # The process that led its session still runs.
        (_RUN_LEFT_UP + ({"pid": 30, "ppid": 1, "pgrp": 30, "session": 30, "tty": 0, "start": 19_000, "uid": 1000,
                          "cwd": "/p"},), ("/p",), "process 30, which leads its session, still runs"),
        # Outside every root, and a root that is only a prefix of its folder's name.
        (_RUN_LEFT_UP, ("/q",), "it runs from /p/apps/web, outside every --root"),
        (_RUN_LEFT_UP, ("/p/apps/we",), "it runs from /p/apps/web, outside every --root"),
        # The probe's own group, session or lineage.
        (tuple({**p, "pgrp": 500} for p in _RUN_LEFT_UP), ("/p",), "process group 500 is this probe's own"),
        (tuple({**p, "session": 500} for p in _RUN_LEFT_UP), ("/p",),
         "process 40 in its process group is this probe, one that started it or in its session"),
        (({**_RUN_LEFT_UP[0], "pid": 400, "pgrp": 400}, {**_RUN_LEFT_UP[1], "ppid": 400, "pgrp": 400}), ("/p",),
         "process 400 in its process group is this probe, one that started it or in its session"),
    ],
    ids=["terminal", "other-user", "started-before", "started-within-slack", "leader-runs", "outside-roots",
         "prefix-root", "own-group", "own-session", "own-lineage"],
)
def test_a_server_that_fails_one_condition_is_left_up(tmp_path, processes, roots, reason):
    assert _verdict(tmp_path, processes, roots) == reason


def test_a_server_whose_workers_share_its_socket_and_group_is_the_runs(tmp_path):
    """A server that forks workers, each holding the listening socket, in its one process group."""
    worker = {**_RUN_LEFT_UP[1], "pid": 42, "ppid": 41, "start": 20_200}
    proc = _proc_with(tmp_path, _RUN_LEFT_UP + (worker,))
    stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
    reason, members = probe_servers._not_the_runs(proc, 3001, _V4, stop, _CALLER, _TICKS)
    assert reason is None
    assert sorted(member.pid for member in members) == [40, 41, 42]


def test_a_holder_that_has_exited_since_its_socket_was_read_is_left_up(tmp_path):
    zombie = {**_RUN_LEFT_UP[1], "state": "Z"}
    assert _verdict(tmp_path, (_RUN_LEFT_UP[0], zombie)) == "a process that holds its socket has exited"


def test_a_session_leader_that_has_exited_but_is_not_reaped_does_not_run(tmp_path):
    leader = {"pid": 30, "ppid": 1, "pgrp": 30, "session": 30, "tty": 0, "start": 19_000, "uid": 1000, "cwd": "/p",
              "state": "Z"}
    assert _verdict(tmp_path, _RUN_LEFT_UP + (leader,)) is None


def test_a_pid_given_to_another_session_since_does_not_lead_this_one(tmp_path):
    reused = {"pid": 30, "ppid": 1, "pgrp": 30, "session": 29, "tty": 0, "start": 19_000, "uid": 1000, "cwd": "/p"}
    assert _verdict(tmp_path, _RUN_LEFT_UP + (reused,)) is None


# As measured with turbo: `bun run dev` reparented to `systemd --user`, which leads a session of its own and started
# at login, long before the marker, and turbo's other task, a server in a process group of its own in the server's
# session, started during the sweep too.
_REAPER = {"pid": 7, "ppid": 1, "pgrp": 7, "session": 7, "tty": 0, "start": 500, "uid": 1000, "cwd": "/"}
_TURBO_LEFT_UP = (
    _REAPER,
    {**_RUN_LEFT_UP[0], "ppid": 7},
    _RUN_LEFT_UP[1],
    {"pid": 50, "ppid": 7, "pgrp": 50, "session": 30, "tty": 0, "start": 20_050, "uid": 1000, "cwd": "/p/apps/api"},
)


def test_a_server_reparented_to_a_reaper_in_another_session_is_the_runs(tmp_path):
    """The run's own case still passes: its parent, `systemd --user`, runs
    and started before the marker, but in a session of its own, which it took
    the server into by adopting it, not by starting it, and every process of
    the server's session started during the sweep."""
    proc = _proc_with(tmp_path, _TURBO_LEFT_UP)
    stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
    reason, members = probe_servers._not_the_runs(proc, 3001, _V4, stop, _CALLER, _TICKS)
    assert reason is None
    assert sorted(member.pid for member in members) == [40, 41]


@pytest.mark.parametrize(
    ("watcher_start", "its_parent", "reason"),
    [
        (9_000, True, _WATCHER_REASON.format(watcher=35, server=40)),
        (19_500, True, _WATCHER_REASON.format(watcher=35, server=40)),
        (9_000, False, f"process 35 in its session started before {_MARKER_NAMED} was written"),
        # The case the docs name: a watcher that started after the marker and starts the server through a process
        # that has since exited, so it is no longer its parent, reads like turbo's other task.
        (19_500, False, None),
    ],
    ids=["began-before-its-parent", "began-after-its-parent", "began-before-not-its-parent",
         "began-after-not-its-parent"],
)
def test_a_watcher_in_the_servers_session_keeps_it_up(tmp_path, watcher_start, its_parent, reason):
    """A watcher of the operator's in the server's session, outside its
    process group: 35, in the group of the command that started it and led
    the session (30, gone)."""
    watcher = {"pid": 35, "ppid": 7, "pgrp": 30, "session": 30, "tty": 0, "start": watcher_start, "uid": 1000,
               "cwd": "/p"}
    processes = (_REAPER, {**_RUN_LEFT_UP[0], "ppid": 35 if its_parent else 7}, _RUN_LEFT_UP[1], watcher)
    assert _verdict(tmp_path, processes) == reason


def test_a_supervisor_of_one_of_its_processes_keeps_it_up(tmp_path):
    """The parent rule reads every process of the group, not its leader only."""
    supervisor = {"pid": 45, "ppid": 7, "pgrp": 45, "session": 30, "tty": 0, "start": 19_500, "uid": 1000,
                  "cwd": "/p"}
    processes = (_REAPER, {**_RUN_LEFT_UP[0], "ppid": 7}, {**_RUN_LEFT_UP[1], "ppid": 45}, supervisor)
    assert _verdict(tmp_path, processes) == _WATCHER_REASON.format(watcher=45, server=41)


def test_a_socket_no_readable_process_holds_is_left_up(tmp_path):
    processes = tuple({k: v for k, v in p.items() if k != "holds"} for p in _RUN_LEFT_UP)
    assert _verdict(tmp_path, processes).startswith("a socket that could have taken the connection has no holder")


def test_the_stop_signals_the_group_and_reads_the_url_again(tmp_path, monkeypatch, capsys):
    """The group gets SIGTERM; once its processes have exited, the URL is
    probed again and read as free."""
    proc = _proc_with(tmp_path, _RUN_LEFT_UP)
    monkeypatch.setattr(probe_servers, "_reads_processes", lambda _proc: True)
    monkeypatch.setattr(probe_servers, "_caller", lambda _proc: _CALLER)
    monkeypatch.setattr(probe_servers, "_clock_ticks", lambda: _TICKS)
    sent = []
    with _listener() as sock:
        port = sock.getsockname()[1]
        monkeypatch.setattr(probe_servers, "_listening_inodes", lambda _port, _proc, _reached=None: {"777"})

        def kill(group, sig):
            sent.append((group, sig))
            for pid in (40, 41):
                (proc / str(pid) / "stat").unlink()
            sock.close()

        stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
        out = probe_servers.probe([f"http://127.0.0.1:{port}"], stop, proc=proc, kill=kill)
    assert sent == [(40, signal.SIGTERM)]
    assert out["answering"] == [] and out["left"] == []
    assert out["stopped"] == [
        {"url": f"http://127.0.0.1:{port}", "port": port, "cwd": "/p/apps/web", "process_groups": [40], "pids": [40, 41],
         "partial": False, "running": []}
    ]


def test_a_group_that_does_not_exit_is_left_up_and_said_so(tmp_path, monkeypatch):
    proc = _proc_with(tmp_path, _RUN_LEFT_UP)
    monkeypatch.setattr(probe_servers, "_reads_processes", lambda _proc: True)
    monkeypatch.setattr(probe_servers, "_caller", lambda _proc: _CALLER)
    monkeypatch.setattr(probe_servers, "_clock_ticks", lambda: _TICKS)
    monkeypatch.setattr(probe_servers, "_GRACE", 0.1)
    monkeypatch.setattr(probe_servers, "_listening_inodes", lambda _port, _proc, _reached=None: {"777"})
    sent = []
    with _listener() as sock:
        port = sock.getsockname()[1]
        stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
        out = probe_servers.probe(
            [f"http://127.0.0.1:{port}"], stop, proc=proc, kill=lambda group, sig: sent.append((group, sig))
        )
    assert [sig for _, sig in sent] == [signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)]
    # Nothing exited and the URL still answers, so nothing was stopped; the reason names the group the signals went
    # to and the processes they did not end.
    assert out["stopped"] == []
    assert out["left"][0]["reason"] == (
        "its processes still ran after SIGTERM and SIGKILL to process group 40 (pids 40, 41)"
    )


def test_a_group_stopped_only_in_part_names_the_processes_that_exited(tmp_path, monkeypatch):
    """A process that leaves its group on SIGTERM outlives the SIGKILL sent to
    that group: the processes the signals ended are listed under `stopped`,
    marked `partial`, with the ones that still run, and the URL, which those
    still answer, under `left`. Before, a partial stop was reported as nothing
    stopped."""
    proc = _proc_with(tmp_path, _RUN_LEFT_UP)
    monkeypatch.setattr(probe_servers, "_reads_processes", lambda _proc: True)
    monkeypatch.setattr(probe_servers, "_caller", lambda _proc: _CALLER)
    monkeypatch.setattr(probe_servers, "_clock_ticks", lambda: _TICKS)
    monkeypatch.setattr(probe_servers, "_GRACE", 0.1)
    monkeypatch.setattr(probe_servers, "_listening_inodes", lambda _port, _proc, _reached=None: {"777"})
    sent = []

    def kill(group, sig):
        sent.append((group, sig))
        # The group's leader exits; its worker (41) does not.
        with contextlib.suppress(FileNotFoundError):
            (proc / "40" / "stat").unlink()

    with _listener() as sock:
        port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
        out = probe_servers.probe([url], stop, proc=proc, kill=kill)
    assert sent == [(40, signal.SIGTERM), (40, getattr(signal, "SIGKILL", signal.SIGTERM))]
    assert out["stopped"] == [
        {"url": url, "port": port, "cwd": "/p/apps/web", "process_groups": [40], "pids": [40], "partial": True,
         "running": [41]}
    ]
    assert [entry["url"] for entry in out["answering"]] == [url]
    assert out["left"] == [
        {"url": url, "port": port, "cwd": "/p/apps/web",
         "reason": "some of its processes still ran after SIGTERM and SIGKILL to process group 40 (pid 41)"}
    ]


@pytest.mark.parametrize(
    ("ends", "pids", "running"), [((41,), [41], [40]), ((), [], [40, 41])], ids=["its-listener-exits", "none-exits"]
)
def test_a_url_nothing_answers_after_a_partial_stop_is_free(tmp_path, monkeypatch, ends, pids, running):
    """After a stop that leaves some of a server's processes running, the
    probe reads the URL once more. Here nothing answers then: the listener
    (41) exits and its group's leader (40) outlives the SIGKILL, or no process
    exits but the server lets go of its socket. The URL is free, and the
    server is listed under `stopped` with the processes still running, so
    each process the probe signalled is named. Before, the URL kept its read
    from before the stop: answering, and under `left`, with nothing listening.
    The twin is the test above, whose survivor still answers."""
    proc = _proc_with(tmp_path, _RUN_LEFT_UP)
    _stop_mode(monkeypatch)
    monkeypatch.setattr(probe_servers, "_GRACE", 0.1)
    monkeypatch.setattr(probe_servers, "_listening_inodes", lambda _port, _proc, _reached=None: {"777"})
    sent = []
    with _listener() as sock:
        port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"

        def kill(group, sig):
            sent.append((group, sig))
            for pid in ends:
                with contextlib.suppress(FileNotFoundError):
                    (proc / str(pid) / "stat").unlink()
            sock.close()

        stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
        out = probe_servers.probe([url], stop, proc=proc, kill=kill)
    assert sent == [(40, signal.SIGTERM), (40, getattr(signal, "SIGKILL", signal.SIGTERM))]
    assert out == {
        "answering": [],
        "free": [url],
        "stopped": [
            {"url": url, "port": port, "cwd": "/p/apps/web", "process_groups": [40], "pids": pids, "partial": True,
             "running": running}
        ],
        "left": [],
    }


# A worker the server (41) forks after the probe has read its group.
_JOINS = {**_RUN_LEFT_UP[1], "pid": 42, "ppid": 41, "start": 20_200, "holds": False}


@pytest.mark.parametrize("joins", ["before-the-signal", "as-the-signal-is-sent", "never"])
def test_a_process_that_joins_the_group_after_it_was_read_is_named(tmp_path, monkeypatch, joins):
    """The signal reaches every process in the group when it is sent, a worker
    forked since the probe read the group included. The probe reads the group
    again right before each signal and right after it, and names each process
    it finds: one forked before the signal, and one forked as it is sent,
    which the signal ends but which is not reaped yet at the read after it.
    Before, only the processes of the first read were named. The twin: none
    joins."""
    proc = _proc_with(tmp_path, _RUN_LEFT_UP)
    _stop_mode(monkeypatch)
    monkeypatch.setattr(probe_servers, "_listening_inodes", lambda _port, _proc, _reached=None: {"777"})
    read = probe_servers._not_the_runs

    def then_a_worker_forks(*args):
        verdict = read(*args)
        if joins == "before-the-signal":
            _add_process(proc, _JOINS)
        return verdict

    monkeypatch.setattr(probe_servers, "_not_the_runs", then_a_worker_forks)
    with _listener() as sock:
        port = sock.getsockname()[1]

        def kill(group, sig):
            if joins == "as-the-signal-is-sent":
                _add_process(proc, {**_JOINS, "state": "Z"})
            for pid in (40, 41) if joins == "as-the-signal-is-sent" else (40, 41, 42):
                with contextlib.suppress(FileNotFoundError):
                    (proc / str(pid) / "stat").unlink()
            sock.close()

        stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
        out = probe_servers.probe([f"http://127.0.0.1:{port}"], stop, proc=proc, kill=kill)
    assert [(entry["pids"], entry["running"]) for entry in out["stopped"]] == [
        ([40, 41] if joins == "never" else [40, 41, 42], [])
    ]


# A second server on the port, at 127.0.0.1, holding socket 777: `bun run dev` (50) and the server under it (51), in
# the session another runner's start command (31, gone) led.
_ALSO_UP = (
    {"pid": 50, "ppid": 1, "pgrp": 50, "session": 31, "tty": 0, "start": 20_300, "uid": 1000, "cwd": "/p/apps/api"},
    {"pid": 51, "ppid": 50, "pgrp": 50, "session": 31, "tty": 0, "start": 20_400, "uid": 1000, "cwd": "/p/apps/api",
     "holds": True},
)
_TERM, _KILL = signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)


@pytest.mark.parametrize(
    ("cwd", "left"),
    [("/p/apps/api", None), ("/q/apps/api", "it runs from /q/apps/api, outside every --root")],
    ids=["it-is-the-runs", "it-is-not"],
)
def test_a_server_that_answers_after_a_partial_stop_gets_a_verdict_of_its_own(tmp_path, monkeypatch, cwd, left):
    """`localhost` resolves to `::1`, where the first server's listener (41)
    holds socket 888, and to `127.0.0.1`, where a second server (51) holds
    777. The probe stops the first only in part: its listener exits and its
    group's leader (40) outlives the SIGKILL. The URL then answers from the
    second server, whose socket none of the processes still running holds.
    Before, the probe gave the URL that server's folder with the first
    server's reason, and never read that server. Now it reads it as any
    server that answers: one the run left up is stopped, and another is left
    up with its own reason."""
    first = ({**_RUN_LEFT_UP[0]}, {**_RUN_LEFT_UP[1], "holds": "888"})
    proc = _proc_with(tmp_path, first + tuple({**p, "cwd": cwd} for p in _ALSO_UP))
    tcp6 = proc / "net" / "tcp6"
    tcp6.write_text(
        tcp6.read_text(encoding="ascii")
        + f"   0: {_proc_hex(socket.AF_INET6, '::1')}:0BB9 {'0' * 32}:0000 0A 00000000:00000000 00:00000000 "
        "00000000  1000        0 888\n",
        encoding="ascii",
    )
    _stop_mode(monkeypatch)
    monkeypatch.setattr(probe_servers, "_GRACE", 0.1)
    monkeypatch.setattr(probe_servers, "_lands_here", lambda _reached: True)

    def runs(pid: int) -> bool:
        return (proc / str(pid) / "stat").exists()

    monkeypatch.setattr(probe_servers, "_reached", lambda _host, _port: _V6 if runs(41) else _V4 if runs(51) else None)
    sent = []

    def kill(group, sig):
        sent.append((group, sig))
        for pid in {40: (41,), 50: (50, 51)}[group]:
            with contextlib.suppress(FileNotFoundError):
                (proc / str(pid) / "stat").unlink()

    url = "http://localhost:3001"
    stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
    out = probe_servers.probe([url], stop, proc=proc, kill=kill)
    stopped_in_part = {"url": url, "port": 3001, "cwd": "/p/apps/web", "process_groups": [40], "pids": [41],
                       "partial": True, "running": [40]}
    if left is None:
        assert sent == [(40, _TERM), (40, _KILL), (50, _TERM)]
        assert out == {
            "answering": [],
            "free": [url],
            "stopped": [
                stopped_in_part,
                {"url": url, "port": 3001, "cwd": cwd, "process_groups": [50], "pids": [50, 51], "partial": False,
                 "running": []},
            ],
            "left": [],
        }
        return
    assert sent == [(40, _TERM), (40, _KILL)]
    assert out == {
        "answering": [{"url": url, "port": 3001, "cwd": cwd}],
        "free": [],
        "stopped": [stopped_in_part],
        "left": [{"url": url, "port": 3001, "cwd": cwd, "reason": left}],
    }


@pytest.mark.parametrize("its_leader_exits", [True, False], ids=["a-later-url-stops-it", "nothing-stops-it"])
def test_a_url_read_before_a_later_urls_stop_is_read_again(tmp_path, monkeypatch, its_leader_exits):
    """Two URLs reach one server. At the first URL's read, the runner's start
    command (30), which leads the server's session, still runs, so the probe
    leaves the server up; the command then exits, and the second URL's read
    finds a server the run left up, and stops it. Before, the first URL kept
    its read from before that stop: answering, and under `left`, with nothing
    listening. Now a URL read before a later URL's stop is read again after
    it. The twin: the start command still runs, and both URLs are left up."""
    leader = {"pid": 30, "ppid": 1, "pgrp": 30, "session": 30, "tty": 0, "start": 19_000, "uid": 1000, "cwd": "/p"}
    proc = _proc_with(tmp_path, _RUN_LEFT_UP + (leader,))
    _stop_mode(monkeypatch)
    monkeypatch.setattr(probe_servers, "_lands_here", lambda _reached: True)
    monkeypatch.setattr(probe_servers, "_reached", lambda _host, _port: _V4 if (proc / "41" / "stat").exists() else None)
    read = probe_servers._not_the_runs

    def then_its_leader_exits(*args):
        verdict = read(*args)
        if its_leader_exits:
            with contextlib.suppress(FileNotFoundError):
                (proc / "30" / "stat").unlink()
        return verdict

    monkeypatch.setattr(probe_servers, "_not_the_runs", then_its_leader_exits)
    sent = []

    def kill(group, sig):
        sent.append((group, sig))
        for pid in (40, 41):
            with contextlib.suppress(FileNotFoundError):
                (proc / str(pid) / "stat").unlink()

    urls = ["http://127.0.0.1:3001", "http://localhost:3001"]
    stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
    out = probe_servers.probe(urls, stop, proc=proc, kill=kill)
    if its_leader_exits:
        assert sent == [(40, _TERM)]
        assert out == {
            "answering": [],
            "free": urls,
            "stopped": [{"url": urls[1], "port": 3001, "cwd": "/p/apps/web", "process_groups": [40], "pids": [40, 41],
                         "partial": False, "running": []}],
            "left": [],
        }
        return
    entries = [{"url": url, "port": 3001, "cwd": "/p/apps/web"} for url in urls]
    assert sent == []
    assert out == {
        "answering": entries,
        "free": [],
        "stopped": [],
        "left": [{**entry, "reason": "process 30, which leads its session, still runs"} for entry in entries],
    }


def _stop_mode(monkeypatch) -> None:
    """The probe's view of a Linux /proc and of its caller, on any system."""
    monkeypatch.setattr(probe_servers, "_reads_processes", lambda _proc: True)
    monkeypatch.setattr(probe_servers, "_caller", lambda _proc: _CALLER)
    monkeypatch.setattr(probe_servers, "_clock_ticks", lambda: _TICKS)


_ELSEWHERE = probe_servers._Address(socket.AF_INET, socket.inet_pton(socket.AF_INET, "192.0.2.1"))


def test_an_address_of_this_host_takes_a_connection_and_another_hosts_does_not():
    assert probe_servers._lands_here(_V4)
    # 192.0.2.1 is TEST-NET-1 (RFC 5737), no host's own address.
    assert not probe_servers._lands_here(_ELSEWHERE)


@pytest.mark.parametrize(("taken", "here"), [(False, False), (True, True)], ids=["never-taken", "taken"])
def test_an_address_that_binds_is_this_hosts_only_when_the_bound_socket_takes_a_connection(monkeypatch, taken, here):
    """Linux's `ip_nonlocal_bind` lets another host's address be bound, and a
    connection made to it then reaches that host, which may answer: only the
    bound socket taking it shows the address is this host's. The twin: one
    that takes it."""

    class _Bound:
        def __init__(self, *_args):
            self.address = None

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def bind(self, address):
            self.address = address

        def getsockname(self):
            return (self.address[0], 40000)

        def listen(self, _backlog):
            pass

        def settimeout(self, _timeout):
            pass

        def connect(self, _address):
            pass

        def accept(self):
            if not taken:
                raise TimeoutError("timed out")
            return _Bound(), ("192.0.2.1", 50000)

        def close(self):
            pass

    monkeypatch.setattr(probe_servers.socket, "socket", _Bound)
    assert probe_servers._lands_here(_ELSEWHERE) is here


@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6")
def test_ipv6_loopback_is_this_hosts_own():
    try:
        _listener(socket.AF_INET6, "::1").close()
    except OSError:
        pytest.skip("::1 cannot be bound here")
    assert probe_servers._lands_here(_V6)


def _link_local_listener() -> socket.socket | None:
    """A socket listening on one of this host's IPv6 link-local addresses, on
    that address's link, which takes a connection made to it there; None when
    there is none. The addresses are read from /proc/net/if_inet6: scope 20
    (link), with neither the tentative (0x40) nor the failed (0x08)
    duplicate-address flag."""
    try:
        rows = Path("/proc/net/if_inet6").read_text(encoding="ascii").splitlines()
    except OSError:
        return None
    for row in rows:
        fields = row.split()
        if len(fields) != 6 or fields[3] != "20" or int(fields[4], 16) & 0x48:
            continue
        address, index = socket.inet_ntop(socket.AF_INET6, bytes.fromhex(fields[0])), int(fields[1], 16)
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            sock.bind((address, 0, 0, index))
            sock.listen()
            sock.settimeout(1.0)
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as client:
                client.settimeout(1.0)
                client.connect(sock.getsockname())
                sock.accept()[0].close()
        except OSError:
            sock.close()
            continue
        return sock
    return None


@_LINUX_ONLY
@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6")
def test_a_link_local_address_of_this_host_is_its_own(capsys):
    """An IPv6 link-local address is one on a link, which a URL names with a
    zone (`[fe80::1%eth0]`, or the link's index), and Linux binds one only on
    its link. The probe dropped the zone, so it could not bind this host's own
    link-local address and read it as another host's: it named no folder for
    the server that answered there, and with the stop flags would have
    stopped nothing for it. The twin: the same address with no link reads as
    another host's."""
    sock = _link_local_listener()
    if sock is None:
        pytest.skip("this host has no IPv6 link-local address a socket can listen on")
    with sock:
        address, port, _, index = sock.getsockname()
        address = address.split("%", 1)[0]
        code = probe_servers.main(["--url", f"http://[{address}%{index}]:{port}"])
        packed = socket.inet_pton(socket.AF_INET6, address)
        assert probe_servers._lands_here(probe_servers._Address(socket.AF_INET6, packed, index))
        assert not probe_servers._lands_here(probe_servers._Address(socket.AF_INET6, packed))
    assert code == 1
    assert json.loads(capsys.readouterr().out)["answering"][0]["cwd"] == os.getcwd()


@pytest.mark.parametrize(("reached", "stops"), [(_ELSEWHERE, False), (_V4, True)], ids=["elsewhere", "here"])
def test_a_url_that_reached_another_hosts_address_stops_no_server_here(tmp_path, monkeypatch, reached, stops):
    """A URL whose host resolves to a container's address, say, answered from
    there: a server of the run's here listening on every address at that port
    never took the connection. It is left up, and the URL listed under `left`
    with the reason; before, it was stopped and named as the URL's server.
    The twin reaches 127.0.0.1, where that server does take it."""
    proc = _proc_with(tmp_path, _RUN_LEFT_UP, listening="00000000")
    _stop_mode(monkeypatch)
    answers = [True]
    monkeypatch.setattr(probe_servers, "_reached", lambda _host, _port: reached if answers[0] else None)
    sent = []

    def kill(group, sig):
        sent.append((group, sig))
        for pid in (40, 41):
            (proc / str(pid) / "stat").unlink()
        answers[0] = False

    url = "http://192.0.2.1:3001"
    stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
    out = probe_servers.probe([url], stop, proc=proc, kill=kill)
    if stops:
        assert sent == [(40, signal.SIGTERM)]
        assert [entry["pids"] for entry in out["stopped"]] == [[40, 41]]
        return
    assert sent == [] and out["stopped"] == []
    assert out["answering"] == [{"url": url, "port": 3001, "cwd": None}]
    assert out["left"] == [
        {"url": url, "port": 3001, "cwd": None,
         "reason": "it answered at 192.0.2.1, which is not an address of this host, so no process here took the "
                   "connection"}
    ]


@pytest.mark.parametrize(("reached", "cwd"), [(_ELSEWHERE, None), (_V4, "/p/apps/web")], ids=["elsewhere", "here"])
def test_a_url_that_reached_another_hosts_address_names_no_folder_here(tmp_path, monkeypatch, reached, cwd):
    """Without the stop flags too: the folder of a server here listening on
    every address is not the folder of the one that answered elsewhere."""
    proc = _proc_with(tmp_path, _RUN_LEFT_UP, listening="00000000")
    monkeypatch.setattr(probe_servers, "_reached", lambda _host, _port: reached)
    out = probe_servers.probe(["http://192.0.2.1:3001"], proc=proc)
    assert out == {"answering": [{"url": "http://192.0.2.1:3001", "port": 3001, "cwd": cwd}], "free": []}


def _proc_listing(tmp_path: Path, lists: str) -> Path:
    """A /proc that lists nothing (macOS, Windows), a socket at that port no connection to 127.0.0.1 reaches, one
    that could have taken it whose holder this probe cannot read, or one that could have taken it, held from
    /p/apps/web."""
    if lists == "nothing":
        return tmp_path / "no-proc"
    if lists == "another-address":
        return _proc_with(tmp_path, _RUN_LEFT_UP, listening="0200007F")
    if lists == "an-unread-holder":
        return _proc_with(tmp_path, tuple({k: v for k, v in p.items() if k != "holds"} for p in _RUN_LEFT_UP))
    return _proc_with(tmp_path, _RUN_LEFT_UP)


def _asked(monkeypatch) -> list:
    """The addresses the probe asks `_lands_here` about, each of which it reads as this host's."""
    calls = []
    monkeypatch.setattr(probe_servers, "_lands_here", lambda reached: calls.append(reached) or True)
    monkeypatch.setattr(probe_servers, "_reached", lambda _host, _port: _V4)
    return calls


@pytest.mark.parametrize(
    ("lists", "cwd"),
    [("nothing", None), ("another-address", None), ("an-unread-holder", None), ("the-address", "/p/apps/web")],
)
def test_without_the_stop_flags_it_listens_on_the_address_only_for_a_folder_proc_names(tmp_path, monkeypatch, lists,
                                                                                      cwd):
    """It tells an address of this host's own by listening on it, which a
    firewall on macOS or Windows can ask the user about. Without the stop
    flags that answer changes only a folder /proc names, so it listens only
    then. Before, it listened at every answering URL's address, on every
    system. The twin: a /proc that names the folder."""
    calls = _asked(monkeypatch)
    out = probe_servers.probe(["http://127.0.0.1:3001"], proc=_proc_listing(tmp_path, lists))
    assert out["answering"] == [{"url": "http://127.0.0.1:3001", "port": 3001, "cwd": cwd}]
    assert calls == ([_V4] if cwd else [])


@pytest.mark.parametrize(
    ("lists", "reason"),
    [
        ("nothing", "this system has no Linux /proc to read the server's processes from, so it stops nothing"),
        ("another-address", "/proc lists no socket here that could have taken the connection at 127.0.0.1"),
        ("the-address", "it runs from /p/apps/web, outside every --root"),
    ],
    ids=["nothing", "another-address", "the-address"],
)
def test_with_the_stop_flags_it_listens_on_the_address_only_when_proc_lists_a_socket_that_could_take_it(
    tmp_path, monkeypatch, lists, reason
):
    """With the stop flags the answer counts only on a system whose /proc it
    reads, and only when /proc lists a socket here that could have taken the
    connection: with none, no process here holds one, so it has nothing to
    stop, and says so. Before, it listened at the address on every system,
    and with no such socket gave the reason of a socket it could not read.
    The twin: a socket that could have taken it, of a server the probe then
    leaves up for another reason."""
    calls = _asked(monkeypatch)
    proc = _proc_listing(tmp_path, lists)
    if lists != "nothing":
        _stop_mode(monkeypatch)
    stop = probe_servers._Stop(Path("/q/.baseline-1-1"), _SINCE, ("/q",))
    out = probe_servers.probe(["http://127.0.0.1:3001"], stop, proc=proc, kill=lambda *_: pytest.fail("signalled"))
    assert out["stopped"] == []
    assert [entry["reason"] for entry in out["left"]] == [reason]
    assert calls == ([_V4] if lists == "the-address" else [])


@pytest.mark.parametrize(
    "bad", ["http://", "http://localhost:notaport", "http://localhost:99999", *_UNENCODABLE_HOSTS]
)
def test_a_bad_url_after_an_answering_one_is_refused_before_anything_is_stopped(tmp_path, monkeypatch, bad):
    """A refusal prints no JSON, so a server stopped before it would be named
    nowhere: every URL is read before the first stop, its host encoded as the
    lookup encodes it. A host the lookup could not encode was found only when
    the probe resolved it, after the answering URL's server was stopped."""
    proc = _proc_with(tmp_path, _RUN_LEFT_UP)
    _stop_mode(monkeypatch)
    # Were a stop to start, it would end quickly.
    monkeypatch.setattr(probe_servers, "_GRACE", 0.1)
    monkeypatch.setattr(probe_servers, "_listening_inodes", lambda _port, _proc, _reached=None: {"777"})
    sent = []
    with _listener() as sock:
        port = sock.getsockname()[1]
        stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
        with pytest.raises(ValueError):
            probe_servers.probe(
                [f"http://127.0.0.1:{port}", bad], stop, proc=proc, kill=lambda group, sig: sent.append((group, sig))
            )
    assert sent == []


def test_a_server_something_keeps_starting_is_left_up_after_a_bounded_number_of_stops(tmp_path, monkeypatch):
    proc = _proc_with(tmp_path, _RUN_LEFT_UP)
    monkeypatch.setattr(probe_servers, "_reads_processes", lambda _proc: True)
    monkeypatch.setattr(probe_servers, "_caller", lambda _proc: _CALLER)
    monkeypatch.setattr(probe_servers, "_clock_ticks", lambda: _TICKS)
    monkeypatch.setattr(probe_servers, "_listening_inodes", lambda _port, _proc, _reached=None: {"777"})
    # Each stop "succeeds" (no process still runs), and the server answers again: a supervisor restarts it.
    monkeypatch.setattr(probe_servers, "_stop_groups", lambda _proc, members, _kill=None: (members, []))
    with _listener() as sock:
        port = sock.getsockname()[1]
        stop = probe_servers._Stop(Path("/p/.baseline-1-1"), _SINCE, ("/p",))
        out = probe_servers.probe([f"http://127.0.0.1:{port}"], stop, proc=proc)
    assert len(out["stopped"]) == probe_servers._STOPS
    assert out["left"][0]["reason"] == f"it answered again after {probe_servers._STOPS} stops, so something keeps " \
        "starting it"


def test_a_mutant_the_reused_server_never_loads_reads_green(tmp_path):
    """The defect the gate's caveat answers: the row's command reaches a server
    started from another tree, so mutate_check.py prints GREEN for a mutant the
    command never saw. A server started from the worktree sees it."""
    mutate_check = _load("mutate_check")
    main_tree, worktree = tmp_path / "main", tmp_path / "worktree"
    for tree in (main_tree, worktree):
        tree.mkdir()
        (tree / "app.txt").write_text("ok\n", encoding="utf-8", newline="\n")
    # The browser spec's stand-in: it fetches the page and fails unless the server serves it unchanged.
    (worktree / "check_app.py").write_text(
        "import sys\nimport urllib.request\n\n"
        # No proxy: a request sent through one set in the environment would not reach this machine's 127.0.0.1.
        "opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
        "body = opener.open(f'http://127.0.0.1:{sys.argv[1]}/app.txt').read()\n"
        "if body != b'ok\\n':\n"
        "    print('FAILED test_app_serves_ok')\n    print('1 failed')\n    sys.exit(1)\n"
        "print('1 passed')\n",
        encoding="utf-8",
        newline="\n",
    )

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    def serve(root: Path) -> http.server.ThreadingHTTPServer:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def row(port: int) -> dict:
        return {
            "file": "app.txt",
            "anchor": "ok\n",
            "replacement": "broken\n",
            "command": f'"{sys.executable}" check_app.py {port}',
            "expect_red": "test_app_serves_ok",
        }

    reused, own = serve(main_tree), serve(worktree)
    try:
        reused_rows, _ = mutate_check.run_table([row(reused.server_address[1])], worktree)
        own_rows, _ = mutate_check.run_table([row(own.server_address[1])], worktree)
        found = probe_servers.probe([f"http://127.0.0.1:{reused.server_address[1]}"])
    finally:
        reused.shutdown()
        own.shutdown()
        reused.server_close()
        own.server_close()
    assert reused_rows[0]["status"] == "GREEN", reused_rows
    assert own_rows[0]["status"].startswith("KILLED"), own_rows
    assert len(found["answering"]) == 1

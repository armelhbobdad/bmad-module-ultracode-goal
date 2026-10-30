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

import functools
import http.server
import importlib.util
import json
import os
import socket
import struct
import subprocess
import sys
import threading
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


@pytest.mark.parametrize("url", ["http://", "http://localhost:notaport", "http://localhost:70000"])
def test_a_url_with_no_host_or_a_bad_port_is_refused(url, capsys):
    assert probe_servers.main(["--url", url]) == 2
    assert "REFUSED" in capsys.readouterr().err


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


_V4 = (socket.AF_INET, socket.inet_pton(socket.AF_INET, "127.0.0.1"))
_V6 = (socket.AF_INET6, socket.inet_pton(socket.AF_INET6, "::1"))


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
        # The same, from one folder: a server's forked workers.
        ([(socket.AF_INET, "127.0.0.1", 3002, "444", "/a"), (socket.AF_INET, "0.0.0.0", 3002, "555", "/a")],
         _V4, "/a"),
        # A socket no readable process holds (another user's server) could be the one that answered.
        ([(socket.AF_INET, "127.0.0.1", 3002, "444", "/a"), (socket.AF_INET, "0.0.0.0", 3002, "555", None)],
         _V4, None),
    ],
    ids=["v6-wildcard", "v4-mapped", "v4-wildcard", "v4-wildcard-for-v6", "other-address", "two-folders",
         "one-folder", "unread-holder"],
)
def test_a_folder_is_named_only_when_every_socket_that_could_answer_shares_it(tmp_path, listeners, reached, expected):
    proc = _fake_proc(tmp_path, listeners)
    assert probe_servers._cwd_of_listener(3002, proc, reached) == expected


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

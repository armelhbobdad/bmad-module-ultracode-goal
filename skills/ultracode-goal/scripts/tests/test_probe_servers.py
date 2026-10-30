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

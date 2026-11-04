"""The native-owner fixture must terminate on remote EOF even with local stdin open."""
import os
import socket
import subprocess
import sys
from pathlib import Path


def test_proxy_closes_cleanly_on_owner_eof(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fakes" / "codex_cli.py"
    with socket.socket() as owner:
        owner.bind(("127.0.0.1", 0))
        owner.listen()
        owner.settimeout(5)
        env = dict(os.environ, FAKE_CODEX_TRACE=str(tmp_path / "trace"),
                   FAKE_CODEX_PORT=str(owner.getsockname()[1]))
        proxy = subprocess.Popen(
            [sys.executable, str(fixture), "--original", "app-server", "proxy"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        try:
            connection, _ = owner.accept()
            with connection:
                connection.sendall(b"last native frame")
                connection.shutdown(socket.SHUT_WR)
            # stdin stays open until after the native process exits.
            assert proxy.wait(timeout=5) == 0
            out, err = proxy.communicate()
            assert out == b"last native frame" and not err
        finally:
            if proxy.poll() is None:
                proxy.kill()
            proxy.communicate()

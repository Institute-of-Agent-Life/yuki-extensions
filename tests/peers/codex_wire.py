"""Run selected driver tests and observe the real loopback app-server connection."""
import argparse
import json
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import pytest
from websockets.asyncio.server import ServerConnection
from yuki_agent_connector.drivers import DriverError
from yuki_agent_connector.drivers.codex import CodexDriver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("nodes", nargs="+")
    args = parser.parse_args()
    cases = {}

    class Capture:
        def pytest_runtest_setup(self, item):
            cases[item.nodeid] = {"transcript": []}
            self.events = cases[item.nodeid]["transcript"]

        def pytest_runtest_logreport(self, report):
            cases[report.nodeid][report.when] = report.outcome

    observer = Capture()
    receive, send, execute = ServerConnection.recv, ServerConnection.send, CodexDriver.execute

    async def recv(socket, *args, **kwargs):
        raw = await receive(socket, *args, **kwargs)
        observer.events.append({"from_driver": json.loads(raw)})
        return raw

    async def transmit(socket, raw, *args, **kwargs):
        await send(socket, raw, *args, **kwargs)
        observer.events.append({"from_owner": json.loads(raw)})

    async def dispatch(driver, command):
        entry = {"instance": driver.spec.id, "input": command}
        observer.events.append(entry)
        try:
            entry["result"] = await execute(driver, command)
        except DriverError as exc:
            entry["error"] = {"code": exc.code, "uncertain": exc.uncertain, "details": exc.details}
            raise
        return entry["result"]

    with patch.object(ServerConnection, "recv", recv), patch.object(ServerConnection, "send", transmit), patch.object(CodexDriver, "execute", dispatch):
        code = pytest.main(["-q", *args.nodes], plugins=[observer])
    args.output.write_bytes((json.dumps({"distribution": version("yuki-agent-connector"),
        "cases": cases}, indent=2) + "\n").encode())
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())

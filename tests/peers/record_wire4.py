"""Observe both directions at the socket of the original reconnect test."""
import argparse
import json
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import pytest
from websockets.asyncio.server import ServerConnection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("nodeid")
    parser.add_argument("expected_version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if version("yuki-agent-connector") != args.expected_version:
        raise ValueError("unexpected installed distribution")
    frames = []
    receive, send = ServerConnection.recv, ServerConnection.send

    async def recorded_receive(socket, *arguments, **kwargs):
        value = await receive(socket, *arguments, **kwargs)
        frames.append({"direction": "from_connector", "body": json.loads(value)})
        return value

    async def recorded_send(socket, value, *arguments, **kwargs):
        await send(socket, value, *arguments, **kwargs)
        frames.append({"direction": "to_connector", "body": json.loads(value)})

    with patch.object(ServerConnection, "recv", recorded_receive), patch.object(ServerConnection, "send", recorded_send):
        code = pytest.main(["-q", args.nodeid])
    args.output.write_bytes((json.dumps(frames, indent=2, sort_keys=True) + "\n").encode())
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())

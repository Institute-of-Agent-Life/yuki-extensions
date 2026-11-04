"""Exercise a real Connector installation with a disposable device journal."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

from yuki_agent_connector import PROTOCOL_VERSION, __version__
from yuki_agent_connector.journal import Journal


def command(key):
    return {
        "type": "command",
        "id": key,
        "instance_id": "native-original",
        "action": "prompt",
        "arguments": {"prompt": "original input"},
    }


def seed(original, copied):
    assert __version__ == "0.4.3"
    original.mkdir()
    journal = Journal(original / "journal.db", namespace="fixture-device-a")
    try:
        for key in ("unknown-original", "confirmed-original"):
            assert journal.begin(command(key)) is None
        journal.complete("confirmed-original", {"type": "response", "id": "confirmed-original", "result": {
            "status": "completed", "admitted": True, "session_id": "original-session", "execution_id": "original-turn",
        }})
        copy = sqlite3.connect(copied)
        try:
            journal.db.backup(copy)
        finally:
            copy.close()
        return {"version": __version__, "operations": journal.db.execute("SELECT COUNT(*) FROM operations").fetchone()[0]}
    finally:
        journal.close()


def reopen(copied, expected_version):
    assert __version__ == expected_version and PROTOCOL_VERSION == 4
    assert importlib.util.find_spec("yuki") is None
    journal = Journal(copied, namespace="fixture-device-a")
    receipts = {}
    try:
        for key in ("unknown-original", "confirmed-original"):
            receipts[key] = journal.begin(command(key))["result"]
            try:
                journal.begin({**command(key), "arguments": {"prompt": "changed input"}})
            except ValueError as exc:
                assert "parameters" in str(exc)
            else:
                raise AssertionError("same-key different parameters accepted")
        assert receipts["unknown-original"]["status"] == "unknown"
        assert receipts["confirmed-original"]["status"] == "completed"
        assert receipts["confirmed-original"]["execution_id"] == "original-turn"
        count = journal.db.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        assert count == 2
    finally:
        journal.close()
    try:
        other = Journal(copied, namespace="fixture-device-b")
    except ValueError as exc:
        assert "another device" in str(exc)
    else:
        other.close()
        raise AssertionError("another device reused this journal")
    return {"version": __version__, "protocol": PROTOCOL_VERSION, "operations": count, "receipts": receipts,
            "different_device_rejected": True, "changed_parameters_rejected": True}


if __name__ == "__main__":
    if sys.argv[1] == "seed":
        result = seed(Path(sys.argv[2]), Path(sys.argv[3]))
    elif sys.argv[1] == "reopen":
        result = reopen(Path(sys.argv[2]), sys.argv[3])
    else:
        raise ValueError("unknown upgrade probe")
    print(json.dumps(result))

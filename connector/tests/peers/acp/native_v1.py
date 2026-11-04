"""Isolated ACP peer. All observations are taken at the subprocess pipes."""
import json
import os
import sys
from pathlib import Path

trace = Path("native.jsonl")
pending = {}


def record(value):
    with trace.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value) + "\n")


def send(value):
    message = {"jsonrpc": "2.0", **value}
    record({"from_agent": message})
    print(json.dumps(message), flush=True)


record({"argv": sys.argv[1:], "cwd": os.getcwd(), "pid": os.getpid()})
mode = os.environ["PEER_LOAD_MODE"]
for line in sys.stdin:
    message = json.loads(line)
    record({"from_driver": message})
    method = message.get("method")
    params = message.get("params", {})
    result = {}
    if method is None:
        continue
    if method == "initialize":
        result = {"protocolVersion": 1, "agentCapabilities": {
            "loadSession": mode != "absent", "sessionCapabilities": {"list": {}},
        }}
    elif method == "session/list":
        result = {"sessions": [{"sessionId": "stored", "cwd": os.getcwd()}]}
        if Path("exit-now").exists():
            send({"id": message["id"], "result": result})
            sys.exit(23)
    elif method == "session/load" and mode == "reject":
        send({"id": message["id"], "error": {"code": -32602, "message": "load refused"}})
        continue
    elif method == "session/new":
        result = {"sessionId": "second"}
    elif method == "session/prompt":
        session = params["sessionId"]
        pending[session] = message["id"]
        send({"method": "session/update", "params": {"sessionId": session, "update": {
            "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "begun"},
        }}})
        if session == "second":
            send({"id": 100000, "method": "session/request_permission", "params": {
                "sessionId": session,
                "toolCall": {"toolCallId": "native-tool", "status": "pending"},
                "options": [{"optionId": "once", "name": "Allow", "kind": "allow_once"}],
            }})
        continue
    elif method == "session/cancel":
        send({"id": pending.pop(params["sessionId"]), "result": {"stopReason": "cancelled"}})
        continue
    if "id" in message:
        send({"id": message["id"], "result": result})

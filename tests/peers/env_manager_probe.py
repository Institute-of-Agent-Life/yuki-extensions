"""Read an unknown run and reconcile an unknown request through the original Manager."""
import asyncio
import json
from pathlib import Path
import sys

source, state = map(Path, sys.argv[1:3])
sys.path.insert(0, str(source / "src"))
from yuki.sandbox.persistent import PersistentManager
from yuki.workspace.store import WorkspaceStore


async def main():
    manager = PersistentManager(state / "manager", WorkspaceStore(state / "store"), "fixture-image",
                                "fixture-egress", "", state / "home")
    try:
        request = "00000000-0000-4000-8000-000000000020"
        read = await manager.handle({"method":"terminal_read","args":{"run_id":request},"request_id":"observation"})
        lookup = await manager.handle({"method":"get_code_run_by_request","args":{"request_id":request},"request_id":"reconcile"})
        assert read.get("error") == "run_not_found", read
        assert lookup == {"error":"unknown_request"}, lookup
        print(json.dumps({"missing_run":read,"original_request":lookup}))
    finally:
        await manager.close()


if __name__ == "__main__":
    asyncio.run(main())

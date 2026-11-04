"""Drive two independent SDK processes over stdio and record observed frames."""
import asyncio
import copy
import json


async def crosswire(consumer_argv, host_argv, cwd, binding, index, errors, env):
    processes = {}
    transcript = []

    async def read(sender):
        line = await processes[sender].stdout.readline()
        if not line:
            raise RuntimeError(f"{sender} exited before sending its frame")
        transcript.append({"from": sender, "line": line.decode().rstrip("\r\n")})
        return json.loads(line)

    async def send(target, frame, origin):
        line = json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
        transcript.append({"to": target, "origin": origin, "line": line})
        processes[target].stdin.write(line.encode() + b"\n")
        await processes[target].stdin.drain()

    try:
        for label, command in (("consumer", consumer_argv), ("producer_peer", host_argv)):
            processes[label] = await asyncio.create_subprocess_exec(
                *command, cwd=cwd, env=env, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        inbound = await read("producer_peer")
        outbound = await read("consumer")
        if inbound["id"] != outbound["id"] or {inbound["method"], outbound["method"]} != {"initialize"}:
            raise AssertionError("expected interleaved initialize requests with the same RPC id")
        # The first responses travel while the other direction still has an outstanding request.
        await send("consumer", inbound, "producer_peer")
        await send("producer_peer", outbound, "consumer")
        consumer_reply = await read("consumer")
        host_reply = await read("producer_peer")
        await send("consumer", host_reply, "producer_peer")
        await send("producer_peer", consumer_reply, "consumer")

        agreed = host_reply["result"]
        assert consumer_reply == host_reply and host_reply["id"] == inbound["id"]
        assert agreed["namespace"] == binding["namespace"] and agreed["grants"] == binding["grants"]
        assert agreed["features"] == ["initialize"] and agreed["extension_points"] == []
        assert agreed["schema_revision"] == index["schema_revision"]
        assert agreed["manifest_revision"] == binding["manifest_revision"]
        assert agreed["version"] == {"major": 1, "minor": 0}
        assert agreed["method_revisions"] == [{"name": "initialize", "revision": index["methods"]["initialize"]["revision"]}]
        assert outbound["params"]["optional_features"] == ["ext002.optional"]

        outcomes = {}
        for target in processes:
            cases = {}
            for reason in ["method_not_found", "unsupported_version", "missing_feature", "manifest_mismatch",
                           "duplicate_declaration", "optional_fields"]:
                request = copy.deepcopy(outbound)
                request["id"] = "test-" + reason
                params = request["params"]
                if reason == "method_not_found":
                    request["method"] = "ext002.undeclared"
                elif reason == "unsupported_version":
                    params["versions"] = {"min": {"major": 9, "minor": 0}, "max": {"major": 9, "minor": 0}}
                elif reason == "missing_feature":
                    params["required_features"].append("ext002.unavailable")
                elif reason == "manifest_mismatch":
                    params["manifest_revision"] += "-replaced"
                elif reason == "duplicate_declaration":
                    params["declarations"] = [{"kind": "tool", "name": "fixture", "revision": 1}] * 2
                else:
                    # Unknown fields cannot redefine the binding or grant new capabilities.
                    params.update(namespace="foreign", grants=["admin"], future_optional=True)
                    params.pop("optional_features")
                await send(target, request, "fault-probe" if reason != "optional_fields" else "optional-probe")
                response = await read(target)
                assert response["id"] == request["id"]
                if reason == "optional_fields":
                    assert response["result"] == agreed
                else:
                    assert response["error"] == {"code": errors[reason], "message": reason}
                cases[reason] = response
            outcomes[target] = cases
        for proc in processes.values():
            proc.stdin.close()
        for proc in processes.values():
            if await proc.wait() != 0:
                raise RuntimeError("peer failed: " + (await proc.stderr.read()).decode())
        accepted = json.loads(await processes["consumer"].stderr.read())
        assert accepted == {"id": outbound["id"], "accepted": agreed}
        return {"transcript": transcript, "consumer_receipt": accepted, "faults": outcomes,
                "producer_peer_exit_code": processes["producer_peer"].returncode}
    finally:
        for proc in processes.values():
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

"""Offline Desktop callsite and legacy API compatibility probe."""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

from desktop_tooling import parser_tools
from oracle import load_oracle


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verified_sources(directory, work, pin):
    bundle = directory / "desktop-source.zip"
    if sha(bundle.read_bytes()) != pin["source_zip_sha256"]:
        raise ValueError("Desktop source archive hash mismatch")
    sources = {}
    with zipfile.ZipFile(bundle) as archive:
        if sorted(archive.namelist()) != sorted(pin["git_blobs"]):
            raise ValueError("Desktop tree differs from pinned blob inventory")
        for name, blob in pin["git_blobs"].items():
            data = archive.read(name)
            if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != blob:
                raise ValueError("Desktop blob mismatch: " + name)
            dest = work / name
            if not dest.resolve().is_relative_to(work.resolve()):
                raise ValueError("unsafe source path")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            sources[name] = data.decode("utf-8")
    return sources


def contracts(sources, pin):
    source = json.loads(sources["contracts/source.json"])
    spec = {}
    for label, entry in [("client", source), ("admin", source["admin"])]:
        content = sources["contracts/" + entry["file"]].encode()
        if (entry["commit"] != pin["backend"] or sha(content) != entry["sha256"]
                or entry["sha256"] != pin[label + "_sha256"]):
            raise ValueError("Desktop " + label + " contract hash or backend mismatch")
        spec[label] = json.loads(content)
    if source["apiRevision"] != 9:
        raise ValueError("unexpected Desktop revision")
    return spec


def diff(before, after, path=()):
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        rows = []
        for key in sorted(before.keys() | after.keys()):
            if key in before and key in after:
                rows.extend(diff(before[key], after[key], (*path, key)))
            else:
                rows.append({"path": [*path, key], "before": before.get(key), "after": after.get(key),
                             "disposition": "review-required"})
        return rows
    equal_set = path[-1:] == ("enum",) and isinstance(before, list) and isinstance(after, list)
    if equal_set and sorted(before) == sorted(after):
        return [{"path": list(path), "before": before, "after": after, "disposition": "enum-order-only"}]
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [row for i, (old, new) in enumerate(zip(before, after, strict=True))
                for row in diff(old, new, (*path, i))]
    return [{"path": list(path), "before": before, "after": after, "disposition": "review-required"}]


def check_surface(pinned, target, sources):
    for label, spec in pinned.items():
        for route, methods in spec["paths"].items():
            for verb in methods:
                if verb not in target[label]["paths"].get(route, {}):
                    raise ValueError(f"missing declared operation {verb} {route}")
    client = target["client"]
    cancel = client["paths"]["/client/v1/works/{identity}/cancel"]["post"]
    ref = cancel["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    body = client["components"]["schemas"][ref]
    for field in ("expected_revision", "request_id"):
        if field not in body["properties"] or field not in body["required"]:
            raise ValueError("missing required Work cancel input: " + field)
    history = client["paths"]["/client/v1/conversations/{identity}/events"]["get"]
    if not {"before", "after"} <= {p["name"] for p in history["parameters"]}:
        raise ValueError("missing business cursor")
    witness = {}
    files = {
        "api/client": ["X-Yuki-Client", "Authorization: `Bearer ${this.token}`", "X-Yuki-Entry",
                       "this.base}/${this.namespace}/${path}", "body.problem ?? {}", "body.data",
                       "body: JSON.stringify(body)"],
        "outbox/work-commands": ["works/${command.workId}/cancel", "expected_revision: command.expectedRevision",
                                 "request_id: item.requestId", "requests/${id}", "original.payload_hash"],
        "media/uploads": ["client.response(`uploads?${query}`", "method: 'POST'", "'Content-Type': 'application/octet-stream'",
                          "body: stream as unknown as BodyInit", "request_id: id, ...params", "size: String(item.size)",
                          "sha256: item.sha256", "filename: item.filename", "kind: item.kind", "requests/${id}"],
        "api/stream": ["hint(event, JSON.parse(data.join", "startsWith('event:')", "startsWith('data:')"],
        "connections": ["query.set('after', String(route.after))", "query.set('before', String(route.before))",
                        "events?${query}", "this.verifyWorkCommand(id, item.requestId)", "'stream?works=active'"],
        "outbox/index": ["attachments: body.attachments", "client.post<MessageResult>('messages', row.body)"],
    }
    for stem, required in files.items():
        name = "src/main/" + stem + ".ts"
        text = sources[name]
        witness[name] = []
        for fact in required:
            line = text.find(fact)
            if line < 0:
                raise ValueError(f"consumer requirement missing in {name}: {fact}")
            witness[name].append({"line": text.count("\n", 0, line) + 1, "source": fact})
    stream = sources["src/main/api/stream.ts"]
    if re.search(r"startsWith\(['\"]id:", stream):
        raise ValueError("SSE id must not replace a business cursor")
    return witness


def check_faults(pinned, core, sources, pin):
    failures = {}
    for mutation in ["wrong-desktop-hash", "drop-used-endpoint", "drop-expected-revision",
                     "change-upload-encoding", "use-sse-sequence-as-cursor"]:
        spec = copy.deepcopy(core)
        files = dict(sources)
        try:
            if mutation == "wrong-desktop-hash":
                contracts(files, {**pin, "admin_sha256": "0" * 64})
            elif mutation == "drop-used-endpoint":
                del spec["client"]["paths"]["/client/v1/works/{identity}/cancel"]["post"]
            elif mutation == "drop-expected-revision":
                del spec["client"]["components"]["schemas"]["WorkCancelBody"]["properties"]["expected_revision"]
            elif mutation == "change-upload-encoding":
                name = "src/main/media/uploads.ts"
                files[name] = files[name].replace("application/octet-stream", "multipart/form-data")
            else:
                name = "src/main/connections.ts"
                files[name] = files[name].replace("String(route.after)", "String(lastSseSequence)")
            check_surface(pinned, spec, files)
        except ValueError as exc:
            failures[mutation] = str(exc)
        else:
            raise AssertionError("mutation survived: " + mutation)
    return failures


def route_sites(routes, specs):
    """Link source expressions to contract paths; dynamic helpers retain their raw inputs."""
    rows = []
    for label, spec in specs.items():
        for path, methods in spec["paths"].items():
            namespace, tail = path.split("/v1/", 1)
            url = re.sub(r"\{[^{}]+\}", "{}", tail)
            sites = []
            for record in routes:
                file = record["file"]
                value = record["pattern"].split("?")[0]
                if value == "computer/{}" and tail in ("computer/sleep", "computer/wake"):
                    value = tail
                if value != url:
                    continue
                if namespace == "/admin" and not tail.startswith("models"):
                    continue
                if file.endswith("agent-connector.ts") or "/api/client.ts" in file:
                    continue
                sites.append(record)
            rows.append({"namespace": label, "url": path, "declared_methods": sorted(methods),
                         "source_expression_matches": sites})
    return rows


def run(root: Path, output: Path):
    directory = root / "compat/desktop"
    pin = json.loads((directory / "source.lock").read_bytes())
    work = output / "work"
    work.mkdir()
    sources = verified_sources(directory, work, pin)
    desktop = contracts(sources, pin)
    tag_ref = pin["release"]["tag_source_json"]
    tag_bytes = (directory / "beta-source.json").read_bytes()
    tag_source = json.loads(tag_bytes)
    tag_blob = hashlib.sha1(b"blob " + str(len(tag_bytes)).encode() + b"\0" + tag_bytes).hexdigest()
    if (sha(tag_bytes) != tag_ref["sha256"] or tag_blob != tag_ref["blob"]
            or tag_source["commit"] != tag_ref["backend"] or tag_source["sha256"] != tag_ref["client_sha256"]):
        raise ValueError("published tag source manifest mismatch")
    core_pin, index, goldens = load_oracle(root)
    core = {label: goldens[label + "-openapi.json"] for label in ("client", "admin")}
    changes = {k: diff(desktop[k], core[k]) for k in desktop}
    if any(change["disposition"] == "review-required" for items in changes.values() for change in items):
        raise ValueError("unclassified OpenAPI drift: " + repr(changes))

    node, compiler = parser_tools(root, work)
    parsed = work / "parsed.json"
    subprocess.run([node, directory / "calls.cjs", compiler, work, parsed], check=True, timeout=180)
    ast = json.loads(parsed.read_bytes())
    if ast["typescript"] != pin["typescript"]["version"]:
        raise ValueError("parser version disagrees with Desktop")
    inventory = ast["inventory"]
    counts = {group: sum(c["group"] == group for c in inventory)
              for group in ("renderer", "preload", "ipc", "connector-cli", "http")}
    if not all(counts.values()) or not ast["dto"]:
        raise ValueError("incomplete source inventory")
    for dto in ast["dto"]:
        names = [k for k, spec in desktop.items() if dto["schema"] in spec["components"]["schemas"]]
        dto["present_in"] = names

    witness = check_surface(desktop, core, sources)
    negatives = check_faults(desktop, core, sources, pin)
    route_index = route_sites(ast["routes"], desktop)
    report = {"source": {k: pin[k] for k in ("repository", "commit", "backend", "source_zip_sha256",
                                                "client_sha256", "admin_sha256")},
              "core": core_pin, "source_package_version": json.loads(sources["package.json"])["version"],
              "release": {**pin["release"], "tag_client_revision": tag_source["apiRevision"]},
              "packaged_UI_exercised": False,
              "cases": {"H30": {"calls": inventory, "dto": ast["dto"], "api_routes": route_index,
                               "consumer_fields": witness, "ordered_payload": ast["fingerprint"],
                               "rejected_mutations": negatives}}}
    evidence = output / "desktop-callsite-pin.json"
    evidence.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    return "desktop-surface-diff.json", {"scope": "pinned Desktop sources and two legacy OpenAPIs",
        "callsite_sha256": sha(evidence.read_bytes()), "source_counts": counts, "dto_references": len(ast["dto"]),
        "source_commit": pin["commit"], "desktop_backend": pin["backend"], "core_source": core_pin["producer_commit"],
        "contracts": {k: {"desktop": pin[k + "_sha256"], "core": index["goldens"][f"protocol/baseline-v4/{k}-openapi.json"],
                          "changes": changes[k]} for k in desktop},
        "faults": negatives, "handoff": "docs/desktop-handoff.md", "packaged_UI_exercised": False}

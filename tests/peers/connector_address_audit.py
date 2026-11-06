"""Bind new Windows address evidence to the exact eleven historical CI receipts."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root, evidence, archive, output):
    output.mkdir()
    pin = json.loads((root / "compat/wire4/address_cases/source.lock.json").read_bytes())
    assert "sha256:" + sha(archive) == pin["github_artifact"]["digest"]
    report = json.loads((evidence / "connector-address-continuity.json").read_bytes())
    manifest = json.loads((evidence / "manifest.json").read_bytes())
    assert report["status"] == manifest["status"] == "PASS"
    for name, digest in manifest["files"].items(): assert sha(evidence / name) == digest
    runtime = json.loads((root / "compat/wire4/address_cases/consumer.lock.json").read_bytes())
    for name, digest in runtime["files"].items(): assert sha(root / name) == digest
    assert report["runtime_bindings"] == runtime and len(runtime["files"]) == 19
    cases = report["cases"]
    assert len(cases) == 15
    comparisons = []
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist()))
        assert all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in z.namelist())
        xml = z.read("integration.xml")
        assert hashlib.sha256(xml).hexdigest() == pin["junit_sha256"]
        tests = [t for t in ET.fromstring(xml).iter("testcase") if t.attrib["classname"].endswith("test_connector_address_e2e")]
        assert len(tests) == 11 and all(not list(t) for t in tests)
        for item in pin["receipts"]:
            raw = z.read(item["path"])
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
            assert (root / "compat/wire4/address_cases" / item["file"]).read_bytes() == raw
            old = json.loads(raw);facts = old["facts"];node = old["nodeid"]
            assert old["revision"] == pin["baseline"]
            if "test_server_cli_only_saves_original_installation" in node:
                matches = [c for c in cases if c["case"] == "save-original-installation" and c["expected_endpoint"] == facts["expected_endpoint"]]
                assert facts["exit_code"] == 0 and facts["original_fields_preserved"] and not facts["journal_created"]
                assert len(matches) == 1 and matches[0]["original_fields_preserved"] and not matches[0]["journal_created"]
            elif "test_server_cli_keeps_remote_tls_requirement" in node:
                matches = [c for c in cases if c["case"] == "remote-TLS-required" and c["target"] in node]
                assert facts["exit_code"] == 1 and len(matches) == 1
                assert matches[0]["exit_code"] == 1 and matches[0]["config_unchanged"]
            elif "test_cli_start_upgrades_old_url_namespace_before_connecting" in node:
                matches = [c for c in cases if c["case"] == "upgrade-original-url-namespace" and c["receipt_version"] == facts["receipt_version"]]
                assert facts["connected"] and facts["same_device_reopen_preserved"] and len(matches) == 1
                new = matches[0]
                assert new["same_device_reopen"] and new["original_unconfirmed_event_preserved"]
                for value in [facts["after"], new["after"]]:
                    assert [r[0] for r in value["operations"]] == ["original-completed", "original-pending"]
                    assert [json.loads(r[4])["status"] for r in value["operations"]] == ["succeeded", "running"]
                    assert value["events"][0][1] == "original-unconfirmed-event"
            elif "test_cli_start_rejects_another_device_without_rewriting_original_evidence" in node:
                matches = [c for c in cases if c["case"] == "different-device-rejected-before-connect"]
                assert facts["exit_code"] == 1 and facts["original_evidence_preserved"] and len(matches) == 1
                assert matches[0]["exit_code"] == 1 and matches[0]["original_evidence_preserved"]
            else:
                assert node.endswith("::test_running_connector_keeps_original_shell_when_address_is_saved")
                matches = [c for c in cases if c["case"] == "live-shell-kept-while-saving-address"]
                assert facts["response"]["input_delivered"] and facts["original_socket_retained"] and len(matches) == 1
                assert matches[0]["input_delivered"] and matches[0]["original_socket_retained"]
                assert matches[0]["receipt"]["exit_code"] == 0
            comparisons.append({"historical_nodeid": node, "historical_receipt_sha256": item["sha256"],
                                "new_case": matches[0], "result": "MATCHED"})
    replay = next(c for c in cases if c["case"] == "same-device-new-WSS-reuses-originals")
    assert set(replay["pending_before_restart"]) == set(replay["second_events"])
    assert not replay["pending_after_ACK"] and "already-acked" not in replay["second_events"]
    assert replay["native_launches"] == 1 and replay["unknown_receipt"]["status"] == "unknown"
    assert replay["first_TLS"] and replay["second_TLS"]
    service = next(c for c in cases if c["case"] == "native-stopped-user-task-not-started-by-address-change")
    assert service["status"] == "PASS" and not service["before"]["installed"]
    assert service["installed_disabled"]["installed"] and not service["installed_disabled"]["running"]
    assert service["after_address_change"] == service["installed_disabled"]
    assert not service["after_cleanup"]["installed"] and not service["start_invoked"]
    wire = json.loads((evidence / "wire.json").read_bytes())
    native_prompts = [v for v in wire if v["direction"] == "to_connector" and v["frame"].get("action") == "exec"]
    assert len(native_prompts) == 1
    (output / "old-comparison.json").write_text(json.dumps(comparisons, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"status": "VERIFIED_WINDOWS_CANDIDATE", "native_manifest_sha256": sha(evidence / "manifest.json"),
        "native_source_snapshot_sha256": manifest["source_snapshot_sha256"], "historical_artifact_digest": pin["github_artifact"]["digest"],
        "historical_commit": pin["baseline"], "historical_receipts_matched": len(comparisons),
        "current_cases": len(cases), "unchanged_runtime_bindings": len(runtime["files"]),
        "wheel_sha256": report["wheel_sha256"], "wire_sha256": sha(evidence / "wire.json"),
        "native_exec_commands": len(native_prompts), "native_launches": 1,
        "old_PID_retained": replay["original_pid"], "replayed_exact_pending_events": replay["second_events"],
        "unknown_remains_unknown": True, "TLS": [replay["first_TLS"], replay["second_TLS"]],
        "native_task_cleanup_verified": True, "temporary_task_name": service["task_name"],
        "not_claimed": ["core Work authority acceptance", "public producer/consumer publication", "production deployment"]}
    (output / "analysis.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    files = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps({"task": "EXT-070", "status": "PASS", "platform": "HJW Windows", "files": files}, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "matched": 11, "cases": 15}))


if __name__ == "__main__":
    audit(*map(Path, sys.argv[1:5]))

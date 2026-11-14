"""Prepare one registered plugin for its exact version tag. No network publication here."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from zipfile import ZipFile

from package import build, sha256
from units import inside, load_catalog


def prepare(root, tag, output, *, candidate=None):
    match = re.fullmatch(r"plugin/([a-z][a-z0-9-]*)/v(\d+\.\d+\.\d+)", tag)
    if not match:
        raise ValueError("invalid plugin release tag")
    unit_id, version = match.groups()
    records = json.loads((root / "catalog/verified.json").read_bytes())
    if tag not in records and candidate is None:
        raise ValueError("no registered release for this tag")
    record = records[tag] if candidate is None else candidate
    unit = load_catalog(root)[unit_id]
    if unit["kind"] != "plugin" or unit["ecosystem"] != "rust":
        raise ValueError("unsupported release unit")
    profile = root / "releases" / unit_id / version
    contract = record.get("sdk_contract", "compat/stable-1.0/source.lock.json")
    sdk_path = inside(root, contract)
    sdk = json.loads(sdk_path.read_bytes())
    inputs = record["inputs"]
    if any(sha256(inside(root, path)) != expected for path, expected in inputs.items()):
        raise ValueError("release input differs from the verified sources")
    profile_files = ("Cargo.lock", "Cargo.toml", "plugin.toml")
    required = {contract, f"catalog/{unit_id}.json",
                *(f"releases/{unit_id}/{version}/{f}" for f in profile_files)}
    source = inside(root, unit["path"])
    files = [p for directory in ("src", "tests") for p in (source / directory).rglob("*")
             if p.is_file() and not p.name.startswith("._")]
    files += [source / n for n in ["rust-toolchain.toml", *unit["notices"]]]
    required.update(p.relative_to(root).as_posix() for p in files)
    if set(inputs) != required:
        raise ValueError("incomplete release source inventory")
    locked = tomllib.loads((profile / "Cargo.lock").read_text(encoding="utf-8"))["package"]
    dependency, = (p for p in locked if p["name"] == "yuki-plugin-sdk")
    if (not sdk["published"] or dependency["version"] != sdk["sdk"]["rust"]
            or dependency["checksum"] != sdk["rust_crate_sha256"]):
        raise ValueError("release SDK does not match the public contract")
    with tempfile.TemporaryDirectory(prefix="yuki-release-") as tmp:
        stage = Path(tmp)
        package = stage / unit["path"]
        for p in files:
            dest = package / p.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
        for name in profile_files:
            shutil.copyfile(profile / name, package / name)
        if tomllib.loads((package / "plugin.toml").read_text())["version"] != version:
            raise ValueError("runtime version differs from tag")
        unit.update(version=version, tag_prefix=f"plugin/{unit_id}/v")
        if "runtime_files" in record:
            unit["runtime_files"] = record["runtime_files"]
        unit["source"] = {**unit["source"], "sdk_contract": contract,
                          "release_inputs_sha256": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()}
        (stage / "catalog").mkdir()
        (stage / "catalog" / f"{unit_id}.json").write_text(json.dumps(unit), encoding="utf-8")
        stage_contract = inside(stage, contract)
        stage_contract.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sdk_path, stage_contract)
        crate = f"yuki-plugin-sdk-{sdk['sdk']['rust']}.crate"
        shutil.copyfile(sdk_path.with_name(crate), stage_contract.with_name(crate))
        shutil.copytree(root / "ci", stage / "ci", ignore=shutil.ignore_patterns("._*", "__pycache__"))
        manifest = build(stage, unit_id, output)
    components = [{"type": "library", "name": p["name"], "version": p["version"],
                   "hashes": [{"alg": "SHA-256", "content": p["checksum"]}]} for p in locked if "checksum" in p]
    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
            "metadata": {"component": {"type": "application", "name": unit_id, "version": version,
                                       "licenses": [{"license": {"id": unit["license"]}}]}}, "components": components}
    sbom_path = output / "sbom.cdx.json"
    sbom_path.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    manifest["artifacts"][sbom_path.name] = sha256(sbom_path)
    (output / "package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_qualification(root, tag):
    """Require the native receipt to cover exactly the sources in the release record."""
    record = json.loads((root / "catalog/verified.json").read_bytes()).get(tag)
    if record is None:
        raise ValueError("no registered release for this tag")
    folder = inside(root, record["qualification"])
    manifest = json.loads((folder / "manifest.json").read_bytes())
    source = json.loads((folder / "source.json").read_bytes())
    if (manifest["task"] != "EXT-043" or manifest["status"] != "PASS"
            or manifest["source_snapshot_sha256"] != sha256(folder / "source.json")
            or any(source.get(n) != h for n, h in record["inputs"].items())):
        raise ValueError("native qualification does not bind these release inputs")
    for name, digest in manifest["files"].items():
        if sha256(inside(folder, name)) != digest:
            raise ValueError("changed qualification artifact: " + name)
    proof = json.loads((folder / "extension-release-lock.json").read_bytes())
    if tag == "plugin/feishu/v0.1.0":
        verify_feishu(root, folder, record, manifest, proof)
        return
    if (proof["release_tag"] != tag or proof["status"] != "PASS"
            or set(proof["cases"]) != {"confirmed", "lost-second"}
            or not proof["host"]["published"]
            or not all(case["observed"]["post_restart_effects"] == 0 for case in proof["cases"].values())
            or not any("modified_registered_package" in case for case in proof["refused"])):
        raise ValueError("release lacks required native observations")


def verify_feishu(root, folder, record, manifest, proof):
    from feishu_release_check import DOMAINS, SCENARIOS, TAG

    contract = record["sdk_contract"]
    sdk_path = inside(root, contract)
    if sha256(sdk_path) != record["inputs"][contract]:
        raise ValueError("qualification SDK contract has changed")
    sdk = json.loads(sdk_path.read_bytes())
    if (proof["release_tag"] != TAG or proof["status"] != "PASS" or proof["published"]
            or not sdk["published"] or proof["host_source"] != sdk["source_commit"]
            or set(proof["platforms"]) != {"macos", "linux", "windows"}):
        raise ValueError("Feishu release lacks the three published-Host observations")
    inputs_digest = hashlib.sha256(json.dumps(record["inputs"], sort_keys=True).encode()).hexdigest()
    expected_cases = {f"{domain}-{case}": state for domain in DOMAINS for case, state in SCENARIOS.items()}
    for system, result in proof["platforms"].items():
        name = result["archive"]
        if (result["status"] != "PASS" or name != f"{system}.zip"
                or manifest["files"].get(name) != result["sha256"]):
            raise ValueError("Feishu qualification archive is missing")
        with ZipFile(inside(folder, name)) as archive:
            native_bytes = archive.read("manifest.json")
            native = json.loads(native_bytes)
            witness = json.loads(archive.read("feishu-stable.json"))
            package = json.loads(archive.read("packages/package-manifest.json"))
            binary = "yuki-feishu.exe" if system == "windows" else "yuki-feishu"
            if (hashlib.sha256(native_bytes).hexdigest() != result["manifest_sha256"]
                    or native["task"] != "EXT-043" or native["status"] != "PASS"
                    or native["source_snapshot_sha256"] != manifest["source_snapshot_sha256"]
                    or native["files"].get("feishu-stable.json") != hashlib.sha256(archive.read("feishu-stable.json")).hexdigest()
                    or witness["tag"] != TAG or witness["platform"] != system or witness["status"] != "PASS"
                    or witness["published"] or witness["paid_calls"] != 0
                    or witness["source_commit"] != sdk["source_commit"]
                    or witness["host_sha256"] != sdk["assets"]["host-" + system]["sha256"]
                    or witness["host_bundle_sha256"] != sdk["asset_sha256"]["yuki-plugin-base-1.1.0.zip"]
                    or witness["rust_sdk_sha256"] != sdk["rust_crate_sha256"]
                    or package["release_tag"] != TAG or package["published"]
                    or package["source"]["sdk_contract"] != record["sdk_contract"]
                    or package["source"]["release_inputs_sha256"] != inputs_digest
                    or witness["binary_sha256"] != package["artifacts"][binary]
                    or witness["binary_sha256"] != result["binary_sha256"]
                    or set(witness["cases"]) != set(expected_cases)):
                raise ValueError("Feishu qualification differs from the pinned release: " + system)
            for file, digest in package["artifacts"].items():
                if hashlib.sha256(archive.read("packages/" + file)).hexdigest() != digest:
                    raise ValueError("Feishu package member changed: " + file)
            for key, state in expected_cases.items():
                case = witness["cases"][key]
                raw = archive.read(key + "/delivery.json")
                actual = json.loads(raw)
                if (case["sha256"] != hashlib.sha256(raw).hexdigest() or case["state"] != state
                        or native["files"].get(key + "/delivery.json") != case["sha256"]
                        or actual["status"] != "PASS" or actual["state"] != state
                        or actual["paid_calls"] != 0 or not actual["original_receipt_reopened"]
                        or actual["plugin_sha256"] != witness["binary_sha256"]
                        or actual["host_sha256"] != witness["host_sha256"]
                        or (state == "failed" and (actual["native_requests"] or actual["token_issuances"]))):
                    raise ValueError("Feishu native replay differs: " + key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() != args.commit:
        parser.error("checkout must match the requested full commit")
    verify_qualification(root, args.tag)
    prepare(root, args.tag, args.out.resolve())

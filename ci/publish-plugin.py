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

from package import build, sha256
from units import inside, load_catalog


def prepare(root, tag, output):
    match = re.fullmatch(r"plugin/([a-z][a-z0-9-]*)/v(\d+\.\d+\.\d+)", tag)
    if not match:
        raise ValueError("invalid plugin release tag")
    unit_id, version = match.groups()
    records = json.loads((root / "catalog/verified.json").read_bytes())
    if tag not in records:
        raise ValueError("no registered release for this tag")
    record = records[tag]
    unit = load_catalog(root)[unit_id]
    if unit["kind"] != "plugin" or unit["ecosystem"] != "rust":
        raise ValueError("unsupported release unit")
    profile = root / "releases" / unit_id / version
    contract = "compat/stable-1.0/source.lock.json"
    sdk = json.loads((root / contract).read_bytes())
    inputs = record["inputs"]
    if any(sha256(inside(root, path)) != expected for path, expected in inputs.items()):
        raise ValueError("release input differs from the verified sources")
    required = {contract, f"catalog/{unit_id}.json", *(f"releases/{unit_id}/{version}/{f}" for f in
                ("Cargo.lock", "Cargo.toml", "plugin.toml"))}
    source = inside(root, unit["path"])
    files = [p for p in (source / "src").rglob("*") if p.is_file() and not p.name.startswith("._")]
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
        for name in ("Cargo.lock", "Cargo.toml", "plugin.toml"):
            shutil.copyfile(profile / name, package / name)
        if tomllib.loads((package / "plugin.toml").read_text())["version"] != version:
            raise ValueError("runtime version differs from tag")
        unit.update(version=version, tag_prefix=f"plugin/{unit_id}/v")
        unit["source"] = {**unit["source"], "sdk_contract": contract,
                          "release_inputs_sha256": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()}
        (stage / "catalog").mkdir()
        (stage / "catalog" / f"{unit_id}.json").write_text(json.dumps(unit), encoding="utf-8")
        shutil.copytree(root / "compat/stable-1.0", stage / "compat/stable-1.0", ignore=shutil.ignore_patterns("._*", "__pycache__"))
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
    if (proof["release_tag"] != tag or proof["status"] != "PASS"
            or set(proof["cases"]) != {"confirmed", "lost-second"}
            or not proof["host"]["published"]
            or not all(case["observed"]["post_restart_effects"] == 0 for case in proof["cases"].values())
            or not any("modified_registered_package" in case for case in proof["refused"])):
        raise ValueError("release lacks required native observations")


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

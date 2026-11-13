"""Use the public Windows base with the two original Actions distributions named in its freeze."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import zipfile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unpack(archive, pin, dest):
    if sha(archive) != pin["sha256"]:
        raise ValueError("fallback ZIP digest mismatch")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if set(names) != set(pin["members"]) or len(set(names)) != len(names):
            raise ValueError("fallback package inventory mismatch")
        for name in names:
            data = z.read(name)
            if Path(name).name != name or hashlib.sha256(data).hexdigest() != pin["members"][name]:
                raise ValueError("unsafe or changed fallback member")
            (dest / name).write_bytes(data)


def run(root, output):
    name = "extension-release-lock.json"
    sys.path.insert(0, str(root / "ci"))
    if os.environ.get("YUKI_STABLE_1_1_BUNDLE"):
        from feishu_release_check import native

        return "feishu-stable.json", native(root, output)
    env = ["YUKI_STABLE_BASE_ZIP", "YUKI_FROZEN_TELEGRAM_ZIP", "YUKI_FROZEN_WEB_FETCH_ZIP"]
    if sys.platform != "win32" or not all(os.environ.get(k) for k in env):
        return name, {"status": "BLOCKED", "reason": "HJW Windows and frozen inputs required", "inputs": env}
    prepare = runpy.run_path(str(root / "ci/publish-plugin.py"))["prepare"]
    joint = runpy.run_path(str(root / "tests/peers/joint_base.py"))["run"]
    lock = json.loads((root / "compat/stable-1.0/source.lock.json").read_bytes())
    freeze = json.loads((root / "compat/stable-1.0/freeze.json").read_bytes())
    for file, field in [("base-consumer-witness.json", "witness_sha256"), ("manifest.json", "acceptance_manifest_sha256")]:
        assert sha(root / freeze["evidence_directory"] / file) == freeze[field]
    archive, telegram, web = [Path(os.environ[k]).resolve() for k in env]
    assets = output / "packages"
    old = assets / "original"
    for unit, file in [("telegram", telegram), ("web-fetch", web)]:
        dest = old / unit
        dest.mkdir(parents=True)
        unpack(file, lock["windows_fallback"][unit], dest)
        assert sha(dest / f"yuki-{unit}.exe") == freeze["windows_replay"]["executable_sha256"][unit]
    shutil.copytree(old / "web-fetch", assets / "web-fetch")
    tag = "plugin/telegram/v0.1.0"
    package = prepare(root, tag, assets / "telegram")
    assert package["release_tag"] == tag and set(package["artifacts"]) >= {"LICENSE","Cargo.lock","sbom.cdx.json","yuki-telegram.exe"}
    refused = []
    for other in ["plugin/web-fetch/v0.1.0", "plugin/telegram/v0.2.0", "connector/v0.1.0"]:
        try:
            prepare(root, other, assets / "rejected")
        except ValueError as err:
            refused.append({"tag": other, "reason": str(err)})
        else:
            raise AssertionError("unregistered version promoted")
    try:
        unpack(telegram, lock["windows_fallback"]["web-fetch"], old / "web-fetch")
    except ValueError as err:
        refused.append({"swapped_archive": str(err)})
    else:
        raise AssertionError("substituted fallback accepted")
    # Change one release input in an isolated catalog. A registered tag alone
    # must not promote this build or mutate the previously verified package.
    bad = assets / "bad-source"
    (bad / "catalog").mkdir(parents=True)
    shutil.copyfile(root / "catalog/telegram.json", bad / "catalog/telegram.json")
    shutil.copyfile(root / "catalog/verified.json", bad / "catalog/verified.json")
    inputs = json.loads((root / "catalog/verified.json").read_bytes())[tag]["inputs"]
    for source in inputs:
        path = bad / source
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, path)
    (bad / "releases/telegram/0.1.0/Cargo.lock").write_bytes(b"changed")
    try:
        prepare(bad, tag, assets / "rejected")
    except ValueError as err:
        assert "release input differs" in str(err)
        refused.append({"modified_registered_package": str(err)})
    else:
        raise AssertionError("changed release sources accepted")
    assert not (assets / "rejected").exists()
    cases = {}
    for case in ["confirmed", "lost-second"]:
        area = assets / case
        joint(root, assets, archive, area, case, rollback=old)
        rows = json.loads((area / "result.json").read_bytes())
        change = json.loads((area / "rollback.json").read_bytes())
        assert change["from"] == package["artifacts"]["yuki-telegram.exe"] and change["from"] != change["to"]
        assert change["to"] == freeze["windows_replay"]["executable_sha256"]["telegram"]
        assert change["web_fetch"] == freeze["windows_replay"]["executable_sha256"]["web-fetch"]
        assert rows["post_restart_effects"] == 0 and rows["confirmed_offset_after_restart"] == 52
        assert rows["published"] and rows["sdk_by_package"]["telegram"] == lock["rust_crate_sha256"]
        with zipfile.ZipFile(output / (case + ".zip"), "x", zipfile.ZIP_DEFLATED) as z:
            for file in sorted(area.iterdir()):
                if file.is_file():
                    z.write(file, file.name)
        cases[case] = {"wire_zip_sha256": sha(output / (case + ".zip")), "replacement": change, "observed": rows}
    for file in ["sbom.cdx.json", "package-manifest.json"]:
        shutil.copyfile(assets / "telegram" / file, output / file)
    return name, {"status":"PASS","card_status":"VERIFIED_ON_PUBLISHED_BASE","release_tag":tag,
                  "extension_published":False,"host":lock,"original_freeze":freeze,"package":package["artifacts"],
                  "refused":refused,"cases":cases}

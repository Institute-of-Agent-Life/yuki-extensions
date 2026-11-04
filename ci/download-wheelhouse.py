"""Transport Windows wheels selected from an existing uv.lock without resolving upgrades."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import tomllib
from urllib.parse import unquote, urlparse
from urllib.request import urlopen


def compatible(filename):
    if filename.endswith(("-py3-none-any.whl", "-py2.py3-none-any.whl")):
        return True
    if not filename.endswith("-win_amd64.whl"):
        return False
    if re.search(r"-(?:py3-none|cp312-cp312)-win_amd64\.whl$", filename):
        return True
    match = re.search(r"-cp3(\d+)-abi3-win_amd64\.whl$", filename)
    return bool(match and int(match[1]) <= 12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lock", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    data = tomllib.loads(args.lock.read_text(encoding="utf-8"))
    selected, unavailable = [], []
    for package in data["package"]:
        if "registry" not in package.get("source", {}):
            continue
        choices = []
        for wheel in package.get("wheels", []):
            name = unquote(Path(urlparse(wheel["url"]).path).name)
            if compatible(name):
                choices.append({"name": package["name"], "version": package["version"],
                                "filename": name, "url": wheel["url"],
                                "sha256": wheel["hash"].removeprefix("sha256:")})
        if not choices:
            unavailable.append(package["name"])
        else:
            selected.append(sorted(choices, key=lambda x: x["filename"])[0])
    args.out.mkdir(parents=True, exist_ok=True)

    def download(wheel):
        path = args.out / wheel["filename"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != wheel["sha256"]:
            if urlparse(wheel["url"]).hostname != "files.pythonhosted.org":
                raise ValueError("unexpected wheel origin")
            with urlopen(wheel["url"], timeout=120) as response:
                content = response.read()
            if hashlib.sha256(content).hexdigest() != wheel["sha256"]:
                raise ValueError("locked wheel digest mismatch: " + wheel["filename"])
            path.write_bytes(content)
        return wheel

    with ThreadPoolExecutor(max_workers=4) as pool:
        wheels = list(pool.map(download, selected))
    args.manifest.write_text(json.dumps({"lock_sha256": hashlib.sha256(args.lock.read_bytes()).hexdigest(),
        "target": "CPython 3.12 win_amd64", "files": wheels,
        "no_windows_wheel_in_lock": unavailable}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"downloaded_and_hash_checked": len(wheels), "no_windows_wheel": unavailable}))


if __name__ == "__main__":
    main()

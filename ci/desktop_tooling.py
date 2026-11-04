"""Pinned parser and optional Windows Node runtime for the Desktop static probe."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
from urllib.request import urlopen
import zipfile


def inputs(root, cache, *, windows_node):
    pin = json.loads((root / "compat/desktop/source.lock").read_bytes())
    ts = pin["typescript"]
    version = pin["windows_node"]["version"]
    node_file = f"node-v{version}-win-x64.zip"
    downloads = [(f"typescript-{ts['version']}.tgz", ts["url"], "sha512",
                  base64.b64decode(ts["integrity"].removeprefix("sha512-")).hex())]
    if windows_node:
        downloads.append((node_file, f"https://nodejs.org/dist/v{version}/{node_file}", "sha256",
                          pin["windows_node"]["sha256"]))
    cache.mkdir(exist_ok=True, parents=True)
    paths = []
    for name, url, algorithm, expected in downloads:
        path = cache / name
        if not path.exists():
            with urlopen(url, timeout=90) as response:
                data = response.read()
            if hashlib.new(algorithm, data).hexdigest() != expected:
                raise ValueError("download digest mismatch: " + name)
            path.write_bytes(data)
        if hashlib.new(algorithm, path.read_bytes()).hexdigest() != expected:
            raise ValueError("cached tool digest mismatch: " + name)
        paths.append(path)
    return paths


def parser_tools(root, work):
    node = shutil.which("node")
    paths = inputs(root, Path(os.environ.get("YUKI_DESKTOP_TOOLS", work / "tools")),
                   windows_node=node is None and os.name == "nt")
    with tarfile.open(paths[0], "r:gz") as archive:
        compiler = work / "typescript.cjs"
        compiler.write_bytes(archive.extractfile("package/lib/typescript.js").read())
    if len(paths) == 2:
        node = work / "node.exe"
        with zipfile.ZipFile(paths[1]) as archive:
            node.write_bytes(archive.read(paths[1].stem + "/node.exe"))
    if not node:
        raise RuntimeError("the Desktop parser requires Node.js 22")
    return node, compiler

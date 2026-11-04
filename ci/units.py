"""Release-unit selection and production dependency boundary checks."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path, PurePosixPath


class BoundaryError(ValueError):
    pass


def inside(root: Path, value: str) -> Path:
    relative = PurePosixPath(value.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or ":" in value:
        raise BoundaryError(f"path must stay within its release unit: {value}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise BoundaryError(f"path escapes through a symlink: {value}")
    return target


def load_catalog(root: Path) -> dict[str, dict]:
    units = {}
    paths = set()
    prefixes = set()
    for manifest in sorted((root / "catalog").glob("*.json")):
        unit = json.loads(manifest.read_text(encoding="utf-8"))
        required = {"unit_id", "kind", "path", "ecosystem", "version", "tag_prefix",
                    "license", "notices", "source"}
        if required - unit.keys():
            raise BoundaryError(f"{manifest.name}: missing {sorted(required - unit.keys())}")
        ident = unit["unit_id"]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", ident) or ident in units:
            raise BoundaryError(f"invalid/duplicate unit_id: {ident}")
        if unit["kind"] not in {"plugin", "connector", "image", "tool"}:
            raise BoundaryError(f"invalid kind: {unit['kind']}")
        if unit["ecosystem"] not in {"python", "rust"}:
            raise BoundaryError(f"unsupported ecosystem: {unit['ecosystem']}")
        path = inside(root, unit["path"])
        if path == root.resolve() or not path.is_dir():
            raise BoundaryError(f"unit directory is missing/too broad: {unit['path']}")
        if any(path == p or path in p.parents or p in path.parents for p in paths):
            raise BoundaryError(f"release unit directories overlap: {unit['path']}")
        if unit["tag_prefix"] in prefixes:
            raise BoundaryError("release tag prefixes must be independent")
        if not unit["license"] or not unit["notices"] or not unit["source"]:
            raise BoundaryError(f"missing license/source attribution: {ident}")
        for notice in unit["notices"]:
            if not inside(path, notice).is_file():
                raise BoundaryError(f"missing notice: {ident}/{notice}")
        units[ident] = unit
        paths.add(path)
        prefixes.add(unit["tag_prefix"])
    return units


def _dependency_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "editable"} and isinstance(item, str):
                yield "path", item
            elif key in {"git", "branch", "rev", "tag", "url"} and isinstance(item, str):
                yield key, item
            else:
                yield from _dependency_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _dependency_values(item)
    elif isinstance(value, str):
        yield "text", value


def _validate_git_records(value):
    if isinstance(value, dict):
        if isinstance(value.get("git"), str):
            revision = value.get("rev", "")
            embedded = re.search(r"(?:@|[?&#]rev=)[0-9a-f]{40}(?:[&#\s]|$)", value["git"])
            if value.get("branch") or not (re.fullmatch(r"[0-9a-f]{40}", revision) or embedded):
                raise BoundaryError("each Git dependency must pin its own immutable commit")
        for item in value.values():
            _validate_git_records(item)
    elif isinstance(value, list):
        for item in value:
            _validate_git_records(item)


def validate_unit(root: Path, unit: dict) -> list[str]:
    path = inside(root, unit["path"])
    python = unit["ecosystem"] == "python"
    config = path / ("pyproject.toml" if python else "Cargo.toml")
    lock = path / ("uv.lock" if python else "Cargo.lock")
    if not config.is_file() or not lock.is_file():
        raise BoundaryError(f"{unit['unit_id']} needs its own manifest and lock")
    data = tomllib.loads(config.read_text(encoding="utf-8"))
    version = data.get("project" if python else "package", {}).get("version")
    if version != unit["version"]:
        raise BoundaryError(f"catalog version differs from package: {unit['unit_id']}")
    if not python and data.get("workspace"):
        raise BoundaryError("a release unit cannot require an outer Rust workspace")
    if not python:
        toolchain = path / "rust-toolchain.toml"
        if not toolchain.is_file():
            raise BoundaryError("Rust release unit needs its own pinned toolchain")
        channel = tomllib.loads(toolchain.read_text(encoding="utf-8")).get("toolchain", {}).get("channel", "")
        if not re.fullmatch(r"\d+\.\d+\.\d+", channel):
            raise BoundaryError("Rust toolchain must pin an exact stable version")
    for file in [config, lock]:
        parsed = tomllib.loads(file.read_text(encoding="utf-8"))
        _validate_git_records(parsed)
        for kind, value in _dependency_values(parsed):
            normal = value.replace("\\", "/").lower()
            if "../yuki-core" in normal or "yuki_core/src" in normal or "yuki-core/src" in normal:
                raise BoundaryError(f"private core checkout dependency in {file.name}")
            if kind == "path" and value not in {".", ""}:
                inside(path, value)
            if kind in {"branch", "rev", "tag"} and normal in {"main", "master", "head"}:
                raise BoundaryError(f"mutable Git dependency: {value}")
            if re.search(r"(?:git\+|git=|\.git[?@#]).*(?:@|rev=|branch=|#)(?:main|master|head)(?:[&#\s]|$)", normal):
                raise BoundaryError(f"mutable Git dependency in {file.name}")
            if "git+" in normal and not re.search(r"(?:@|[?&#]rev=)[0-9a-f]{40}(?:[&#\s]|$)", normal):
                raise BoundaryError(f"Git dependency must pin a commit: {file.name}")
    checked = []
    for source in sorted(path.rglob("*")):
        rel = source.relative_to(path)
        if any(p in {".venv", "target", "dist", "__pycache__", ".git"} for p in rel.parts):
            continue
        if source.is_symlink():
            inside(path, rel.as_posix())
        if not source.is_file() or source.name.startswith("._"):
            continue
        if source.suffix == ".py":
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(rel))
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                    [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                if any(n.split(".")[0] in {"yuki", "yuki_core"} for n in names):
                    raise BoundaryError(f"private core import in {rel}")
        elif source.suffix == ".rs":
            if re.search(r"\b(?:use|extern\s+crate)\s+yuki_core\b", source.read_text(encoding="utf-8")):
                raise BoundaryError(f"private core crate in {rel}")
        checked.append(rel.as_posix())
    return checked


def select_units(root: Path, changed: list[str]) -> list[str]:
    changed = [p.replace("\\", "/") for p in changed]
    units = load_catalog(root)
    shared = ("ci/", ".github/workflows/", "tests/cases/EXT-001", "tests/fixtures/EXT-001/")
    if any(p.startswith(shared) for p in changed):
        return sorted(units)
    return sorted(ident for ident, unit in units.items() if any(
        p == f"catalog/{ident}.json" or p in unit.get("check_paths", []) or p.startswith(unit["path"].rstrip("/") + "/")
        for p in changed))

# Yuki extensions

Official extensions, the Python Connector, environment images and setup tools are
independent release units. Install and build only the unit you need. The public
protocol and SDK belong to `yuki-core`; this repository never imports its private
implementation or uses a neighbouring checkout as a production dependency.

Build checks require Python 3.12, uv 0.12.0 and rustup with Rust 1.90.0 for the
independent Rust fixture. Each product Rust unit pins its own toolchain. Local
verification runs on Windows; CI requires Windows, macOS and Linux before merging.

```powershell
python ci/check.py EXT-001 --out artifacts/EXT-001/01
python ci/affected.py --changed connector/pyproject.toml
```

Build the Connector development wheel and sdist with
`python ci/package.py --unit connector --out dist/connector`. Run the upgrade
and portable-runtime checks with `python ci/check.py EXT-007 --preparation --out artifacts/EXT-007/local`.
The independent candidate uses version 0.4.4.dev0 and wire 4.
Formal EXT-007 acceptance awaits the pinned CORE-002 oracle.

`catalog/*.json` describes packaging, source and licensing only. It does not
define the plugin wire, grant model or host declarations. Units enter the catalog
when their implementation exists. Test fixture packages are not product plugins.

Progress and current limitations: [docs/implementation-progress.md](docs/implementation-progress.md).
The verified taskbook is retained under `docs/taskbook/v3.2`; its wording is
reference material subject to the user's working agreements. K05 governs the
shared logical-request reservation and separate physical-attempt accounting.

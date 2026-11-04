# Yuki extensions

Official extensions, the Python Connector, environment images and setup tools are
independent release units. Install and build only the unit you need. The public
protocol and SDK belong to `yuki-core`; this repository never imports its private
implementation or uses a neighbouring checkout as a production dependency.

Python tooling requires Python 3.12 and uv 0.12.0. Local verification runs on
Windows; CI requires Windows, macOS and Linux before merging.

```powershell
python ci/check.py EXT-001 --out artifacts/EXT-001/01
python ci/affected.py --changed connector/pyproject.toml
python ci/package.py --unit connector --out dist/connector
```

`catalog/*.json` describes packaging, source and licensing only. It does not
define the plugin wire, grant model or host declarations. Units enter the catalog
when their implementation exists. Test fixture packages are not product plugins.

Progress and current limitations: [docs/implementation-progress.md](docs/implementation-progress.md).
The verified taskbook is retained under `docs/taskbook/v3.2`; its wording is
reference material subject to the user's working agreements. K05 governs the
shared logical-request reservation and separate physical-attempt accounting.

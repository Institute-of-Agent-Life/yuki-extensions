# Release catalog

Each implemented release unit gets its own JSON record: `unit_id`, `kind`
(`plugin`, `connector`, `image`, `tool`), `path`, `ecosystem` (`python` or `rust`),
`version`, `tag_prefix`, `license`, `notices`, and immutable `source` attribution.
Python units have their own `pyproject.toml` and `uv.lock`; Rust units have their
own `Cargo.toml` and `Cargo.lock`. Nothing at the repository root builds all units.

The catalog is build metadata, not a duplicate of the core-owned public protocol.

Use `check_paths` for exact repository-relative test and fixture paths outside a unit. A change to a listed path selects that unit in CI.

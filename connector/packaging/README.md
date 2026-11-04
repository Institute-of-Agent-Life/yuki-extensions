# Connector development candidate

The candidate uses distribution version `0.4.4.dev0`, wire 4 and Python 3.12.
The 0.4.3 source preparation is reproducible at commit `0150c76`.
Its 43 original file digests, source commit and historical CI wheel digest are
in `source.lock.json`. The exact historical wheel lives under
`tests/fixtures/connector/` at the repository root.

The candidate changes package metadata and the runtime builder. The builder
takes the license from this release unit and records the digest of the wheel
installed in the portable runtime. The fixed drivers and journal are checked
against the original source bytes.

From the repository root on a machine with Python 3.12 and uv 0.12.0:

```powershell
python ci/package.py --unit connector --out dist/connector
python ci/check.py EXT-007 --out artifacts/EXT-007/local
```

The preparation uses isolated installations and a SQLite backup of a disposable
0.4.3 device journal. It exercises an in-place upgrade, original receipts, a
different device, empty doctor, Desktop stdin EOF, standalone lifetime and the
relocated portable runtime. The package contains its own license and dependency
lock. CI retains the built wheel, sdist, test transcripts and runtime manifest.

Formal acceptance uses the pinned CORE-002 oracle under `compat/core-002`.
It compares the wire transcript of both installed distributions against the
recorded reconnect, interleaved query and duplicate ACK scenario.

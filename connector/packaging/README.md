# Baseline source preparation

These files are an unchanged source port of the taskbook's fixed Connector 0.4.3,
not a new 0.4.3 release. The 43 upstream file digests and the historical CI wheel
digest are recorded in `source.lock.json`. All 16 runtime Python files match that
wheel byte for byte. Connector wire revision remains 4.

`verify_source.py` first checks every original file and wheel digest, installs the
wheel with hash-locked dependencies into a clean environment, runs the original
ruff/mypy/pytest checks, then exercises doctor on an empty fixture device. It does
not log in to native agents, purchase a model request or install an OS service.

The Windows preparation uses Python 3.12 and the original uv.lock. The local
transport helper downloads only wheels from that lock, checks their hashes and
sends them to the Windows test directory. The baseline wheel is taken from
`audit/evidence/upstream-connector.zip` in the verified user attachment and placed
at `.ci-transfer/oracle/yuki_agent_connector-0.4.3-py3-none-any.whl`.

```sh
python3 ci/windows.py EXT-007 --run source-03 --connector-source
```

Preparation results are deliberately separate from EXT-007 acceptance. The latter
requires the immutable CORE-002 oracle and manifest; it has not been delivered.
The development branch records this verified source preparation separately from
card acceptance. A new distribution must use a new PEP 440 version and must
not overwrite the original 0.4.3 artifact.

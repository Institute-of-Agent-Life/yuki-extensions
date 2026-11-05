# Environment status

The Rust plugin exposes `environment_status`. Bind an installation to the original
Manager socket through the `YUKI_ENV_MANAGER_SOCKET` environment allowlist.
The tool checks its host-bound operation before dispatch and before returning
the result. Only the readiness flag crosses the plugin boundary. The Manager's
list of other runs and services remains private. A missing Manager yields
`manager_unavailable` on this call; other Host tools remain online.

Terminal execution/read/control await a host-authorized original Work and run.
The independent Manager/execd source lock lives in `backend/source.lock.json`.

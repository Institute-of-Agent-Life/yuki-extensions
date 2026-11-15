# Environment status

The Rust plugin exposes `environment_status`. Bind an installation to the original
Manager socket through the `YUKI_ENV_MANAGER_SOCKET` environment allowlist.
The tool checks its host-bound operation before reading and again before
returning. Its result includes Manager readiness, the virtual HOME and
workspace, and storage capacity. Manager jobs, service names, and host paths
stay in the backend. A missing Manager yields `manager_unavailable` and the
Host continues.

Preparation uses the released Plugin Base 1.0.0 and the pinned Manager source.
Linux runs the original Manager socket. Mac and Windows exercise the unavailable
backend path and verify the Rust status projection.

Terminal execution/read/control await a host-authorized original Work and run.
The independent Manager/execd source lock lives in `backend/source.lock.json`.

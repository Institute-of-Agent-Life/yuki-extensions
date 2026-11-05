# Code plugin candidate

Rust Host adapter for the independently packaged `monty-runtime` image. The
plugin owns no identity, authorization or primary database. It uses the public
SDK and frozen Host script aliases, saves opaque native snapshots through
`code.snapshot.put`, and feeds only the original durable child receipt.

This is an unpublished development candidate. `compat/core-034/source.lock.json`
pins the build SDK. The newer Host at `f74ecdd86b73` fixes same-feed acknowledgement;
its full package pins and the byte-identical SDK source comparison are recorded
in `artifacts/EXT-023/feed-fix-intake/`. The earlier Host cannot complete that flow.

`YUKI_CODE_RUNTIME_CONFIG` names the operator-installed runtime JSON containing
`image_id`, `docker_socket`, `seccomp_path` and `contract`. The image must be pinned,
the local Unix socket reachable, and the original three AppArmor profiles enforced.
No runtime, daemon, profile or image is installed by the plugin. The independent
runtime unit carries Monty, its original patch, launcher, codec and notices.
The controller is a trusted Docker client; scripts receive no Docker socket or
host mounts. Container-wide NoNewPrivs would block the original launcher
transition. The worker retains enforced NoNewPrivs inside the original bwrap
boundary.

Native execution currently requires Linux with that isolation setup. Windows and
macOS builds return `runtime_abi_unavailable`; HJW integration uses a Windows Host
and byte-preserving WSL transport to the real Linux Rust binary. Direct mode does
not depend on this plugin or image. Unsupported native futures fail closed.

The Host must register the actual composition ABI/digests and one explicit Code
tool. Scripts pass one object to each frozen alias. Parent operation, child
ordinal, original feed and engine call ID survive snapshot restore. Two calls
with equal arguments retain different child operations. Unknown receipts return
partial without redispatch; closing the stream cancels native workers, including
when the final frame is malformed. Forget acknowledges only after cleanup.

Candidate evidence covers real effects and crash boundaries, not full EXT-024
acceptance. The current public catalog exposes aliases only through `tool.schema`,
so bootstrap reads then discards schemas to obtain the frozen projection. A light
alias projection is still needed to satisfy strictly on-demand schema lookup.
Work/run futures, full H14 budget/stop cases and formal publication remain open.

Run `python ci/package.py --unit codemode --out <new-directory>` to build this
independent package. `python ci/codemode_worker_check.py --out <new-directory>`
checks the portable worker component. Its ignored native test is not a native
runtime pass; explicitly run `native_suspend_restore_and_cancel` only with the
installed isolated runtime. The HJW integration fixture and exact invocation
are documented in `docs/EXT-023-024-sequences.md`.

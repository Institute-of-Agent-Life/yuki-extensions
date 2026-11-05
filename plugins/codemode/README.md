# Code runtime worker component

The Rust worker controller is implemented and independently tested. It starts
only the pinned Linux x86_64 image on a local Docker socket, verifies the original
AppArmor profiles and seccomp bytes, checks the actual worker/launcher/codec/ABI,
and owns cleanup of the container it created. Scripts enter the codec only over
stdin. The interpreter remains the original pinned native Monty worker.

Set `YUKI_CODE_RUNTIME_CONFIG` to an administrator-owned JSON file containing
`image_id` (immutable `sha256:` image ID), `docker_socket` (local `unix:///` socket),
`seccomp_path`, and the built image's `contract`. The user of this controller is
a trusted Docker client. The script has no access to Docker or host files.
Install the exact original AppArmor profiles before use. Container-wide
NoNewPrivs would block the original launcher transition; the worker itself
retains enforced NoNewPrivs through the original bwrap boundary.

Run `python ci/codemode_worker_check.py --out <new-directory>` for portable
compilation and the pre-cancelled admission case. On HJW Arch the explicit
`native_suspend_restore_and_cancel` case also executes the native VM, preserves
both equal-argument calls at feed 0 with distinct engine call IDs, restores the
original dump and removes each container. Non-Linux hosts report unavailable;
an ignored native case is not a native runtime pass.

The Host composition adapter is still in the working tree, outside this
completed component. It is not a release unit yet. CORE-034 `f3f3723aa532`
accepted the first actual send but rejected its post-answer acknowledgement at
the original native feed 0. See `artifacts/EXT-023/core034-consumer-01/`.
No parallel core rules or synthetic VM positions are introduced to bypass that
boundary. Full EXT-023/024 acceptance and publication remain pending.

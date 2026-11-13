# Lighthouse

Lighthouse is a Rust example that plays a three-move rescue game in a durable
Host session. CORE-051 candidate `9db8b3f073e3` and Rust SDK 1.0.0-alpha.9
are pinned in `compat/core-051/`.

Install the executable and add `plugin.toml` to the owner's configuration.
Use an absolute program path and set `namespace` to `lighthouse`. In
`yuki.toml`, the installation starts with `[[plugins]]`. Its settings use
`[plugins.sessions]`, `[plugins.aux_routes.game]` and
`[plugins.aux_routes.game.profile]`. Replace the example entry ID, model
and endpoint with the ones approved for the game. The provider uses the
separate `game` profile. The example enables foreground calls from the
listed entries and leaves background creation disabled.

1. Invoke `/lighthouse/start` from a listed entry. The Host command receipt
   returns the original session ID and epoch.
2. Invoke `/lighthouse/play SESSION EPOCH TURN_KEY search`. Use `fit` and
   `signal` with new turn keys. To reconcile a turn, send the same session,
   epoch, key and move.
3. Invoke `/lighthouse/status SESSION [AFTER]` to read a page under the original
   Person or group scope. The receipt includes the next cursor.

On the development Host, the OS operator can inspect an original command
receipt with `operator ingress claim EVENT` and then
`operator effect read EXECUTION command:EVENT PERSON`. This example's result
is returned on the Host command wire. Sending it to a chat platform would
require that platform's authorized delivery path.

The Host retains the transcript and performs source erasure. The extension
keeps no transcript files. It stops its in-flight RPC worker before returning
the original erasure key and watermark. Ordinary Main and Memory have no
game transcript. The original ingest record identifies the command source.

Run the independent local acceptance with:

```sh
YUKI_HOST_CANDIDATE=/path/to/the/pinned/platform.zip \
  python ci/check.py EXT-047 --preparation --out /tmp/yuki-lighthouse-check
```

The fixture uses local loopback providers. Exact package digests and
third-party migration gaps remain in `docs/sdk-migration.md`.

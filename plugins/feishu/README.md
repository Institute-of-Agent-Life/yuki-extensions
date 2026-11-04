# Feishu / Lark gateway

Build the independent Rust executable with `python ci/package.py --unit feishu --out dist/feishu`.
Bind each installation to its own host namespace and original bot stage. Supply
the app ID, app secret, tenant and region (`feishu` or `lark`) through the
manifest environment allowlist. Each installation obtains its native WebSocket
URL from its own region. A test deployment may select a loopback API endpoint.
An optional HTTP(S) CONNECT proxy uses the same configured route for both steps.

The plugin reassembles native protobuf fragments and keeps native ping/pong and
card responses available while awaiting the host writer. Success for a message
requires a durable gateway receipt from the original installation. Reconnection
discards incomplete frames. Durable events and account bindings belong to the host.

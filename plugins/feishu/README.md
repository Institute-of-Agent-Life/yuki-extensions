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

When the Host approves `gateway.media` for this installation, ingress includes
its application and tenant. The Rust adapter uses the original message ID,
resource key and type at that app's regional REST endpoint. A bounded worker
reads up to 16 MiB and sends pages of up to 24 KiB, separately from WebSocket
admission ACKs. The tenant token and one in-flight resource are held in memory.
An idle transfer expires after 30 seconds. A failed resource GET is not retried.

With `gateway.send`, the native worker delivers the pure text plan to the original
app and recipient. The Host supplies `route.scope`, original thread root and any
explicit quote. Each confirmed response returns its original message ID. A
platform refusal is failed, and response loss or a missing message ID is unknown.
The Host owns durable receipts and subsequent status reads. `gateway.recall`
uses the original sent ID under the same installation.

Text splitting preserves v4's 150,000-byte serialized text-body limit, including
JSON escaping. The first part keeps an explicit quote and later parts use the
original thread root. Token renewal stays inside this application's worker.

`forget.owner` cancels and joins the current HTTP pipe, clears token and resource
pages, then acknowledges the original key and watermark. An `erasure_only`
process completes its handshake and cleanup without loading platform credentials.
Outbound media and structured native mentions remain pending in EXT-006.

REST operations require curl 8.3 or newer. Set `YUKI_FEISHU_CURL` to the installed
executable and include that name in the Host installation's environment allowlist.
The body is streamed through binary stdin. URL and token are expanded from the
child environment, keeping credentials outside process arguments. The Windows gate
uses the existing Git curl executable.
[HTTP variable expansion](https://curl.se/docs/manpage.html#--variable)

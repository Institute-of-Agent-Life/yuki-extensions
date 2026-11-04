# Public page reader

The Rust executable exposes the read-only `web_fetch` tool on the CORE-032
candidate. Its owner grants only `tool.call`. The SDK pairs each callback to
its original call handle; the plugin checks that handle before reading and
again before returning the result.

Build this release unit with `python ci/package.py --unit web-fetch --out dist/web-fetch`.
It uses the operating system's curl and certificate store. Each HTTP or HTTPS
hop gets a fresh DNS check. Curl connects to the selected IP while preserving
the origin hostname and TLS verification; configured proxies and NO_PROXY
remain effective. Set these through the plugin-specific
`YUKI_WEB_FETCH_HTTP_PROXY`, `YUKI_WEB_FETCH_HTTPS_PROXY`,
`YUKI_WEB_FETCH_ALL_PROXY` and `YUKI_WEB_FETCH_NO_PROXY` allowlist. Cross-origin redirects discard caller headers and body.
Failures return typed states without retrying directly or calling a model.

Responses retain the original and final URL, HTTP status, content type, observed
byte count and SHA-256. Small originals also include their bytes. The transport
reads at most 2 MiB; larger inputs report a partial result and a digest of the
observed prefix. The plugin has no persistent page database. The host owns the
committed tool result and its paging.

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
byte count and SHA-256. Original bytes are included as hex, including error and unsupported responses. When the SDK frame cannot hold the full representation it carries the observed prefix and marks the original incomplete. The transport
reads at most 2 MiB; larger inputs report a partial result and a digest of the
observed prefix. The plugin has no persistent page database. The host owns the
committed tool result and its paging.

The two-consumer build pins SDK 1.0.0-alpha.14 from the signed CORE-039 development distribution. Rebuild and run the Windows witness with the instructions in `compat/base/README.md`.

### Select the v4 declaration

Use `plugin-read-webpage.toml` in place of `plugin.toml` when the installed
model profile expects `read_webpage(url, question?)`. Use the same executable,
namespace, `tool.call` grant, and proxy settings. In a manual Host installation,
use the selected manifest's `[[tools]]` entry as `[[plugins.tools]]`. The
Host pins the declaration per execution and requires approval when an existing
installation changes it. The package's default declaration is `web_fetch`.

The selected name reads the explicit URL through the same direct reader. It
normalizes the optional question and returns the v4 source ID, original URL,
and extracted text. The source ID preserves the path and query as submitted,
including Unicode and existing percent escapes. HTTP uses the validated,
encoded URL and checks each redirect. An oversized
download returns `extract_failed`. A result that exceeds the SDK frame returns
`result_too_large`. The Host can page a result that fits the SDK frame and read
it back after a restart. Each new operation fetches the URL again. The v4
implementation kept a ten-minute extraction cache.

Record the oracle from a read-only v4 checkout at
`329ca7c487414d2f54ddd98ff4727446ed2446cd` using its installed Python
environment. Run from the extension repository and pass a new output path.

```sh
PYTHONPATH=ci:tests/peers "$V4_CHECKOUT/.venv/bin/python" -B - \
  "$V4_CHECKOUT" /path/to/read-webpage-oracle.json <<'PY'
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from read_webpage import oracle, write

with TemporaryDirectory() as tmp:
    write(Path(sys.argv[2]), oracle(Path(sys.argv[1]), Path(tmp)))
PY
```

Build the package with `ci/package.py`. The replay uses a signed 1.0.0 Host,
a loopback proxy, and a loopback model.

```sh
PYTHONPATH=ci python tests/peers/read_webpage.py \
  --host /path/to/published-base.zip \
  --package /path/to/web-fetch-package \
  --oracle /path/to/read-webpage-oracle.json \
  --out /path/to/new-receipts
```

### Published Windows Host acceptance

Use the public 1.0.0 Windows ZIP in `YUKI_STABLE_BASE_ZIP` and the web-fetch Actions ZIP named by its freeze (artifact 13524465074) in `YUKI_FROZEN_WEB_FETCH_ZIP`. Run `python ci/check.py EXT-028 --out <new-directory>`. First redirect a requested page to a monitored loopback address. The Host must receive the original refusal with zero requests to that destination. Then serve more than 2 MiB. The original execution must read a partial result that distinguishes the observed bytes from the retained prefix, with matching source, digest and UTF-8 text. The existing signed-candidate command and its R07 network and owner receipts remain available.

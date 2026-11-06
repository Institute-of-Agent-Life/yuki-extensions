# Telegram gateway

Install this Rust release unit using the host's private `[[plugins]]` configuration.
Bind the gateway to its original Telegram SELF stage and namespace, set its
absolute program path, and grant `gateway.inbound`. The plugin uses the
pinned CORE-038 development SDK (alpha.13) and connects to Telegram's Bot API through curl.
Build from the extensions root with `python ci/package.py --unit telegram --out dist/telegram`
using the pinned toolchain and the verified SDK distribution.

Pass the selected credential and its expected numeric bot ID using
`YUKI_TELEGRAM_TOKEN` and `YUKI_TELEGRAM_BOT_ID`. Give the plugin its private
cursor directory in `YUKI_TELEGRAM_STATE`. The identity must agree with getMe.
Each bot holds a file lock and stores its next offset only after the host's
gateway receipt. A restart resumes that bot's committed prefix.
`YUKI_TELEGRAM_API` supports a loopback recorder for offline tests. Production
uses `https://api.telegram.org`.

For attachment intake, the operator must also approve `gateway.media` for
the original application and Bot stage. A grant without the application
identity does not start on Host `0ef956a9c6d9`. Ingress-only installations
continue to omit that optional identity. The adapter calls getFile and the
same Bot's download endpoint only when the Host selects a file. Transfers
are limited to 16 MiB, one active stream and 24 KiB per page; remaining bytes
are discarded after 30 seconds idle or on process exit.

When the original installation grants `gateway.send`, the Host may plan and
dispatch plain Telegram text. The planner splits at 4,096 Unicode characters.
Each physical call uses the original Bot, chat and topic. The gateway returns
the native chat/message locator only after a matching successful response.
A lost or ambiguous response returns `unknown` without another send.
This version refuses quoted events and outbound media during planning; those
need a resolved native locator or the original authorized immutable media.

The two-consumer build pins SDK 1.0.0-alpha.14 from the signed CORE-039 development distribution. Rebuild and run the Windows witness with the instructions in `compat/base/README.md`.

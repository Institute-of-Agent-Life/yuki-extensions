# Telegram ingress

Install this Rust release unit using the host's private `[[plugins]]` configuration.
Bind the gateway to its original Telegram SELF stage and namespace, set its
absolute program path, and grant `gateway.inbound`. The plugin uses the
CORE-032 business preview SDK and connects to Telegram's Bot API through curl.
Build from the extensions root with `python ci/package.py --unit telegram --out dist/telegram`
using the pinned toolchain and the verified SDK distribution.

Pass the selected credential and its expected numeric bot ID using
`YUKI_TELEGRAM_TOKEN` and `YUKI_TELEGRAM_BOT_ID`. Give the plugin its private
cursor directory in `YUKI_TELEGRAM_STATE`. The identity must agree with getMe.
Each bot holds a file lock and stores its next offset only after the host's
gateway receipt. A restart resumes that bot's committed prefix.
`YUKI_TELEGRAM_API` supports a loopback recorder for offline tests. Production
uses `https://api.telegram.org`.

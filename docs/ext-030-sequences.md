# EXT-030 candidate sequences

Use the immutable CORE-050 `952954d86166` Host and SDK alpha.6. This is an
unpublished development pairing. The existing Rust media processor owns decoding;
the Host owns the selected source, authorization, Profile and request ledger.

1. Explicit `media.process(purpose=transcript)` reads the original authorized
   handle, verifies MIME, bounded bytes and digest, then chooses original WAV/MP3
   or bounded AMR conversion using the already pinned FFmpeg. SILK needs the
   original receiver's conversion; unsupported bytes fail before purchasing.
2. `llm.complete` uses the configured `asr` route and a stable source/digest key.
   The Host fixes the Profile and logical reservation. Result pages must retain
   request identity, digest and size. Only a complete successful textual response
   produces a transcript with its original source and version.
3. Repeat the original call, issue a second call for the same source, and replay
   through a second Bot. Count actual HTTP requests and logical IDs. An extra
   purchase is a producer/consumer acceptance gap, never a passing assertion.
4. Delay ASR while another independent media request completes. Erase the source
   while HTTP is pending; wait for the real forget callback and reject late data.
5. Close HTTP without a response, return an invalid response, and send malformed
   audio. Preserve unknown/error state without fallback or a fabricated transcript.
6. Return `/ai admin ...` as fixture ASR content. It remains sourced data; the
   processor has no command, promotion or send grants. Actual original Main and
   history use, cross-Bot identity and source reuse require separate Host evidence.

The HTTP peer is an independent deterministic provider fixture, not a speech
quality test or paid external model. Retain the raw method transcript, request
bodies, Host/SDK/plugin hashes and source hashes in `artifacts/EXT-030/`.

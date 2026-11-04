# Selected media inspection

The independently built Rust plugin consumes CORE-038 media.process, reads only
the bound source through media.open, and publishes immutable sampled frames
through media.publish. It retains the original event/slot or artifact/version,
PDF page markers and video timestamps. It creates no model request.

The PDF backend is the unchanged baseline document_reader.py. Install the pinned
pypdf and defusedxml wheels into a private Python 3.12 environment and set
YUKI_MEDIA_PYTHON to its absolute executable. The decoder is run with Python
isolated mode, fixed package versions, a verified script digest, bounded output
and a 15-second deadline. It extracts text from at most 12 pages and reports
truncation and encryption. The runtime files in the package keep the original
reader separately auditable.

Set YUKI_MEDIA_FFMPEG to the verified executable selected in packaging/codecs.lock.
The initial runtime witness uses the Windows x86_64 imageio-ffmpeg 0.6.0 wheel.
The Rust package builds separately on Windows, macOS and Linux. Video execution
on another target requires a separately verified codec entry. FFmpeg receives
only a local selected file, whitelisted containers and local-file protocol.
It samples up to eight frames at their actual timestamps, within 600 seconds,
and scales to at most 1024 pixels across. It does not decode audio.

YUKI_MEDIA_TEMP optionally selects an existing private temporary directory.
Calls use disposable subdirectories. On forget.request the plugin cancels all
volatile work, stops decoder children, clears temporary files and acknowledges
only after cleanup. Host authorization is rechecked before results leave the
plugin. A scope error prevents late publication.

This uses an unpublished alpha.4 Host contract. Actual original-model pixel
presentation and public-release acceptance remain separate open checks.
The current candidate does not automatically register volatile media ownership.
The Windows callback witness uses the public operator privacy acquire command;
automatic source-bound registration must be supplied by the Host before release.

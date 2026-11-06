# Offline candidate setup

Build the independent Rust installer with `python ci/package.py --unit yuki-setup --out dist/setup`.
It uses local Python 3.12 and OpenSSH ssh-keygen to verify the producer signature.
The signed native packages and OCI archive are supplied separately. The compiled
trust pins are under `tools/yuki-setup/inputs/`. CORE-039 source `093716ad01c0`
is a development version; its handoff pins were published in producer commit
`fe278a51`. OCI is available for Linux ARM64. Native targets are Windows x86_64,
macOS ARM64 and Linux ARM64.

To generate a local direct-profile Compose kit and run its offline doctor:

```text
yuki-setup init --archive PATH_TO_SIGNED_OCI_TAR --core core-039-093716ad01c0 --dir KIT --profile direct --entry local --timezone Asia/Shanghai
yuki-setup doctor --archive PATH_TO_SIGNED_OCI_TAR --dir KIT
```

The kit contains the digest-pinned Compose file, a timezone in .env and an editable
SOUL example. Reapplying a timezone preserves unrelated assignments, NapCat remnants,
secret references and comments. The installer reports missing optional packages before
writing. It performs no image import, container start, login, network discovery or model
probe. Prepare a writable data directory for UID/GID 65532 and import the verified OCI
into a compatible local runtime before an operator-approved Compose launch. The core
service initializes a fresh owner and uses a read-only root with no Docker socket.
The candidate exposes local owner operations; external ingress and optional sidecars
require separately verified delivery and endpoint contracts.

To install the native release for the current OS into a new directory:

```text
yuki-setup native --archive PATH_TO_SIGNED_NATIVE_ZIP --dir NEW_NATIVE_DIRECTORY
```

The native command verifies the architecture, every archive member, the SDKs and
the fixture hash before making the installation visible. Operator-owned state lives
outside that directory. Start the installed executable with a fresh data directory
using `yuki-core --data OWNER init` and `yuki-core --data OWNER run`.

On Windows the native installer can also compose the verified Rust web-fetch
candidate from extensions commit `0bac149`:

```text
yuki-setup native --archive WINDOWS_HOST_ZIP --dir NEW_NATIVE_DIRECTORY --plugin web-fetch --plugin-file VERIFIED_WEB_FETCH_EXE
```

This creates a new owner directory inside that installation with only the selected
tool and its original grants. The binary's SHA-256, original consumer SDK and
manifest are pinned in `tools/yuki-setup/inputs/web-fetch.lock.json`. Other
installations, unsupported tools and missing binaries are untouched. To start the
composed owner, run its verified core executable with `--data NEW_NATIVE_DIRECTORY/owner run`.

## 公開原生基底 1.0.0

在空目錄用 `yuki-setup native --core 1.0.0 --archive <本機公開平台ZIP> --dir <新目錄>` 安裝。不下載套件、不啟動服務。可另行執行 `bin/yuki-base --data <新owner> init --memory-mode lexical-only` 及 `run`。Windows 程式帶 .exe 副檔名。

Windows 如明選原 web-fetch，加 `--plugin web-fetch --plugin-file <原Actions ZIP>`（資產 13524465074）。安裝器核實原包、建立獨立 owner 並寫入該包授權及工具宣告。無 QQ／其他插件的新 owner 應可 ready；明選原包的新 owner 應只啟用 web-fetch。錯平台、錯版本、壞 ZIP、未知選配或已有目的地必須拒絕，且舊 owner 的配置與 SOUL 逐 bytes 保留。候選原生安裝與 Compose 原先的入口繼續使用各自的鎖。CORE-044 此次發布提供原生基底與 SDK，Compose 映像及外部入口另行驗證。

Windows 原生驗證可同時指定 `YUKI_STABLE_BASE_ZIP` 與 `YUKI_FROZEN_WEB_FETCH_ZIP`，執行 `python ci/check.py EXT-040 --preparation --out <新回條目錄>`。測試會在隔離目錄另外啟動宿主，安裝命令本身不開服務。回條在 `artifacts/EXT-040/public-native-01`。第一輪修正新舊簽名驗證器重複傳入 timeout；第二輪觀察到公開 Host 在無插件時回覆成功且清單為空。第三輪核對該原回應與明選插件的 online 狀態。

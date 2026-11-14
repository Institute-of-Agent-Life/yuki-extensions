# Offline candidate setup

Build the independent Rust installer with `python ci/package.py --unit yuki-setup --out dist/setup`.
The installed Rust binary verifies the pinned producer's OpenSSH Ed25519
signatures, archive inventory, and content digests in-process. The CI command
above uses Python to build the package. Installation and offline doctor work
with an empty executable search path.
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

The kit contains a digest-pinned Compose file, a timezone in `.env`, and a SOUL
example. Rerun `init --timezone` to change the timezone while keeping operator
comments, other environment assignments, and the SOUL example. Setup verifies
packages and configuration offline.

Import the verified OCI archive into a local Linux ARM64 Docker engine.
From the kit directory, run `docker compose up -d --pull never --wait`.
The local kit has one core service with a read-only root and an isolated network
namespace. Docker stores the owner in a named volume so SQLite and the operator
socket use a Linux filesystem. Compose checks `/readyz` inside the container.
Each new kit saves a distinct project name in `compose.yaml`. Keep that name and
volume when recreating the service. Run Compose without `--project-name` or a
`COMPOSE_PROJECT_NAME` override. The doctor reports `project=compose-default`
for older kits and preserves their project selection. Kits with
`storage=legacy-bind` need a bind source that supports Unix sockets.

To connect an operator-managed proxy on an existing private Docker network, use
a separate kit:

```text
yuki-setup init --archive PATH_TO_SIGNED_OCI_TAR --dir KIT --entry external --entry-network PROXY_NETWORK
yuki-setup doctor --archive PATH_TO_SIGNED_OCI_TAR --dir KIT --entry external --entry-network PROXY_NETWORK
```

Attach the proxy to `PROXY_NETWORK` and point it to
`http://<project>-core:8080` using the project name reported by the offline
doctor. Keep TLS and public routing on the proxy.
The kit defines an upstream on the selected network and publishes no host
ports. The core candidate uses `direct`. SnowLuma and the Code profile require
compatible pinned deployment inputs. The [SnowLuma deployment guide](https://snowluma.github.io/en/docs/guide/deploy/docker)
describes the runtime privileges and operator-managed QQ login.

To install the native release for the current OS into a new directory:

```text
yuki-setup native --archive PATH_TO_SIGNED_NATIVE_ZIP --dir NEW_NATIVE_DIRECTORY
```

The native command verifies the architecture, archive members, SDKs, and fixture
hash before making the installation visible. For the signed public base on macOS,
choose an APFS destination or a volume that supports exclusive rename. Use a short
path for the operator-owned data directory on macOS and Linux to fit the Unix socket
path limit. Start the candidate with `yuki-core --data OWNER init` and
`yuki-core --data OWNER run`.

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

原生驗證用 `YUKI_STABLE_BASE_ZIP` 指定當前平台的原包，再執行
`python ci/check.py EXT-040 --preparation --out <新回條目錄>`。Windows 可另指定
`YUKI_FROZEN_WEB_FETCH_ZIP` 驗證選配。測試會在隔離目錄啟動宿主。
要驗證 Compose，先在本機匯入候選映像，再設 `YUKI_CORE039_OCI` 並省略
`--preparation`。完整卡回條會分列 Compose、原生安裝和 SnowLuma 實測狀態。

## 公開原生基底 1.1.0 與 1.2.0

將同一版本的 ZIP、`manifest.json`、`SHA256SUMS`、`SHA256SUMS.sig`
及 `signer.pub` 放在同一個本機目錄，選擇版本及新安裝路徑。

```text
yuki-setup native --core 1.2.0 --archive yuki-plugin-base-1.2.0.zip --dir NEW_NATIVE_DIRECTORY
```

離線安裝會核對發布簽名、Host 架構及兩套 SDK 雜湊。新目錄包含當前平台的
`bin/yuki-core`、SDK 和已核對的協議。可用 `--data OWNER init --memory-mode lexical-only`
建立獨立 owner，再執行 `run`。這兩個版本的原生安裝只選核心，維護插件按其
發布版本另行安裝。當指定已存在的安裝目錄時，命令拒絕覆寫。

以 `YUKI_SETUP_BASE_1_1`、`YUKI_SETUP_BASE_1_2` 指定兩個原 ZIP，
執行 `python ci/check.py EXT-040 --preparation --out NEW_EVIDENCE` 重現原生驗證。

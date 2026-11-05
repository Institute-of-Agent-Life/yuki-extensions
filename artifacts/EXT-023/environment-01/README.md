# HJW Arch 隔離測試環境

使用者已授權本次 Arch 環境準備及必要的 WSL 重啟。`manifest.json` 的 PASS 僅表示實際容器環境通過探測；Monty worker、Rust 插件和 CORE-034 的原生快照消費另行驗收。

WSL 3.0.1.0 使用 `C:/Program Files/WSL/wsl.exe`，核心為 Linux 6.18.40.1 x86_64。`enable-apparmor.py` 是已執行的一次性設定變更，保留原檔所有 bytes 後追加 AppArmor 參數；不要重複執行。`wsl-config-change.json` 保存前後 SHA 與實際重啟結果。

`packages.lock.json` 固定原 Arch 索引中的 10 個官方封存套件及 SHA。每個套件的 detached signature 均在 HJW 用原 Arch keyring 通過驗證，然後交由 pacman 驗完整性並安裝。既有基礎套件未升級。Arch 的 Python 3.14 僅供環境工具使用；Monty 的 codec 仍須使用原 CPython 3.12。

Arch 的 systemd-firstboot 尚未完成，一般 Docker 啟動工作因此等待。本次取消新建的 Docker／containerd／socket 工作，使用 `start-docker.sh` 啟動專用 daemon。它使用獨立 socket、data-root、exec-root 和暫存目錄，不設網路 bridge、不修改轉送規則，也不啟用開機服務。WSL 關閉後，下一次驗證會重新啟動這個 daemon。

`base-images-transfer.json` 記錄公開映像的原始 reference、Linux amd64 digest、下載 image ID、傳輸檔 SHA。macOS 僅下載及匯出映像；所有容器探測在 HJW Arch 執行。將相應 tar 傳到 HJW 後，使用專用 daemon 的 `docker load` 載入，再於 Arch 的本目錄執行 `sh run-container-probe.sh`。此腳本使用固定 image ID、原基線 AppArmor／seccomp 策略及非 root UID。

`container-probe-run-02.json` 實收 enforce、Seccomp=2、三組 capability 全零、NoNewPrivs=1、僅 loopback、外網拒絕、宿主 canary 不可見、根目錄不可寫，以及 keyctl 拒絕。原始失敗回條保留：鏡像 404、securityfs 未掛載、一般服務等待、Docker Hub 直連拒絕和未建立的 `/run/user/0` 暫存目錄。最後一項只修正測試 daemon 的環境變數。

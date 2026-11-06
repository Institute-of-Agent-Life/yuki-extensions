# EXT-043 獨立升級及回退

1. 從公開發行 plugin-base-v1.0.0 核對簽署者、來源、三平台分發與 freeze 指向的 EXT-067 原回條。取 freeze.windows_replay 列出的兩個 GitHub Actions 原包，核 ZIP、exe、Cargo.lock 和配置。
2. 只選 Telegram，沿原 Rust 來源以 SDK 1.0.0 製作獨立包、授權文件與 SBOM。web-fetch 始終使用同一份已驗原包。基底只宣告六個方法；需要候選媒體能力的安裝繼續使用原分發。
3. HJW 在隔離資料目錄啟動已發布 Host。新 Telegram 與舊 web-fetch 讀取原頁並確認三段送達。另一輪第二段失去回應，確認 unknown。兩輪各自停止兩個子程序與 Host，再在同一資料目錄換回 freeze 指定的舊 Telegram，讀同一游標，核舊更新重投無新效果。
4. 非登錄插件、錯誤版本及包損壞需被拒絕；只有與通過回條相符的來源可準備對應 tag。合併後另行核准實際 tag 與發版。

設定 `YUKI_STABLE_BASE_ZIP` 為公開 Windows ZIP，`YUKI_FROZEN_TELEGRAM_ZIP`、`YUKI_FROZEN_WEB_FETCH_ZIP` 分別為 freeze 列出的 Actions 資產 13523402982、13524465074。以空輸出目錄執行 `python ci/check.py EXT-043 --out artifacts/EXT-043/01`。原生包摘要、原 witness、完整簽署者與九份發行資產的 ID／SHA 在 `compat/stable-1.0/`。

Telegram 的候選媒體安裝與六方法基底分別保留依賴鎖。基底發行由 `releases/telegram/0.1.0/` 的 Cargo 與執行配置選用同一份 Rust 來源。發行登錄逐檔固定編譯輸入；未申請發版時僅建包。Tag 工作流按當前提交建立三平台產物；實際發布另需在該 tag 明選 publish 並通過 plugin-release 環境。

第一輪改動啟動命令的程式路徑，冷啟後未收到第二次 Telegram 握手。該輪回條存於 `artifacts/EXT-043/iterations/changed-launch-path.zip`。通過的部署方式是在子程序與 Host 都停止後，於相同路徑替換已核 digest 的程式，沿用原配置與資料。其他部署方式待個別驗證。

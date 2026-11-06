# EXT-003 停機副本與水位回退

正常時序在全新的測試目錄進行。以 #40 的 Windows Telegram alpha.4 在固定簽署 Host 接納一個 chat 資料更新，停機後複製 Bot 101 的原水位檔。alpha.5 在副本的首次輪詢必須帶原水位，下一個 Host 回執到達後才推進。再停機，把新水位交回同一個 alpha.4，核首次輪詢、原檔與第二個 Bot 的哨兵檔。核原始 RPC 與平台請求，不使用真 Bot 憑據。

故障時序在獨立副本執行。以負水位示範舊 reader 的第一次原生請求；新 reader 遇相同內容必須退出，保留原位元組，getUpdates 零次。截斷成非整數也必須退出。首次輪詢收到負 update_id，或收到加一會溢位的 update_id，必須在送入 Host 前拒絕，且不建立水位。所有平台回應來自 loopback。

舊 Python 基線 329ca7c 的 telegram_ingress.py（Git blob 54ea92759a979336e1dca408103bc310809b3043）在 _run 內以 offset=None 開始，收到資料後只更新記憶體變數。Rust 從 7dbe738 起使用各 Bot 的十進位換行檔。在舊 Python 沒有持久水位的情況下保留缺檔狀態，首次輪詢交由原平台回放與 Host 既有事件回執處理。這裡使用停止的測試副本，沒有讀取現場資料庫。

重現入口為 tests/peers/telegram_cursor_compat.py。使用獨立輸出目錄、compat/base 所鎖的 Host ZIP、#40 的 Telegram Windows 套件及以 ci/package.py 建置的新套件。

HJW 的第 1 輪在更換測試安裝參數後沒有啟動第二個 reader。第 2 輪沿同一安裝路徑替換停機的執行檔，兩個版本都讀到原水位；故障例同時暴露 Python 觀測程序結束時的 stdin 鎖爭用，原 ZIP 保存在 cursor-compat-02。第 3 輪的正例誤用了零事件斷言，保留實收 wire。第 4 輪修正觀測程序及斷言，四個故障例均取得 Rust 原退出碼 1。最終結果在 artifacts/EXT-003/cursor-compat-04/windows.zip，內含原平台請求、Host 對話、建置命令、來源 SHA 及各成員 manifest。Bot API 的負水位行為見 [getUpdates](https://core.telegram.org/bots/api#getupdates)。

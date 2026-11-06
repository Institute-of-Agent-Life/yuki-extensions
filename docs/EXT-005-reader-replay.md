# EXT-005 更換 reader 與分片重投

在 HJW Windows 使用原始 #13 alpha.1 與 #40 alpha.2 套件、CORE-038 0ef956a9c6d9 的 Windows Host，以及基線 protobuf 與 loopback WebSocket。每個安裝使用不同 app、tenant、域名與 Bot stage。安裝命令與命名空間在同一安裝的三次啟動保持一致。

1. 舊版完整處理 A，收到 200。送出 B 的前半段，用獨立 card 的 ACK 確認插件已處理該段，停止插件與 Host，保存停止的插件工作目錄。
2. 新版只收到 B 的後半段。另一個 card 必須先收到 ACK，B 仍沒有 event ACK。補回前半段後 B 才取得一次原生 200；重投 A 必須回到舊版收到的 Host event。
3. 停機後以舊版讀取新版留下的插件目錄，再投 B，核回同一 Host event。飛書及 Lark 使用同名平台訊息鍵，兩個安裝的 Host event 必須分開。逐階段核原生 seq/log、原 RPC、工作目錄檔案與可執行檔 SHA。

舊 Python 在 feishu_ws.py 的連線清理中清空記憶體分片。Rust 的 Assembler 跟隨單次連線，已接納事件由 Host 保存。這個測試把停止的插件目錄交給前後兩個實際版本，並保留同一 Host 的公開回執。正式發行與現場舊庫另列。

舊包取自擴展 #13 的合併測試樹 98eb7aab4850（Windows artifact 13393314223），新版來自 #40 的 4d744e700a59（13522719490）。兩份套件皆比對 GitHub digest、包內 manifest 與實際執行檔。首次測試曾在停 Host 後碰到 Windows 鎖住子程序工作目錄，原生 ACK 與 wire 留存在 reader-replay-02。最終六次都先經觀測程序終止並等到原生子程序退出，再停 Host 和複製目錄。

用 Python 3.12 設定 YUKI_HOST_CANDIDATE 為相符的 Windows ZIP，UV_FIND_LINKS 指向 tests/peers/lark-fixture.lock.json 鎖定的兩個 wheel。執行 python tests/peers/feishu_reader_replay.py 舊包.zip 新包.zip 新輸出目錄。包內 Rust 程式與 SDK 沿既有版本，沒有部署平台服務。

### 公開基底的接納與 ACK

在 HJW Windows 將 #47 的原生 alpha.4 套件（Actions artifact 13539727686）接至公開 B0。兩個域各用原 app、tenant、namespace 和 Bot stage。傳送重複的尾段，先以獨立 card ACK 驗 writer 仍未收到完整事件，再補首段。首次在 writer 前斷開，不能有成功 ACK；冷啟後接納與重投都應取得同一事件，第二安裝同形 open_id 和 message_id 必須分開。錯租戶回錯，壞憑據不能取得連線。用逐方法 wire 比對原生 card 和 ping，不得為它們發出聊天事件。writer 前的回環模型 HTTP 必須為零；重投後以同一端點等到第一次普通訊息的模型請求。

Windows 以 `YUKI_STABLE_BASE_ZIP` 指定原名的 CORE-044 Windows ZIP，以 `YUKI_QUALIFIED_FEISHU_ZIP` 指定 #47 的原 Actions ZIP，`UV_FIND_LINKS` 指向 lark-fixture.lock.json 所列兩個 wheel。執行 `python ci/check.py EXT-005 --out artifacts/EXT-005/01`。

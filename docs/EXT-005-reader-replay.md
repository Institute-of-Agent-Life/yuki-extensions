# EXT-005 更換 reader 與分片重投

在 HJW Windows 使用原始 #13 alpha.1 與 #40 alpha.2 套件、CORE-038 0ef956a9c6d9 的 Windows Host，以及基線 protobuf 與 loopback WebSocket。每個安裝使用不同 app、tenant、域名與 Bot stage。安裝命令與命名空間在同一安裝的三次啟動保持一致。

1. 舊版完整處理 A，收到 200。送出 B 的前半段，用獨立 card 的 ACK 確認插件已處理該段，停止插件與 Host，保存停止的插件工作目錄。
2. 新版只收到 B 的後半段。另一個 card 必須先收到 ACK，B 仍沒有 event ACK。補回前半段後 B 才取得一次原生 200；重投 A 必須回到舊版收到的 Host event。
3. 停機後以舊版讀取新版留下的插件目錄，再投 B，核回同一 Host event。飛書及 Lark 使用同名平台訊息鍵，兩個安裝的 Host event 必須分開。逐階段核原生 seq/log、原 RPC、工作目錄檔案與可執行檔 SHA。

舊 Python 在 feishu_ws.py 的連線清理中清空記憶體分片。Rust 的 Assembler 跟隨單次連線，已接納事件由 Host 保存。這個測試把停止的插件目錄交給前後兩個實際版本，並保留同一 Host 的公開回執。正式發行與現場舊庫另列。

舊包取自擴展 #13 的合併測試樹 98eb7aab4850（Windows artifact 13393314223），新版來自 #40 的 4d744e700a59（13522719490）。兩份套件皆比對 GitHub digest、包內 manifest 與實際執行檔。首次測試曾在停 Host 後碰到 Windows 鎖住子程序工作目錄，原生 ACK 與 wire 留存在 reader-replay-02。最終六次都先經觀測程序終止並等到原生子程序退出，再停 Host 和複製目錄。

用 Python 3.12 設定 YUKI_HOST_CANDIDATE 為相符的 Windows ZIP，UV_FIND_LINKS 指向 tests/peers/lark-fixture.lock.json 鎖定的兩個 wheel。執行 python tests/peers/feishu_reader_replay.py 舊包.zip 新包.zip 新輸出目錄。包內 Rust 程式與 SDK 沿既有版本，沒有部署平台服務。

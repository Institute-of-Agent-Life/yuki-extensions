# EXT-006：原租戶附件

先用原 app/tenant 的 WS 事件確認來源，再取 Host 選回的原 message_id/resource_key：
飛書使用 open.feishu.cn，Lark 使用 open.larksuite.com；各自的租戶 token 只交同域。
在兩個回環端點放同名 key 但不同內容，核實 message 路徑、image/file 類型和兩頁摘要。
錯 app、tenant、域、namespace 或不能形成原消息定位時不得請求 token、也不得下載。
token 到期後，僅後續明選的新取件重新取 token；中途錯頁、HTTP 拒絕、轉址或超限不切換 app/域重試。
既有 WebSocket 接納和 ACK 與 REST 下載分開處理。
平台 fixture 的證據與真 Host 選讀／授權分列。

重現平台層：依 `lark-fixture.lock.json` 準備原生 frame fixture 的兩個 wheel（`UV_FIND_LINKS`），執行 `python ci/check.py EXT-006 --preparation --out <new-output>`。兩條獨立 stdio／REST 測試使用實際 Rust binary，Host 端為 fixture。把 API 暫停在 GET 期間觀察原 pbbp2 ACK，不能用函式單測代替。

HJW 對照：舊實作在 `try_clone()` 出來的 Windows socket 上設 500ms，
實際 WebSocket 仍用握手的長逾時。見 `windows-socket-control` 的最小實驗；
新實作改同一個 OS handle，保留 TLS/CONNECT 握手逾時。平台 peer 的第一次
針對外租戶的 callback 曾逾時、平台 HTTP 為零；另一次 Lark fixture 只有
24,000 bytes，未達第二頁，測資另行修正。

真 Host 對照：把固定 Windows candidate 指給 `YUKI_HOST_CANDIDATE`，使用平台案例已建出的
`packages` 目錄；執行 `python tests/peers/feishu_media_host.py <root> <new-dir> <packages> <exe-sha256>`。
兩個安裝 ID 分別綁定原 app、stage、namespace，只給 `gateway.inbound`。
在 writer 回應前中止、重啟並重放，核對五筆 submission、四份相同父事件的回執（1/1/2/2），
以及原 protobuf ACK；跨 tenant 回 500，錯憑據不送事件。這條路徑不發起附件 callback。
`ingress-02/03` 保留同一 ID 換 namespace 後 offline/disabled、operator enable 被拒的原回條。
最終對拍在 `platform-05` 及 `ingress-05`，兩者使用同一 Windows release binary。

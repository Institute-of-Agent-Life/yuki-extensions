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

## 原應用發送的正常與故障時序

固定 v4 `feishu_ingress.py` 的 216–218 行以原 `root_id`（缺少時用本次 `message_id`）作話題路由。先核對 Rust 入站的同一行為，再用原應用 token 把文字、引用及撤回交回原 chat／root。兩域使用獨立回環端點，同名消息與資源鍵分開記錄。

正常例覆蓋私聊、群話題、原消息引用、token 到期後的新操作及原消息撤回。故障例覆蓋錯 app／tenant、缺授權、原生拒絕、回應遺失、冷啟查原回條及多段中止。附件上傳與發送還需由核心分開記帳，準備步的回條必須能供原後續步讀取。這項核心補充完成後再接上傳、文件發送和附言失敗時序。

## 原文字、引用與撤回的下一步

先以同一個 Rust 發行包連接飛書和 Lark 的獨立回環端點。Host 從原 app/tenant 接納群話題或私聊，Main 明選原事件引用並發送三段文字。計畫保留原 route，首段保留原引用，其餘段沿原話題根消息。每個原生回應保存 message ID，第二段回應遺失時停止，冷啟只讀原回執。平台拒收、撤回無權、格式不明及 token 到期各有獨立斷言。

原生文字請求依 JSON 序列化後的 150,000 bytes 上限切分。回覆端點使用原 message ID，話題回覆帶 `reply_in_thread=true`，普通私聊沿原 open_id。撤回只用 Host 綁定的原 message ID。token 在同一 app 的私有記憶體中到期更新，原效果鍵沿 Host 傳入值。HTTP 管線可取消，退出時先結束正在使用的 curl。

引用、發送及撤回的路由欄位依官方 SDK 與 API 文件核對。[發送訊息](https://open.feishu.cn/document/server-docs/im-v1/message/create) [回覆訊息](https://open.feishu.cn/document/server-docs/im-v1/message/reply) [撤回訊息](https://open.feishu.cn/document/server-docs/im-v1/message/delete)

此階段交付原文字、引用和撤回的候選。附件需要核心先提供獨立上傳回執及後續發送引用原資源的合同，提及需要原人物解析後的結構化欄位。完整 EXT-006 保持進行中。

既有去重鍵保留原 `thread_id` 作 `topic`。SDK alpha.18 的獨立 `topic_root` 保存原 `root_id`，缺少時採本次 `message_id`。只有獲授權的 app／tenant 入站附上原根定位。Mac 已以實際核心候選通過飛書／Lark 的原話題根、首條話題訊息及普通群三種情境，原事件為 1／1／2／2。

`ci/feishu_topic_check.py` 執行三種情境。`ci/feishu_topic_readers.py` 接受已核對的舊、新原生包，對同一資料目錄跑 alpha.4 → alpha.5 → alpha.4。Mac 回讀 app A 的 1 → 2／1 → 2、app B 的 3 → 4／3 → 4，原根證據只存在新事件 2 和 4。三端同來源候選與回條由本地 CI 彙整後交接。完整 EXT-006 繼續等待原生投遞、上傳與 owner-disposition 驗收。

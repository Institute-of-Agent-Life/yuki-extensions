# EXT-037 正常與故障時序

先用 CORE-037 固定來源 `1e7b89362b6f806aa11eed841b28071b22151e7e`、
Rust SDK alpha.11 對拍。三平台 ZIP／成員檢查見
`artifacts/EXT-037/producer-intake/inspection.json`；這只驗交付完整性。
原角色／權限與 trace 都以公開 Host 為真源，不讀主庫。

1. HJW Windows 啟動隔離 Host、實際 Rust consumer 與 loopback 模型。
   公開 operator 建兩個原 Person／QQ 階段；Main 真正派發 tool.call。
   consumer 以原 handle 呼叫 `control.read` 的 `trace.read`，沿固定 Admin
   DTO 的 kind、identity、after、limit、content 參數。預設 content=false。
   記 Host／SDK／consumer digest、逐方法原訊框及模型 HTTP 筆數。
2. 對同一來源另明選 content=true；全文權限由 Host 判斷。
   非管理員、偽造 actor、另一個 handle／撤權需在原寫入或發布邊界被拒。
   不用插件自行解析 Person 身份或角色來補核心決策。
3. 得到可用原 trace 與來源依賴後，才接插件的有界佇列／私庫。
   metadata 是預設；可讀全文需限時保存。滿載如實記 drop，原工具／模型
   效果仍從核心原 operation 查回，不從缺樣 trace 推斷花費或效果。
4. R18：暫停診斷 writer，forget 原作者，再讓舊 writer 返回。
   原 forget.request／水位需使暫存與待寫副本失效；沒有來源依賴責任證據
   不回覆成功 ACK。只保留仍授權的 metadata 或缺樣。
5. 匯出先重查原 scope，預設 metadata；全文另獲許可亦不匯出 opaque、
   簽名、憑證或臨時媒體 URL。版本化匯出走原 tool artifact 讀取。

1／2 是方法與授權 intake。3／4／5 的私庫、丟事件與匯出只有在取得真
來源、授權及清除契約後才可驗收。拒絕診斷不算正式插件或整卡完成。

## 已落實的查詢候選

`plugins/trace` 是獨立 Rust release unit，提供 `trace_query` 真工具。
只保留處理中記憶體，沒有私庫、快取或背景訂閱。輸入限定原 kind／identity、
游標與 1–20 列；正文須明選 boolean。原 handle 由 Host 傳入，不接受 caller
提供 actor／role／handle。每次查詢只呼叫一次原 `control.read/trace.read`。

Windows `source-intake-01` 用獨立 Rust probe 實收公開角色、metadata、正文、
普通人／撤權拒絕。`candidate-01` 的原 Host 日誌拒絕未驗證的 parallel_read
宣告；保留該失敗。只改為順序派發後，`candidate-02` 的 release 插件實收
metadata、含 canary 的明選正文、普通人／撤權拒絕及擦除後空頁。模型 HTTP
實收 12 筆；這是原 Main 的實體 recorder，不由 trace 缺樣推論費用。

正式 Windows 入口：設定 `YUKI_HOST_CANDIDATE` 為 source.lock 所釘 Windows
ZIP，再執行 `python ci/windows.py EXT-037 --preparation --run <新名稱>`。
`ci/check.py EXT-037` 不帶 preparation 會拒絕整卡驗收，因私庫／R18／匯出
仍未實作與驗證。這些範圍也沒有用假 Host 替代。

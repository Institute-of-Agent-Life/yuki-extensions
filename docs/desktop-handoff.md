# Desktop 相容交接（EXT-019）

Desktop 源碼 `bee5692292d8601033798cb2772a075b8db8004b` 固定後端
`004ae36dbe26046d3946b78934c4766333831bcf`、Client rev 9。來源 ZIP
保留 118 個 TypeScript／TSX 檔及 Desktop 的 LICENSE、package.json、兩份
OpenAPI 與 source.json。每個成員按該提交的 Git blob 核對。
`compat/desktop/source.lock` 記錄完整雜湊與來源。

公開預發版 `desktop-v1.0.0-beta.8` 的 tag 指向 `e9ed2f5`。該 tag 的
source.json 固定後端 `c728bb1`、Client rev 7，未列 Admin pin。Windows、
macOS 與 Linux 的安裝包名稱、GitHub 報告的 digest 均列在 lock。
本卡驗的是固定源碼；打包 UI 與候選宿主的實機測試屬 EXT-044。

| 實際差異或依賴 | 交接方式 |
|---|---|
| Client 兩份 OpenAPI 的 bytes 完全相同 | 源安裝沿原 Client／agents 服務。保留 URL、header、query、ordered payload、原 request／Work 的查回方式。 |
| Admin 僅有 ModelDocument.search_backend 的 enum 順序不同 | 兩個字串仍為 model 與 tavily；原 Admin 端可直接沿用。保留兩份 digest。變更證據在 desktop-surface-diff.json。 |
| beta.8 的 tag 釘 rev 7，源安裝釘 rev 9 | 已安裝的 beta 比照原服務。手動升版時，Desktop 倉先更新 source.json、重生 DTO、釘 Connector，再驗打包 UI 與服務能力。 |
| 新 Host／插件尚未交付真消費證據 | 保留舊服務與設備資料。新服務的 shim 或 Desktop PR 須以其實際接口差異決定。 |

執行 `python ci/check.py EXT-019 --out artifacts/EXT-019/local` 可重算結果。
`desktop-callsite-pin.json` 的 H30 包含 TypeScript AST 中 renderer、preload、IPC、
HTTP 與 Connector CLI 的呼叫、原始參數、行號與 DTO 引用。路由表分列 OpenAPI
宣告的方法與相符的源碼字串；動態分派的實際參數保存在呼叫清冊中。
五個故障輸入覆蓋錯誤雜湊、丟失 endpoint、刪除 cancel 欄位、改變上傳編碼與
誤用 SSE 游標。同一份來源的 fingerprint 函式也驗證了附件順序參與雜湊。

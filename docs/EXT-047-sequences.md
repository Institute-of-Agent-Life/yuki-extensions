# EXT-047：真外部消費者與隔離遊戲

## 正常時序

1. 固定 GitHub Monitor `efba5e1ad77f` 的 manifest、觀察入口和授權。逐檔驗 Git blob／SHA-256，不匯入或執行 API9 Python 入口。
2. 依 [燈塔插件配置](../examples/scoped-session/plugin.toml) 安裝 Rust 遊戲。按原入口分配路由，沿用 CORE-051 的 `session` 和 `call` origin。遊戲包含尋找鏡片、校準燈具及引導船隻三步。
3. 原命令 handle 建立 durable、context_profile=none 的會話。玩家用原 session、epoch、key 執行各步，遊戲對話由 Host 的 session API 保存。
4. 核 provider 的可見歷史；遊戲不出現在 Main／Memory；重啟同 key 讀原收據，不另買回答。原 session.page、sources 與內容 digest 對齊。
5. 真 Monitor 的相同 GitHub 事件分別送兩個具有不同授權的訂閱，確認原目標、原 event key 和實收效果。

## 故障時序

- 缺安裝 sessions policy 時，前景原 handle、原已接納 Work handle、actorless 三條路徑均記錄原 Host 回覆。拒絕不是遊戲驗收，也不能定位成核心程式缺陷。
- 斷網記觀測失敗，不能填零活動；相同事件不同目標不得借用授權；正文中的指令只作外部文字。
- 原 API9 manifest 與新 Host 契約不同，不自動載入 Python。真正載入拒絕和舊 Host 可用性需另有執行證據。
- raw QQ 無真 scope 拒絕需真插件與公開受權 gateway，沒有這兩項就列未驗。
- kill／unknown／reset／close 依原 key、epoch 對帳；不以換 key 重新發送未知請求。
- 另一個 Person 即使在已核准入口也不能讀原會話。同鍵改動作或使用舊 epoch，Host 在模型派發前拒絕。原來源清除後，插件先收束 RPC worker 再回覆同一 watermark。

## 本次邊界

`ci/session_intake.py` 保存 Windows 配置缺口的原診斷。現在用
`ci/check.py EXT-047 --preparation` 驗真正的 Lighthouse Rust 發行單位。命令結果沿原
Host operation receipt 回讀。R11 和原 API9 裝載驗證另有自己的第三方輸入。
`compat/external-plugins/github-monitor/` 保留固定版的唯讀參考。

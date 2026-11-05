# EXT-047：真外部消費者與隔離遊戲

## 正常時序

1. 固定 GitHub Monitor `efba5e1ad77f` 的 manifest、觀察入口和授權。逐檔驗 Git blob／SHA-256，不匯入或執行 API9 Python 入口。
2. 使用生產者公開的 sessions policy／auxiliary route 配置安裝 Rust 遊戲。遊戲為有燈塔、鏡片、照明和船隻狀態的多輪解謎，不以 echo 代替。
3. 原 handle 或明確安裝的 actorless policy 建立 durable、context_profile=none 的會話；原 key 執行至少三輪。只有 session API 保存遊戲對話。
4. 核 provider 的可見歷史；遊戲不出現在 Main／Memory；重啟同 key 讀原收據，不另買回答。原 session.page、sources 與內容 digest 對齊。
5. 真 Monitor 的相同 GitHub 事件分別送兩個具有不同授權的訂閱，確認原目標、原 event key 和實收效果。

## 故障時序

- 缺安裝 sessions policy 時，前景原 handle、原已接納 Work handle、actorless 三條路徑均記錄原 Host 回覆。拒絕不是遊戲驗收，也不能定位成核心程式缺陷。
- 斷網記觀測失敗，不能填零活動；相同事件不同目標不得借用授權；正文中的指令只作外部文字。
- 原 API9 manifest 與新 Host 契約不同，不自動載入 Python。真正載入拒絕和舊 Host 可用性需另有執行證據。
- raw QQ 無真 scope 拒絕需真插件與公開受權 gateway，沒有這兩項就列未驗。
- kill／unknown／reset／close 依原 key、epoch 對帳；不以換 key 重新發送未知請求。

## 本次邊界

`ci/session_intake.py` 僅驗公開配置缺口的最小 Rust consumer，使用真 Windows Host。
沒有把它登記為官方遊戲插件、發布單位或 EXT-047 全卡通過。
`compat/external-plugins/github-monitor/` 是唯讀固定參考，不是遷移發行版。

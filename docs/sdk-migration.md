# 外部插件遷移狀態

## GitHub Monitor 1.2.3

固定來源是 `Institute-of-Agent-Life/Yuki-GitHub-Monitor@efba5e1ad77f52364c13702c342ab6b937c86c1e`。
`compat/external-plugins/github-monitor/source.lock.json` 記錄原 manifest、註冊／命令／輪詢／配置／觀察入口、LICENSE、NOTICE 的
Git blob 和 SHA-256。這是 AGPL-3.0-only 的唯讀參考，未變更外部版本或發布。

| 原消費面 | 已確認內容 | 遷移狀態 |
|---|---|---|
| manifest / entrypoint | API `9.0`、`yuki_requires >=4.0.0`、Python `github_monitor:GitHubMonitorPlugin` | 固定 v4 已載入並啟停。Rust Host 在配置階段拒絕 `plugin_api`／`entrypoint` |
| 背景與 HTTP | 一個背景任務、四個 HTTP 併發、`api.github.com` allowlist、`GITHUB_TOKEN` | 原輪詢已驗本機 GitHub 線路。503 保留前次成功時間與已提交游標 |
| 自有配置與 KV | config read/write、storage.private，100 MB | 插件自有；不映射到核心主庫 |
| 通知與媒體 | notification.publish/agent、media.artifact.create | R11 已驗兩個原目標及撤權。Rust Host 在相同發布鍵指向第二目標時拒絕，原目標重讀原回條 |
| 命令 | 原 `github`／alias `github` 命令，SUPERUSER、30 秒；text 最大 2000 | status/repos/add/remove/pause/resume/sync/test/events/rate-limit/outbox；新 Host 註冊與原 scope 待驗 |
| 觀察 | `observe_queue` 讀原配置／queue／diagnostics，分開 queue_available、error_category、last_success_at、failures、pending/inflight | 原觀察入口已核缺 queue、撤權中斷、授權恢復與 503 |
| 獨立 AI session | 已核註冊／命令／輪詢入口未呼叫獨立 session；通知帶 ask_agent/agent_intent | 不將通知 Agent 意圖當隔離遊戲；遊戲另驗 |
| MESSAGE_NORMALIZED | 固定 register 入口只註冊 config、github 命令與背景服務，未註冊 MESSAGE_NORMALIZED | 其他外部插件時序清單未完成；不以 accepted observer.event 取代 |

Mac、Linux、HJW Windows 各跑完原 Monitor 的 25 項測試、一組 R11 和七筆 Rust Host 操作。
R11 在隔離 v4 載入原插件，透過本機 GitHub HTTP、原通知資料庫及兩個私聊目的地重放。
撤銷第二目標後，原插件接納游標為 101，提交游標停在 100。恢復授權後，第二目標以原請求取得獨立回條，
提交游標才推進至 101。外部正文保留 `external_untrusted`，原 Main 工作為零。

CORE-058 以 plugin 和 event key 辨識發布。移植時，消費者需將原來源鍵與新目標發布鍵對應保存，
並在失去回應時讀同一目標的原回條。對拍的試驗鍵證實兩筆發布可分開授權和記帳。
原 KV、真 QQ scope、其他插件對 `MESSAGE_NORMALIZED` 的依賴與正式安裝組合仍待驗。
[原包 SHA-256、線路與逐端回條](../artifacts/EXT-047/original-monitor-01/monitor-migration.json)

重現時，從鎖定的 v4 建立隔離測試副本，將
`tests/peers/github_monitor_v4.py` 放在該副本的 `tests/integration/test_original_monitor_replay.py`。
用原 v4 的鎖定依賴和 Vec1 執行 pytest，讓 `YUKI_MONITOR_REPLAY_OUT` 指向新 JSON。
接著以 `YUKI_HOST_CANDIDATE` 指向對應平台的 CORE-058 原包，執行
`python ci/github_monitor_intake.py --work NEW_WORK --original ORIGINAL_JSON --out NEW_JSON`。
Windows 的 v4 重放使用已驗 SQLite 3.46.0，因 v4 的 FTS5 DDL 需要 `contentless_delete`。

## 隔離遊戲

CORE-051 `9db8b3f073e3`／Rust SDK alpha.9 固定在 `compat/core-051/`。
Windows 最小 Rust intake（`ci/session_intake.py`）已用真 Host 取得原 tool.call 與 dispatched handle。
在目前交付文件未提供完整安裝 policy 的設定下，前景、已接納 Work、actorless 三例
`session.create` 均回 -32003，未呼叫 session.run。這驗證當前配置被拒，不能據此定位核心缺陷。

CORE-051 原包的 foreground 安裝方式見 [Lighthouse](../examples/scoped-session/README.md)。
部署以 `plugins.sessions` 明選 game route、`context_profiles=["none"]` 和
`background=false`，auxiliary route 僅允許原 `session`、`call` 與列出的入口。
玩家透過真 `command.invoke` handle 啟動、續玩和查閱。Rust 插件 0.1.0-alpha.1
由 `ci/check.py EXT-047 --preparation` 對固定原包驗原鍵冷啟、跨 Person 拒讀及原來源清除。
回退保留原 API9 版本與原 Host。GitHub Monitor 仍由原 Host 執行，Rust 遷移組合待維護者驗收。

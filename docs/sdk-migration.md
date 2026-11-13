# 外部插件遷移狀態

## GitHub Monitor 1.2.3

固定來源是 `Institute-of-Agent-Life/Yuki-GitHub-Monitor@efba5e1ad77f52364c13702c342ab6b937c86c1e`。
`compat/external-plugins/github-monitor/source.lock.json` 記錄原 manifest、註冊／命令／輪詢／配置／觀察入口、LICENSE、NOTICE 的
Git blob 和 SHA-256。這是 AGPL-3.0-only 的唯讀參考，未變更外部版本或發布。

| 原消費面 | 已確認內容 | 遷移狀態 |
|---|---|---|
| manifest / entrypoint | API `9.0`、`yuki_requires >=4.0.0`、Python `github_monitor:GitHubMonitorPlugin` | 與 Rust Host 的公開握手不能直接等同；未安裝、未自動執行 |
| 背景與 HTTP | 一個背景任務、四個 HTTP 併發、`api.github.com` allowlist、`GITHUB_TOKEN` | 尚需真 GitHub HTTP 故障與重放驗收；不讀真 token |
| 自有配置與 KV | config read/write、storage.private，100 MB | 插件自有；不映射到核心主庫 |
| 通知與媒體 | notification.publish/agent、media.artifact.create | CORE-058 真目標 grant intake 被拒；兩訂閱 R11 尚未跑到 |
| 命令 | 原 `github`／alias `github` 命令，SUPERUSER、30 秒；text 最大 2000 | status/repos/add/remove/pause/resume/sync/test/events/rate-limit/outbox；新 Host 註冊與原 scope 待驗 |
| 觀察 | `observe_queue` 讀原配置／queue／diagnostics，分開 queue_available、error_category、last_success_at、failures、pending/inflight | 靜態核對完成；未在舊 Host 或新 Host 執行原觀察入口 |
| 獨立 AI session | 已核註冊／命令／輪詢入口未呼叫獨立 session；通知帶 ask_agent/agent_intent | 不將通知 Agent 意圖當隔離遊戲；遊戲另驗 |
| MESSAGE_NORMALIZED | 固定 register 入口只註冊 config、github 命令與背景服務，未註冊 MESSAGE_NORMALIZED | 其他外部插件時序清單未完成；不以 accepted observer.event 取代 |

原觀察入口在 queue 不存在時保留 `queue_available=false`，只在有有效 queue 時加入 pending 數量。
診斷分類與成功時間是不同欄位；網路失敗不得寫成零活動。外部正文不是命令或收件授權。
本次沒有聲稱原 API9 已被新 Host 實際拒載，也沒有聲稱已重驗舊 Host 可用性；兩者保留具名待驗狀態。

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
GitHub Monitor 的兩目標驗收及原 API9 裝載重放仍待交接。

回退保持原 API9 版本與原 Host。第三方未實收新版本、未驗原 QQ scope 前，不改其版本或宣稱相容。

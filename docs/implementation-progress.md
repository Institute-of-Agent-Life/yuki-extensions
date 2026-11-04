# 實作進度

- 任務書 ZIP：`79dfd2ba5a8b96f22dea4c5f72a94ca761b15f2e354e33b36c7ecdbedc3ec3ee`。
  行為基線 `329ca7c487414d2f54ddd98ff4727446ed2446cd`；原倉與核心倉只讀。
- 語言：官方插件接入層用 Rust；Connector 保留 Python 3.12。Monty、參與庫、
  Manager／execd 沿用既有後端；建置與驗收工具可用 Python。

## 已完成：EXT-001

- 實作 `4cbaff3`，三系統 CI 設定 `033bb04`，Rust 真編譯補驗 `f136b4d`。
  PR #1 已合併；功能合併提交 `b481539`。完成卡先推送、三系統 CI 通過才合併。
- 兩個 Python fixture 各建 wheel／sdist 並乾淨安裝；Rust fixture 以獨立
  Cargo.lock／Rust 1.90.0 編譯、打包及執行。只改 alpha，beta／Rust bytes 不變。
  私有 import、越界依賴、浮動 Git、共用他人 rev 及缺 lock 均拒絕。
- CI：初版 `41818382374`；含真 Rust 編譯的 PR run `41819289910`，三系統全通過。
  產物 `artifacts/EXT-001/03/`、`ci-f136b4d/{windows,macos,ubuntu}-latest/`。
  PR 的 checkout 是 `3478b8f`，已核父提交及 tree 與 `f136b4d` 相同，不冒填 head SHA。
- 上述 Rust 程式是建置 fixture，沒有冒充正式插件、SDK 消費或 B0 見證。

## EXT-007 候選包

工作分支 `codex/ext-007`。來源提交 `0150c76` 固定 0.4.3 的 43 個檔與歷史 wheel。
候選提交 `8fd6ed8` 提供 `0.4.4.dev0` wheel、sdist 與可攜 runtime，wire 為 4。
52 個第三方依賴的版本、來源和雜湊與原鎖檔逐項一致。

Windows 結果在 `artifacts/EXT-007/candidate-02/`。乾淨安裝及原地升級均通過，
舊 journal 的副本仍可查 confirmed／unknown 原操作，異設備與同鍵異參均被拒。
原設備設定與原始 DB bytes 保持一致，已設定的 canary daemon 啟動次數為零。
ruff、mypy 與 doctor 通過。原定向測試 164 passed、1 skipped，跳過項是
Windows 檔案 handle 的重新命名限制。runtime 在中文路徑執行，清冊含 5,404 項，
其中的 wheel SHA-256 為 `6160954210d696b0b83d5493fa244b245a59dece24fc3cf43d7ffe6196f615bb`。

`source-01` 保留早期 doctor 探針失敗，`source-02` 為原版通過結果。
`candidate-red` 記未登記發行單位，`runtime-red` 記慢速連外下載中止，
`candidate-01` 記 ruff 行長錯誤，`candidate-02` 為修正後結果。
以上是收到 CORE-002 之前的準備紀錄。

[PR #3](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/3) 已上傳候選。
`6fa4af8` 的 [三平台 CI](https://github.com/Institute-of-Agent-Life/yuki-extensions/actions/runs/41825437154)
在 Windows 得到 164 passed／1 skipped，macOS 和 Linux 各 163 passed／2 skipped。
後兩者略過 Windows ACL 與 PowerShell 專用案例。三個 runtime 都安裝了各自受測的 wheel。
wheel 的 21 個成員內容逐位元組相同，ZIP 建置平台欄位有別。平台雜湊與 runtime
清冊雜湊保存在 `artifacts/EXT-007/ci-receipt-6fa4af8.json`。

## EXT-007 正式對拍

CORE-002 PR #2 已合併於 `2ea4477`；Oracle 產自 `89f15db`，交付說明為
`2bc490c`。未發布的候選 ZIP SHA-256 為
`ccdefae10242b19d2f1a201fcd59f5567c08395fd0c051c3d4e92282f6434df0`。
`compat/core-002/source.lock.json` 固定完整提交、index 及 manifest digest。
版本為 Connector 0.4.3、wire 4、Client rev 9。

Windows 實機正式驗收與產物在 `artifacts/EXT-007/01/`。安裝原 0.4.3 與
候選 0.4.4.dev0，各跑原重連案例，逐筆對照核心提供的 124 筆訊框。
同機兩份 transcript 的 SHA-256 均為
`38b288e670e16160cfbaf662b18dbe4f334637594bbd43471f5f99b47eba139e`。
跨系統 hello 的平台、shell 與中斷能力另按實機檢查。刪 ACK、改 sequence
均遭拒絕。原地升級、隔離資料與 runtime 通過；Connector 未發布。

可交回核心的 Connector 證據為 `connector-upgrade.json`、兩份原始
`wire4-*.json` 與同次 manifest。插件 Host／SDK 尚無消費證據。

## 下一步

PR #3 已在提交 `41860a2` 通過三平台正式 CI（run `41833181301`），
合併到 `main` 的提交為 `18e028c`。每平台的 manifest 與 transcript 雜湊
均已覆核，見 `artifacts/EXT-007/ci-receipt-41860a2.json`。EXT-008／009／010
可沿已驗 Connector 檢查原生驅動，EXT-019 可用同一 oracle 盤點 Desktop。
EXT-002 尚需 CORE-031 Rust／Python SDK 與 schema；其餘需求見
`docs/core-interface-requests.md`。共享預算依總書 K05。


## EXT-008 Codex 原生驅動

分支 `codex/ext-008`。Windows 在已安裝的 0.4.4.dev0 重現 queue
回 `native_error`（18 通過、1 失敗）。候選 0.4.4.dev1 將原生
`-32601` 回為 `unsupported_action` 並清除已明確拒絕的待排項目。
52 個依賴維持原鎖定。Windows 實機的 19 個案例通過，包含原生問答、
指定 turn 的 steer／cancel、detach、CLI 發現，以及接納 prompt 後丟失回應。
恢復只讀原 operation，daemon 共收到一次 turn/start。證據在
`artifacts/EXT-008/01/codex-driver-wire.json`，失敗基線在
`artifacts/EXT-008/faults/`；此為本機 loopback daemon，無模型呼叫。

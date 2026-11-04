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
候選仍待 CORE-002 的具名 oracle 與 manifest。整卡驗收與發版保持待辦。

草稿 [PR #3](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/3) 已上傳候選。
`6fa4af8` 的 [三平台 CI](https://github.com/Institute-of-Agent-Life/yuki-extensions/actions/runs/41825437154)
在 Windows 得到 164 passed／1 skipped，macOS 和 Linux 各 163 passed／2 skipped。
後兩者略過 Windows ACL 與 PowerShell 專用案例。三個 runtime 都安裝了各自受測的 wheel。
wheel 的 21 個成員內容逐位元組相同，ZIP 建置平台欄位有別。平台雜湊與 runtime
清冊雜湊保存在 `artifacts/EXT-007/ci-receipt-6fa4af8.json`。PR 的合併條件仍包含 CORE-002。

## 跨倉輸入與下一步

- 未消費任何新核心包；目前沒有 Host／SDK 的版本或 digest，核心 Releases 為空。
  CORE-002／031／039 的交付產物目錄亦未見候選。未拿鄰倉源碼作生產依賴。
- 已核 68 張擴展卡：沒有尚未完成且前置全滿足的卡。前沿與觀察來源見
  `artifacts/readiness/2026-11-04.json`；EXT-043 另待 CORE-044 穩定面。
- 下一步：取得有來源 commit／manifest／hash 的 CORE-002 `v4-oracle-index.json`，
  完成 EXT-007／019；取得 CORE-031 不可變 Rust／Python SDK 與 schema 再做 EXT-002。
  方法、欄位語義與失敗案例需求在 `docs/core-interface-requests.md`。
- 真插件對拍尚未發生，沒有可交還核心的宿主／SDK／插件方法見證。發布、部署及
  真平台切換未執行。共享預算一律依總書 K05；不增加 unknown 重試權。

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

## 準備中：EXT-007

- 工作分支 `codex/ext-007`。43 個原檔已取出，16 個執行檔與附件歷史 0.4.3 wheel
  bytes 相同；來源與 SHA 在 `connector/packaging/source.lock.json`。wire 維持 4。
- Windows／原 wheel：ruff、mypy、doctor 通過；pytest **164 passed、1 skipped**。
  skip 是 Windows 已開啟 handle 不允許刪除／替換。證據在本地
  `artifacts/EXT-007/source-02/`，狀態是來源準備 PASS、整卡 BLOCKED。
- `source-01` 的測試已通過，最後 doctor 因新探針誤加 `--json` 失敗；保留失敗原件。
  `source-02` 修正探針後通過。沒有改 Connector 行為或發布新的 0.4.3。
- 因 CORE-002 尚未交付，本卡程式及準備產物保持未提交，不先合併為完成卡。

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

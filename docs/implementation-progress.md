# 實作進度

- 任務書：v3.2 核心文檔補核版，ZIP SHA-256
  `79dfd2ba5a8b96f22dea4c5f72a94ca761b15f2e354e33b36c7ecdbedc3ec3ee`。
- 分支：`codex/ext-001-rust`（EXT-001 Rust 建置補驗）；遠端最初為空倉。每張卡推送，三系統 CI
  通過後再合併到 main。現有使用者檔案保持原位。
- EXT-001：Windows 11／Python 3.12 驗收通過（`artifacts/EXT-001/02/`；
  增補 Cargo 個別依賴 pin 與 Windows 路徑案例的最終證據為 `03/`）。
  兩包各建 wheel／sdist，分別乾淨安裝；只改 alpha 不重建 beta。私有核心 import、
  越界路徑、浮動 Git 及缺 lock 均拒絕。Rust 僅驗 manifest 邊界，未跑編譯器或 Host。
  實作提交 `4cbaff3`；三系統 CI 提交 `033bb04`，已推送 `codex/ext-001`。
  CI run `41818382374` 的三個 acceptance job 全部通過，已以同 SHA 建立 main。
  首次長分支推送曾失敗；改用 `codex/ext-001` 成功，未刪既有 Git 中繼檔。
- CI 已按追加要求設 Windows／macOS／Linux 三系統；本機測試仍只在 Windows。
- 初次 Windows 線上下載工具停住，尚未執行產品測試；改傳官方雜湊鎖定 wheelhouse
  後離線執行成功。工具來源：`ci/tooling.lock.json`；每次源快照 SHA 記於 transport。
- 核心套件：尚無可消費的已提交 SDK／Host／CORE-002 oracle。沒有核心套件版本或
  digest 可列；未用鄰倉原始碼作生產依賴。
- 真消費者交還證據：尚無；EXT-001 是建置隔離，不冒充插件對拍。
- 進行中：EXT-001 補入真 Rust binary 的獨立建置／執行；只屬測試 fixture。
  新官方插件接入層使用 Rust；Connector 繼續是 Python 3.12，既有 Monty、參與庫、
  Manager／execd 後端沿用原實作。EXT-002 仍待核心發布 SDK，不另造協議。
- EXT-007 準備：已取固定提交的 43 個檔，16 個執行檔與附件的歷史 0.4.3 wheel
  bytes 相同；source pin 在 `connector/packaging/source.lock.json`。未驗證移植候選，
  未取得 CORE-002 `v4-oracle-index.json`，不列完成。
- 下一步：核對 CORE-002 不可變產物，再完成 EXT-007／EXT-019。
- 共同預算：依總書 K05，接納邏輯請求只預留一次；各物理 attempt 分記派發、
  回應及 usage／未知費用。同一請求的重試不再預留，也不取得未知請求重試權。

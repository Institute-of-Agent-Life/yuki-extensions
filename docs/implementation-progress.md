# 實作進度

- 任務書：v3.2 核心文檔補核版，ZIP SHA-256
  `79dfd2ba5a8b96f22dea4c5f72a94ca761b15f2e354e33b36c7ecdbedc3ec3ee`。
- 分支：`codex/rust-extensions-v3-2`。遠端原為空倉；每張通過卡推送，三系統 CI
  通過後再合併到 main。現有使用者檔案保持原位。
- EXT-001：Windows 11／Python 3.12 驗收通過（`artifacts/EXT-001/02/`；
  增補 Cargo 個別依賴 pin 與 Windows 路徑案例的最終證據為 `03/`）。
  兩包各建 wheel／sdist，分別乾淨安裝；只改 alpha 不重建 beta。私有核心 import、
  越界路徑、浮動 Git 及缺 lock 均拒絕。Rust 僅驗 manifest 邊界，未跑編譯器或 Host。
  本地提交：`4cbaff3`。GitHub 首次推送連續兩次回 Internal Server Error；
  尚未推送成功、尚無遠端 CI、尚未建立 main。
- CI 已按追加要求設 Windows／macOS／Linux 三系統；本機測試仍只在 Windows。
- 初次 Windows 線上下載工具停住，尚未執行產品測試；改傳官方雜湊鎖定 wheelhouse
  後離線執行成功。工具來源：`ci/tooling.lock.json`；每次源快照 SHA 記於 transport。
- 核心套件：尚無可消費的已提交 SDK／Host／CORE-002 oracle。沒有核心套件版本或
  digest 可列；未用鄰倉原始碼作生產依賴。
- 真消費者交還證據：尚無；EXT-001 是建置隔離，不冒充插件對拍。
- 下一步：完成 EXT-001 Windows 驗收；核對 CORE-002 的不可變產物，再接 EXT-007
  與 EXT-019。Connector 的固定源搬入可先準備，不先宣稱卡片驗收完成。
- 共同預算：依總書 K05，接納邏輯請求只預留一次；各物理 attempt 分記派發、
  回應及 usage／未知費用。同一請求的重試不再預留，也不取得未知請求重試權。

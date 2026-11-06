# CI 執行與快取

PR 以 merge ref 執行一套 Windows／macOS／Linux acceptance 與受影響 release units
的 package 檢查。main push 與手動執行保留。同 PR 的新執行取消舊執行；不同 PR、main
與手動執行互不取消。PR #33 的九行去重修正已精確重用於佇列首張 PR #16 的 `972c66d`。
當 main 前進，下一張卡仍需正常合入 main，核對 merge parents、當前 head／base 的
完整檢查、下載 ZIP／GitHub digest／成員 manifest 和最後 merge tree。

快取沒有增加 job、改變 runner、合併發行單位或省略測試。現有較大的 package 矩陣先
保留；後續分組應根據實際等待和執行時間決定。queued 不佔 running 名額，兩種時間分開記錄。

## 正常時序

1. acceptance 以 OS／架構、兩個固定 Rust 版本、Cargo.lock／toolchain 和 SDK crate
   bytes 選擇 registry 快取。所有 crate 每次讀取仍核鎖定 SHA-256；只有顯式指定的
   `YUKI_CRATE_CACHE` 可寫入，使用者的 Cargo cache 只讀。
2. Rust package 先驗來源邊界及實際 SDK crate，取得真正 rustc verbose host／版本、
   Cargo 版本、OS／架構／映像、編譯 flags、該單位全部來源與 lock、建包腳本及 SDK
   contract／crate SHA。完整輸入形成一個 key，沒有寬鬆的 target restore prefix。
3. 僅重用 registry archives 與這個單位的 target。來源／vendor 另建於短路徑，
   不入快取；已存在的原碼目錄一律拒絕覆蓋。臨時來源名稱用 16 位前綴以免 Windows
   路徑過長；持久 target、輸入和快取 key 保留完整 SHA-256。
4. 無論 cache hit 與否，原 cargo test／cargo build、SDK／lock 驗證及發行包產生
   全部執行。版本、發行 tag、package-manifest 與原 package ZIP 結構保留。
   真實快取輸入以獨立 `cache-inputs-<unit>-<os>-<sha>` artifact 交付。

## 故障時序

- 缺快取：正常下載已鎖 registry 分發包，核 SHA 後才原子寫入；離線 SDK 照原 contract。
- 壞快取：忽略不符 SHA 的 archive；網路仍回壞 digest 時失敗且不入快取。
- 同名／同版本不同 SDK：實際 crate SHA 與 contract 不符即拒絕；正式更換 pin 後得到新 key。
  OS、架構、compiler、lock 或 flags 不同也不共用 target。
- 來源殘留／並行撞目錄：建立失敗，保留原內容；只清理由該次 build 成功建立的臨時目錄。
- 測試／建包失敗：維持原失敗結果。沒有 cache-hit 跳過檢查或 continue-on-error；
  actions/cache 只在整個 job 成功後保存。快取讀寫不影響業務／模型重試和 K05。

## Windows 實收

`artifacts/readiness/ci-cache/receipt.json`：HJW Windows GNU Rust 1.96.0，原 local-agent
alpha.1／SDK alpha.3，兩次真正 cargo test（含原 SQLite 重開／外庫拒絕回歸）及 release
build。冷輪 207.235 秒、38 筆 registry GET；熱輪 26.719 秒、零 registry GET、零
compile lines。熱輪封鎖 registry 網路，兩輪 binary 均為
`fdfb6d7d15eef8fe34e518f3eaf6139c88f7b06aa26b2eb6461acfb65b30bd1f`。
十項 cache 故障／隔離測試通過，19 份來源綁定未變，原 jobs／步驟／矩陣核對及
Windows actionlint 1.7.12 通過。原始 manifest／命令／來源 ZIP 回條在 `windows-02`；
完整原 ZIP 留在其 transfer.json 的 HJW 目錄，binary／target 不提交 Git。

`windows-01` 保留初次深路徑解包失敗與同源診斷。縮短臨時路徑後重驗通過；沒有改
Windows 登錄設定、Core、SDK 或插件。以上是本機 cache 實驗，不是 GitHub cache hit、
組織配額或排隊改善的實證，也不是插件／Host 新驗收。

actions/cache 鎖官方 v6.1.0 commit `55cc8345863c7cc4c66a329aec7e433d2d1c52a9`，
[官方使用說明](https://github.com/actions/cache/tree/v6.1.0) 與
[快取隔離／命中規則](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)。

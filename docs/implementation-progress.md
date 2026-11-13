**EXT-027 原投遞目標。** 分支 `codex/ext-027-pending-target`。Rust subscription-monitor 0.1.0-alpha.4 在派發前核對訂閱目前的入口。未派發且已移除目標的請求從待辦清出，原去重鍵保留。失去確認的請求持續保留原 key 和 payload。Mac、Linux、HJW Windows 各通過 11 項 Rust 測試及八筆 Host 發布。改目標後冷啟為零重送，恢復原目標後才核原回條。[三端包與回條](../artifacts/EXT-027/native-target-fence-01/subscription-deliveries.json) SHA-256 `4f996da246aa9f1d23f99a77cacd36c9aa43c3ae8a6608d00292c614b63dcf2b`。

**EXT-027 RSS 2.0 與 Atom。** 分支 `codex/ext-027-rss-atom`。Rust subscription-monitor 0.1.0-alpha.3 新增 UTF-8 XML 來源，沿用原訂閱授權和 journal。Mac、Linux、HJW Windows 各通過 10 項 Rust 測試及八筆 Host 發布。RSS 和 Atom 都先靜默保存基線，拒絕截斷文件或 DTD，恢復後各送一筆新條目。冷啟重抓維持一筆，清除回條後仍保留去重鍵。回放核對原條目 ID、作者／標籤篩選、相對連結和 UTC 時間。[三端包與回條](../artifacts/EXT-027/native-xml-01/subscription-deliveries.json) 的 SHA-256 為 `73b41387b281fd0f22d57fe62039ad3966c275779439a6aa337ec3f2361dd68a`。仍需 R06 原來源錄製、舊 KV 遷移和正式 Host／插件組合。

**EXT-027 Miniflux 分頁。** 分支 `codex/ext-027-miniflux-pages`。Rust subscription-monitor 0.1.0-alpha.2 按 entry ID 分頁，整次讀取成功才保存原訂閱狀態。Mac、Linux、HJW Windows 各驗第二頁 HTTP 失敗、總數變動、重複 ID 後保留原狀態，以及恢復後兩個訂閱各發布一次。每端共六筆發布，原 OneBot 投遞的 unknown 與新投遞的 confirmed 均可回讀。三端原包與回條見 [subscription-deliveries.json](../artifacts/EXT-027/native-pagination-01/subscription-deliveries.json)，SHA-256 `e42f62a754d0bbc2654f807cec66be34b4abb00c6c128c03ddc5e950197c4ad2`。原錄製、RSS／Atom 和正式安裝仍待驗。

**EXT-028 原讀頁快取。** 分支 `codex/ext-028-reader-cache`，Rust web-fetch 0.1.0-alpha.4。原 `read_webpage` 在程序內保留十分鐘的公開正文快取，命中仍核原 Host handle；不同問題及冷啟重新取頁。Mac、Linux、HJW Windows 各通過 25 組原讀頁及一組預設 `web_fetch`，失敗與超大結果各驗再次取頁。固定 v4 比對及正式 1.0.0 Host 的三端原包見 [fetch-source.json](../artifacts/EXT-028/reader-cache-01/fetch-source.json)，SHA-256 `282413ddc0329a2188fad9db1e1599b8e072729becd39c5de67b5b39bba06cde`。快取隨程序退出回收。插件是本地候選。

**EXT-036 原來源與索引稽核。** 分支 `codex/ext-036-quality-integrity`。Rust memory-maintenance 0.1.0-alpha.3 用原 SDK alpha.8 連接核心 #126 的開發 Host `f9a3bc7302a6`。Mac、Linux、HJW Windows 各通過 21 組，掃描零模型呼叫及零資料變更，FTS 修復只改核准列，缺證與無效證據分列，未知 embedding 原操作重啟後未再次派發。三端也通過 EXT-034 原重建授權和故障回歸。[原包與回條](../artifacts/EXT-036/native-quality-integrity-01/hygiene-report.json)，SHA-256 `dff11371c88c5a4f1d8ded93e27277aaaa4fd3de6eaa71e924108300bd4e2c74`。本地報告按來源清除和公開安裝組合待驗。

**EXT-030 原 QQ 首輪開發驗收。** 分支 `codex/ext-030-original-main`。Mac、Linux、HJW Windows 各以核心 #125 受測 Host `eb9d6d2e0d69` 和 #73 的原 Rust 媒體插件驗八組，包括語音首輪、純文字並行、另一人引用、雙 Bot、損壞、超時拒絕、清除中斷及跨 handle 去重。模型端為回環，付費為零。[三端回條](../artifacts/EXT-030/native-main-audio-01/asr-source.json) SHA-256 `a43df4a1273036fbeb42313ba88eaf71009fcf41d96a5d176db9d4a51d453ea8`。雙 Bot 是隔離 OneBot 測試接收器，固定 MP3 由原 `get_record` 線路回傳。真 QQ 接收器 SILK 轉換及公開安裝組合待補。

**EXT-030 Rust 語音候選。** 分支 `codex/ext-030-native-audio`，[#73](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/73) head `932293d6ce3e`，main `c1e83ccd15a0`。media 0.1.0-alpha.2／Rust SDK 1.0.0-alpha.21。Mac、Linux、HJW Windows 每端以同一執行檔驗 WAV、AMR、原請求重讀、損壞檔、失回應與清除中斷，再過六組 EXT-031 Main 影片及 PDF 回歸。[三端包與來源](../artifacts/EXT-030/native-asr-01/asr-source.json) SHA-256 `269e8d060f6a402e59b77249a0d5a11ed6d8840e027518e8c080170438287847`。

**EXT-031 原接收器三端回放。** 分支 `codex/ext-031-native-receiving`。Mac、Linux、HJW Windows 各使用正式飛書 0.1.0 原包、CORE-038 `0114269addf5` 及 #71 的原生媒體插件，從飛書／Lark 長連線接納到 Main 讀回原 PDF 頁文。兩域各只取件一次。兩個錯位用例均為零取件、零解碼。三端 12 組原線路、來源與雜湊見 [selected-receiving.json](../artifacts/EXT-031/native-receiving-01/selected-receiving.json)，SHA-256 `7fcedd823105598d8864a5ffcd63ad772367ee48fa5ed50361f8c09e38f352d7`。Windows 以現有 Git curl 8.17.0 重放。正式 producer／安裝組合仍待交付。

**EXT-031 原生影片與 PDF 候選。** 分支 `codex/ext-031-native-codecs`。Mac、Linux、HJW Windows 各以 CORE-038 `0114269addf5`、reader 58 跑同一份 Rust 媒體插件來源。六組所選附件、六組實際 Main 回放包含 PDF 頁文、原影片 0 秒與 5 秒的像素、無選擇、無視覺、損壞及清除後遲到結果。FFmpeg 與舊 PDF 解析器均按目標鎖雜湊。三端原包、來源與回執在 [media-inspection.json](../artifacts/EXT-031/native-selected-erasure-01/media-inspection.json)，索引 SHA-256 `85766eee41c008d8d9b6057133e2fcb9f74c306336b1c9c7c1fc2e4d8ba6027f`。Windows 大封包回傳逾時後從原檔擷取並驗證全數具名證據。此為未發布候選，接續以同一組實物驗原入站取件與公開安裝。

**EXT-006 開發驗收完成。** 分支 `codex/ext-006-published-rest`。Mac、Linux、HJW Windows 各以 GitHub 下載的飛書 0.1.0 原包和正式 Host／SDK 1.1.0 通過 30 組文字／撤回、32 組上傳、22 組提及、三組話題與雙租戶入站。原包另在隔離線路驗兩域取件、token 續期、錯租戶拒絕、失回應及清除中斷。保留 HJW 先前原取件進入 Main 的證據，以及固定舊版 55 項核對、合成舊資料和空私庫清冊。三端逐次回條與 SHA-256 在 [lark-rest-receipts.json](../artifacts/EXT-006/published-rest-01/lark-rest-receipts.json)，總索引 SHA-256 `bfea4c760a5f907fddab0cbf5c1892e731026c0d2dc5567f4d2738e41cf98084`。核心來源 `09bdd7382de4`，擴展原包來源 `66a593a47cb8`，付費呼叫為零。現場企業連線及實例映射由 EXT-041 接續。此卡合入後，擴展完成 13／68。EXT-069 需核心提供受權的原群恢復接口，EXT-031 繼續三端附件重放。

**EXT-043 飛書與 Lark 0.1.0 已發布。** 分支 `codex/ext-043-feishu-stable`，[#69](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/69) 的 `66a593a47cb8` 合入 `0478196050b5`，發布 tag 指向原來源。三端用 Host／SDK 1.1.0 通過 18 例。GitHub 五個附件回取與 SHA-256 見 [發布回條](../artifacts/EXT-043/feishu-published-0.1.0/github-publication.json)，回條 SHA-256 `b818a9c506eeea14be38568803cbd3b892b1bd9161815ebd77c09807ed27382e`。[飛書 0.1.0](https://github.com/Institute-of-Agent-Life/yuki-extensions/releases/tag/plugin/feishu/v0.1.0)

**EXT-034 歷史重建 Rust worker。** 分支 `codex/ext-034-rebuild-worker`，memory-maintenance alpha.2。Mac、Linux 和 HJW Windows 以同源 CORE-035／050 開發包 `fca3f22ce60d` 驗證原範圍、候選預覽及明確批准子集。核心提交後中斷取回原回執，收到不符的 ordinal 時保留原批准。擦除先清可辨識的來源，遇無法辨識的檔案留同一 watermark，修復後補交。每端僅一筆回環模型請求，付費為零。三端候選、來源清冊及回條在 [rebuild-subset.json](../artifacts/EXT-034/rebuild-worker-02/rebuild-subset.json)，SHA-256 `795bb296d9c1215ab2742fab9c8f02fc233d149792e66ce37bfebca2124691ba`。完整卡仍需不可變 producer 發布及正式 Host 安裝驗證。

**EXT-040 獨立 Rust 安裝器。** 分支 `codex/ext-040-standalone-installer`，yuki-setup alpha.3。Rust 程序直接驗證原 Ed25519 簽署、SHA-256 與包清冊，再安裝到新目錄。三端使用空 `PATH` 驗公開基底、原開發包和離線 `init`／`doctor`。Windows 的兩種原 web-fetch 選裝均完成握手。Mac 另以固定 Linux ARM64 映像通過 22 項 Compose 驗證。Linux 首次輸出遇到外接盤 AppleDouble 權限，改由容器內完成驗證，再封存回條。三端安裝器與來源清冊見 [setup-install.json](../artifacts/EXT-040/rust-installer-01/setup-install.json)，SHA-256 `a2c6ba351a07573eedb5f7635e68f12edd04eba19ee0979052e23cd10e53c703`。SWE-2 Max 核對原合同。此為未發布候選，完整卡仍需同架構 SnowLuma 的實際就緒驗證。正式總數 12／68。

**EXT-028 原 `read_webpage` 選裝入口。** [#66](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/66) head `34d09eb82926`，合併 `603785b82ae9`。Rust web-fetch alpha.3。Mac、Docker Linux、HJW Windows 使用公開 B0 1.0.0 Host 與固定 v4 oracle，各通過 18 個相同結果、一個 SDK 超大幀拒絕及原預設 `web_fetch` 回歸。模型工具宣告、Unicode 路徑、來源鍵與分頁逐項比對。回環驗證，付費呼叫零。SWE-2 Max 已核對授權、來源識別和預設工具。三端來源、原包及回執見 [read-webpage.json](../artifacts/EXT-028/read-webpage-03/read-webpage.json)，SHA-256 `3c59724912f9ec2bc03a034d81bb90dfcd61ae4665aa232145619db49e28183f`。候選為本地未發布。v4 十分鐘快取、URL／HTML 邊界及同一安裝 E13 待驗。

**EXT-040 Compose 安裝已通過本地三端驗證。** [#65](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/65) 合併 `edfadf86fcc3`，分支 `codex/ext-040-compose-install`，yuki-setup alpha.2。Mac、Linux、HJW 分別完成 7、7、8 項原生基底 1.0 安裝驗證。Mac 另用固定 Linux ARM64 映像完成 22 項 Compose 操作。兩個同名安裝擁有獨立資料卷，重建後各自保有資料。明選的外部入口只在既有代理網路提供 `/readyz`，未設定的 QQ 路由回傳 404。未發布三端包、來源雜湊與原回條在 `artifacts/EXT-040/compose-entry-04/setup-install.json`，SHA-256 `d2923d6926a053e13352962b2065e72c38cf760f0217c81ca9f7054edfb890b3`。完整卡仍需 SnowLuma 的同架構原映像、啟動就緒及 QQ 登入驗收，正式總數 12／68。

**EXT-006 原帳號提及已合併。** [#64](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/64) `37fcab390f11` 進入 main `80784b724308`。分支 `codex/ext-006-native-mentions`，Rust alpha.8／SDK alpha.21，核心 #118 受測來源 `338245cab96f`，已合併核心 main `2a25234e0a44`。Mac、Linux、HJW Windows 各通過 30 個文字／撤回、32 個上傳、22 個提及及三種原話題重放，另驗舊版回讀、55 項 owner 核對與擦除取消。獨立審查以同一簽署 Host 重現 alpha.7 的原提及規劃拒絕，alpha.8 完成 11,000 個提及與 323 頁原註記，失回應後冷啟未重送。

原包、來源快照、雜湊與回條位於 `artifacts/EXT-006/original-mentions-02/original-mentions.json`，SHA-256 `0e7764a1340037607a182eb0bba9406dd757196d0f715687ea2a136def660d7f`。三端該輪自建 target 已清理。此為未發布開發候選，整卡待擴充公開合同驗收，正式完成數維持 12／68。

**EXT-006 owner-disposition 三端通過。** 分支 `codex/ext-006-owner-disposition`。固定舊版 `329ca7c487414d2f54ddd98ff4727446ed2446cd` 的隔離 oracle 通過 55 項測試，保存合成 SQLite 與兩筆原回執。Mac、Linux、HJW Windows 各驗空私庫、原 app／platform 篩選、缺失目錄、未知資料、三種未關閉 SQLite sidecar、錯 schema 與來源變更。正常卡入口產出 owner 檔與明確的結構化提及待辦，完整卡維持 blocked。

三端原包與 reader 證據在 `artifacts/EXT-006/original-owner-01/original-owner.json`，SHA-256 `68d6612c8e674e063516b79f18c004a4048d31d8586d29bfc876f83462a0dac6`。來源快照 `3024d01498e754ede58b1ee301a2c0f0ab2597254bf04077b25a1386e35c3f82`，623 個來源檔已綁定。Rust／SDK 輸入沿 #62 原三端結果，611 個既有輸入逐檔相同，詳 `runtime-reuse.json`。此輪沒有新增編譯 target，Linux 臨時容器已移除。前兩輪檢查失敗和修正原因保存在 `previous-attempts.json`。

附件上傳 #62 的本地提交 `890d695a0def` 已合併 main `a5d126f8bdc5`，合併回條見 `artifacts/ci/local-pr/62/receipt.json`。全部為未發布開發候選，實際部署的 tenant 綁定、secret 引用、私庫盤點與 CORE-041 映射留待實例核對。正式總數維持 12／68，下一步完成核心原 account 提及與飛書消費者。

**EXT-006 原生附件上傳三端通過。** 分支 `codex/ext-006-native-upload`，Rust alpha.7／SDK alpha.20，鎖定核心 #116 的受測來源 `0e45e53958e77`，核心 main 已合併 `8e150d8325a6`。Mac、Linux、HJW Windows 每端完成 32 個附件情境、30 個文字／撤回情境、三種話題路由、alpha.6 → alpha.7 → alpha.6 回讀，以及原件分頁遺忘、晚到頁隔離與上傳中取消。每步回執及原包索引在 `artifacts/EXT-006/original-upload-01/original-upload.json`，SHA-256 `7a66c85ded679224fec90813014db71d3fabd50be3429c228df93bb53ad8ed06`。來源快照 `7b0ba3a2b9ba23b5957a2c525528584c73c831dc670d3bf68a1755ec11db039e` 的 635 個檔案已核對。

三端包雜湊為 Mac `f2273eb2aece656acfabef5fb98506bc188d1998426a70195b4757b0d24f2623`、Linux `1910aab1e690e761e7f8f8871b40a8f338e3dd9beed8450a046f293796ab8db6`、Windows `5f1814d205c0dfb8e1425e2e514fc69609b1629a4a598d9388788750f486c001`。本輪原包均為未發布開發候選，平台和模型均用回環，付費呼叫為零。三端 gate 自建 target 已清理，另清理兩個已完成 SDK20 的 Mac 預驗 target，共 942,468,338 bytes，2,437 個保留檔案校驗相符，回條在 `artifacts/ci/cleanup-20261107/rest20-preflight/`。完整 EXT-006 保持進行中，正式總數維持 12／68，接續結構化提及與 owner-disposition。

**EXT-006 原文字、引用與撤回三端通過。** 分支 `codex/ext-006-native-rest`，Rust alpha.6／SDK alpha.20，鎖定核心 #115 的受測來源 `942a534763ba`。Mac、Linux、HJW Windows 各 30 組真 Host 對拍、三種話題路由、alpha.5 → alpha.6 → alpha.5 回讀及兩域的原取件／遺忘取消全部通過，8 MB 原文分頁各端均在限時內完成。完整原包、逐次回執及來源綁定見 `artifacts/EXT-006/original-rest-22/original-rest.json`，SHA-256 `a4a2a93845c33d297ec180869aa440070b6d45a2dba0937dfa0a13afff225959`。三端均使用回環平台及模型，付費呼叫為零。

本輪修正 Windows curl 7.79.1 長配置行遺失正文／授權的故障，REST 使用 curl 8.3 以上的 binary stdin 與子程序環境展開，HJW 明選現有 Git curl 8.17.0。獨立重現與修正對照見 `artifacts/EXT-006/curl-compatibility/`。另修正取消驗收對 Windows TCP reset 的判讀。前兩輪失敗詳 `original-rest-22/previous-attempts.json`，本輪三端編譯 target 已清理。全部候選尚未發布，正式總數維持 12／68，接續原生附件上傳、結構化提及與 owner-disposition。

**EXT-006 原話題定位三端通過。** 分支 `codex/ext-006-original-delivery`，#60 的飛書 alpha.5 鎖定核心 #113 三端候選 `e6e4972a76911` 與 Rust SDK alpha.18。Mac、Linux、HJW 各完成三種話題情境、同安裝 alpha.4 → alpha.5 → alpha.4 回讀及原 app／tenant 媒體回歸。原 `thread_id` 保持事件去重鍵，原 `topic_root` 由首次接納獨立保存，舊事件重投沒有補填。601 個快照檔案與三端原包經核對，EXT-001／002／019 基線的 47 個輸入保持相同，完整證據在 `artifacts/EXT-006/original-topic-18/`。所有平台端點使用回環，付費呼叫為零。正式任務總數維持 12／68，原生投遞、上傳分步與 owner-disposition 繼續實作。

**EXT-036 保留報告的清除。** 分支 `codex/ext-036-audit-erasure`。Rust memory-maintenance 0.1.0-alpha.4 用核心 [#127](https://github.com/Institute-of-Agent-Life/yuki-core/pull/127) 同一受測來源 `dcabd6fc5b52` 的三端原包，Mac、Linux、HJW Windows 各過 23 個保留報告案例及 21 個舊 Host 案例，另過原重建。新安裝明選保留報告和私有工作目錄。遇無法分類的檔案保留原清除待辦，冷啟只清指定原報告和暫存，並回覆同一 watermark。[三端原包與回條](../artifacts/EXT-036/native-quality-erasure-01/hygiene-report.json) SHA-256 `c1ad5195a79e31621efa214a3cea77c5aaf4dead5113f1db2c693c3786f180e8`。正式安裝仍待發布的 Host／插件組合。

**EXT-027 直接送達與未知實收。** [#78](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/78) 合入 `797c61b15e94`。Mac、Linux、HJW Windows 各驗六筆原發布。OneBot 測試端確認第一段後斷線，核心保留第二段 unknown。冷啟只送下一個新訂閱項目，原 unknown 保持原狀。三端回條 [subscription-deliveries.json](../artifacts/EXT-027/native-delivery-01/subscription-deliveries.json)，SHA-256 `ed719efe2fb71928d73afa2e89b2711cf5d29298dcfa0626bc5eb6ccd653c24c`。整卡仍待 R06 原錄製輸入、RSS／Atom 及 Miniflux 分頁和正式安裝組合。

**EXT-027 訂閱通知開發候選。** [#77](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/77) 合入 `b7188ac1d35b`。Rust subscription-monitor 0.1.0-alpha.1 使用 CORE-058 原 Host `cb02f74ea48b` 與 SDK 1.0.0-alpha.10。Mac、Linux、HJW Windows 各以本機 HTTP 驗 Miniflux、Bilibili 動態和直播轉態，包含原管理員授權、四份獨立發布、回應丟失後重讀、撤權及私聊來源清除。三端原包與回條見 [subscription-deliveries.json](../artifacts/EXT-027/native-notification-01/subscription-deliveries.json)，SHA-256 `d809440f53ac95cca5c4c367b2c88dde3a7cace62b731e20f7b3954225aeb4ba`。

# 擴展實作進度

**Telegram 0.1.0 已正式發布。** 分支 `codex/telegram-published-receipt` 補存發布、五個附件回取驗 SHA 及舊工作流停用回條。來源 `e9e012d761da`、SDK 1.0.0。Linux arm64 需 glibc 2.39 以上與 curl，已在 glibc 2.41 的本地鏡像重放。本次文件提交沿用 #58 的三端各 22 例，全部 556 個執行／測試／依賴輸入逐檔相同，另核對核心 #110 三端各 51 張檢查。具體版本與完整 SHA-256 在 `artifacts/EXT-043/published-0.1.0/`。此處補記既有 EXT-043 的發布狀態，正式完成數仍 12／68。

任務書 ZIP SHA-256 `79dfd2ba5a8b96f22dea4c5f72a94ca761b15f2e354e33b36c7ecdbedc3ec3ee`。
行為基線 `329ca7c487414d2f54ddd98ff4727446ed2446cd`。官方插件接入層用 Rust。
獨立 Connector 沿用 Python 3.12；共享預算沿總書 K05。

**EXT-004 三端候選驗收通過。** 分支 `codex/ext-004-typing`，Telegram Rust alpha.9／SDK alpha.17。Mac、Linux、HJW 各以核心 #109 受測提交 `78394082d8ea` 通過 22 組真 Host 重放，含附件、原事件引用、原消息撤回及 typing。UI 403、格式錯誤和懸停均保留成功投遞，停用、缺授權、到期及清除來源均有原線路證據。三端原包與完整 SHA-256 在 `artifacts/EXT-004/original-activity-17/telegram-delivery.json`，來源快照 `121ae753ad5f691b31e6d62a39396d9ea18c5ce98a695276770dd864d3ecc98b`。各端重跑 Rust 11 項、HTTP／cache／快照來源回歸及正常卡入口；EXT-001／002／019 的三端基線復用經 47 個相同輸入校驗，另驗變更後的卡入口，詳 `baseline-reuse.json`。早期 Linux 寫回條缺 Git 的故障已修正並重驗，原始失敗保留。

核心 #109 已合併 `dc698f5a88dd`，#108 已合併 `427ffdf8a937`，擴展撤回 #57 已合併 `f2bb0c977eaf`，回條在 `artifacts/ci/local-pr/57/receipt.json`。三個 GitHub 工作流均只保留手動入口，後續 PR 與新標籤沿本地 CI。全部新增能力為未發布候選，EXT-004 正式跨倉驗收仍待擴充合同發布，正式總數維持 12/68。下一步推進 EXT-006 原 app／tenant 的原生投遞及 CORE-045 真實穩定插件相容驗收。

**EXT-004 原消息撤回三端通過。** 分支 `codex/ext-004-original-recall`，Telegram Rust alpha.8／SDK alpha.16。Mac／Linux／HJW 各用核心 #108 同平台簽署候選 `120db2d663af` 通過十五組真 Host 重放，涵蓋公開歷史選取原消息、重複撤回、授權拒絕、平台拒絕、回應遺失與格式不明、冷啟原回執。三端二進位、SDK、原 wire 及完整 SHA-256 在 `artifacts/EXT-004/original-recall-14/telegram-delivery.json`。本輪重跑 HTTP／cache 單元測試及真插件重放，EXT-001／002／019 三端既有基線的 48 個輸入檔雜湊逐件相符，復用證據見 `baseline-reuse.json`。包為本地未發布候選，完整 EXT-004 接續 typing。

**EXT-004 原事件引用三端通過。** `codex/ext-004-original-reply` 的 Telegram alpha.7 消費核心 #107 的簽署候選 `7965392bd7de`。Mac／Linux／HJW 各十組真 Host 重放通過，群話題內的附件與文字只有首段引用原 message ID，原訊息不存在時保留 failed，冷啟零重送。完整來源、版本、三端 ZIP 及 SHA-256 在 `artifacts/EXT-004/original-reply-13/telegram-delivery.json`。尚未發布，整卡繼續補撤回與 typing 生命周期。

引用子項 #56 `372484a836a8` 已合併 `5ba070ca10f8`，合併樹回條在 `artifacts/ci/local-pr/56/receipt.json`。

附件子項 #55 實作 `4b3b68c` 已合併 `22f33fcfb6dd`，本地三端驗證與實際合併樹回條見 `artifacts/ci/local-pr/55/receipt.json`。正式總數仍為 12/68。

**EXT-004 附件子項三端通過。** 分支 `codex/ext-004-outbound-attachment`，Telegram Rust alpha.6。原件分頁／摘要、原 Bot 與 chat/topic、UTF-8 caption 分段、拒收與失回應、冷啟零重送、讀取中刪除和晚到頁面隔離均已驗。macOS arm64、Docker Linux arm64、HJW Windows x86_64 各七組真 Host 重放，另各完成 EXT-001、EXT-002、EXT-019。回環平台及模型，付費呼叫為零。

候選與完整 SHA-256 在 `artifacts/EXT-004/outbound-attachment-12/telegram-delivery.json`，三個平台 ZIP 含獨立執行檔、SDK／鎖檔、原 wire 和來源檔案雜湊。Host 固定核心 #105 的受測提交 `19cbc9bf21f98`、SDK alpha.15，插件沿用 SDK alpha.14。全部為本地未發布候選。打包清單與 Desktop parser 已排除 AppleDouble 元資料，既有 Desktop 見證摘要三端相同。

完整 EXT-004 繼續進行，下一步消費核心 #107 的原事件引用，再補撤回與 typing 生命周期。整卡正式完成數仍為 12/68。兩倉依使用者指示共同推進，各自提交，GitHub 檢查工作流改為手動，本地三端通過後合併。原 Codemode 未完成來源保留在主工作目錄。

**EXT-029 已按維護者指定的模型原生範圍通過 HJW 驗收。** `codex/ext-029-model-native` 以已發布 B0 1.0.0（來源 `c6bd0c75e387`）把原私聊的 Main 搜尋接到模型 Responses 的 `web_search`。成功來源、純文字無證、429、斷線與冷啟皆有原根逐次回執。三次普通對答／搜尋之後，各故障各新增一筆物理回執；冷啟沒有新增預留或請求。四個搜尋 HTTP 均到回環模型。操作步驟見 `docs/EXT-029-model-native.md`，Windows 原始 wire 與 Host、來源及封包雜湊見 `artifacts/EXT-029/01`。早期缺字段及舊版不接受 `max_results` 的失敗已留存。原 EXT-029 的 Tavily 插件移出本倉範圍，核心 #104 新增三個外部搜尋方法僅供核對。原 #53 合併後的主線 CI `42315421136` 全過。現行範圍 12/68（含 1 張改範圍），剩餘分級在 `artifacts/readiness/after-model-native-search.json`。

**Windows 重現入口。** `codex/public-base-windows-runner` 讓 `ci/windows.py` 傳送三張卡各自已核的公開 Host 和原插件 ZIP。EXT-003、005、028 在 HJW 的三個獨立目錄併行執行，逐份核對返回的 ZIP、來源快照及 manifest。回條在 `artifacts/ci/windows-public/receipt.json`。#52 實作 `736bc7ffc6fe` 已合併 `32400b6d39f0`，三平台 7 個 CI 作業、9 個 ZIP 及實際合併樹均已核。正式 11/68；其餘分級及下一步見 `artifacts/readiness/after-public-fetch-network.json`。

**EXT-028 公開基底網路驗收通過。** `codex/ext-028-public-fetch`。在 HJW 使用 CORE-044 `plugin-base-v1.0.0` 與公開 freeze 的原 web-fetch 套件。由 Main 明選的網頁重導至回環埠，原操作收到 `destination_denied`，目標收到零個請求。第二個原頁 2,109,144 bytes，reader 在 2,097,152 bytes 停止；原執行以相同 handle/version 讀回 `partial`、來源、實收 SHA 與 18,022 bytes 保留前綴的開頭。逐方法與逐跳回條在 `artifacts/EXT-028/public-network-01`。前一輪寫回條時變數名稱錯誤，原診斷保留；最終命令重驗通過。DNS 換址、跨來源憑據、代理故障、空 HTML 和完整頁由原 `artifacts/EXT-028/01` 與 R07 覆蓋。#51 已合併 `a56cffde23ce`；兩個入站插件實收已交核心 #103。正式 11/68，EXT-067 保留簽署候選見證。

**EXT-005 公開基底入站驗收通過。** `codex/ext-005-public-admission` 在 HJW 將 #47 原 Windows 套件（飛書 alpha.4，SDK alpha.13）裝入公開 Host 1.0.0。writer 前斷線無成功事件 ACK，ping 與卡片無模型 HTTP；補齊分片後，飛書重投取得 1、1，Lark 同鍵取得 2、2，兩域的 open_id 分屬不同 account。錯租戶回 500、錯認證無連線。原生 ACK、Host transcript、模型正控與來源雜湊在 `artifacts/EXT-005/01`，停機副本沿用 #45。正式 10/68，另兩張簽署候選。#50 實作 `4c0af7fee853`，7 個 CI 作業和 9 個 ZIP 通過，普通合併 `8ca5f7077f11`。EXT-004/006 的原生操作與正向附件路由仍待核心交付。

**EXT-003 公開基底入站驗收通過。** `codex/ext-003-public-admission` 在 HJW 使用公開 Host 1.0.0（`c6bd0c75e387`）及 #48 原 Telegram 0.1.0 套件。提交前斷線留下水位 11，回應遺失留下 12；重投均回原事件。兩個 Bot 同一私聊鍵分別收到事件 2、7。獨立遷群只留下事件 1，模型 HTTP 為零，後續一般訊息通過同一回環端點。wire 與兩端 digest 在 `artifacts/EXT-003/01`，三次未通過的驗收迭代在 `artifacts/EXT-003/public-intake`。停機副本與回退沿用 #44、#48。正式 9/68，下一項是 EXT-005 在公開 Host 上的 writer 與租戶隔離。

**EXT-040 公開原生包。** `codex/ext-040-public-base` 實作 `bc2fe451a0d8` 的 yuki-setup alpha.2 可明選公開基底 1.0.0。HJW Windows 八項安裝操作通過。空插件及明選原 web-fetch 的兩個隔離 owner 均 ready，後者只有原包 online；錯誤輸入未留下安裝，原配置與 SOUL 雜湊保持一致。證據及兩輪故障在 `artifacts/EXT-040/public-native-01`。完整卡仍待外部入口、選配服務與真正的 Compose 部署。EXT-043 實作 `e9e012d761da`，#48 已合併 `24258c7c8c5c`，53 個驗證作業成功，91 份 ZIP 與實際合併樹相符。兩包消費回條已交核心 #103；詳 `artifacts/readiness/after-public-native-setup.json`。

**EXT-043 獨立升級。** `codex/ext-043-stable-telegram`。核心已公開發行 `plugin-base-v1.0.0`（來源 `c6bd0c75e387`），9 個發行資產與簽署清單已核。HJW Windows 只將 Telegram 升至 SDK 1.0.0，原 web-fetch 及其 SDK 維持原包。三段確認、第二段失回應保留 unknown，兩次停止並換回舊 Telegram 後，各讀原游標 52，新增派發均為零。原始回條與 SBOM 在 `artifacts/EXT-043/01`，發行鎖在 `compat/stable-1.0/source.lock.json`。Telegram 標籤與插件發布另待授權。正式 8/68，另 2 張通過簽署候選驗收。EXT-044 仍待 Desktop、部署及原控制前置，詳 `artifacts/readiness/after-public-base-upgrade.json`。

**EXT-005 富文字與原生貼紙。** `codex/ext-005-feishu-rich-post` 實作 `afb432bc50d5`。HJW Windows 用 #46 原套件與 alpha.4 在同一 CORE-038 Host（`0ef956a9c6d9`、SDK alpha.13）分別接收飛書及 Lark 原群訊息。新版富文字的 12 段保留標題與換行、提及、連結目的地、程式碼、表情及原圖／影片鍵；原生貼紙只有文字標記和回覆定位，可下載附件為零。正常重投、writer 斷開及錯租戶回條、兩版 wire、binary 與來源 digest 在 `artifacts/EXT-005/rich-message-01`。#46 三平台全過、9 份 ZIP 已核，合併 `98b08c435a6f`。正式 7/68，另 2 張簽署候選通過。EXT-043 等核心 B0 公開發行，EXT-029 的物理 attempt 對帳已向核心 #101 提交具體需求。見 `artifacts/readiness/after-feishu-rich-messages.json`。

**EXT-005 原群提及。** `codex/ext-005-exact-mentions` 的 `ac360c785115` 修正飛書與 Lark 文字事件中的身份錯配。HJW Windows 以 #40 alpha.2 重現短鍵截走長鍵及未列鍵，再以 Rust alpha.3 對同一 Host（CORE-038 `0ef956a9c6d9`、SDK alpha.13）重放兩種表順序。兩個域都將 `@_user_10` 交給原成員、將 `@_user_1` 交給原應用、將無登記的 `@_user_100` 保留為文字。writer 前斷線無成功 ACK，兩安裝各自重投回讀事件 1、2。兩份原始線路、ACK、Rust 測試及 digest 在 `artifacts/EXT-005/mention-identity-01/`。#45 的託管 macOS 套件也已通過，新增兩份 ZIP 已下載核對。68 卡分級及下一步見 `artifacts/readiness/after-exact-mentions.json`。

**EXT-005 停機副本與跨版重投。** 分支 `codex/ext-005-reader-replay`，實作 `316e11fe5a68`。HJW Windows 以原 #13 / #40 的 Rust 套件在 CORE-038 `0ef956a9c6d9` 完成兩個安裝各三輪。飛書舊版／新版／回退回讀事件 1、2，Lark 同鍵回讀 3、4。半個 frame 經冷啟仍等補齊才發 ACK，已接納的重投回到原 ID。六次都核原生子程序退出，插件工作目錄各自為空。故障迭代、兩版 SDK 與執行檔 digest、原 ACK 及 Host wire 在 `artifacts/EXT-005/reader-replay-02/`。#44 三平台及 9 個產物已核，合併 `8db6b9afa013`。全卡正式發布與現場資料仍待上游。下一步是從公開 B0 發行包驗 EXT-043，或在生產者交付新路由後驗對應功能。

**EXT-003 水位相容。** 分支 `codex/ext-003-cursor-compat`，實作 `8bef6ed6a34e`。Telegram alpha.5 在 HJW Windows 通過 8 例。alpha.4 寫 41，alpha.5 從 41 繼續，實收後寫 42；回退 alpha.4 第一次就讀 42。舊版會向回環平台送出負 offset，新版遇同一壞檔保留原 bytes 並停止輪詢；兩個無效 update ID 均在 Host 入站前停止。最終原始證據與 Host/SDK/兩個 binary SHA 在 `artifacts/EXT-003/cursor-compat-04/windows.zip`。簽署 Host 來源 4a41470e89b4，SDK alpha.14。CORE-044 已普通合併至 c6bd0c75e387；本次查到的公開版本仍只有握手預覽，EXT-043 等待可固定的 B0 發行包。68 張清冊沿用，正式 7 張、另 2 張通過簽署候選驗收。#43 合併回條在 `artifacts/ci/local-pr/43/receipt.json`。

**EXT-004 媒體拒絕。** `codex/ext-004-media-refusal` 的 `1f62c7106f9f` 在 HJW Windows 對拍核心 #98 的簽署包 `dce1a6862000`。同一對 Rust 發行包已有發送權；原工具取頁成功後，Main 分別收到不支援 emoji 和缺少檔案讀取權的原生錯因。兩次均沒有計畫、派發或 Bot 實收。殺插件、重啟 Host、重投舊 update 後，按原操作讀回相同 failed 回執。原 wire、權限配置、SDK／binary digest 及兩份原子回條見 `artifacts/EXT-004/media-send-refusals-01/`。正向平台引用、撤回、附件傳送及 typing 繼續逐項驗收；尚未發布。#42 的合併回條在 `artifacts/ci/local-pr/42/receipt.json`。

**EXT-004 入站安裝拒絕發送。** 分支 `codex/ext-004-gateway-refusal`，實作 `603a98bef211`。在 HJW 安裝 #40 的 Windows Telegram alpha.4 與 web-fetch alpha.2，逐包核 SHA。新版簽署 Host `1eb6708fafd0` 的 SDK alpha.14 與插件原鎖只有 VCS 元資料不同，兩份 crate digest 分列於 `compat/gateway-refusal/source.lock.json`。取網頁、四頁原件續讀成功後，只有入站權的 Telegram 在原 Main 收到 `failed / gateway_send_not_granted`；計畫、派發與原 Bot 發送皆零。殺兩個真插件、重啟宿主後，用原 namespace、operation 和 Person 讀回同一拒絕，再投舊更新沒有新增效果。完整回條在 `artifacts/EXT-004/send-grant-refusal-03/`。#41 的三平台與合併樹核對在 `artifacts/ci/local-pr/41/receipt.json`。本案例補該卡一項授權拒絕，正式分母仍見下方 68 張清冊。

**EXT-028 簽署候選驗收。** 在 HJW Windows 以分支 `codex/ext-028-signed-fetch` 的乾淨提交 `f4f4e2653e28` 跑預設 `ci/check.py EXT-028`。Host 來源 `4a41470e89b4`，SDK alpha.14，Rust web-fetch alpha.2。三次真工具派發分別讀取正文、大頁及只有 style/script 的 HTML。原文 6,250 bytes 分 49 頁核回，正文分 19 頁；第三個工具結果為 `empty_page`，保留原 bytes。六項 Rust 網路回歸涵蓋跨 origin 清除憑據、DNS 換址、合法 304 與代理故障。測試使用隔離 HTTP 和模型端點。Windows 執行檔 `a39fc7dbaa33`，與 EXT-067 獨立建置。回條、原連線、封包、三類資料所有者在 `artifacts/EXT-028/01/`。重現時將 `YUKI_BASE_HOST_ARCHIVE` 指向 `compat/base/source.lock.json` 固定的本機平台 ZIP。

**合併與交接。** PR #16 至 #40 已合入主線；#40 合併 `1a2ed566a06e`，59 份 Windows/Linux 產物及本機 macOS 16 項檢查見 `artifacts/ci/local-pr/40/receipt.json`。68 張逐卡清冊見 `artifacts/readiness/after-signed-web-fetch.json`，分列先前正式通過、此次簽署候選驗收、部分證據及尚無具名產物。CORE-044 已收到 EXT-067 兩個真包的原始見證，待生產者發布。後續追蹤 CORE-038 真權限拒絕與原回執，以及 EXT-004/006 平台引用、撤回及媒體出站。

**EXT-067 兩個真包的 Windows 驗收。** 分支 `codex/ext-067-joint-candidates`，實作 `18fba3707948`，乾淨重跑提交 `49f7b19`。簽署來源 `4a41470e89b4`、SDK alpha.14 `e41a2375efb2`，三平台逐包驗簽。HJW 在空資料目錄同時安裝 Telegram alpha.4 及 web-fetch alpha.2。七例通過，涵蓋取回原件後三段送達、第二段回覆丟失、殺兩個子程序後重播、跨人物換 handle、移除必要 RPC，以及取件中和重啟後的擦除拒絕。兩個插件的工作目錄為空，Telegram 自有的持久檔只有 offset 和空鎖。六個方法的方向、grant、schema、原始 wire 與各包 digest 在 `artifacts/EXT-067/01/base-consumer-witness.json`；CORE-044 可據此裁決基礎發布。正式總表此前為 7/68，完整 EXT-004 仍待引用、撤回、附件出站和 typing。此包尚未發布。

PR #39 普通合併 `48b634a060d7`，受測樹 `9b95740c3270`；Windows/Linux 原 6 份 ZIP、本機 macOS 兩項回條見 `artifacts/ci/local-pr/39/receipt.json`。PR #37 已另在 HJW 原生補跑 16 項，含 14 套件、四張 Connector 回歸卡、acceptance 和 worker；逐檔校驗見 `artifacts/ci/local-pr/37/hjw-supplement.zip`。本機首次 archive 遇到正在使用的 Windows 零位元鎖；改讀 live 大小，kill 後核原 SHA，再從乾淨提交重跑完整入口。

**EXT-004 Telegram 文字投遞候選。** `codex/ext-004-telegram-parts` 的 Rust alpha.3 和固定 CORE-038 `0ef956a9c6d9` 在 HJW 跑過 4 個真 Host 案例和 5 項 Rust 測試。私聊及群話題各將 8,197 個字元分 3 段，保留原 chat/topic 與各段 message_id。第二段被平台接收後斷線，首段 confirmed、第二段 unknown、第三段未派，雙程序重啟後原 cursor 接續且未重送。引用案例的計畫只收到核心 event ID，原生請求為零。完整收據 `artifacts/EXT-004/text-delivery-02/`。正式完成仍 7/68；附件出站、原引用定位、撤回與 typing 仍待交付或驗證。

**合併佇列。** PR #16 已合併至 `41cb089afe83`。PR #37 整合其餘 21 張的原 head，普通合併至 `d3f231b2fc02`。實際 merge parents 與受測 tree `9e072834e150` 一致。Windows/Linux 各 14 個套件、三平台驗收、Linux native Monty 與三平台 worker 已核，本機 macOS arm64 跑完 16 個作業。60 份 GitHub ZIP 的回條在 `artifacts/ci/local-pr/37/`；GitHub 列原 #16–37 全部 MERGED。

**EXT-004 原 Bot 取件。** 真 Host `0ef956a9c6d9`、SDK alpha.13 與原 Rust 插件在 HJW 完成選取 slot 0 和錯 slot 1。單次原生 GET、7 塊共 161,058 bytes，原處理器及 Main 回讀兩頁 PDF。錯 slot 零取件。完整原始 wire、模型 HTTP、配置、SHA 與失敗回條在 `artifacts/EXT-004/selected-native-03/`。正式完成 7/68。舊結果以下依執行時間保留。

**EXT-006 原 app/tenant 取件。** HJW 用相同資源鍵、兩個原 app 及各自的 tenant 收件。飛書 131,058 bytes／6 塊，Lark 101,058 bytes／5 塊，各一次原生 GET。錯 slot 各收到 failed，取件與處理器呼叫均為零。回條、可重放命令和完整 SHA 分別在 `artifacts/EXT-006/selected-native-03/`、`docs/EXT-004-006-selected-native.md`。只使用回環平台及模型。仍待出站投遞、逐平台動作與正式發布。

**舊 EXT-006 候選快照。** 分支 `codex/ext-006-feishu-media`，實作 `2db0fa096b2f`。
HJW Windows 的 Rust alpha.2 在兩個區域端點各取回 26,789 bytes；同名 key 的內容摘要不同。
下載中原 WS 可回 ACK；錯 app/tenant 不發 HTTP、403 不重試。修正 Windows 複製 socket 導致原讀取逾時沒有更新的問題。
同一執行檔 `4fc4e77480ba` 對固定 CORE-038 `0ef956a9c6d9`／SDK alpha.13、Host `4dd7a9fc3456`，
用兩個獨立安裝接納與重放，真回執 event 1/1/2/2；這條測試只授入站權限，附件 callback 為零。
見 `artifacts/EXT-006/evidence-index.json`、`platform-05`、`ingress-05`。平台端為回環 fixture，
真選讀需原 app/tenant 的公開安裝配置，Social 和舊資料導入仍待。
上張 [EXT-004 PR #36](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/36) 已推；
[原安裝配置回條](https://github.com/Institute-of-Agent-Life/yuki-core/pull/73#issuecomment-6680974214)。
合併佇列先處理 #16；最新清單：`artifacts/readiness/after-feishu-native-media.json`。

**EXT-004 部分候選；正式完成 7/68。** 分支 `codex/ext-004-telegram-media`，實作 `adb9c36eae38`。
HJW 的 Rust Telegram alpha.2（SDK alpha.13，來源 `0ef956a9c6d9`、crate `25694e880798`）已驗原 Bot 單次取檔、兩頁同摘要、跨身份零取件、轉址／超限拒絕及長輪詢中止。
平台證據在 `artifacts/EXT-004/platform-01`；真 Host 的 ingress-only 寫入 event 1，新增 grant 時缺 application 核准而無法啟動（`host-02`）。待核公開配置、真選讀、發送／撤回／typing 與發布。
前排 PR #16 等 macOS；CI 快取回條見 `dec012ed155c`。最新狀態：`artifacts/readiness/after-telegram-native-media.json`。

| 任務／分支 | 實作、三平台 PR CI 與主線合併 | Windows 實機證據 |
|---|---|---|
| EXT-001 · codex/ext-001 系列 | `4cbaff3`、`033bb04`、`f136b4d`；CI `41819289910`；主線 `93adb61` 含 Rust 補驗 | `artifacts/EXT-001/03/`，隔離建包、Rust 真編譯與故障案例 |
| EXT-007 · codex/ext-007 | 來源 `0150c76`、打包 `8fd6ed8`、正式對拍 `41860a2`；CI `41833181301`；PR #3 合併 `18e028c` | `artifacts/EXT-007/01/` 與 `ci-receipt-41860a2.json` |
| EXT-008 · codex/ext-008 | `d434482`；CI `41833796596`；PR #4 合併 `15ea291` | `artifacts/EXT-008/faults/` 重現舊錯，`01/` 實測 19 例 |
| EXT-009 · codex/ext-009 | `c0d30fb`；CI `41834256598`；PR #5 合併 `9eb9223` | `artifacts/EXT-009/01/`，4 例含真 SDK、原問題回執、EOF 與檔案保留 |
| EXT-010 · codex/ext-010 | `ab16e07`；CI `41834791702`；PR #6 合併 `2c55dbb` | `artifacts/EXT-010/02/`，8 例含實際子進程退出碼 23、雙 session 取消及 unknown |
| EXT-019 · codex/ext-019 | 實作 `7531d84`、PR head `9d1e8a8`；三平台 CI `41835863011`；PR #7 合併 `7625095` | `artifacts/EXT-019/02/`，呼叫表、schema 差分、5 個故障變異；`03/` 固定跨平台順序 |

## 2026-11-06 EXT-031 原 Main 頁文／影格見證

- 分支 `codex/ext-031-main-media`，實作 `3b65ab18830f6dc349f7f5dc20cdf492c11a3a84`。
  CORE-038 source `0ef956a9c6d9`／SDK alpha.13／DB50，三平台 ZIP 全成員已核，
  pin 在 `compat/core-038-main`；Win ZIP `a81c49a722b9`、Host `4dd7a9fc3456`、
  crate `25694e880798`，未發布。原 Rust binary `2d0e7e9b9107`／SDK alpha.4、
  document_reader.py／FFmpeg 原樣重用，沒有重新編譯後端。
- HJW Windows 五例已驗：原 PDF 頁文與 operation／version 完整回到同一 Main；
  影片 0/5 秒原像素按 SHA／id／version／ordinal 進同一正常續輪；未選零處理、
  無 vision 零處理、壞 PDF 一次處理且結構化失敗。每個正例三筆正常 Main HTTP，
  其中一筆 capability 供公開 cache-file fixture 取得原 execution，選讀／續輪兩筆；
  沒有額外 vision 路由或付費供應者。保護的 cache fixture 不是原平台取件。
- `faults-07/forget` 第二塊讀取中，公開 privacy erase 回 SQLite 787 外鍵錯誤；
  沒有成功清除回執，不改核心／主庫、不重送未知效果。`audit-09` 在 Windows 核
  原 ZIP／manifest／方法配對／頁文／實際影像 bytes、五例與原失敗；14 單位邊界
  及 media 選擇器通過。詳 `main-evidence-index.json`、`main-iteration-disposition.json`。
- Main 呈現缺口已在這個固定 tuple 解除。新 Main forget 阻塞、原 receiving gateway
  真取件與正式發布仍待；舊 e25 tuple 的自動 forget 回條保留，正式完成仍 **7／68**。
- EXT-015 已推 [PR #32](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/32)，
  head `3014ed0`；回條已交核心 #67 `6677934279`、#71 `6677939829`、#72 `6677943216`。
- 使用者最新 CI 建議：先去重與取消舊 PR 執行，再做分 OS／arch／Rust／lock／實際
  SDK hash 的快取，最後才評估有限分組；排隊不算佔用執行中名額，組織限額未知。
  下一項先落實本倉 CI，維持三平台、當前 merge SHA 與原產物驗證門檻。
  最新 readiness：`artifacts/readiness/after-core038-main-witness.json`。排程仍 PAUSED。

## 2026-11-06 EXT-015 明選 Client9 候選

- 分支 `codex/ext-015-selected-client`，實作 `59e0d07c21b44609af2e3e12fbc0ec950930adba`；
  由 PR #31 `4801377c8fbe` 建獨立樹，含 main `ac8c1b287e5a`，沒有改其他 WIP。
- 原 Rust Client 升至 alpha.2／SDK alpha.12，轉送原 X-Yuki-Entry／Conversation、
  UUID／有序附件、home、串流上傳及 SSE；沒有插件身份／去重庫。SSE 四、上傳四、
  一般八個名額分開，65 秒上游 response 上限讓遺留流釋放名額；原 bytes 逐塊 flush。
- CORE-033 固定 source `c616cf35e4424e2b9f3c99a4481bfab1c99a34f3`、DB48，
  三平台 ZIP／全部成員／producer manifest 及 dirty=false 已核；完整 pin 在
  `compat/core-033-client`。Win ZIP `5260a4f063fa`、Host `7e78050e2032`、
  crate `29f5e9f0b89d`；仍未發布，不是 PR head。
- HJW Windows `selected-08` 九組功能案例、兩項 Rust 回歸、release build、14 單位
  邊界及選擇器通過。涵蓋兩設備原 UUID、合併後分辨原人物及明選 B、錯誤／重複
  標頭、附件改序衝突、**入站**持久游標／SSE 重連、滿四流仍可一般 GET、撤權關
  原四流、停用入口讀舊件／拒新寫及冷啟。模型 fixture HTTP 四筆，無付費供應者。
- `selected-analysis-01` 在 Windows 核 35 個來源、原 ZIP／manifest／所有 SHA、
  Host／SDK／plugin／wire 及原失敗；binary `ecd3200867585a7c38ed5682d855cb5177e960a1776e7c49211583ed0587f960`，
  wire `0d81770a1414d6b34dc0e8dc9de8bf374bc3f24902f0e78961db4c365b27ac69`。
- ACP：公開 account／entry／ingress／home 已列真 ACP conversation，匹配 header
  仍 404。Social：原 06 沒有 binding fixture，Main 接納後 send 段 held/runner_failed；
  原 05 fixture ACK 沒有本地事件，不能算 Social 成功。具體公開安裝／ACP session／
  receiving Presence 設定需求在 `docs/core-interface-requests.md`；原失敗全保留。
- **正式完成仍 7／68。** H24 ACP／NULL／完整 target/operation、原本地 Social、
  H27 最後溢出、H28 原件與忘記競態及正式發布仍缺。預備候選不改整卡 BLOCKED。
- PR #16 最新 head `58cd960e1a99`／base `ac8c1b2`：push 15 success/9 queued/1 running，
  PR 16 success/9 queued，沒有新失敗；不能合併。#23 原 504 attempt2 已 success。
- 新核心 PR #67／71／72 已消費本卡固定包；#73 gateway media、#74 Main 媒體、
  #75 原 Work/Manager terminal、#76 canonical QQ send、#77 memory merge／#78 native
  mentions 為新交付，逐項看真前置。下一步核 #74 已實跑本倉原 EXT-031 binary 的
  Windows 回條，續做真正就緒工作；不能沿用上一輪「沒有新 PR」的判斷。

## 2026-11-06 EXT-070 原 Connector 改址候選

- 分支 `codex/ext-070-address`，實作 `cc39f5911859585385f48742defd536d61ae8a06`，
  基於 PR #30 的 `ce1cec3a2092`（已正常含 main `ac8c1b287e5a`）。
  原 Connector 19 個 runtime／鎖檔 bindings 未改，wheel 仍
  `2748ec830b56e38f404d33964350578e543232ab1fce02e2399fc3ab045a74d8`。
- 基線 CI `41554925880` 的 integration artifact `13194877063` 已核 GitHub ZIP digest
  `da2c0c140992b3a2af8dee54bd89e0a32caf4184dca5dae0dc131637c0e9b70b`、CRC、安全成員、
  JUnit 的 11 個 pass 與原 11 回條／commit。原資料及只讀 source oracle 在
  `compat/wire4/address_cases`；未執行舊 Host 私有模組，也不把歷史綠燈當本次測試。
- HJW Windows `candidate-03` 15 例通過：CLI 僅改 URL／保原 token-instance，遠端非 TLS
  拒絕、v0/v1 `[url,device]` journal 升級、另一 device 拒絕；真 pipe shell 在保存新址後
  收 stdin、原 PID `13168`、exit 0，唯一 native exec／實體啟動各一次。
- 真 CLI 重啟到第二個 TLS 1.3 WSS 後查原 succeeded 回條，unknown 保持 unknown；
  B 的 event ID 集合精確等於重啟前未 ACK 集合，已 ACK 不補送。臨時 user task 用原
  UserService 的 LeastPrivilege／InteractiveToken 註冊、禁用且未啟動；改址前後原 Task
  XML／action／非 running 不變，finally 核 action 後清除，實收 installed=false。
- `analysis-01` 在 Windows 逐份對上 11 個舊回條，核原 ZIP、15 例、73 個來源綁定、19 個
  unchanged runtime、全部 14 發行單位邊界／選擇器；wire SHA
  `919a7a90cd0e1db1ad5a20357d159e4dde272de254e1bfa6070b3db3baac127c`。
  01／02 分別是功能與事件細化的已驗迭代，不冒充含真 OS task 的最終 03。
- EXT-011 已推 [PR #30](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/30)，
  head `ce1cec3a2092`；真消費回條已交
  https://github.com/Institute-of-Agent-Life/yuki-core/pull/66#issuecomment-6676124728 。
  兩卡的正式發布／公開部署仍缺，正式完成仍 **7／68**。
- PR #16 當前 `58cd960e1a99` 無新失敗，三平台及套件仍有 runner 排隊；後續按既定順序，
  main 前進才正常合入新 main 重驗。#23 原 504 全輪已結束，本輪已 rerun failed，attempt 2 排隊。
- EXT-044 還缺 EXT-017／039／043／046 及原 Work／管理／發布整組，不因 EXT-070 局部
  就緒就開空實作。其他核心回條無新回覆、現有固定交付未換；最新 readiness
  `artifacts/readiness/after-connector-address.json`，剩 CI／上游契約等待，全部既有 WIP 保留。

## 2026-11-06 EXT-011 原 Connector 鑑權與 wire4 候選

- 實作 `a7b35e96dda240f021f43efed7a46c7976d4197c`；正常合入 main `ac8c1b287e5a`，
  僅進度有衝突，兩邊歷史保留，31 份實收來源未變。
- 分支 `codex/ext-011-connector-auth`，基於 `5986cba`；Rust local-agent
  `0.1.0-alpha.2` 已完成本輪可用接線。正式完成仍 **7／68**。
- CORE-033 `c85a00b121d0277578292e8b60170b799e4ad6db`／SDK alpha.12，
  三平台 ZIP／全成員／producer manifest 已核，完整 pin 在 `compat/core-033-connector`。
  Windows ZIP `6249cf5145c4`、Host `e26626a017c5`、crate `7f260fdd21a7`；未發布。
- HJW Windows `connector-auth-07`：真 Rust＋原安裝 Python Connector 的 WSS／TLS 1.3
  12 例通過，模型 HTTP 0。涵蓋 chat／缺憑據拒絕、空設備、全量 catalog、舊 epoch
  catalog／close fence、人物合併、原帳號 transfer、偽造 hello、無 Work 的 event 不 ACK、
  撤權與冷啟。原 `Connector.run` 240.141 秒自動重連，epoch 3→4，未停止 owner。
- `connector-analysis-01` 在 Windows 核 31 個來源綁定、47 組原方法配對
  （connect 9／check 29／close 9）、build／SDK／Host／wire SHA；原 alpha.1 binary
  實測 schema1→2 保留設備，舊 reader 拒絕新事實且 DB bytes 未變。新格式前向修復。
  binary `791e7ceb89fd526be00bc390831afa0889e8cd503adfc3beb9fb3577d44860a5`；
  wire `bc94657fe5a687444f39959e12f2453b2cfe42d236b87ecc8bb351059cf8c3e0`。
- 原 Python Connector／驅動／journal 未改。原 raw Bearer 只交私有核心 exchange；
  安裝 ID 明選、與 SDK namespace 分開；proof／handle 不落 catalog。續期用 1001，
  原 1008 會停 owner，不能以只跑 connection() 的 PASS 冒充自動重連。
  02…06 原配置／觀測失敗與 05 的覆蓋缺口全部保留，見 iteration-disposition。
- 仍需正式發布、公開 WSS 部署、原設備／catalog 匯出導入演練；CORE-057 現有包只含
  import-models，不能代替設備資料。EXT-012／014 的原 Work/run 授權、operation 綁定
  與回流另交核心，不把 device.connections 當一般業務授權。
- PR #15 本輪已核 48 ZIP 並普通合併 main `ac8c1b287e5a`；回條
  `artifacts/EXT-011/ci-receipt-0107c0a.json`。PR #16 已正常合 main 至 `58cd960e1a99`，
  新三平台 CI 等 runner；其後各 PR 輪到時仍須正常合入新 main。
- 下一個獨立可做項是 EXT-070；已從基線 CI `41554925880` 核得 11 份原 address
  回條、JUnit 與來源，尚未把它們當本次執行結果。所有既有 WIP 保留。

## 2026-11-06 EXT-024 普通拒絕與後續效果對拍

- 分支 `codex/ext-024-rejection-continuation`，從已驗角色／trace 的 `d9cfee9` 建獨立樹；
  main 仍 `996deedef3e1`。本次只新增對拍與契約 pin，Rust Code 本體來源未變。
  實作與原回條 `af6e61b95009b6a3c592ecbea302fe0df51a13e5` 已推
  [PR #29](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/29)。
- CORE-015 固定來源 `969fb62e34de`／SDK alpha.11 的三平台 ZIP、所有成員及原
  producer manifest 已核；完整來源／版本／雜湊在 `compat/core-015-isolation`。
  Windows ZIP `3b45be537020`、Host `9cd0c5ac8c8a`。候選仍未發布。
- HJW Windows／Arch 三例共 9 筆模型 HTTP：direct 的原 bad call 收到明確 failed，
  原 good call 實收；真 Rust／Monty 的同一無效項 `tool.invoke` 收到 -32003，後項
  未執行。正對照先合法送達並 ACK，再遇相同無效項拒絕，已確認效果仍保留。
  三例各冷啟兩次，未重買／重送，專用 daemon 容器集合回原集合。
- `artifacts/EXT-024/refusal-01`、`control-01` 保留逐方法 wire、原配對與 binding；
  `analysis-01` 是 Windows 原 ZIP／manifest／來源與原 child／ACK 的實際重核，
  狀態 `DIAGNOSTIC_VERIFIED`。這不是整卡 PASS，不從 generic RPC error 猜 admission。
- Windows `validation-02` 已過最新 Python 語法、SDK／13 個原來源／八個方法 DTO
  綁定與 release 邊界；選擇器仍選全部 14 單位。`validation-01` 是測試傳輸漏帶
  舊 build 回條的來源檢查失敗；補齊具名輸入後重驗，原失敗保留，不算 Host 缺陷。
- 原 Rust binary `23f888dc639f`／alpha.5 consumer 沿用，13 個來源／建置檔與
  `fe7c9c0411cc` 逐 bytes 相同；沒有重跑既有六個恢復案例或重編 Monty 後端。
- **正式完成仍 7／68。** 新阻塞及精確方法／字段／授權／故障需求已列
  `docs/core-interface-requests.md`；缺普通拒絕的可分類 child receipt／續跑路徑，
  其餘 light alias、Work/run、H14／根帳本、越權等價及發布缺口延續。
  真回條已交 [CORE-015 #61](https://github.com/Institute-of-Agent-Life/yuki-core/pull/61#issuecomment-6673430091)
  及 [CORE-034 #43](https://github.com/Institute-of-Agent-Life/yuki-core/pull/43#issuecomment-6673443351)。
  三平台當前 SHA CI 與合併仍待遠端 gates；佇列仍從 PR #15 起，最新 40 success／
  4 個 macOS package queued，沒有新失敗。PR #29 輪到時仍需正常合入新 main 並重驗。
  最新 readiness：`artifacts/readiness/after-core015-refusal-intake.json`。
  其餘使用者 WIP 全部保留。

## 2026-11-05 EXT-038 Rust 共用角色／SOUL 候選

- 分支 `codex/ext-038-character`，實作 `87c3f6531a8d5c412e1212047a84a494e366aeec`；
  正常合入 trace 的 CI 選擇修正 `20534f8ed7b0`，merge `82c731f8351a`，程式樹未變。
  trace 已推 [PR #27](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/27)，
  真回條交 [核心 #51](https://github.com/Institute-of-Agent-Life/yuki-core/pull/51#issuecomment-6669933736)。
- 獨立 `character` Rust package／lock／catalog 已落實，使用同一已核 CORE-037
  `1e7b89362b6f`／SDK alpha.11。角色、SOUL、身份與授權真源均留核心；沒有插件角色庫。
- HJW Windows 正式 transport 的 `artifacts/EXT-038/candidate-04` 過 21 例、實收
  模型 HTTP 42 筆：公開讀／權限拒絕、改名原 ID、原 UUID 重放、改 body／舊 revision
  拒絕、空 SOUL、原已付 system 角色／SOUL 不變、新激活用新版本、冷啟和撤權。
  插件 digest `1e321b8852d8ef3af1ffbab7a2600426d379bdfd1054cbbb147f3060f24f74b6`；
  shared-character digest `bc8f2e6ff4b25dae0c7d82e1af0f3c50e4546f8e3a26aa65e27909ba0c55f261`。
- 壞檔故障只改新 owner 的 fixture SOUL.md，真原 reload 和 Host 拒絕訊框均未改寫。
  保存、原拒絕及後續新明選 reload 分欄；不從 generic -32003 推斷 admission。
  candidate-02／03 保留兩個測試時點失敗；最終雙向 relay 在回傳前恢復原 fixture，
  Main 完成原配對。26 個來源綁定、wire／build／manifest 和 owner-disposition 可交核心。
- **整卡仍進行中，正式完成 7／68。** 頭像 immutable version／原圖保留、逐 Bot
  平台 nickname/avatar 套用與真結果、舊資產導入及正式發布缺口列於 interface requests。
  CORE-055 已開 PR #52，尚未消費；EXT-049 仍缺 EXT-015 真個人入口／Social 前置。
- 合併佇列 main 仍 `996deedef3e1`；PR #15 最新 36 success／8 個 macOS package queued，
  沒有新失敗；PR #23 原 504 仍未結束整輪，不到 rerun 條件。PR #27 新 head `20534f8`
  push `42116257171`／PR `42116267407` 已啟動；已核過期 SHA 後請求取消舊 `646584e`
  兩輪。當前 SHA／base 的三平台與全部 package/native/worker gates 均保留，未合併。
  最新 readiness `artifacts/readiness/after-core037-character.json`；其餘 WIP 全保留。

## 2026-11-05 EXT-037 Rust 查詢候選

- 分支 `codex/ext-037-trace`；實作 `76feabd5cb5c354309e4556e881f5bd1579a7baf`。
  正常合入已驗 main `996deedef3e1` 的提交 `1e177495404b` 只保留兩邊進度。
  原主樹四個 Code adapter、ASR／rebuild／subscription WIP 均未動。
- CORE-037 固定來源 `1e7b89362b6f`、tree `f58b344f4da4`、SDK alpha.11；
  三平台 ZIP／成員及 producer manifest 已核。Windows ZIP `cfad9951aa18`、
  Host `b3fbd607fe5a`、crate `cb6db37ce6b3`，完整 pin 在 `compat/core-037`。
  候選未發布。CORE-055 新 PR 不代表 EXT-049 的個人入口前置已齊。
- 獨立 `plugins/trace`／catalog／鎖檔／release unit 已可執行 `trace_query`。
  HJW Windows `candidate-03` 通過 release build、兩項 Rust 回歸與真 Host 查詢：
  metadata、明選正文、普通人／撤權拒絕、擦除後空頁；實收模型 HTTP 12 筆。
  插件 digest `58c73b9d6fa28fb1e9801df972a9a7fd8d35c470e1b48f0b0cf88754cf28dde3`。
  trace-query digest `7c1fa65768dd6f08ce61a9624f78107de2edcd33c76c276bcb6ec458f262c88e`。
  原 wire／build／manifest／27 個來源綁定同目錄可交核心；正常與故障時序見 EXT-037-sequences。
- `candidate-01` 保留未驗並行讀宣告被 Host 拒絕的原日誌；改為順序派發後，
  `candidate-02` 真插件過，`candidate-03` 再驗正式 `ci/windows.py` 入口。
  沒有修改核心驗權或改成接受失敗；macOS／Linux package 仍須 CI。
- **整卡仍進行中，正式完成仍 7／68。** 已實作單次授權查詢，不保存私料。
  opt-in trace 訂閱、私庫 SourceHold／forget、R18 遲到 writer 及 versioned export
  尚缺公開契約，需求已列 core-interface-requests。下一可獨立進行項是 EXT-038
  已公開的共用角色／SOUL；頭像版本與平台套用需另外核 CORE-038／Gateway 真接口。
  最新 readiness：`artifacts/readiness/after-core037-trace-query.json`。

## 2026-11-05 固定資產 GET 的 504 回歸

已驗修正提交 `b82112b5b452`，分支 `codex/ext-047-scoped-session`，沿 PR #26 驗新 SHA。

- PR #26 `b2393fc` 的新失敗是 PR run `42043545403`／job `127300355097`
  acceptance/Ubuntu 在已發布握手資產 GET 收到 HTTP 504。原 ZIP
  `52db6dd1f504eecbabfaf1ad5435e3979c76a9c36f3f9e337a1a67e758ee47e8`、四成員／manifest
  及 merge parents 已核；證據 `artifacts/readiness/ci-release-504-20261105/original/`。
- `ci/download_http.py` 只為無 body 的固定資產 GET 做 502／503／504 最多三次讀取，
  等待 1、2 秒；Retry-After、其他 HTTP、TLS 錯誤直接失敗。原 checksum／來源／版本／
  receipt／能力核對保留，壞 digest 不重試、不落盤；不增加任何業務或模型請求重試權。
  正常與故障時序在 `docs/ci-download-sequences.md`。
- HJW Windows 的七項真 loopback HTTP／TLS 例外／完整性回歸通過，產物
  `ci-release-504-20261105/verification-01`；只驗 CI 讀取，不重做 EXT-002 消費者。
  同一 `b2393fc` 的兩個 native jobs `127300387575`／`127301499397` 都 success，
  此處僅核 job 狀態，未據此宣布間歇性 134 根因已修復或整張卡通過。
- PR #14 的 22 份現有 ZIP 已核 GitHub digest、成員、manifest、當前 base／merge parents；
  回條 `artifacts/readiness/pr14-dfe8eb4-ci-partial.json`。只差 Connector/macOS
  `127165347504` 與 package／connector-upgrade 兩產物，未合併。
- 核心 main 已普通合併 CORE-027 至 `3d7d12c0d329aef5fb0db117161cc81a07242946`；
  CORE-035／051／058 只整合 CI window，CORE-025 只整合新 main，未補本倉所缺安裝配置
  或新的公開 Host／SDK 交付。授權回條仍無回覆，公開 release 仍只有已驗握手版。
  正式完成 7／68；最新 readiness `artifacts/readiness/after-ci-get-retry.json`。

## 2026-11-05 native CI exit134 診斷補強

已驗本地提交 `335bc62e0d3e`，分支 `codex/ext-047-scoped-session`，推送至 PR #26 後驗當前 CI。

- PR #26 原 head `e0625154c09a` 的 push run `42031856344`／job `127260154799`
  在 blocked-feed disconnect 退出 134，OOMKilled=false；另一 PR run 的同源 native job 通過。
  原 ZIP `5926a977bc64982960b1ace015e77888cad4ba84173b0357348b2e9d041130ce` 的
  9 個成員／manifest 已核，保留在 `artifacts/EXT-023/disconnect-134-diagnostics-01/original/`。
- HJW 原 `65fcd704d953` 映像增加 60 次不同斷開時點驗證，exit=0、原 PID 全消失；
  仍未重現 CI 134，沒有做根因修復主張。控制實驗確認 Docker 未宣告 AttachStderr
  仍會傳回 stderr，故未採用該錯誤假設。
- 診斷補強啟用 CPython fatal signal trace，並讀 Docker logs；真受控 abort 的退出碼
  仍為 134，新增可讀堆疊。完整 native codec 通過，測後容器集合還原。
  CI 先複製實含 runtime contract，失敗時仍保存該次 image.tar；原檢查或 export 失敗
  仍 FAIL，後者不能遮蔽原錯。沒有修改 backend、原 worker／launcher 或授權規則。
- Windows `verification-03` 的 5 項 evidence orchestration、3 項 OCI integrity 及
  source package 皆通過；`verification-02` 保存真容器前後對照及 native 回條。
  上述 artifact 根 manifest 鎖變更來源及逐檔 hash。PR #26 接續重跑當前 SHA 三平台 gates。
- PR #14 仍差 Connector／飛書 macOS 排隊，未合併。核心 CORE-039 PR #28 已合併
  `9a0b14afe68bc461220ec918f2dd6b1c917c995e`，尚無新增正式 release；各授權回條無新回覆。
  正式完成仍 7／68。readiness 改為 `artifacts/readiness/after-native134-diagnostics.json`。

## 2026-11-05 CORE-051 consumer intake

- 最新工作樹 `.ci-transfer/work-scoped-session`，分支 `codex/ext-047-scoped-session`，已驗診斷提交 `cfd405d5dc82`。
  EXT-027 的已驗診斷 `07b4da6` 已推 PR #25；核心回條
  https://github.com/Institute-of-Agent-Life/yuki-core/pull/48#issuecomment-6658294529 。
- EXT-047 的 `source-intake-01` 已在 HJW Windows 編譯／執行真 Rust consumer；
  CORE-051 `9db8b3f073e3`、Host `cb2e2e8592bc`、SDK alpha.9 crate `2b1e5fbe107a`，
  consumer `3644baf1e9c6`、wire `195b711c07b6`，全部輸入／回條 SHA 已核。
  前景、已接納 Work、actorless 的 session.create 皆 -32003，session.run 為零。
  原 method grants 可協商，缺公開 sessions policy／aux route 配置；沒有判成核心 bug。
- GitHub Monitor 1.2.3／API9 固定 `efba5e1ad77f` 的原 manifest、註冊、命令、輪詢、
  配置、觀察及授權已核 Git blob／SHA；唯讀對照在 `compat/external-plugins/` 和
  `docs/sdk-migration.md`。沒有升版／發布／自動執行舊插件。R11、遊戲、QQ scope、
  原 API9 新 Host 拒載和舊 Host 可用仍待驗，詳見 external-consumer-ledger。
- 正式完成仍 7／68 卡。本輪新增的是兩張授權診斷，沒有新增正式驗收卡。
  readiness 改為 `artifacts/readiness/after-core051-intake.json`。先等待公開安裝配置、
  PR #14 的剩餘 macOS jobs 與其他已具名上游缺口；下一次 main 前進仍要更新後續 PR base。
- 原主樹／ASR／rebuild 及 `work-subscription` 的完整 Rust 訂閱 WIP 保留。

## 2026-11-05 CORE-058 intake

- CORE-058 `cb02f74ea48b`／SDK alpha.10 的三平台 ZIP、source tree 和全部成員已核，
  固定來源見 `compat/core-058/`，回條 `artifacts/EXT-027/producer-intake/inspection.json`。
  包仍未發布；Windows Host SHA `44e051731197`，crate SHA `4975c4e27096`。
- `codex/ext-027-subscription` 位於 `.ci-transfer/work-subscription`。Windows 最小 Rust
  consumer 的 `source-intake-01` 已確認三種原呼叫都仍被 `notification.grant_target`
  以 -32003 拒絕：前景、已接納 Work、略去 conversation／bot 使用原入口。
  Person 已為 admin、三個 `tool.status` 都為 dispatched；notification.publish 次數為零。
  診斷 binary `7ecb61ef9d779`，完整 policy、operator、model、wire 和 manifest 均保存。
  此為已驗診斷，沒有把發布／送達算通過。
- 完整 Rust 訂閱插件留 WIP：`plugins/subscription-monitor/`、catalog、EXT-027 case、
  relay、`ci/windows.py` 與正常／故障時序。Windows 已編譯，5 項游標／journal 測試過；
  candidate-01…03 皆在授權階段失敗，尚未跑到 outbox ACK 丟失、實際發布、撤權。
  原 Code／ASR／rebuild WIP 保留。待生產者補最小安裝／授權設定後續跑，不提交成已驗插件。
- PR #14 仍差 Connector、飛書的 macOS package；三平台 acceptance 已過。PR #20
  原 504 workflow 已結束，`gh run rerun --failed` 成功請求第二次 attempt，只重跑失敗項。
  GitHub connector 的同操作回 403 integration 權限不足，已用既有 gh 授權完成。
  PR #23 原 504 workflow 尚在跑，未重試。新 main 仍 `526a35382d9b`。
- EXT-047 已具 CORE-058／051 候選，但真 Monitor 的目標授權仍受本次 intake 阻塞；
  原 GitHub Monitor 固定 `efba5e1ad77f`，未升版或聲稱遷移。隔離遊戲會話仍待實作驗證。

## 2026-11-05 10:04 UTC 更新

- PR #13 當前 head `9db5191` 的三平台與四套 package／Connector 升級檢查全過，
  21 份 ZIP、GitHub digest、manifest 成員及 merge parents 已核；普通合併 main
  `526a35382d9bb464f92adc947e1b212e0ea41c3c`。回條 `artifacts/EXT-005/ci-receipt-9db5191.json`。
  PR #14 已正常合入此 main，head `dfe8eb46d64a`；Windows／Linux 過，七個 macOS job 排隊。
- PR #20 的 connector/macOS、#23 的 acceptance/macOS 原日誌均為固定依賴下載 HTTP 504。
  原 ZIP 已驗；整輪仍排隊時 GitHub 拒絕單 job rerun。等結束再重跑，沒有降檢查或合併。
- `codex/ext-023-feed-recovery` 位於 `.ci-transfer/work-code-recovery`，從 `ab63ec2` 接續。
  原主樹四個 Code adapter、work-asr 與 work-rebuild 的 WIP 均保留。
  本次形成獨立 Rust `codemode` 建置單位，原 Monty 映像仍獨立發行；異常訊框也會
  走 native worker 清理。Windows 建包與 HJW Arch 同源編譯通過，見
  `artifacts/EXT-023/package-candidate-02/`，Linux binary `23f888dc639f`。
- CORE-034 新候選來源 `f74ecdd86b732d0fb34fa12f0ca9defa377db6b8`，handoff `befb66685306`；
  Windows ZIP `4d073b6f15f5d10c0c8594064c568555671e90c49394f7da64ff1d9568b7ec2e`。
  三平台 ZIP 與每個成員已核。SDK alpha.5 的新包只變 `.cargo_vcs_info.json`，
  插件沿已釘原 crate `ea6a1c2f5e8e`，來源逐成員一致；完整 pin 在 `feed-fix-intake/`。
  原 binary `f26e88f7` 已先實收兩筆同參數 send，證實原 feed 0 ACK 問題解除。
- EXT-023 `candidate-03` 三個真案例通過：兩筆不同 operation、缺 runtime 零效果、
  畸形訊框後原 native 容器清除；全部在 Windows Host／HJW Arch 執行。
  EXT-023／024 都仍是未發布候選，未加入七張正式驗收清單。
- EXT-023 插件候選實作 `fe7c9c0411cc`、EXT-024 驗證 `75c3b42c5dc2` 已推遠端。EXT-024 `candidate-03` 已驗第一筆
  回執未餵入時恢復、第一筆確認後雙重啟、unknown 配對後雙重啟不復活。
  原父與兩筆實收 operation 對應完整；六個案例各三次模型 HTTP，容器集合均還原。
  `evidence-analysis-01` 在 Windows 重算 snapshot SHA 與原位點；native restore 本身
  計一次 suspension，正常累計 2、恢復累計 3，沒有歸零或把兩筆呼叫合併。
- CORE-051 新交付 `9db8b3f073e3`／SDK alpha.9 的三平台 ZIP 與全部成員已核，
  `artifacts/readiness/core051-handoff-inspection.json` 留來源與能力；尚未真消費。
  EXT-047 仍缺 CORE-058，沒有建立空 scoped-session 插件。
- 最新 readiness 為 `artifacts/readiness/after-core034-feed-recovery.json`。
  下一步按 PR #14→…→#23→本次候選處理當前 base 的三平台 gate；CORE-035 extraction
  配置、CORE-036 身份／Jev、CORE-050 音訊授權均仍無新回覆。EXT-024 的 light alias
  投影、Work/run 等待及完整 H14 預算／停止見證需求見 `docs/core-interface-requests.md`。

## 2026-11-05 08:28 UTC 已有進度

- PR #12 已普通合併 `e90035586e9b`，18 份 CI ZIP／成員驗證回條在 PR #13 的
  `artifacts/EXT-028/ci-receipt-f0843e1.json`。PR #13 head `9db51914174e` 已合入新 main；
  Windows、Linux acceptance 與四個 package 通過，macOS 尚排隊。
- PR #20 的 native job `127064263207` 已通過。`artifacts/EXT-023/ci-native-1e9c4b3/`
  保留下載驗證：ZIP `09be6a2742ce217058f2fd91928513af35f88c4c5c7b904822ed99f3057c7e44`、
  18 個頂層成員、真 Rust worker 與原 PID 清理。舊故障未重現；沒有新增因果修復主張。
- 分支 `codex/ext-036-maintenance` 新增獨立 Rust `memory-maintenance`，管理者明選本地工作，
  scope／指紋／原操作／Profile 均交核心核權。`candidate-06` 是當前 Windows 對拍；
  已驗掃描、批准子集、重啟原回條、同筆數修訂拒舊指紋、兩個同維不同 Profile、
  HTTP unknown 重啟不重發，以及清除來源後拒絕新 Reembed。正常 HTTP 2 次，未知 1 次。
- CORE-035 固定來源 `0cdd9dffe07c18949990492fd2a9944919c455d3`，交付說明提交 `69cfdfd7b0ef`，
  Rust SDK alpha.8；Windows ZIP `e2b964e87a30d5c230fbb0805a9de973cb91160b6e8b52606b363ca0fd77a152`，
  crate `a8739c74d300f1044c94749ced333d9694920aa7c91728b19f624ff9fbaf2e63`。
  三平台 bytes／成員均核驗，完整 pin 在 `compat/core-035/`，回條在 `producer-intake/`。
  CORE-028 vector-coverage 回歸另鎖原 manifest／tree，標明 dirty 參考，不代替乾淨候選。
- EXT-036 整卡仍 BLOCKED：公開 audit 未提供原 SQL FTS／向量／來源完整性問題清單；
  audit/reembed 沒有自動清除回調，metadata 保留責任待釐清。`candidate-01` 留缺 write_subject
  的拒絕，`candidate-04` 留未發生回調的失敗。插件收到此回調會停止並拒絕未證實的 ACK，
  不刪無關工作。未發布、未部署、未計入七張正式驗收。
- EXT-036 實作 `fdaa47576a54` 已推 [PR #22](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/22)，
  Windows／Linux jobs 通過，macOS 排隊。真插件回條已交 [CORE-035 #46](https://github.com/Institute-of-Agent-Life/yuki-core/pull/46#issuecomment-6651927585)。
- 已接續 EXT-034。`codex/ext-034-rebuild` 的診斷提交 `69e4e5a` 在
  `artifacts/EXT-034/source-intake-02/` 保留真 Rust 最小重現：同一 Person／entry 的來源讀取成功，
  `model.open`／`extract.preview` 皆 `-32003`，HTTP 零次；完整安裝設定、source version、
  Host／SDK／consumer digest 與 transcript 均保存。這是可重現授權拒絕，未驗收重建。
- `.ci-transfer/work-rebuild` 的完整 job journal／審閱／apply 尚未提交：
  catalog、ci/windows.py、plugin.toml、main.rs、rebuild.rs、EXT-034.py、rebuild_stdio.py、
  EXT-034-sequences.md 及 candidate-01…06 仍留工作樹。批准子集、kill 恢復、付費復用及
  forget 尚未跑到，不把這些檔計入已驗插件。主樹四個 Code adapter 與 work-asr 改動均保留。
- 最新 readiness 為 `artifacts/readiness/after-core035-intake.json`。暫無獨立就緒下一卡；
  下一步等 CORE-035 公開 extraction route 設定或 PR #13 macOS gate。
  EXT-033 缺精確選簇向量與權屬投影，EXT-035 缺原 SELF／真人前臺退讓交接。
  EXT-048 還缺個人寫入及角色管理前置；CORE-051 目前只有 Mac 開發證據，沒有可驗 Windows
  Host 交付，CORE-058／037 亦未見交付。CORE-034/036/050 三份回條仍待回覆。
## 2026-11-06 PR #35 兩平台 CI／產物實收

- 候選分支 `codex/ci-locked-cache` 及 PR #35 固定在 `8eba25f1c44b70983293bdc6b46b00edb5979174`；
  快取實作 `0daf4c9`。本樹／分支 `codex/ci-cache-evidence` 只提交實收證據，保留已驗候選 head。
- run `42183667489` 的 Windows／Linux acceptance、七個套件和 Connector 回歸全部通過，
  17 個 jobs success；8 個 macOS checks 尚 queued。沒有合併。
- 已下載核 30 ZIP：14 package、2 acceptance、2 Connector upgrade、12 cache-inputs；
  GitHub digest／CRC／安全唯一成員／全部成員 SHA／manifest 內容、原 lock／來源 SDK
  和實際 cache inputs 均符本 head。synthetic merge `f4772f760ee58e6bc8dd085ce4b7ff42eebc0fa4`
  parents 為 main `ac8c1b2`／本 head，tree 與本 head 相同。
- 12 個已完成 Rust package jobs 有 8 個從完整原 key 真命中；由原 GitHub job log／SHA
  與 cache-input artifact 交叉核對。命中後仍跑 cargo test/build，依賴得到重用，插件本體
  在新 checkout 的 debug／release 各編一次。未把本機熱輪零編譯推成 CI 全部零編譯。
- 回條 `artifacts/readiness/ci-cache/hosted-8eba25f/receipt.json`／`summary.json`，原 ZIP 和
  job logs 留在 source.json 所列本機只讀快取。macOS 尚缺 15 份 artifacts，完整 gate=false；
  等其通過且核完全部產物才普通合併。原 Native Windows 207.235／26.719 秒結果仍沿用。
  不由 hit 或執行快推斷排隊／組織配額改善。正式完成仍 7／68，原 WIP 保留。

## 2026-11-06 收尾核對

- 快取 [PR #35](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/35)
  已推 `324d189721ef`（實作 `0daf4c9`）；PR #16 的去重 `972c66d` 已推。
  07:45 UTC 全部目前 open PR #16…35 的所有 runs／分頁 jobs 無 failure，快照
  `artifacts/readiness/current-pr-gates-before-cache-metadata.json`。PR #16 當時 7 success／
  13 queued／5 running；PR #35 3 success／22 queued，均未全過，不合併。
  本進度快照屬寫入前 head；後續合併只採 API 即時 head／base 與完整產物。
- 原 PR #16 head `58cd960` 的 push `42149145226`、PR `42149150676` 已確認
  completed/cancelled；新 head run `42179984095` 的完整 25 jobs 仍保留。
- 新 CORE-038 gateway.media `b99b01a92443`／alpha.13、CORE-032 terminal
  `61999b662f1e`／alpha.14 的六份 ZIP／全部 member SHA／來源與 dirty=false 已核。
  `artifacts/readiness/new-interface-deliveries/` 是靜態交付核對，不是安裝或真插件消費。
  公開方法已交付；尚需原 application／tenant 安裝核准與真 Main Work 路由的最小
  公開配置序列。具體字段／正反例已交核心 PR #73 comment6679830369、
  #75 comment6679830928，詳 `docs/core-interface-requests.md`。
- 核心 main 仍 `ce66753708ef`，唯一公開 release 仍已驗 EXT-002 的握手預發版；
  沒有新的正式 SDK／Host 發布。原 44／45／46／47／48／51／61 回條及本次
  73／75 配置請求未見新回覆。只剩 runner／公開配置及既有上游合同等待。
  正式完成 7／68；原四份 WIP 和未驗功能均保留。排程在本次收尾後恢復每小時檢查。

## 2026-11-06 Rust CI 快取候選

- `codex/ci-locked-cache` 實作 `0daf4c9d324bd5c80e738119bc2366ef67863f61`，從去重提交 `972c66d` 延續；快取作為獨立後續 PR，
  PR #16 新 head `972c66d6e40e` 已推；新 PR run `42179984095` 已建立，原
  `58cd960` 的 push／PR 兩輪均核無失敗後請求取消，產物未刪。快取需等 PR #16／
  當前 main 前置及完整新基底 CI 後才可合併。正常／故障時序與來源策略見
  `docs/ci-performance.md`。三平台與全部受影響單位的 gates 保留；沒有新增 job。
- HJW Windows 10 項 cache 回歸與真 local-agent 冷／熱 build 通過。207.235 秒／
  26.719 秒，38／0 筆 registry GET，熱輪無重編譯，原 SQLite 回歸兩輪皆執行。
  actionlint 通過；十九份來源與原矩陣／步驟核對一致。具名回條
  `artifacts/readiness/ci-cache/receipt.json`；第一輪路徑限制失敗保留於 windows-01。
- 快取以 OS／架構／實際 Rust host／版本／lock／來源／實含 SDK SHA 隔離。
  命中不跳過測試、重新建包和逐 bytes 驗證。原碼／vendor 不入快取；不寫使用者的
  Cargo cache。SDK 仍為原 CORE-033 alpha.3，沒有新 Host／插件行為主張。
- GitHub 當前 SHA 的三平台 CI、真正 cache hit、具名 ZIP／merge tree 仍待驗。
  正式完成仍 7／68。Client9 PR #32 及 Main 媒體 PR #34 已推候選；最新功能進度見
  `.ci-transfer/work-media-main/docs/implementation-progress.md`，本次新擦除阻塞回條
  https://github.com/Institute-of-Agent-Life/yuki-core/pull/74#issuecomment-6679099141 。
  CORE-032 terminal.work 的新候選已讀公開說明；尚未逐成員核包或消費，後續核真前置。

## 2026-11-06 CI 去重同步至佇列首張 PR #16

- 沿用 PR #33 的 `11fbc352c9ca`：本提交工作流與已在 HJW Windows 驗過的
  `e8f3465def7ebdbf0aee8024b580eb2edc13cb3342652137dbf6f9a35de6fa22` 逐 bytes 相同。
  分支 push 改由 PR merge ref 跑三平台；main push／手動執行保留。
  只取消同 PR 過期執行，不讓 main 或手動執行互相取消。
- 原 jobs、矩陣、選擇器、測試、建包與上傳步驟均保留。原 Windows 五事件／YAML
  回條 `artifacts/readiness/ci-dedupe-windows.json`，本次來源核對
  `artifacts/readiness/ci-dedupe-pr16.json`。這是既有驗證的精確重用，沒有重跑同件。
- PR #16 基底仍為 `ac8c1b287e5a`；新 head 的三平台 acceptance、全部受影響套件與
  ZIP／manifest／merge tree 未核完之前不合併。只有在新 head gates 已存在後，才取消
  原 `58cd960` 的兩輪過期執行；保留其既有產物。
- Rust 快取為獨立後續變更。原 local-agent、Connector 和 SDK 都未改。
  正式完成仍 7／68。新的 Client9／Main 媒體候選在 PR #32／#34；
  詳細進度見 `work-client-selection`／`work-media-main` 工作樹，原四份 WIP 保留。

## 2026-11-06 PR #15 合併與 PR #16 新基底

- PR #15 head `0107c0afc9f79e30fa7c32a5466b3fcc18fb69b3` 的 push `42058530137`、
  PR `42058542237` 全 44 項檢查成功：三平台 acceptance、六個 release units package
  及 Connector 回歸。已下載核對全部 48 ZIP 的 GitHub digest、安全成員、CRC、
  manifest／逐成員 SHA、36 個 package 的真 binary／wheel 與已鎖 native tests。
- CI merge `dfff7d48543b` parents 為舊 main `996deedef3e1`／該 head。普通合併
  `ac8c1b287e5a320107f64975dfd318b521bd8f13` 的相同 parents 及 tree
  `54a39c56ca2d0ee204bbb19c8f0f12c43132519d` 已重核，與測試 merge tree 相同。
  完整回條 `artifacts/EXT-011/ci-receipt-0107c0a.json`。
- PR #16 原 `12b3ace901e3` 在獨立 `codex/ext-011-gates` 工作樹正常合入此 main；
  只進度有衝突，兩邊完整保留，local-agent／Connector 原碼未改。新 head／current
  base 的三平台 acceptance、受影響 package 與具名產物須重驗後才可普通合併。
- 另有 `work-connector-auth` 的新 CORE-033 alpha.12 Rust 接入 WIP，獨立保留，
  正在 HJW 驗證；本 PR #16 的原配對候選不冒充新 wire4 鑑權整卡驗收。
  其餘 Code／ASR／rebuild／subscription WIP 未動。正式完成仍 7／68。
## CI 觸發去重（進行中）

分支 `codex/ci-dedupe`，基於 main `ac8c1b287e5a320107f64975dfd318b521bd8f13`。
PR 只跑一套 merge ref 檢查；更新 PR 時只取消同一 PR 的舊執行。
main push 與手動執行仍保留，三平台及套件作業定義未改。Windows 實機的靜態檢查及
事件模擬回條為 `artifacts/readiness/ci-dedupe-windows.json`；actionlint 1.7.12 通過。
GitHub 實際觸發與當前 PR 的三平台、受影響套件及具名產物仍待驗證後才能合併。

## 2026-11-05 PR #14 合併與 PR #15 新基底

- PR #14 head `dfe8eb46d64a` 的三平台 acceptance、五套 package 和 Connector 回歸
  全過，24 份 ZIP／GitHub digest／manifest／來源 parents 已核。普通合併 main
  `996deedef3e119246651050dc8cac186044a925a`；實際 tree 與 CI merge `a5ece9e35203` 相同。
  回條 `artifacts/EXT-040/ci-receipt-dfe8eb4.json`。EXT-020 的完整前置仍待核心交付。
- 本分支 `codex/ext-040-setup` 從原 head `a2285c3bc6a2` 正常合入新 main；
  同步提交 `f8aef1b` 只合併歷次回條／進度，安裝器與插件程式樹未改。當前 SHA 三平台 acceptance
  和受影響 packages 需重新通過並驗產物，才可合併 PR #15，不能使用舊 base 綠燈。
- 隨後把已驗固定資產下載修正 `b82112b5b452` 同步到本分支，避免後續 CI 繼續
  遇到相同 504。四個來源檔和原 contract inputs 逐 bytes 相同；在此新基底又於 HJW
  Windows 驗七例通過，回條 `artifacts/readiness/ci-release-504-pr15/`。只改 CI
  讀取；安裝器、插件、原 SDK／資產和授權未變。本地修正提交 `f707400a754a`；新 SHA 要重跑全部 gates。
- 正式完成仍 7／68。PR #26 已推固定資產 GET 的有限重試，修正 `b82112b5b452`、
  head `c2600d644a02`；Windows 七例過。原 native exit134 只有診斷補強，根因未解。
  後續卡與核心包 pin 的完整進度固定於
  https://github.com/Institute-of-Agent-Life/yuki-extensions/blob/c2600d644a027a163d7533300c7dd111d5e0f9c1/docs/implementation-progress.md 。
  這些後續 PR 尚未合入本分支；原 Code／ASR／rebuild／subscription WIP 保留。
- 合併佇列最新 snapshot：`artifacts/readiness/after-pr14-merge.json`。

## 核心輸入與可交還證據

CORE-002 未發布 oracle 產自 `89f15dbbfc5535a0d9fa94244a9e5cde96638ece`，
合併 `2ea4477`。ZIP SHA-256 為
`ccdefae10242b19d2f1a201fcd59f5567c08395fd0c051c3d4e92282f6434df0`。
`compat/core-002/source.lock.json` 固定 ZIP、manifest、index 及來源。
原版為 Connector 0.4.3、wire 4，Client rev 9。

- EXT-007 將原版與 0.4.4.dev0 逐筆對照 124 個 wire4 訊框。三平台各自的
  舊／新 transcript 相同。實機還驗過異設備拒絕、原地升級保留原操作、
  不啟 daemon、可攜 runtime。擴展可交回兩份 transcript、manifest 與 CI receipt。
- EXT-008 起沿未發布的 0.4.4.dev1；第三方依賴仍是原鎖定的 52 個。
  Codex、Claude、ACP 各自的具名 JSON 包含本機 peer 的實際回執與故障邊界。
- EXT-019 對拍的是 Desktop 源碼與舊協議。源安裝固定 rev 9；公開 beta.8
  的 tag 固定 rev 7。詳見 `docs/desktop-handoff.md`。
- EXT-002 記握手 SDK digest。CORE-032 真插件與 CORE-039 原生宿主的逐方法證據見各候選回條。

## EXT-002 握手 SDK

分支 `codex/ext-002-preview`，實作提交 `e2ca2aa`。[PR #9 的三平台驗證與合併紀錄](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/9)。
核心合併提交
`dd694a0db605bfe13b0d72663bef01599560230b`，候選 ZIP SHA-256
`6e2ca1040f6d1eac2f70b0ff363887faf662782f72a7acd367d4a52a17b2caa2`。
本地交付和核心 CI 的 Ubuntu ZIP 完全相同。Rust SDK `1.0.0-alpha.1`、
Python SDK `1.0.0a1`、schema 修訂 1、wire 1.0，方法只有 `initialize`。
`contracts.lock` 記錄 producer 和各交付檔。兩個 consumer 各自鎖定依賴。

預覽 PR #9 合併於 `4f350b7`。Windows 實機在 checkout 外編譯 Rust consumer，從 wheel 安裝 Python consumer，
分別對接交付的 stdio peer。可交還核心的回條是
`artifacts/EXT-002/preview-03/handshake-preview.json` 和同次 manifest。
回條含各實物／測試 consumer digest、逐方向訊框、協商結果及故障回執。
額外欄位不能改 namespace 或提升空 grant；錯版、缺能力、同名宣告、
變更 manifest 與未宣告方法均局部拒絕。修改 ZIP 或 wheel 也被拒絕。
`preview-02` 記錄首個 wheel 反例在格式檢查就遭拒；`preview-03` 用格式有效、
內容相同但 SHA 不同的 wheel，確定是消費方 lock 攔下。正式插件採 Rust，
Python 在此卡只驗 SDK。完整宿主與業務插件仍待相應交付。

## EXT-002 正式驗收

分支 `codex/ext-002-release`，實作提交 `4a281fd`。[PR #10 的三平台驗證與合併紀錄](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/10)。
核心公開預發版 `handshake-preview-dd694a0db605`
指向同一合併提交。ZIP bytes 與預覽相同。`contracts.lock` 已釘公開下載位置、
release receipt 及 SHA256SUMS 的 digest。Windows 測試傳輸程序重新下載三個
公開資產，實機驗雜湊後乾淨安裝，再跑兩端對拍。早期直連逾時的紀錄在
`artifacts/EXT-002/release-download-red/`。

正式可交還證據為 `artifacts/EXT-002/01/published-sdk.json` 與同次
manifest。回條含來源提交、SDK／schema／peer／消費者 digest、逐方向原始訊框、
錯誤碼與實收效果；正式狀態為 PASS。該預發版只含握手，生產插件採 Rust，
宿主及各業務方法仍待核心後續交付。

## 當前進度

七張卡已完成任務書驗收。另有八張卡完成下表的 Windows 候選工作。
三平台 CI 與合併狀態以各 PR 為準。此批開發對拍不計入七張正式驗收。
先前快照見 `artifacts/readiness/after-core032-039-candidates.json`、`after-core033-candidates.json`、`after-core038-candidate.json`。本輪更新見 `artifacts/readiness/after-core034-readiness.json`。

| 卡／分支 | 實作提交 | Windows 已核實 | 仍需 |
|---|---|---|---|
| EXT-003 · codex/ext-003-telegram | `bef4def` · [PR #11](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/11) | 雙 Bot 接納、提交前斷線、提交後丟答與原 offset | CORE-032 正式交接 |
| EXT-028 · codex/ext-028-web-fetch | `0bac149` · [PR #12](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/12) | 兩次 tool.call、R07、19 頁正文與 49 頁原件 | CORE-032 正式交接 |
| EXT-005 · codex/ext-005-feishu | `6183e58` · [PR #13](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/13) | 飛書／Lark 身份隔離、亂序重組、writer 斷線無成功 ACK | CORE-032 正式交接 |
| EXT-020 · codex/ext-020-env | `cf1c2a5`、`1e7906b` · [PR #14](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/14) | 原 Manager 來源包、run 查詢與缺後端局部失敗 | Work/run 授權，真 gVisor/execd、PTY 及輪轉 |
| EXT-040 · codex/ext-040-setup | `a607e8c` · [PR #15](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/15) | 簽名原生／OCI 安裝，無 QQ ready，明選 web-fetch | CORE-039 正式交接、外部入口與選配服務實測 |
| EXT-011 · codex/ext-011-local-agent | 12b3ace · [PR #16](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/16) | 原 Connector 配對、無 instance 裝置跨重啟保存 | Work 以外的裝置授權與撤權狀態 |
| EXT-015 · codex/ext-015-client | `1d8d377` · [PR #17](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/17) | 雙裝置重放、合併後原入口隔離、撤銷單台設備 | 原入口明選、附件／目標操作、Social 出站與 SSE |
| EXT-031 · codex/ext-031-media | `b69ca40` · [PR #18](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/18) | 所選 PDF 頁文、原影片幀與時間、三類壞檔、自動清除回調與暫存回收 | 原模型呈現、正式交付 |

CORE-033 已交接未發布的個人入口候選包，EXT-011／015 可做開發對拍。CORE-025 已開
[核心 PR #34](https://github.com/Institute-of-Agent-Life/yuki-core/pull/34)。EXT-004／006
仍缺原 Bot／租戶附件的公開授權與驗收回條，詳見 `docs/core-interface-requests.md`。
CORE-038 已補齊出站媒體版本讀取；入站原 Bot／租戶取件回調仍待交接。
EXT-067 完整基底對拍還需 EXT-004 的實際分段投遞證據。

PR #15 修正外接磁碟打包時讀取 catalog 的問題。Windows 實機驗證
`catalog/._alpha.json` 不選任何單元，真正的 alpha 變更只選 alpha，損壞的正式
manifest 會報錯。兩個 Python 套件及一個 Rust 執行檔均成功建置。
`artifacts/EXT-001/catalog-sidecar-03/` 含完整回條。首兩次失敗分別記錄
Cargo 不在 PATH 和共用工具鏈缺少 rustc；綠燈使用 HJW 擴展測試目錄內的 Rust 1.90.0。

## EXT-003 Windows 開發候選對拍

分支 `codex/ext-003-telegram`。Telegram 是獨立建置的 Rust 插件，使用
`compat/core-032/source.lock.json` 的宿主及 SDK。真宿主啟動獨立 binary，
Bot API 的受控 loopback recorder 只使用 fixture credential。核心握手、
逐方法訊框與實收效果見 `artifacts/EXT-003/`。早期 `dev-01/02` 的拒絕
保留原始回執；`dev-03` 通過第二條在 commit 前斷線的開發對拍。這些
snapshot 使用候選包，正式進度仍取決於 CORE-032 的有效交付。

可交還核心的 Windows 回條為 `artifacts/EXT-003/candidate-02/telegram-offset.json`
（SHA-256 `7f208179ebfa200709c5574a6756f7edcde83995db369b0bd4b41059f0d64303`）。
來源 `199dff09`；宿主、SDK、schema 與 Rust binary 雜湊均在回條。三條中
第二條提交前斷線停在 offset 11，第三條提交後回執丟失停在 12，復送取得同一
event 3。另一 Bot 的同號消息取得 event 7。edit 和遷群各有 durable event，
accepted 為 false。27 個 stdio 訊框與平台 poll 記錄可逐一覆核。
`dev-03` 是早期開發測試；卡的驗收狀態以 candidate-02 的 preparation manifest
為準。完整宿主候選對拍在 Windows 實機執行，三平台 CI 各自編譯並測試插件。

PR #11 的 Linux Connector 打包在等待 Codex 代理重連時逾時。移入 `6f36958`
已驗證的 EOF 修正後，HJW 回歸 172 例中 171 通過、1 跳過；舊／新 wire4
逐筆相符（124 幀）。失敗的 CI、fixture 雜湊與新回條見 `artifacts/EXT-007/pr11-ci-repair.json`。

修正提交沿 `7dbe738` 的實作，把 Bot API 的秒數轉成宿主接納的毫秒；
Windows 重驗 `artifacts/EXT-003/candidate-03/telegram-offset.json` SHA-256
`a81f960527f3d5e959fef3003af13a8539f4174c9d35af91d1b5855e833f9338`。
新 binary `0eb1cc4cbbc40321028032fc5ba5175ff51bce4e9c99c9af77d23c0fea95c0f2`。在本次三條的故障序列中仍得到 event 3 重投回原 ID。
[擴展 PR #11](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/11)

PR #11 的 head `03cabaa6f53d` 已完成三平台 acceptance、Connector 與 Telegram
package jobs；push `41902511932`、PR `41902523876` 的 24 份產物逐一下載驗
ZIP digest、manifest 和套件成員。2026-11-05 普通合併至 main `8d2f3c6d85e1`。
回條為 `artifacts/EXT-003/ci-receipt-03cabaa.json`。EXT-003 仍是未發布宿主的
開發候選；正式驗收待 CORE-032 交付。PR #12 合入此 main 後程式樹未改，
在新 head／base 重跑三平台 CI；依 #12→#13→#14→#15→#16→#17→#18 順序合併。

## EXT-028 Windows 開發候選對拍

分支 `codex/ext-028-web-fetch`。實機回條 `artifacts/EXT-028/candidate-04/fetch-source.json`
的 SHA-256 為 `efd9f1d22f5e34c1ac7565d808a9b27a9aa1b0e8bb358399f0f1eba939999508`。
真實 CORE-032 Host 來自 `199dff095be0`，ZIP、binary、Rust SDK alpha.2 和 schema
釘在 `compat/core-032/source.lock.json`。插件 binary SHA-256
`a230b4b7d920966bdde578300e99047e8cae7eb69486f61741d7288f4d1359c7`。
`wire.jsonl` 記錄一次 initialize、兩次 tool.call 和四次原 handle 的 tool.status。
小頁面經測試代理送達 Main；大頁由宿主儲存，按原 execution、reader、handle
和 version 讀回 19 頁。R07 同埠換 host 與同 host 換埠都清除敏感標頭和正文，
也覆蓋私有重導、304 和代理斷線。來源歸屬見同目錄的 owner-disposition.json。
前三次實機失敗保留在 candidate-01 至 03。此回條驗的是未發布候選，正式卡待 CORE-032 交付。

EXT-028 實作提交 `de2a867` 的後續實機回條在 `artifacts/EXT-028/candidate-05/`。
Host 現在可逐位元組讀回原件。6250 bytes 經 49 頁重建，正文另經 19 頁重建。
超過訊框預算會保留原件前綴與觀察雜湊，分開記錄傳輸是否完整與保存是否完整。
新插件 SHA-256 `e2f00b2f853a3a69485ac509cecce9f2247e928675ee4b9f2f5117902faed91c`，
回條 SHA-256 `e1f5569fd35045fadd0729b0222e229eef21bcbf798fb821ac086fbc539691d9`。

## EXT-005 Windows 開發候選對拍

分支 `codex/ext-005-feishu`。飛書與 Lark 各用自己的 app、tenant、域名與
Host namespace。測試對端用舊基線原版 protobuf schema、鎖定的 protobuf
與 websockets，經真 WebSocket 連接 Rust 插件。未發布 Host/SDK 釘在
`compat/core-032/source.lock.json`，此回條的來源是 `199dff095be0`。
`artifacts/EXT-005/candidate-01/lark-frames.json` SHA-256
`55fb682c455fc5f43349d87d9c7c6c3c760d2136579d8c6e92738ae754dce9a3`。
Windows 插件 SHA-256 `e0684be789a3f16a282bb83b5387549e0e15c90c07a7004ad8a6e125f1109bba`。
宿主中斷前只有 ping 和 card ACK；重投、重複分片及兩 app 同 open_id 分別得到
原事件 1、1 與 2、2。錯租戶回 500，錯密鑰被拒。逐方法訊框在同目錄 wire.jsonl。
正式驗收待 CORE-032 交付。

## EXT-020 Manager 來源包與後端不可用案例

分支 `codex/ext-020-env`。原 Manager、supervisor、execd 鏡像配方等 38 個成員
釘在 `plugins/env/backend/source.lock.json`。獨立封裝 `deploy/env/manager-source.zip`
SHA-256 為 `c21901e0eca498be372507d3b600281ed2e43e221bc90744f762b8470cbdfab6`。
Windows 用原 Manager 開隔離資料目錄，核實不存在的 run 與 request 各自回
run_not_found 和 unknown_request。Rust env 對拍 `199dff095be0` 的 CORE-032
宿主，插件 SHA-256 `a6745e364e7d28bc5f9193fea926d05c064c5b475e0ea2bea447fb55e948d937`。
沒有 Manager 時，原 Main 收到 manager_unavailable 並繼續；插件仍在線。
回條 `artifacts/EXT-020/candidate-02/env-preparation.json` SHA-256
`b7a4ca9553cd3596c3b1fd0db8c58e9380b689149c859c451e33df4a29e080f0`。
第一輪因 fixture 的 Main 配置缺 name 而失敗。以上是準備項；
原 Work/run 授權、真 Linux Manager/runsc/execd 的 PTY、輪轉及重啟仍待驗證。

EXT-020 實作提交 `cf1c2a5`。Linux package job 另以隔離的原 Manager Unix socket
檢查 Rust 工具只回傳 ready。Windows `candidate-03` 通過相同宿主故障案例，
插件 SHA-256 `44a5e57ec0941dcd067726cc41eaf0b11fd55723209e5674b73562ad30dc6440`。

## EXT-040 Windows 離線安裝候選

分支 `codex/ext-040-setup`。獨立 Rust 工具消費 CORE-039 `093716ad01c0`；
由 `fe278a51` 交接記錄核對的 Windows 原生 ZIP SHA-256
`03989033a13260cb863d1ff81e2407f0593d43c7a6c0779704ca9eb2c6b1a871`，
Linux ARM64 OCI tar SHA-256 `b5975cbc593594c6b55222e7ae1fd8ac9a2bbb3bd147ee1081438df04c708ec9`。
三平台原生包、簽署者、fixture、架構及方法釘在 `tools/yuki-setup/inputs/`。
此版本尚未發布，ARM64 Compose 在 Windows 只完成產生和驗證。

Windows 安裝器 SHA-256 `9ed9a8aa2ae7415efe12cd38a92ce0ffc6638fcc57454b8806ee350e053a8a12`。
具名回條 `artifacts/EXT-040/candidate-06/setup-install.json` SHA-256
`ec6d75176646ddcebae6a22792f4e0a95c22669ffd6e146dd17dd219cc75fbd8`。
13 次安裝／doctor 操作驗過註釋、人工密鑰引用、NapCat 殘留、不支援的選配與錯誤檔案。
空 owner 無插件時真實 /readyz 通過。明選 web-fetch 後，另一個新 owner 只載入該實際 binary。
純安裝不啟服務。Windows 測試另外啟動兩個隔離 owner 驗證結果。CORE-032 消費者與
CORE-039 宿主內的 SDK 同為 alpha.2，crate 雜湊不同；兩者均記在回條。
正式外部入口、選配服務與 Compose 實際部署仍待相應交付。

PR #15 的 Linux push 檢查曾在 Codex 測試代理重連時逾時。Windows 四次重現
代理持有 stdin 緩衝鎖而異常退出；修正測試代理後四次均正常退出。
`artifacts/EXT-007/proxy-eof-regression.json` 記原錯與修正 SHA。
`artifacts/EXT-007/proxy-eof-01/` 是修正後 Windows 完整升級與 wire4 對拍；
172 個 pytest 案例中 171 通過、1 跳過。Connector 的發行程式與鎖檔未改。

## EXT-011 個人入口開發候選

核心 PR #36 交接 `becbdb0316aa` 提供未發布的乾淨 CORE-033 `994aee20ced7`。三個 OS 包、宿主 schema、Client9／wire4 來源及方法索引釘在 `compat/core-033/`。HJW 實用 Windows 包 SHA-256 `ddc2cf1c01dd9df9e0eecf6b1b85984176810b8c763a4b7bd493d924e40a53f8`；宿主 SHA-256 `54e4825ddd9de64d3e71626e320fbec2e8ddd0d60099ef6775a5573aaf2bbfa3`，Rust SDK `1.0.0-alpha.3 / e5b9fde5298eb71ff252fc8acd430b44d8d965761d5d3c948da47fced49c7dbd`。

原 Python Connector 用一次性碼向 Rust local-agent 配對。錯用途和重用配對碼回 401，重啟後仍能按原 device_id 列出沒有 instance 的設備。原 wire4 連線不帶 Work，宿主交換接口缺 Work 回 422；插件拒絕升級，保留舊 journal。需要核心給出與指定 Work 無關的 connector 鑑權、原裝置 ID／namespace 和即時撤權語義，再驗兩條連線的 fencing。

實機插件 SHA-256 `51a4dde84c7eb06127793c62a82fa3e7d6ee8b46c1b5d94f81db4ef49f0f2ee1`。回條 `artifacts/EXT-011/candidate-03/device-catalog.json`，SHA-256 `410fd6c97aafcfe5c3a896291b7d6332e12a1bf0326c5c5d5e188101cd195434`。同目錄有 manifest、transport 與逐方向 `wire.jsonl`。

## EXT-015 多裝置 Client9 開發候選

同一 CORE-033 與 alpha.3 SDK，Rust client 透過真宿主握手，使用零業務 grant。HJW 的 34 次插件 HTTP 呼叫核實兩裝置共享入口、重放只留一事件、不同正文回 409、另一原入口可獨立使用同 UUID。Person A 併入 B 後兩個原 request_person_id 和各自回條仍可讀。單台被撤權時另一台仍能讀取，宿主重啟可取回原回條。

直接向候選宿主明選另一入口仍回預設 binding。插件在派發前拒絕明選入口／會話，失敗寫入無回條。附件／agent_target 回 503，原 SSE 路由回 404；對應入口選擇、完整衝突判定與原子出站效果仍待核心。兩個 Rust 路由邊界回歸在 `artifacts/EXT-015/package-windows/`。

實機插件 SHA-256 `5b890f5e8244a82738633682a1e7a49f94e3fa576602fd57c503a564aa0a2cad`。回條 `artifacts/EXT-015/candidate-01/original-uuid-entry.json`，SHA-256 `a4767cdd810ab075363ee2d269232ce95f5527d4480dca2487916e7cfc8bf216`。同目錄有 manifest、transport 與逐方向 `wire.jsonl`。

## EXT-031 選讀文件與影片開發候選

CORE-038 乾淨來源 `e25c2b8acce34858d5fd67ac408186e49a1da160`，交接提交 `685b1d59ae64`，SDK Rust `1.0.0-alpha.4`。三平台候選成員逐一驗雜湊，固定於 `compat/core-038/source.lock.json`。HJW 使用 Windows ZIP `f7bff236ca0c518016a4bf40dafaddb29b9d86d6fa92722fdce179620d296310`；原生宿主 `7b1c226caf099264dc74f64a988391963a50505a438c5f6d7a1d022f7c52af71a3`。均未公開發布。

獨立 Rust media 插件按原 handle 分塊讀取，復用基線原版 document_reader.py 和鎖定的 FFmpeg 7.1；原解析器 bytes 未改。實機只解碼 slot 1，取得 PDF 兩頁文字和影片第 0／5 秒的兩個不可變 PNG。壞檔、加密、空文件回未讀。第二塊到達前清除來源，晚到結果失效，再讀遭拒，臨時目錄清空。`candidate-01` 太早截取 wire，漏等非同步 forget；`candidate-02` 曾加入手動暫存責任登記。原始回條保留。

`artifacts/EXT-031/candidate-02/media-inspection.json` SHA-256 `3cdd5fd92089a927627f9cdd5f3bd842bbd39600c9ad5175738075c6ea29ab1b`；插件 SHA-256 `ad83ae19b484349ace01f83a3bbb491c97fd6ef7e444dc57fe17be247324ee46`。同目錄含逐方法 wire、manifest、transport 與 owner-disposition；`package-windows.json` 保留獨立建包命令。兩幀目前為 no_vision，待選讀與原 Main 呈現的公開串接。影片 runtime 現鎖 Windows x86_64，其他平台需另驗 codec；三平台 CI 建置／測試與真 Host 解碼分列。

2026-11-05 修正測試等待時序。CORE-038 `d1b7c1b` 的診斷證實原包已登記持有者；Windows `candidate-03` 完全移除手動 acquire，實收原來源 `[6]` 的 forget 回調、原 key／watermark，等待 pending 清空。回條 SHA-256 `405e7c1359165dced882df1c6400bdd29ae2f781106b583e56225d17b587ea55`，新建插件 binary `2d0e7e9b910789bf34b8d263475c71a720a2ee650628fc88a3292a64e26d454c`。`package-windows-03.json` 記建包，宿主／SDK 鎖未變。撤回自動登記缺失的判定；原 Main 呈現與正式發布仍待交付。

修正提交 `262d782` 已推 PR #18，[更正回條已交還核心](https://github.com/Institute-of-Agent-Life/yuki-core/pull/40#issuecomment-6646981531)。PR #11 已合併 `8d2f3c6`；PR #12 head `f0843e1` 合入新主線後正重跑 CI。其餘依順序合併，舊 base 的綠燈不可替代新 merge 產物。

## 下一步：EXT-023 的執行環境

CORE-034 未發布候選來源 `f3f3723aa5322c6a2a20e8cb3b04d845cd7773cc`，SDK alpha.5、composition 1；三平台 ZIP 與每個成員均已驗 SHA。Windows ZIP `fc5f6f1cb8ddd2fe4c62b335705699b6fb8e181993b0a57fa920fe0798e67d04`，完整能力及雜湊見 `artifacts/readiness/core034-handoff-inspection.json`。尚未記作真 Monty 消費證據。

原 worker 固定 Monty `3f9d6ef413fb951e5b80113b7088d535bd028fcb`、原 string-cache 補丁、Linux bwrap launcher、Rust 1.96.0／CPython 3.12 codec。原平台清單沒有 Windows ABI。舊回條 `core034-windows-prerequisites.json` 只測 PATH 上的 System32 舊入口；其「拒絕訪問」不能證明 WSL 不可用。

2026-11-04（太平洋時間）經 SSH 實收：`C:/Program Files/WSL/wsl.exe` 可使用 WSL 3.0.1.0，成功進入 Arch，核心為 `6.18.40.1-microsoft-standard-WSL2 x86_64`。核心已編入 AppArmor／seccomp filter，但 AppArmor enabled 為 `N`；Arch 沒有 apparmor、bubblewrap、docker、python、rust、gcc。具名回條 `artifacts/readiness/core034-ssh-wsl-prerequisites.json` SHA-256 `3ac09579389cb3eb5bbf2e74762b40e5d53fdc9d96098899c591c95fd3238bd0`，探測腳本 `codemode-ssh-wsl-preflight.py`；SSH 和 Linux 探測成功，尚未執行 worker 隔離驗收。

使用者隨後明確授權準備 Arch、安裝隔離工具和必要的 WSL 重啟。`codex/ext-023-codemode` 已保留 `.wslconfig` 原有 memory／swap 設定，追加 AppArmor 啟動參數；重啟時只有本次探測的 Arch 在執行。原索引對應的 10 個 Arch 官方封存套件逐一核 SHA 並驗簽安裝，包含 Docker 29.6.0、AppArmor 4.1.7、bubblewrap 0.11.2，沒有升級既有基礎套件。

`artifacts/EXT-023/environment-01/manifest.json` 記錄環境準備 PASS，含原始故障回條。Arch 的既有 systemd-firstboot 阻塞一般服務啟動，因此本次 daemon 使用專用 socket／資料目錄，未啟用開機服務。公開映像固定 digest 後傳入 HJW；真容器已驗 enforce、Seccomp=2、CapEff/CapPrm/CapBnd 全零、NoNewPrivs=1、只有 loopback、外網失敗、宿主檔不可見與根目錄不可寫。這是執行環境驗證；EXT-023 的原 Monty worker 建置及 Rust 插件仍在進行，尚無 VM 真消費回條或整卡驗收。

### EXT-023 原生 runtime 已驗，Rust 插件對拍進行中

分支 `codex/ext-023-codemode`、PR #19；環境提交 `3dda59a0e5a09c524f1575df54a8557c1b77b292` 已推遠端。原 Monty SHA／補丁／launcher 已在 HJW Arch 建成獨立映像，`images/monty-runtime` 有自身版本、來源鎖、建置、驗證與發行前綴。為符合原 4 GiB WSL 限額，建置期使用 16 codegen units、停用 LTO；執行期限制未變。

未發布 OCI digest `65fcd704d953a9ca9be9c1e70269fc21768b571635e8fa8c38bc8b30c84ceb9a`，archive SHA `fc82cc61ab4b26bb07ef0978b58ff5de0173e41fe08b1879d870a9345502f1ee`。`artifacts/EXT-023/runtime-01/manifest.json` 彙總實收：原 worker 的 stacked AppArmor enforce、Seccomp=2、NoNewPrivs=1、零 capability、六種 namespace、無宿主資料與網路，以及取消／逾時／父程序死亡後清除。兩次同參數呼叫在原 feed 0 保留 call ID 0／1，跨三個新容器恢復；壞 dump 和非凍結函式遭拒。這是 VM／codec 證據，尚未證明核心業務父鍵／子序號及實體效果。

映像封裝的讀取權限已修正。先前誤加的容器層 NoNewPrivs 阻止原 launcher 轉換；依原安全文檔恢復 bwrap 內的原邊界，worker 的 NoNewPrivs=1 斷言保留。598 個鎖定依賴及 326 份 notice 的稽核無未解析項，原兩項上游 MIT 通知缺項有明確記錄。Windows 獨立來源包、兩個完整性故障回歸及 `artifacts/EXT-001/codemode-packaging-01` 通過；三平台來源包與 Linux 真映像 CI 已加入，結果待遠端執行。

CORE-034 `f3f3723aa532`／SDK alpha.5 的 crate、schema、三平台來源與 SHA 鎖在 `compat/core-034/`；Rust worker 控制模組初版已通過 Windows `cargo check`，尚未提交為完成插件。下一步是實收公開凍結投影、接入 Rust Code 插件，再對拍原父 operation／子 ordinal 和未知結果；未交還真插件消費回條，也未標記 EXT-023／024 整卡完成。

映像與封裝提交 `d76aae47ec5853b9d373b55b4ccad663409c93c4` 已推 PR #19。其 Windows package job `127037883124` 的 OCI 來源包成功；archive 回歸在非正規化 TEMP 基底誤拒合法成員。修正為基底與成員都先 canonicalize，保留越界與非普通檔案拒絕。HJW 三項回歸與來源包均過，回條 `artifacts/EXT-023/packaging-fix-01/`；遠端須重驗當前 head。

PR #19 的 d5d2aa1 Linux native job 已通過；PR #20 的 job 127051966392
隨後在 blocked-feed disconnect 的退出碼斷言失敗。原日誌／artifact ZIP 已核 SHA。
HJW Arch 完整重播五次、另做三十次斷開測試全部通過，尚未重現 CI 故障。
驗證器保留退出碼為零及原 native PID 消失的斷言，失敗時增加容器 state、
stdout／stderr；Windows 來源包驗證通過。回條在
`artifacts/EXT-023/disconnect-diagnostics-01/`。等待新 CI 診斷，沒有宣稱故障已修復。

### EXT-023 真 Rust／Host 對拍的具體阻塞

Windows Host `f3f3723aa532` 與 Rust SDK alpha.5 已實際協商，Linux Rust binary
`f26e88f764a44c666cdee68b012e28d422ebd46a9ffbeae5240bee71d33d6b0d` 經同一 HJW
的 WSL 啟動真 Monty。第一筆 `send` 有 HTTP 實收與原 child 回條；第一筆餵入後
原 VM 仍是 feed 0、下一 engine call ID 是 1。核心拒絕 feed 0 的 post-answer
確認（`tool.resume` 回 -32003），所以第二筆未派發。具名回條及所有 digest 在
`artifacts/EXT-023/core034-consumer-01/`。未偽造 feed 序號，未新增重試或模型購買。

獨立 Rust worker 模組在 HJW Windows 編譯／預取消測試通過，原生 ABI 測試明列
不適用；Arch 實跑兩項測試全部通過，包含跨容器原 dump、同參數的兩個原 call
及清除。`plugins/codemode` 現提交可用 worker library；完整 `main.rs`、`rpc.rs`、
`catalog.rs`、`compose.rs` 尚在工作樹，待公開接口修正後才可完成驗收與發行單位。
下一步是消費核心相容 feed-ack 交付、續做原父／子恢復；同時等待順序 PR 的 CI。

## EXT-025 候選輸入已對拍，等待具體生產者接口

`codex/ext-025-participation` 從 `d5d2aa1` 建立獨立工作樹，保留 EXT-023 未完成的
Host adapter。EXT-023 的 feed 回條已交還
https://github.com/Institute-of-Agent-Life/yuki-core/pull/43#issuecomment-6649583219 。
`b0b515f` 修正已使 PR #19 的 Windows／Linux OCI package 通過，最新 worker 的
Windows／Linux jobs 也通過；macOS 與 native image 仍在執行／排隊。

CORE-036 `9f9c3d0eaace`／SDK alpha.7 和 CORE-050 `952954d86166`／alpha.6 的
三平台包逐成員核 SHA，鎖在 `compat/core-036` 與 `compat/core-050`。實際消費
使用整合 aux 方法的 alpha.7 Windows Host，binary `429b1797ffdda7411314572f812123bac2ca31826ca0dd725acdc1c36a45db38`。
Rust 診斷程式已實收 metadata 通知與 source bytes，沒有 promotion／模型呼叫。
缺 canonical Person／Conversation／generation 等原庫必要輸入；原 Jev wire
也沒有已驗的相容 Profile。回條 `artifacts/EXT-025/source-intake-01/` 與具體欄位
需求已備妥。未建立空正式插件，未改寫參與庫，未聲稱 EXT-025 完成。

EXT-025 intake 提交 `2874585` 已推 PR #20；[具體回條已交核心 #45](https://github.com/Institute-of-Agent-Life/yuki-core/pull/45#issuecomment-6649779250)。

## EXT-030 音訊路由 intake 與本輪 CI

分支 `codex/ext-030-asr` 位於 `.ci-transfer/work-asr`，從 `2874585` 建立。
CORE-050 `952954d86166`／Rust SDK alpha.6 的實物鎖在 `compat/core-050/`。
HJW Windows 的真 Rust 診斷 binary `d1c5277638265bc52aceba1dc77328494b21f5e0a15495554ad71a3ed32333b9`
已讀到原 WAV 的 MIME／digest。同一 handle／route 的文字請求成功，HTTP 一次、
usage 4+8；`selected_media=true` 被 -32003 拒絕，未派發音訊。
`artifacts/EXT-030/source-intake-01/` 含逐方法 wire、原 provider bytes、build、
manifest 與所有 helper/source hash。這是 scope 診斷，沒有 ASR 成功或逐字稿。

Rust `asr.rs`、媒體 SDK 升級與整卡測試仍留本工作樹，尚未提交為完成插件。
先前 `candidate-01` 是測試配置缺欄位；具名診斷已補原入口、原執行 root 及
公開 `origins=["call"]`。目前需要生產者給出選定音訊的配置／授權條件。
原 Main／歷史、雙 Bot、引用不再購買、轉碼與清除晚返均未宣稱通過。

PR #19 `d5d2aa1` 的 Linux native image／Rust worker 已通過，下載 ZIP 與 18 個
成員驗 SHA；回條在 `artifacts/EXT-023/ci-native-d5d2aa1/`。這份 CI 映像為
`92b3ab6849f868142975eb453b078a26169a113c23a71b38ece353d619b17d05`，不可混同 HJW 映像。
PR #20 的 native job `127051966392` 隨後在 blocked-feed disconnect 的退出碼
斷言失敗，正在 HJW Arch 重現；先修此故障。PR #12 剩 macOS package 排隊，
其餘順序 PR 不越過；最新 queue 檢查在 `artifacts/readiness/after-core050-intake.json`。
CORE-032 已合併 `30a5ea77bf6c`，公開 release 仍只有握手預發版。

本輪提交／交接：EXT-030 診斷 `b5a007c` 已推 [PR #21](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/21)，
[回條交核心 #44](https://github.com/Institute-of-Agent-Life/yuki-core/pull/44#issuecomment-6650249495)。
取消時序診斷 `5ea1d55` 已推 #19，正常合入 #20 `1e9c4b3`、#21 `cb52127`。
另把 PR #19 的原 image.tar 核全部 blob SHA 後送到 HJW，再做十次 native
斷開測試全部通過；`artifacts/EXT-023/ci-image-disconnect-01/` 留原件。Docker
load 所用 OCI manifest `2be28421f615` 與 CI config ID `92b3ab6849f8` 明確分列。

目前 45 次 Arch 斷開均無重現，仍等新 CI 的退出碼／container state／stdout／stderr，
不宣稱已修復 runner 故障。已對 #19／#20 的十個過期 SHA workflow 請求取消，
保留原 failure 回條；當前 SHA 的全部檢查仍為合併條件。PR #12 尚等 web-fetch
macOS package，其餘 #13→#21 按新 main、當前 SHA 及下載產物逐張處理。
已就緒本地工作已推；下步等待 CI 或核心回覆，原未完成 adapter／ASR 工作樹保留。

## PR #12 合併與 PR #13 新基底

PR #12 head `f0843e106711` 的 push `41939834061` 與 PR `41939841639` 全過。
已下載 18 份 ZIP，核 GitHub SHA-256、成員雜湊及各 task PASS；PR 產物來自
`867562e4c971`，parents 為 main `8d2f3c6d85e1` 與該 head。普通合併提交
`e90035586e9b91af19a5c6162c2e565dbfe966cf`，回條 `artifacts/EXT-028/ci-receipt-f0843e1.json`。
PR #13 已正常合入此 main；程式樹未變，新增前卡回條與進度。新 head 的三平台
與受影響套件仍須重驗，舊基底綠燈不作合併證據。

本次 Code 候選已正常合入 main `526a35382d9b`；合併只加入前卡 CI 回條與進度，
程式內容不變。後續 main 前進仍須再正常合入，不能沿用本次 base 的舊綠燈。
## PR #13 合併與 PR #14 新基底

PR #13 head `9db51914174e` 的 push `41980406600`、PR `41980413395` 三平台及
四套件全過。下載核驗 21 份 ZIP、所有 manifest 成員與執行回條；測試 merge
`98eb7aab4850` 的 parents 為 `e90035586e9b` 和該 head。普通合併至 main
`526a35382d9bb464f92adc947e1b212e0ea41c3c`，回條 `artifacts/EXT-005/ci-receipt-9db5191.json`。
PR #14 正常合入此 main；僅合併回條與進度，程式樹不變。新 SHA 的三平台及套件
檢查仍需全過並驗下載產物，才可合併。

## EXT-011 個人入口開發候選

核心 PR #36 交接 `becbdb0316aa` 提供未發布的乾淨 CORE-033 `994aee20ced7`。三個 OS 包、宿主 schema、Client9／wire4 來源及方法索引釘在 `compat/core-033/`。HJW 實用 Windows 包 SHA-256 `ddc2cf1c01dd9df9e0eecf6b1b85984176810b8c763a4b7bd493d924e40a53f8`；宿主 SHA-256 `54e4825ddd9de64d3e71626e320fbec2e8ddd0d60099ef6775a5573aaf2bbfa3`，Rust SDK `1.0.0-alpha.3 / e5b9fde5298eb71ff252fc8acd430b44d8d965761d5d3c948da47fced49c7dbd`。

原 Python Connector 用一次性碼向 Rust local-agent 配對。錯用途和重用配對碼回 401，重啟後仍能按原 device_id 列出沒有 instance 的設備。原 wire4 連線不帶 Work，宿主交換接口缺 Work 回 422；插件拒絕升級，保留舊 journal。需要核心給出與指定 Work 無關的 connector 鑑權、原裝置 ID／namespace 和即時撤權語義，再驗兩條連線的 fencing。

實機插件 SHA-256 `51a4dde84c7eb06127793c62a82fa3e7d6ee8b46c1b5d94f81db4ef49f0f2ee1`。回條 `artifacts/EXT-011/candidate-03/device-catalog.json`，SHA-256 `410fd6c97aafcfe5c3a896291b7d6332e12a1bf0326c5c5d5e188101cd195434`。同目錄有 manifest、transport 與逐方向 `wire.jsonl`。

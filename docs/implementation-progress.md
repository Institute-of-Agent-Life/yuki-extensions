# 擴展實作進度

任務書 ZIP SHA-256 `79dfd2ba5a8b96f22dea4c5f72a94ca761b15f2e354e33b36c7ecdbedc3ec3ee`。
行為基線 `329ca7c487414d2f54ddd98ff4727446ed2446cd`。官方插件接入層用 Rust。
獨立 Connector 沿用 Python 3.12；共享預算沿總書 K05。

| 任務／分支 | 實作、三平台 PR CI 與主線合併 | Windows 實機證據 |
|---|---|---|
| EXT-001 · codex/ext-001 系列 | `4cbaff3`、`033bb04`、`f136b4d`；CI `41819289910`；主線 `93adb61` 含 Rust 補驗 | `artifacts/EXT-001/03/`，隔離建包、Rust 真編譯與故障案例 |
| EXT-007 · codex/ext-007 | 來源 `0150c76`、打包 `8fd6ed8`、正式對拍 `41860a2`；CI `41833181301`；PR #3 合併 `18e028c` | `artifacts/EXT-007/01/` 與 `ci-receipt-41860a2.json` |
| EXT-008 · codex/ext-008 | `d434482`；CI `41833796596`；PR #4 合併 `15ea291` | `artifacts/EXT-008/faults/` 重現舊錯，`01/` 實測 19 例 |
| EXT-009 · codex/ext-009 | `c0d30fb`；CI `41834256598`；PR #5 合併 `9eb9223` | `artifacts/EXT-009/01/`，4 例含真 SDK、原問題回執、EOF 與檔案保留 |
| EXT-010 · codex/ext-010 | `ab16e07`；CI `41834791702`；PR #6 合併 `2c55dbb` | `artifacts/EXT-010/02/`，8 例含實際子進程退出碼 23、雙 session 取消及 unknown |
| EXT-019 · codex/ext-019 | 實作 `7531d84`、PR head `9d1e8a8`；三平台 CI `41835863011`；PR #7 合併 `7625095` | `artifacts/EXT-019/02/`，呼叫表、schema 差分、5 個故障變異；`03/` 固定跨平台順序 |

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

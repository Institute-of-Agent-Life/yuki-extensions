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
- 握手 SDK 的 digest 見下方 EXT-002；完整 Host／正式插件仍無逐方法消費證據。

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

## 下一張可執行卡

直接前置與最新觀察見 `artifacts/readiness/after-ext-002.json`。共有 7 張卡
通過實機驗收。Telegram 與 web-fetch 的下一步分別是 EXT-003 與 EXT-028，
兩者均待 CORE-032；EXT-011／015 待 CORE-033，EXT-040 待 CORE-039。

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

## PR #12 合併與 PR #13 新基底

PR #12 head `f0843e106711` 的 push `41939834061` 與 PR `41939841639` 全過。
已下載 18 份 ZIP，核 GitHub SHA-256、成員雜湊及各 task PASS；PR 產物來自
`867562e4c971`，parents 為 main `8d2f3c6d85e1` 與該 head。普通合併提交
`e90035586e9b91af19a5c6162c2e565dbfe966cf`，回條 `artifacts/EXT-028/ci-receipt-f0843e1.json`。
PR #13 已正常合入此 main；程式樹未變，新增前卡回條與進度。新 head 的三平台
與受影響套件仍須重驗，舊基底綠燈不作合併證據。

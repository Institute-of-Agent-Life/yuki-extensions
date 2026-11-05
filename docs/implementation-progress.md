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
- EXT-023 插件候選實作 `fe7c9c0411cc` 已推遠端。EXT-024 `candidate-03` 已驗第一筆
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

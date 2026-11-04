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

## EXT-002 握手預覽

分支 `codex/ext-002-preview`，實作提交 `e2ca2aa`。[PR #9 的三平台驗證與合併紀錄](https://github.com/Institute-of-Agent-Life/yuki-extensions/pull/9)。
核心合併提交
`dd694a0db605bfe13b0d72663bef01599560230b`，候選 ZIP SHA-256
`6e2ca1040f6d1eac2f70b0ff363887faf662782f72a7acd367d4a52a17b2caa2`。
本地交付和核心 CI 的 Ubuntu ZIP 完全相同。Rust SDK `1.0.0-alpha.1`、
Python SDK `1.0.0a1`、schema 修訂 1、wire 1.0，方法只有 `initialize`。
`contracts.lock` 記錄 producer 和各交付檔。兩個 consumer 各自鎖定依賴。

Windows 實機在 checkout 外編譯 Rust consumer，從 wheel 安裝 Python consumer，
分別對接交付的 stdio peer。可交還核心的回條是
`artifacts/EXT-002/preview-03/handshake-preview.json` 和同次 manifest。
回條含各實物／測試 consumer digest、逐方向訊框、協商結果及故障回執。
額外欄位不能改 namespace 或提升空 grant；錯版、缺能力、同名宣告、
變更 manifest 與未宣告方法均局部拒絕。修改 ZIP 或 wheel 也被拒絕。
`preview-02` 記錄首個 wheel 反例在格式檢查就遭拒；`preview-03` 用格式有效、
內容相同但 SHA 不同的 wheel，確定是消費方 lock 攔下。正式插件採 Rust，
Python 在此卡只驗 SDK。完整宿主與業務插件仍待相應交付。

## 下一張可執行卡

EXT-002 的預覽對拍已可重現；正式狀態為 `AWAITING_PUBLICATION`。
收到正式 SDK 的來源、取得位置和 digest 後，重新安裝該版本並跑正式驗收。
其餘擴展卡的直接前置記在 `artifacts/readiness/after-ext-019.json`。
EXT-043 仍待 CORE-044 與沿途 EXT-067，EXT-011 另需 CORE-033 與 EXT-002。

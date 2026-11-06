# EXT-024：普通拒絕後的獨立呼叫

本次只消費 CORE-015 `969fb62e34de` 的未發布逐項拒絕候選，原 Monty
映像、Rust Code binary 與 launcher 沿已驗 digest，不重跑已完成的六個恢復案例。
先逐三平台 ZIP 核來源、SDK、manifest、所有成員與實含方法，再在 HJW Windows／Arch
建立各自的新 owner。原 provider 回應、Host wire 及 binding HTTP 全部保存。

## 正常與故障順序

1. 由公開 operator 建立原 Person／QQ 帳號／Bot stage／入站，Main 接納原 Work。
2. direct 同一模型回應先呼叫 `send({text: 42})`，再呼叫
   `send({text: "continue after original refusal"})`。第一筆違反原 paid schema；
   應有原 call ID 的拒絕、零外部派發，第二筆只有一次真 binding 實收。
3. 另一新 owner 使用真 Rust Code 插件，在原隔離 Monty 中依同序呼叫
   `yuki_send`。保留原父／子 operation、ordinal、feed／engine call ID、
   失敗回條、餵入與 ACK；普通拒絕不能被當作 unknown 或建立額外重試權。
4. 使用公開 `main inspect` 核當前原 operation；從下一筆真模型 HTTP 的原配對
   內容核兩種方式是否都保留拒絕、繼續第二筆並完成。冷啟動不應重發已結算送達。
5. 比對測前／後專用 daemon 容器集合；結束必須清除本次 native worker。

若 Code 的第一項被泛稱 -32003 拒絕，另開新 owner 作 `code-control`：
先送合法 `before original refusal`，再送同一 `text: 42`，最後送原合法項。
只有先實收合法項，才能排除整個 Code 安裝或 send scope 不可用；原失敗項與
第三項未執行分開記錄。這不是撤權或預算分類的證明。

若公開 `tool.invoke` 只回不可分類的 RPC 錯誤，或拒絕項沒有可餵的原回條，
保留該 wire 和實收效果，停止該段驗收並提出原 Host 方法／分類／回讀需求。
不把 RPC 錯誤自行轉成 VM 值，不重新派發，不修改核心或讀主庫。

本段不宣稱越權 grant 的完整 direct／Code 等價、Work/run future、H14 根額度／
paired partial/code_stop、輕量 frozen alias 或正式發布已完成。

## 2026-11-06 實收

`refusal-01` 的 direct 原 bad/good call IDs 都完成配對：bad 是 failed、
`invalid_tool_arguments`／`dispatched=false`／`executed=false`，good 只有一次 binding
實收。Code 原 `tool.invoke`（ordinal 0／feed 0／engine call 0）回 -32003，
沒有取得可餵 child receipt；原公開 composition 投影沒有 child，後項未執行。

`control-01` 的真 Monty 先完成合法 send、原 child receipt、post-answer snapshot
及 ACK，第二項（ordinal 1／feed 0／engine call 1）才以同一泛稱錯誤拒絕。
第一筆已確認效果保留，第三項沒有派發。這排除整個 Code 安裝不可用，仍不從
泛稱錯誤判斷內部 admission／費用或將它當成普通 VM 值。

三例合計 9 筆模型 HTTP、2 筆 binding；各冷啟兩次未新增模型或送達，容器集合
均回測前。`analysis-01` 在 HJW Windows 重核原 ZIP／manifest／SHA、原配對、
逐方法 request/reply、首筆成功 ACK 與第二筆拒絕，狀態 `DIAGNOSTIC_VERIFIED`，
整卡仍 `BLOCKED`。

新 Host 的配套 SDK 是 alpha.11，Rust Code binary 仍為原 alpha.5 consumer
`23f888dc639f01754f4122dd606bfeebddf9e77f84757bee8db8fc318e05bb47`。
13 個插件來源／建置檔與 `fe7c9c0411cc` 相同；本次不宣稱重新編譯或升版插件。
新 Host schema 2 與已驗 CORE-037 alpha.11 的完整 schema 相同；原 alpha.5 的
完整 Host schema 不同，八個實際使用的 composition method DTO 逐項相同，
比較及原 binary／SDK／13 個來源綁定見 `compat/core-015-isolation/consumer.lock.json`。

Windows 重現入口：設定 `YUKI_HOST_CANDIDATE` 為 `compat/core-015-isolation`
釘定的 Windows ZIP，執行 `python ci/codemode_rejection_intake.py --out <新目錄>
--fixture-root D:/yuki-extension-tests/core034-public-help
--linux-plugin /var/tmp/yuki-ext023/feed-recovery-02/target/debug/yuki-codemode
--plugin-sha256 23f888dc639f01754f4122dd606bfeebddf9e77f84757bee8db8fc318e05bb47`。
正對照另加 `--modes code-control`；先保留兩次 driver 各自生成的 `evidence.zip`，
再用 `ci/codemode_rejection_verify.py --first <首次 evidence> --control <對照 evidence>
--out <新分析目錄>` 重核。原隔離 profile／daemon 只恢復既有專用配置。

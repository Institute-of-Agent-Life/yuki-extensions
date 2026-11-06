# 下一批跨倉交付需求

本分支保留 PR #16 原消費者的歷史請求；後續功能的完整修訂與解除記錄見
[固定的最新功能請求](https://github.com/Institute-of-Agent-Life/yuki-extensions/blob/6c5be41e98d96146d5941b857f7d18ac5ed22542/docs/core-interface-requests.md)。
例如下方舊 CORE-033 Workless 請求已由 PR #30 的 alpha.12 真消費解除；本分支仍建
原 alpha.3 package，不把舊候選限制重新當成目前核心缺口。下方終端／原收件媒體已更新。


Telegram、飛書、web-fetch 與 env 的 Windows 候選回條已記入實作進度。
以下需求沿用核心已發布的方法與授權規則，未定欄位由核心生產者確認。

## CORE-002 → EXT-007／EXT-019

已收到 CORE-002 `89f15db` 的未發布 oracle、index 與 manifest，
完整雜湊見 `compat/core-002/source.lock.json`。EXT-007 已在 Windows
驗證原版及候選的 wire4 重連、ACK 邊界與原操作保留。逐筆對拍與故障結果見
`artifacts/EXT-007/01/connector-upgrade.json`。
EXT-019 已對照兩份 OpenAPI，Desktop 固定 `bee5692` 的後端是
`004ae36`；源碼呼叫、tag 區別與故障探針見 `docs/desktop-handoff.md`。

## CORE-031 → EXT-002

已收到合併提交 `dd694a0db605bfe13b0d72663bef01599560230b` 的握手預覽。
`contracts.lock` 固定 handoff manifest、sdk-crosswire 與 ZIP 雜湊。
核心 GitHub Actions run `41839465940` 的 Ubuntu artifact 裡有逐位元相同的 ZIP。
對端、schema 修訂 1、方法索引與 Rust／Python SDK 都已實際消費。
雙向 `initialize`、同 ID 的交錯 RPC、optional 欄位、錯版、未宣告方法、
缺必需能力、重複宣告與變更 manifest 的結果在 EXT-002 預覽回條中。
核心已將同一 ZIP 以 `handshake-preview-dd694a0db605` 公開預發。正式雙向消費回條見
`artifacts/EXT-002/01/published-sdk.json`。下一步需 CORE-032 等業務方法。

## CORE-032／CORE-039 → 首批 Rust 插件

第一批是 Telegram 與 web-fetch；需要包含下列能力的同一個宿主候選，列 OS／arch、
host／schema／SDK digest。以下名稱沿用總書方法族，實際欄位以發布 IDL 為準。

| 方法族 | 插件需要傳遞或取得的事實 | 正常／失敗案例 |
|---|---|---|
| `gateway.inbound/status` | 綁定 namespace、原 bot／native chat／message／版本／topic、時間、segments、mentions、附件索引；持久 event／admission 結果 | commit 後才 ACK／推游標；相同 native 重投查原接納；純觀察不冒充 admission |
| `tool.call/status` | 宿主建立的 opaque call handle、原 operation／父鍵／ordinal、schema revision、參數與來源 handle；typed result／error | 同鍵同參查原結果，同鍵改參拒絕；自報 Person／admin 不升權；取頁途中撤權，遲到結果不可發表 |
| `gateway.plan_send/dispatch_part/status` | 無 I/O 的原分片計畫、各 part 的穩定鍵、原定位及逐片 platform receipt | 第一片 confirmed、第二片 unknown；重讀保持原狀態，不以新鍵補發未知片 |
| `forget.request/ack`（有持久來源私料時） | 原 forget／plugin 鍵、清理義務、水位及 logical／physical／pending 結果 | kill 後重啟先清欠交；清除後原操作不復活；沒有持久私料時不假造 owner 表 |

用量／預算沿 K05：插件只消費宿主綁定的原請求與預算 handle，不能複製核心規則。
邏輯預留一次；物理 attempt 的派發、回應、usage／未知費用分列。unknown 不是新的
重試許可，也不能被填成零費用或成功。

已交還核心的宿主、SDK、插件雜湊及逐方法回條見
`artifacts/readiness/after-core032-039-candidates.json` 的 `handoffs`。
EXT-067 的 B0 還需要同一候選上的實際分片投遞與原授權證據。


### CORE-032 候選的 Telegram 消費結果

已釘 `199dff095be0bc87c9713beaa0419400cb424a7c`，schema 2、SDK
`1.0.0-alpha.2`，來源與各平台 digest 在 `compat/core-032/source.lock.json`。
`gateway.inbound` 的 `segments` 索引只列 object。Windows 候選實際接受
扁平的 text/text、mention/native/label/span、media/kind/reference 及
reply/native_id；舊 Telegram 的巢狀 data 會回 `-32003`，與拒絕未授權來源
同碼。建議在生產者 schema 的 segments items 明列這些形狀與失敗分類。
遷群目前能以 data 事件交原 from/to，尚無可授權轉移原 space 綁定的方法。
擴展只記平台服務事實；若要移轉既有綁定，需由核心提供帶原 Bot、原新 chat、
生效時間與同鍵重投語義的授權方法。

### EXT-020 original Work and terminal run

更新：CORE-032 `61999b662f1ead1cfd526efdb9b163b02d389cdf`／SDK alpha.14 已交
`terminal.scope` 與 `terminal.bind`。三平台 ZIP／逐成員／dirty=false 已核，靜態回條在
`artifacts/readiness/new-interface-deliveries/terminal-work-inspection.json`。
原先缺公開 Work／Manager 綁定方法的請求已由此候選補上；本分支尚未消費此 tuple。

`terminal.scope(handle)` 的原 `operation`、`installation`、`work_id`、`execution`、
`request_id`、`launch_request`、`run_id` 及 `mode` 原樣用於原 Manager 對賬；模型提供的
Work／run 不是授權。仍需可解析安裝／Main Work route 的公開最小配置與操作序列，
讓真正已接納 Work 的正常 Main 呼叫 `terminal_exec`；不能拿 producer 合成 peer 或
舊 Client9 的 held/runner_failed 當這個新候選的測試結果。

具體請求、合法啟動／reconcile 不重啟、跨 Work 拒絕和取消觀察案例已交
https://github.com/Institute-of-Agent-Life/yuki-core/pull/75#issuecomment-6679830928 。
取得該序列後接原 Python Manager/runsc/execd，在 HJW Windows／Arch 驗 PTY、
byte cursor、輪轉、原 run 重啟讀回與非零退出後文件。當前只保留原 readiness consumer。

### CORE-025／038 → EXT-004／EXT-006 的附件授權

更新：CORE-038 `b99b01a924439b4104bd087808d789ba46809202`／SDK alpha.13 已交
原收件 callback `gateway.media`，不再列為缺失方法。三平台 ZIP／全部成員／來源已核，
`artifacts/readiness/new-interface-deliveries/gateway-media-inspection.json`；尚無本倉真消費。

callback 固定原 namespace、platform、Bot stage、application／tenant、source_event、
attachment／segment、locator／reference 與 transfer 的 offset／length；回同 transfer、
offset、size、SHA-256 和 bounded base64。Host 在原執行和 writer 再核來源。這些欄位
只作候選合同核對，未形成第二套身份／授權規則或生產依賴。

公開兩份 gateway 說明要求核准 application／tenant，但未列這一批准的可解析 TOML
欄位及真正 ingress→明選讀取的最小操作序列。已請核心指向既有公開例子或給配置：
https://github.com/Institute-of-Agent-Life/yuki-core/pull/73#issuecomment-6679830369 。
需原 Telegram Bot、Feishu app／tenant、錯裝／換部署／撤權／forget 及遲到最後頁案例，
不猜配置，不以 producer 的 207 項檢查充作擴展驗收。新終端／媒體包皆未發布。
出站不可變版本與原 operation／part 回條沿既有媒體／發送卡，原 e25 tuple 自動 forget
既有通過結果保留；0ef Main 擦除 FK 787 是另外一個已交回核心的阻塞。

## CORE-033 → EXT-011

Windows 候選 `994aee20ced7` 能以一次性碼配對 connector。原 Connector 在
`/agents/v1/connect` 升級時只有 Bearer 憑證，尚無 Work。現有
`/core/v1/entry/exchange` 缺 Work 回 422；SDK `device.auth` 以 Work proof
換取 handle、scope、expires_in。wire4 hello 的 device_id 由客戶端填寫。

請核心指定既有憑證在未選 Work 時的驗證入口、grant、用途、穩定原裝置 ID
與 journal namespace，以及在線撤權的通知或複核時點。案例需覆蓋 chat 憑證、
已配對舊設備、A→B 合併、帳號換人、憑證撤銷、舊連線晚到的 catalog／close。
取得授權後，插件才能為已認證裝置管理當前連線與 instance 快照。

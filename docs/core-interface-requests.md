# 下一批跨倉交付需求

尚無真 Rust 插件消費證據。以下是依 v3.2 卡片列出的消費需求，不是新 IDL；欄位拼法、
公共 wire、SDK 生成與授權真源均由核心發布。擴展不自行補出平行協議。

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
正式驗收還需要核心發布能固定版本、來源及 SHA-256 的 SDK 產物。

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

對拍完成後交回：同一 host／SDK／插件 digest、逐方法 transcript、實收效果、撤權／
錯版／重投／部分未知等失敗案例。現階段沒有 SDK／Host 消費證據可交，勿標 B0 已驗。

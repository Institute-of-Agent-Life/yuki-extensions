# 下一批跨倉交付需求

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

The CORE-032 tool.call at `199dff095be0` carries the operation, call handle and
parent/ordinal. Its tool.status result supplies that handle and state. Identify
the public lookup or add a capability-scoped binding for original Work,
execution, installation and permitted target run. The original Manager sets
YUKI_WORK_ID from trusted context, and its status contains other runs.
A model-supplied Work or guessed run cannot authorize read/input/cancel.
Required cases cover cross-Work guesses, redispatch/restart of one original
request, a changed Work after dispatch and cancelling an observation while the
terminal continues. The partial plugin exposes readiness only.

### CORE-025 → EXT-004／EXT-006 的附件授權

核心 PR #34 的提交 `d40d4f524e11c5590c45ca16478cb2979a40c698` 提供 QQ 收件、
快照與到期案例。其公開 Host schema revision 2 的 SHA-256 仍為
`4822f19fb937eba524e475b35c0753a713587f48feee87ae6bd7b53ccab06cba`。
`gateway.dispatch_part` 接受一般 arguments；公開索引沒有標出從這些 arguments
取得附件版本的授權方式。[核心 PR #34](https://github.com/Institute-of-Agent-Life/yuki-core/pull/34)

- 請指明既有 callback 或 SDK 方法如何讓原收件 gateway 解析 Telegram file_id
  或飛書／Lark media key。宿主需要綁定原安裝、接收 Bot／app 階段、租戶、
  event、attachment_index 及原 segment 位置。換 Bot 或跨 app／租戶重用同一 key
  應遭拒，原生下載次數為零。
- 發送時請給出原 operation／part handle 如何授權讀取已固定的版本、SHA-256
  與位元組。替換來源檔後仍應發送原版本；到期、撤權或 forget 後應返回相應狀態。
  平台回應未知時，重連只能查原 part，不得生成一次新的派發。

下一個可用交付須附該公開方法的 grant、欄位、乾淨宿主／SDK digest，以及
同安裝成功、換安裝拒絕的回條。擴展才能把以上案例接入 EXT-004／006。

CORE-038 `e25c2b8acce3` 已提供出站原 plan 的 `media` 描述與 dispatch handle 的
`media.open` 讀取，此部分缺口已收斂。仍需入站 Telegram file_id／飛書 key
的原 Bot／app 取件 callback、原 event/slot 和到期語義，才能接完整原件解析。

## CORE-033 → EXT-011

Windows 候選 `994aee20ced7` 能以一次性碼配對 connector。原 Connector 在
`/agents/v1/connect` 升級時只有 Bearer 憑證，尚無 Work。現有
`/core/v1/entry/exchange` 缺 Work 回 422；SDK `device.auth` 以 Work proof
換取 handle、scope、expires_in。wire4 hello 的 device_id 由客戶端填寫。

請核心指定既有憑證在未選 Work 時的驗證入口、grant、用途、穩定原裝置 ID
與 journal namespace，以及在線撤權的通知或複核時點。案例需覆蓋 chat 憑證、
已配對舊設備、A→B 合併、帳號換人、憑證撤銷、舊連線晚到的 catalog／close。
取得授權後，插件才能為已認證裝置管理當前連線與 instance 快照。

## CORE-033 → EXT-015

同一 Windows 包的原 Client9 入口支援配對、訊息、事件、原 UUID 回條與
裝置撤權。A→B 合併後各憑證仍能讀取原 request_person_id。直接向宿主用
A 的 token 與 B 的 X-Yuki-Entry 查 /me，宿主回 200 並選了 A 的 binding。
Rust 插件對明選入口／會話先回 503，失敗寫入沒有產生回條。

請核心在原 Client9 的授權及提交交易內處理 X-Yuki-Entry 與
X-Yuki-Conversation，涵蓋合併後切換、越權原件、停用入口／撤設備、
ACP 既有會話和舊 NULL。另需可用的附件及 agent_target 正反例、同號操作／
目標衝突、提交後 Social Outbound 的 SSE 與斷線續讀。回條需給出所選原
binding、request_person_id、事件／conversation、可見範圍及明選失敗時的零寫入。

## CORE-038 → EXT-031

Windows 真 Rust 插件已消費 `e25c2b8acce3` 的 `media.process/open/publish`，
固定來源、SDK、schema 與三平台包於 `compat/core-038/source.lock.json`。
`artifacts/EXT-031/candidate-02/` 含原 PDF 頁文、兩張實際影片幀、失敗結果和 wire。

- `candidate-01` 中已讀首塊後，`privacy erase` 阻止後續讀取，卻未發
  `forget.request`。`candidate-02` 在相同時序加入公開 operator
  `privacy acquire media volatile-decoder-fixture <event>` 才收到回調，Rust
  清理完畢回原 key／watermark／proof，pending 清空。請確認宿主應在
  `media.process` 授出或 `media.open` 首讀時自動登記的暫存責任，綁定
  installation、原 handle、source/version、水位；或指明已有的插件端方法。
  案例需覆蓋分塊讀途中清除、解碼中清除、完成前清除與重啟欠交。
- 普通 `tool.call` 的 `data.images` 已有原 profile 的呈現合同。選讀現在由
  operator `host process` 觸發，回條兩幀是 no_vision。請給出由使用者或
  Main 的原執行選定 processor/event/slot 後，如何把該 media call 的
  artifact/version 帶回原 Main 的公開路徑與案例。需證明原圖 bytes 到達
  原模型、無另購 vision 請求、失效 handle 不呈現；擴展不另造轉接授權。

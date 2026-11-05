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

- 自動媒體清除責任已核實，撤回先前缺口判定。生產者 `d1b7c1b` 的只讀
  診斷指出 `candidate-01` 太早截取 wire；原包 `e25c2b8` 已有自動持有者。
  Windows `candidate-03` 移除手動 acquire，等待原來源的非同步
  `forget.request` 和 pending 清空後才結束。實收 key `remove-original`、
  sources `[6]`、watermark `1`；晚到結果失效、新讀取遭拒，暫存清空。
  新回條 SHA-256 `405e7c1359165dced882df1c6400bdd29ae2f781106b583e56225d17b587ea55`。
- 普通 `tool.call` 的 `data.images` 已有原 profile 的呈現合同。選讀現在由
  operator `host process` 觸發，回條兩幀是 no_vision。請給出由使用者或
  Main 的原執行選定 processor/event/slot 後，如何把該 media call 的
  artifact/version 帶回原 Main 的公開路徑與案例。需證明原圖 bytes 到達
  原模型、無另購 vision 請求、失效 handle 不呈現；擴展不另造轉接授權。

## CORE-034 → EXT-023／024：原 Monty feed 位點確認

固定 Windows Host `f3f3723aa532`、SDK alpha.5 與真 Rust 消費者，在 HJW Arch
啟動 OCI `65fcd704d953` 的原 worker。原 Main 接納 Work，`tool.schema` 提供
凍結 `script_name`，第一個 `send` 已由 HTTP 對端實收。T0／T1 和 T3 回條均成功。

原 Monty 對同一段程式的兩次呼叫產生 `(feed_index=0, engine_call_id=0)` 和
`(feed_index=0, engine_call_id=1)`。第一筆餵回後，原 post-answer 快照仍在 feed 0；
以 `tool.resume` 確認 `{checkpoint:1,snapshot:<原SHA>,feed_index:0}`，Host 回
`-32003 method, grant or original scope denied`，第二筆沒有派發。不得把原 feed
改成 child ordinal 以迎合不相容條件。兩個 dump／envelope 的 SHA 已重新核對。

請生產者確認 `tool.resume.ack.feed_index` 的公開語義並提供可消費修正：同一
原 feed 內以不同 engine_call_id 前進，仍以原 checkpoint 防止重餵；同 ack
重投冪等，換 snapshot／原 child 位點拒絕。需附 T3 後未餵、post-answer 確認後
雙重啟、原父 operation／子 ordinal 不變及兩筆同參數效果恰為兩次的案例。
使用者 K05 的根預留和未知請求重試權不變。

回條 `artifacts/EXT-023/core034-consumer-01/native-feed-ack.json` 含 Host／SDK／
Rust binary／worker／launcher／codec digest、原始逐方法 wire、實際 HTTP 效果和
失敗位置。這是已執行的消費者不相容回條；完整 Host adapter 尚留工作樹，未作
完成插件或穩定接口見證。可獨立驗證的 Rust worker 控制模組另行提交。

## CORE-036／CORE-050 → EXT-025：原參與庫的輸入與 Jev wire

CORE-036 `9f9c3d0eaace` 與 CORE-050 `952954d86166` 的三平台候選和每個成員
已驗 SHA；前者整合的 `llm.complete/result` 與後者公開定義逐欄一致。仍未發布。
原參與庫固定 `a6a13d4f04ecc36da26adb5f364abdb4f032fc1e`，archive SHA
`0e2cad3ad0f16e710e39f6fd2c9513c0a4c889ca54617ad6fdcb599f313a6ab4`。

Windows 真 Rust SDK 診斷收到 `observer.event` 的 entry/event/kind，及 source
頁中的 account、bot_stage、segments、space/topic、原時間與 transport source。
原 Person、canonical Conversation／generation 不在回傳中；用 operator 建立的
Person UUID 與實收 account UUID 不同。完整原始線路見
`artifacts/EXT-025/source-intake-01/`，此 consumer 不 promotion、不買模型。

請指定 scoped hydration 的既有公開路徑，或補欄位使 `ScopedEvent`／原
`UnitBinding` 可無推測地建立：canonical Conversation／generation、原真人
Person／assignment 與當前代表、human／SELF 真來源、原 reply/mention refs、
source revision/order、thread/target 及已有普通接納關係。需覆蓋雙 Bot、同名不同
Person、A→B 合併／帳號換人、topic、原生無人名提及、quiet 和原發送回條。
不得要求插件自行查主庫、推斷 generation 或重建核心身份規則。

原 `JevObserver` 固定發送 `{model,state,questions}`，按 `model/answers/usage`
驗證回應。候選 Profile 實測拒絕 `protocol="jev"`，列出的六種協定是 chat、
openai_responses、deepseek_responses_legacy、deepseek_responses、
anthropic_messages、gemini。名為 jev 的文字 route 尚未證明等於原 Jev wire。
請給出相容的公開 route／輸入形狀與原始回應讀取方式，保持原問題／修訂／usage，
沿 K05 一次邏輯預留、分列實際 attempt，未知不得新購重試。擴展保留原庫，
不將其換成另一套文字分類器。

## CORE-050 → EXT-030：已讀原音訊但選定媒體模型派發遭拒

固定 `952954d86166`、SDK alpha.6，Windows Host binary
`cba774439b078e5b6879f93271f2bbb08d06e2601c1e8d81a05f64dc15e5006e`。
實收 `media.open` 的 `audio/wav`、3244 bytes 及版本
`9a1215ca91037cc6916a991befd4a8205175b62e41fa591d1818935a86394e62`。
同一真 `media.process` handle，路由 asr、purpose transcript、origins call、
明選 group entry、Chat Profile、明設原 execution root，純文字 `llm.complete`
成功並實收 HTTP 一次；加 `selected_media=true` 後為 -32003、零音訊 HTTP。
原始回條在 `artifacts/EXT-030/source-intake-01/`。這只定位拒絕條件，不先判定核心缺功能。

請交付可直接使用的音訊 route／Profile 配置範例及其公開 capability 欄位、
可讀 handle 到 `selected_media` 的授權條件、成功／跨 source 拒絕案例。
若可透過已有方法達成，請指出具體路徑。另需確認同一 source／Profile 經新
media call 或雙 Bot 重投時如何取得原 request，及原 Main 首輪／history 的
有來源 transcript 入口。未知仍不得新購，K05 邏輯預留與逐 attempt 帳本不變。
EXT-025 原 Jev wire 的需求仍見上一節，不能用 Chat 文字 route 充當 Jev。

## CORE-038／CORE-050 → EXT-032 的保留與原 Social 子效果

公開候選已列 media.open/publish/process 和輔助模型方法。請明確給出收藏授權、
原事件到期後的保留／再次讀取及 forget 範圍；collection owner 需要可驗的原
來源關聯，不自行推導 Person/ACL。也需指明原 Social 意圖／文字已送回條的
回呼、穩定圖片子鍵、取消／撤權與 Work 正常結束的區分及補圖回聲排除。
要求純圖、文字成功後崩潰、圖片已發布未確認、原圖改動與來源清除案例。
目前沒有這組具體交接，未建立空 sticker 插件或自造平行送訊協議。

## CORE-035 → EXT-036／033／035：真維護消費與尚缺投影

固定乾淨來源 `0cdd9dffe07c`、SDK alpha.8，三平台交付成員均核。
EXT-036 的真 Rust binary 經 Windows Host 讀取 `maintenance.audit`、批准子集
`maintenance.audit.apply` 及 `maintenance.reembed`；回條在
`artifacts/EXT-036/candidate-06/`。已核原 scope、Person/entry、write_subject，
兩個同維不同模型分別購買，原 unknown 重啟保持三次 HTTP，清除後新補向量被拒。

1. `maintenance.audit` 目前只有 fact/revision/status/evidence_total/evidence_retained/
   vector_profiles、embedding_routes 與 fingerprint。需要原 SQL 品質檢查的具名
   issue code、count、bounded fact IDs、FTS 缺失／孤兒、向量缺失／尺寸或原文版本不符、
   來源／工具回執完整性及 pending/unknown 覆蓋。scope 內讀取、無付費；apply 只作用於
   同一 plan fingerprint 的明選子集，變更來源或衍生索引時拒舊計畫。請附真故障前後回條。
2. audit/reembed 後擦除原 event 沒有 `forget.request` 或 pending obligation。
   候選只存 opaque fact/profile/operation 與計數；請明定這些 metadata 的保留責任，
   或提供 source dependency／自動 owner 登記，才能只清相應本地回條而不刪無關工作。
   不用手動 acquire 冒充產品自動責任；目前 forget ACK 未驗收。
3. EXT-033 原稀疏精確選簇需要授權內原語義向量、Profile／版本與維度、穩定 fact order，
   及 canonical ownership/visibility 分區。現有 profile ID 列表不能還原向量或 tie。
   請提供 bounded 讀取／精確鄰接投影或生產者選簇輸入，含跨分區拒絕與同分排序例。
4. EXT-035 需要原 SELF 寫入分區與本批工具來源映射的配置例，以及前臺有真人工作時的
   公開退讓／恢復信號。不能以任意 scope 名或全庫掃描代替原分區與新事件水位。

以上請求不改核心授權規則；EXT-034 的 extraction preview/apply 將先獨立對拍。

## CORE-035 → EXT-034：公開 extraction route 安裝設定

`artifacts/EXT-034/source-intake-02/` 用鎖定的 Rust alpha.8 診斷 consumer，
在 HJW Windows 重現同一 Person／entry／scope 的兩個 `history.page` 成功；
原返回版本與 primary/context 送到 `model.open` 和 `extract.preview`，兩者
均 `-32003`，HTTP 次數為零。`maintenance-policy.toml` 保存完整 fixture 設定，
`wire.jsonl` 是原始訊框；未讀核心私有模組或資料庫。這是授權路徑診斷，不是重建驗收。

請提供能用原包重現的最小公開安裝設定：所需 grant、scope methods／purposes／
routes、aux route 的 origins／entry／Profile，以及原 event version 是否還需額外交接。
已安裝 history/model.open/extract.preview/extract.apply、llm.complete/result 與
forget.owner；scope 原 Person 與 entry 可成功讀取來源，write_subject 固定同一 Person。
請附與同一源事件的 extraction format/text_json 正常回條，以及 foreign scope／
撤權拒絕。不要以廣開全部權限或換一套 extraction 協議消解這個缺口。

完整 EXT-034 job journal／審閱實作仍在 `codex/ext-034-rebuild` 工作樹未提交。
subset apply、核心已寫後 kill、原已付重用與 forget 尚未跑到，沒有完成主張。

## CORE-034 → EXT-023／024：feed 修正已實收，尚缺完整消費交接

`f74ecdd86b73` 的三平台候選已逐成員核驗；SDK alpha.5 的來源與已釘 crate
相同，僅封裝內 VCS commit 改變。原 `f26e88f7` Rust binary 對拍成功，原 feed 0
的 call 0／1 分別實收兩筆同參數 send。完整插件 `23f888dc639f` 在 HJW Windows／Arch
又驗回執前 kill、確認後雙重啟、unknown 已配對後重啟不復活、缺 runtime 零效果、
畸形訊框清除。`artifacts/EXT-023/candidate-03/`、`EXT-024/candidate-03/` 是實收回條。

1. `tool.catalog` 目前只有 name／description，唯一 script_name 位於 `tool.schema`。
   請在公開凍結投影提供 bounded `{name, script_name|null, revision}` 或指出既有輕量
   入口，讓 VM 只取得可用 alias 而不預讀所有 schema。別名及 script 排除仍由 Host
   決定，插件不自行加 `yuki_` 前綴。附相同 revision 分頁、script 排除及改版拒絕案例。
2. `tool.invoke`／`tool.resume` 的 pending/unknown 需要公開原 run 等待／回讀規則：
   穩定 child operation、原 Work/run ID、何時可餵與何時僅等待、恢復入口、取消與
   已配對 partial/code_stop 的終止區分。現在非 can_feed 的回應只安全返回 partial；
   沒有假定它可重新派發，也沒有將 future 改成第二套本地 run。
3. 請提供可由已打包 Host 公開安裝／operator 入口重現的 H14 控決定與根額度見證：
   未配對段額耗盡如何續原快照、已配對 partial/code_stop 如何不再復活、
   同一 root 的原預留／剩餘額度與逐 attempt 狀態怎樣有界讀取。消費者已保留
   三次原模型 HTTP、同一 execution 與 native 累積計數，但不讀主庫湊完整預算帳。
   需要 direct／Code 相同越權項目和普通拒絕後獨立合法項目的配置及回條。

原 native restore 本身增加 suspension。回條的正常計數 2、恢復計數 3 保留原值；
不把未知當重試權，也不將恢復視作補充根額度。所有結果仍為未發布候選消費，
完整 EXT-024／穩定接口與正式發版尚未驗收。

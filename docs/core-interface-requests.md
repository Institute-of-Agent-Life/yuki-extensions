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

## CORE-015／034 → EXT-024：direct 已續跑，普通拒絕的 nested 回條仍缺

固定 CORE-015 `969fb62e34de6a52a5fbe31d798e6b5436d6e9a8`／Host schema 2，
三平台 ZIP／全成員與 manifest 已核；pin 在 `compat/core-015-isolation`。
Windows ZIP `3b45be537020e1aa094afbd1c2e9f0ed81dda90defdf6b1518aa0cf61aa08dca`，
Host `9cd0c5ac8c8acbbd8e703acc832878f5efd31a16c1cea395c3c90f147e31f387`。

HJW Windows／Arch 真原 Rust Monty consumer：direct 同一 paid response 的
`send({text:42})` 有 failed／invalid_tool_arguments／executed=false／dispatched=false
原回條，後續合法 send 實收一次。相同 Code 呼叫的 `tool.invoke` 卻回泛稱 -32003，
沒有取得可餵入的原 child receipt，後項未執行。正對照先合法 send，取得真實送達、
原 receipt 與 ACK；再送同一無效參數才收到同一 -32003，首筆效果不回滾。
三例 9 筆模型 HTTP，六次冷啟不重送，測後容器集合回原集合。
原 wire／配對及原 manifest 見 EXT-024 `refusal-01`、`control-01`、`analysis-01`。
這是已核診斷；不是越權等價、費用或完整 EXT-024 驗收。

請依既有 `tool.invoke`／`tool.resume` 合同提供普通參數拒絕的最小公開配置或修正：
穩定 child operation／parent／ordinal、原 feed_index／engine_call_id、checkpoint、
失敗 receipt 與 `can_feed` 的含義，以及何時 ACK 後可合法續下一項。
若此 -32003 按設計屬於整體撤權或安裝策略拒絕，請交可重現的分類／原 operation
回讀與正反例，讓消費者區分應停止與可餵普通拒絕；不從文字猜測 admission，
不由插件製造 child receipt。另需核 bad 項零派發、同 root 不加預留、下一合法項
獨立授權、拒絕後 kill／恢復不重做首筆；未知項仍無新增重試權。

## CORE-058 / EXT-027 原管理員 target grant intake

`cb02f74ea48b`／alpha.10：Windows 最小 Rust consumer 三次原 Host call 都取得
`tool.status.state=dispatched`，其 canonical Person 已由公開 operator 設 admin。
前景、接納原 Work 後、略去 conversation／bot 的原入口三例，grant_target 皆 -32003。
具體原 handle、mutation key、target、Person／entry、模型與安裝配置見
`artifacts/EXT-027/source-intake-01/`。尚無 notification.publish 或送達；不先判定核心 bug。

請交可直接套用的公開最小安裝設定和操作序列：notification policy（若須額外欄位）、
原管理員作用域、QQ receiving bot／Conversation 的公開建立方式，以及原 handle 如何
符合授權。請含成功、非管理員／換 Person／換 topic／撤權拒絕，並示範原 source 不借
最近管理員的背景 publication。若要新 candidate，請附來源、版本與三平台 digest。
同時提供 CORE-051 `plugins.sessions` 的完整可解析最小 policy（routes、context
profiles、background permission）及 aux session route 設定，供 EXT-047 隔離遊戲使用。
擴展不讀主庫、不借 fixture 私有寫入建立 grant，也不猜測替代身份規則。

## CORE-051 → EXT-047：隔離 session 的可用安裝設定

固定 `9db8b3f073e3`／SDK alpha.9；Windows `source-intake-01` 是真 Rust consumer，
`session.create` 前景原 handle、原已接納 Work handle、actorless 三例皆 -32003。
目前設定只有已公開的 method grants，沒有文件未交付的 `plugins.sessions` policy／aux route。
三個 `tool.status` 都是 dispatched，session.run 為零；這是配置缺口診斷，不是核心缺陷認定。

請提供可直接解析的最小 TOML 與原公開 operator 序列：sessions 的 routes／context profiles／
background permission 欄位，session origin 的 auxiliary route、Profile、purpose，以及原 handle／
原 event 的授權條件；附無 policy 拒絕、有 policy 成功、換 Person／撤權拒絕案例。
遊戲需要 durable/context_profile=none、穩定 run key、原 epoch、重啟原已付 receipt、
unknown 不重買、Main／Memory 不入遊戲正文的公開驗收入口。

可重現入口 `ci/session_intake.py`，證據 `artifacts/EXT-047/source-intake-01/`。
原 GitHub Monitor 的 manifest／observe／register／commands／polling／config 已固定原版 hash，
遷移對照在 `docs/sdk-migration.md`；R11 的兩目標 grant 另受 CORE-058 回條阻塞。

## CORE-037 → EXT-037：真查詢已可用，私庫訂閱與清除仍需公開契約

固定來源 `1e7b89362b6f806aa11eed841b28071b22151e7e`、SDK alpha.11，三平台 ZIP
及成員已核，見 `compat/core-037/source.lock.json` 和 EXT-037 producer-intake。
Windows 真 Rust probe 與獨立 `yuki-trace` release 插件均使用原 Main tool.call
handle 呼叫 `control.read/trace.read`。kind／identity／after／limit／content 沿原
Admin DTO；metadata 與明選正文成功，普通人／撤權被 -32003 拒絕，擦除原 source
後讀回空頁。原 canary、逐方法 wire、模型 HTTP、build 和 Host/SDK/binary digest
見 `artifacts/EXT-037/source-intake-01` 與 `candidate-02`。這是未發布查詢候選，
不是完整 trace／R18／匯出驗收。

請在核心擁有的既有 observer/control/forget 合同中補齊以下可直接消費的路徑：

- **事件訂閱**：如何為已安裝插件明選 metadata／限時全文、bounded queue 與
  backpressure？現在 observer.event 只有 event／entry／kind；請提供原 trace row
  ID、source_event_id、turn/work/operation、generation、保留期限、drop/cursor 的
  已授權投影與最小 TOML／呼叫序列。沒有原 handle 時，背景收集的真授權由核心
  供給，不以插件自報 actor／superuser 或自造 handle 補足。
- **私料責任**：插件在私庫或暫存寫入前，如何公開取得並綁定原 SourceHold／
  dependency？需要來源集合、原讀取授權／generation、清除 watermark、重啟 pending
  和證明 ACK 的具體字段與先後順序。現有無私庫的 query consumer 擦除後沒有 callback
  或 pending；不據此判核心 bug，也不手動 operator acquire 冒充產品自動登記。
- **R18 與匯出**：請交付暫停 writer → forget → 原模型／工具確認 → 舊 writer 返回
  的真正反例，以及拒絕已撤權 reader、metadata 預設／全文另權、刪除後不可重放的
  versioned tool artifact 讀取方式。opaque／簽名／憑證／臨時媒體 URL 不得出現在匯出。

本插件目前只保留單次 RPC 的記憶體結果，沒有私庫、排隊 writer 或 cache；因此沒有
聲稱清除私庫、背壓丟樣、全文留存或匯出已完成。原核心效果及用量仍由核心原回條判定。

## CORE-037／038 → EXT-038：共用角色可用，頭像與逐平台套用待交接

同一 CORE-037 `1e7b89362b6f`／SDK alpha.11 已供獨立 Rust `character` 使用。
已實收 public/get/identity、SOUL read/save/reload、原 revision／UUID 和當前人物
權限；原共享身份、SOUL 和操作回條仍由核心擁有。原字串／空值不在插件內重解碼。
本卡沒有把全域 display_name 更新當作 QQ／Telegram 平台改名成功。

目前公開 control README 及固定 Admin DTO 列角色 presentation／SOUL，沒有可消費的
頭像變更或逐平台套用方法。請交接核心擁有的下列完整路徑，不需第二套角色／權限：

1. 原圖沿 CORE-038 授權 handle／immutable version 發布的精確方法、purpose、MIME、
   hash／大小、來源依賴與保留責任。要能把管理員選定的原圖變成公開角色資產；不能把
   私人附件 scope 或臨時 URL 永久當頭像，也不能靠本地路徑繞過授權。
2. control 的頭像 apply/read DTO：原 role ID、asset/version、expected avatar revision、
   原 request_id、當前 Actor/installation authority，以及儲存版本／生效版本的回讀。
   請提供普通人讀公開圖、普通人／撤權寫入拒絕、同 UUID 不同圖拒絕案例。
3. Gateway 的 nickname/avatar 能力與動作：原 namespace、receiving Bot／stage、原
   操作鍵、原圖版本、逐平台 confirmed／unsupported／unknown 與原 receipt。兩平台
   一成功一不支援必須有真對端回條；unknown 不得自動換 key 重送，共用原圖不得被覆蓋。
4. SOUL 保存／顯式 reload 的原操作回讀方式。泛稱 Host -32003 沒有 admission／
   operation 引用時，插件不推斷它是已接納的 failed receipt；請給出公開區分和讀回範例。

角色候選無自己的角色庫或頭像快取；原資產／平台 receipt 的歷史資料仍列現場待核，
不能據新安裝的空私庫推論舊實例沒有資料。完整頭像、逐平台故障與導入仍待本卡續做。

# EXT-015：明選入口及原 UUID

候選來源固定為 CORE-033 `c616cf35e4424e2b9f3c99a4481bfab1c99a34f3`，
不是 PR head，也不是正式發布。三平台包與全部成員先由
`artifacts/EXT-015/client-producer-intake/inspection.json` 核驗。
所有執行在 HJW Windows，Rust Client 及真 Host 經正式 HTTP/stdio。

正常時序：同一 Person 的兩個 chat 設備配對到同一原 App，第二設備以原
UUID 和正規化相同本文重放，只取得第一筆事件。A/B 合併後，A 的默認入口
保留原 request Person；明選 B 才讀 B 的歷史／回執。同 UUID 在兩個原入口
互不碰撞，ACP 則保留原 conversation 作用域。上傳原 bytes、長度與雜湊後，
原有序附件參與訊息提交；插件不正規化、不另建去重帳本。

故障時序：碼重用不能再取 secret；合併前跨人明選、錯誤 conversation、
不匹配雙標頭、重複權限標頭、改本文／附件順序、撤設備必須拒絕且不回退。
停用入口的讀取與新增寫入分開核。冷啟仍讀原回執，插件不保存身份或 secret。
未公開的 ACP 建立或停用方法，先索取公開操作序列，不直接建立資料庫資料。

SSE 正常時序：先收到真 Host sync，再送本文，以已提交入站的持久 cursor
找 GET events。選用 `YUKI_CLIENT_SOCIAL_PROBE=1` 時，fixture 先接納 Work、
再以原 send 要求本地 Social，嚴格要求原出站事件及其游標；不滿足即失敗。
重連 SSE id 不作帳本 cursor。故障：不讀／丟棄提示後，以原 events cursor
恢復；撤設備舊流結束。四條 SSE 與八個一般請求分開限額，滿額有界拒絕；
不得以另一條 SSE 的初始 sync 冒充已提交出站。H27 最後一次廣播溢出與
H28 開檔後撤權只在取得真故障注入／執行回條時記驗收。

重現：在此 checkout 執行 `YUKI_HOST_CANDIDATE=<已核 Windows ZIP>`，
由 `ci/windows.py EXT-015 --preparation --run <新名稱>` 傳至 HJW；輸出為
具名 `personal-entries.json`、`original-uuid-entry.json`、HTTP／SSE transcript、
模型請求、原 stdio wire 與 manifest。沒有付費供應者、私庫或假 Host。

## 本輪回條與界線

`selected-08`：Windows 九組功能案例、兩項 Rust 回歸、release build、14 單位
邊界／選擇器通過，35 個來源綁定在 `source-bindings.json`。
四條流滿額後一般 GET 仍成功；撤設備原四條流結束；停用入口保持設備及舊
回執可讀，新增寫入拒絕。啟用／停用用公開 DTO 的原 expected_revision。

`selected-04` 與 08 的 ACP 診斷：公開 account／entry／ingress 建立原
ACP conversation，home 列出其真 binding／conversation；同 token 明選仍
404。需要公開 ACP session／presence 的最小操作序列；沒有直接寫 DB。

`selected-06`：沒有 main.binding_endpoint。真 Main 接納 Work，send 後公開
main inspect 為 held／runner_failed，未取得原已配對 send 回條或出站事件。
先前 05 的 fixture binding ACK 並未提交本地 Social，不能作為正對照。
需要原 App 的公開安裝／路由設定或固定修正後，才重驗這段。
`selected-analysis-01` 在 Windows 重新核原 ZIP、manifest、全部來源、Host／
SDK／plugin／wire、九組案例及原 06 故障。整卡保持 BLOCKED。

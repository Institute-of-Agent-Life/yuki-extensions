# EXT-038 正常與故障時序

使用已核 CORE-037 `1e7b89362b6f`／SDK alpha.11，先實作共用角色與 SOUL。
核心固定 Admin DTO 與 control.read/write 擁有原人物、revision、操作回條和授權。
插件只傳原 tool.call handle；不讀主庫，不生成第二個角色 owner。

1. HJW Windows 真 Rust 插件接原 Main 呼叫。普通人讀公開角色成功、讀 SOUL／
   寫角色拒絕；管理員讀原角色／永久 ID／SOUL 成功。
2. 帶明選 request_id、expected_revision 改名；保留永久 ID。同 ID／body 重放
   取得原 revision；同 ID 改 body、舊 revision 新 ID 均拒絕，插件不替換 revision。
   原已付 Main 的下一請求保持先前 system 角色；下一次接納才用新角色。
3. 空 SOUL 合法。按原 revision 儲存，再讀 active_revision／實際正文。
   寫入一段唯一 SOUL marker，核同一原已付 continuation 與後續新接納的差異。
   保存與顯式 reload 各有自己的原 request_id／結果，不合併成泛稱成功。
   先讓 Main 凍結原提示詞、真插件產生 reload，再於透明 relay 暫停原訊框。
   只在新測試 owner 的已保存 SOUL.md 中注入非法 UTF-8，放行未改寫的原請求；
   等到 Host 真拒絕回應後，先恢復該 fixture 檔再放行未改寫的錯誤訊框，讓
   Main 正常配對。後續明選 reload 是另一個命令。泛稱 -32003 不當作已接納
   失敗 receipt，也不憑此測試宣稱原失敗 ID 的重放語義。
   candidate-02 在新 Main 激活前破壞檔案，未送到 reload；candidate-03 已收到
   原 RPC 拒絕，但太晚恢復檔案，當輪未發出下一模型 HTTP。兩個測試時點失敗
   均保留，不當作核心重載缺陷或完整故障驗收。
4. 原 Host 重啟後讀相同角色與 active SOUL。撤權後原人物的新呼叫／舊回條
   重放皆由核心再拒絕，不由插件本地記錄授權。
5. 頭像必須有受權 immutable asset/version 與平台 nickname/avatar action。
   現有固定 DTO 只列角色 presentation 與 SOUL；先向核心核實該橋的具體方法、
   接收 Bot／原圖及逐平台結果，不自行發明協議或以 unsupported 假裝兩平台驗收。

1–4 為共用角色候選；頭像／兩平台套用、原資料導入與正式發布未驗時，整卡保持
進行中，具名產物不得叫完整 character-application 驗收。

## Windows 查驗

`candidate-01` 真 release 插件通過 19 例。`candidate-04` 由正式
`ci/windows.py EXT-038 --preparation` 入口通過 21 例，實收模型 HTTP 42 筆。
同 UUID／body 原 revision、改 payload／舊 revision 拒絕、空 SOUL、正常 reload、
角色 identity、兩次 owner 啟動及撤權均有逐方法 wire。

壞 SOUL 的拒絕是在真插件已送出原 control.write 後，由透明 relay 暫停傳輸
精確安排；Host 的 -32003 原回應未改寫。原 fixture bytes 在交還錯誤給插件前恢復，
讓 Main 完成原工具配對；另一明選命令成功 reload。saved revision／原錯誤／後續
active revision 分開列在 `soul_operations`，沒有把 generic 錯誤判為已接納 receipt。
Source binding 核 26 個 runtime/build 檔，原 Windows manifest 保持原 bytes。
owner-disposition 只確認本次空私庫及核心共用 owner；舊頭像／平台資料仍待現場核對。

頭像／兩平台回條、原資料導入及正式發布未通過。`ci/check.py EXT-038`
不帶 preparation 明確拒絕整卡驗收，不能把這份 shared-role 候選算為正式完成。

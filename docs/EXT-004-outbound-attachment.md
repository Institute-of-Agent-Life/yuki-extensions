# Telegram 原 chat 的附件發送時序

Windows 上從原 Bot 收到私聊，Main 取得本次執行身分，以公開 operator 在該身分固定一件原檔；Main 明選同一 artifact 的 file 發送。原 gateway 計畫須保留 Host 的 artifact_id 與版本，派發時才用原 handle 分頁讀取，驗完整 SHA-256 後才交給原 Bot。保留原目的 chat/topic、原回條、平台定位及物理上傳次數。

錯誤路徑包括版本損壞、撤銷讀權、平台拒收與上傳後失聯。不得以 URL、其他 Bot、私庫、舊授權或自動重送補件。平台回應丟失時，重啟只回讀原操作。

附件第一段帶至多 1,024 個 Unicode 字元的說明，其餘依 4,096 字元分成文字段。各段沿用原 Bot、chat、topic 和自身的原生回條。第二段失聯即保留 unknown，後續段停止。限制與固定 v4 的分段方式一致。[Telegram Bot API](https://core.telegram.org/bots/api#senddocument)

讀取期間收到 `forget.request` 時，先清除暫存並終止讀取，再確認原 key／watermark。晚到的頁面回應只會排空。已啟動的上傳先關閉 curl 與傳輸管線，原效果保留 unknown。原始檔與 UTF-8 caption 經記憶體管線傳遞，密鑰由子程序環境讀取。清理入口在確認原義務前保持 Bot 連線關閉。附件上傳需要 curl 8.3 以上的變數展開功能。[curl 手冊](https://curl.se/docs/manpage.html#--variable)

本地重現使用 Python 3.12、Rust 1.96.0，以及 `compat/core-038-outbound/source.lock.json` 所釘同平台的簽署 Host ZIP。設定 `YUKI_HOST_CANDIDATE` 指向原包，執行 `python ci/telegram_outbound_check.py --out <新的輸出目錄>`。入口建置獨立 Telegram 包，驗原 Bot 媒體與刪除競態，再逐一執行二十二組真 Host 重放。具名回條為 `telegram-delivery.json`，候選清單記錄每個執行檔、SDK 與鎖檔雜湊。

Windows 若系統 curl 低於 8.3，可將已安裝的新版本絕對路徑放入 `YUKI_TELEGRAM_CURL`，並在 Host 的插件 `env` 清單列入此名稱。CI 會先驗所選 curl 版本，再將該執行檔明確交給插件。附件讀取另需 `media.open` 與 `forget.owner` 兩項授權。

依使用者指定，三端 CI 在本地執行。GitHub 的三個工作流改為手動啟動。完整候選驗收入口是 `python ci/check.py EXT-004 --out <新的輸出目錄>`，產出 `telegram-delivery.json` 和 `manifest.json`。三端本地候選驗收後，正式跨倉驗收仍待擴充合同發布。

三端本輪回條在 `artifacts/EXT-004/outbound-attachment-12/telegram-delivery.json`。打包清單逐件核對 ZIP 實含成員，AppleDouble 元資料不列為可分發產物；Desktop 呼叫表也已在三端重驗。

## 原事件引用時序

Main 明選 `reply_to_event_id`，Host 在同一 entry／原 receiving SELF 查回 `event_id` 和 `native_id`。純計畫僅第一段保留這組原定位，派發前再次比對原 chat 與首段 ordinal，將原 message ID 放入 `reply_parameters`。群話題沿原 `message_thread_id`。附件 caption 與後續文字只引用一次。

先驗群話題的附件引用和文字引用，再驗原訊息已不存在時的平台 400。後者保留 failed，冷啟只查原操作，不改成無引用發送。跨 Bot／chat、變更的定位、非首段引用在派發前拒絕。`allow_sending_without_reply` 固定為 false。[Telegram Bot API](https://core.telegram.org/bots/api#replyparameters)

原事件引用三端回條在 `artifacts/EXT-004/original-reply-13/telegram-delivery.json`，固定 Host 受測提交 `7965392bd7de`。

## 原發送事件撤回時序

Main 用公開 `query_chat_history` 取得自己已發消息的 event ID，呼叫 `recall_own_message`。Host 沿原確認的發送段解析 Bot、chat/topic 和 native ID。`gateway.recall` 需單獨授權，Telegram 使用 SDK alpha.16，鎖定來源與 crate／wheel 摘要在 `compat/core-025-recall/source.lock.json`。

插件在原 Bot 上呼叫 `deleteMessage`，原 chat 與正整數 message ID 必須一致。200 且 `ok=true/result=true` 確認撤回，具相符 error_code 的 4xx 記為 failed。斷線或格式不明的回應記為 unknown。第二個邏輯撤回讀同一物理回條，冷啟後可再讀回原操作。授權缺少時原生撤回次數為零。群話題案例也核對原公開事件、原段定位及零重送。[Telegram Bot API](https://core.telegram.org/bots/api#deletemessage)

原消息撤回三端回條在 `artifacts/EXT-004/original-recall-14/telegram-delivery.json`，固定 Host 受測提交 `120db2d663af`。每個平台只在原 chat 派出一次 native delete，第二個邏輯請求與冷啟均沿原回條。

## 原 chat 的 typing 生命周期

接收 Host 的 `gateway.activity` 通知，按 lease ID 保留原 Bot、chat、topic，5 秒未續約就到期。活動期間每 3 秒最多派一個原生 `sendChatAction`，turn 結束清除 lease。授權需明列 `gateway.activity`。本輪 SDK alpha.17 來源與原包摘要在 `compat/core-032-activity/source.lock.json`。

正常時序覆蓋私聊與群話題的啟動、續期和結束。故障時序覆蓋 403、格式錯誤、連線懸停、缺少授權、停用、遺失續期及清除來源。UI 請求使用獨立管線，2 秒後取消卡住的請求；發送回條仍依原生發送結果確認。`forget.request` 在原 key／watermark 的 ACK 前清除全部 lease 及 UI 管線。

Telegram 的 chat action 最長維持 5 秒。停止時結束本地續期，平台依原生期限清除顯示。[Telegram Bot API](https://core.telegram.org/bots/api#sendchataction)

三端完整候選回條在 `artifacts/EXT-004/original-activity-17/telegram-delivery.json`。每端 22 組由正常卡入口通過，封包逐成員及原來源雜湊已核。Host 為 #109 受測提交 `78394082d8ea`，Telegram alpha.9，SDK alpha.17。各方法的真消費案例列在回條的 `method_witnesses`，供核心擴充版本相容驗收使用。

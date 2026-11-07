# Telegram 原 chat 的附件發送時序

Windows 上從原 Bot 收到私聊，Main 取得本次執行身分，以公開 operator 在該身分固定一件原檔；Main 明選同一 artifact 的 file 發送。原 gateway 計畫須保留 Host 的 artifact_id 與版本，派發時才用原 handle 分頁讀取，驗完整 SHA-256 後才交給原 Bot。保留原目的 chat/topic、原回條、平台定位及物理上傳次數。

錯誤路徑包括版本損壞、撤銷讀權、平台拒收與上傳後失聯。不得以 URL、其他 Bot、私庫、舊授權或自動重送補件。平台回應丟失時，重啟只回讀原操作。

附件第一段帶至多 1,024 個 Unicode 字元的說明，其餘依 4,096 字元分成文字段。各段沿用原 Bot、chat、topic 和自身的原生回條。第二段失聯即保留 unknown，後續段停止。限制與固定 v4 的分段方式一致。[Telegram Bot API](https://core.telegram.org/bots/api#senddocument)

讀取期間收到 `forget.request` 時，先清除暫存並終止讀取，再確認原 key／watermark。晚到的頁面回應只會排空。已啟動的上傳先關閉 curl 與傳輸管線，原效果保留 unknown。原始檔與 UTF-8 caption 經記憶體管線傳遞，密鑰由子程序環境讀取。清理入口在確認原義務前保持 Bot 連線關閉。附件上傳需要 curl 8.3 以上的變數展開功能。[curl 手冊](https://curl.se/docs/manpage.html#--variable)

本地重現使用 Python 3.12、Rust 1.96.0，以及 `compat/core-038-outbound/source.lock.json` 所釘同平台的簽署 Host ZIP。設定 `YUKI_HOST_CANDIDATE` 指向原包，執行 `python ci/telegram_outbound_check.py --out <新的輸出目錄>`。入口建置獨立 Telegram 包，驗原 Bot 媒體與刪除競態，再逐一執行七組真 Host 重放。具名回條為 `telegram-delivery.json`，候選清單記錄每個執行檔、SDK 與鎖檔雜湊。

Windows 若系統 curl 低於 8.3，可將已安裝的新版本絕對路徑放入 `YUKI_TELEGRAM_CURL`，並在 Host 的插件 `env` 清單列入此名稱。CI 會先驗所選 curl 版本，再將該執行檔明確交給插件。附件讀取另需 `media.open` 與 `forget.owner` 兩項授權。

依使用者指定，三端 CI 在本地執行。GitHub 的兩個檢查工作流改為手動啟動。上述回條標記 EXT-004 的附件子項通過，整卡仍待原事件引用、撤回及 typing 生命周期驗收。

三端本輪回條在 `artifacts/EXT-004/outbound-attachment-12/telegram-delivery.json`。打包清單逐件核對 ZIP 實含成員，AppleDouble 元資料不列為可分發產物；Desktop 呼叫表也已在三端重驗。

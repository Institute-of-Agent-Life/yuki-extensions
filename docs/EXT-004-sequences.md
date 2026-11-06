
原 Bot 的普通文字投遞：真 Main 選 send，Host 對 gateway.plan_send 傳原 bot/chat/entry/topic 與 message.text。計畫階段不得存取 Bot API。用超過兩段的 Unicode 原文核對 4,096 字元邊界；收到 gateway.dispatch_part 才對原 chat/topic 做一次 sendMessage。成功時以原聊天與原 message_id 回執。第二段在原生端接受後斷線，必須回 unknown，冷啟不重送。錯 Bot、錯目的地、額外未支援的附件或引用先拒絕。出站文字、取回原件及 typing 分開驗證。

在 Windows 將 `YUKI_HOST_CANDIDATE` 設為固定 CORE-038 候選 ZIP，使用 Python 3.12 執行
`python tests/peers/telegram_text_delivery.py <repo> <獨立telegram套件目錄> <新回條目錄> --case <confirmed|lost-second|topic|quote>`。
前三例會冷啟另一個 Host／gateway 程序，等待真 Bot API 以已接納的 offset 52 接續輪詢，再核送達與模型請求數。
quote 案例使用真入站回執的 event ID；Host 只交此 ID 時停止在計畫階段。

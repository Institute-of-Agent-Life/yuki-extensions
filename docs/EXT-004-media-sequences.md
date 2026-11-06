# EXT-004: Telegram 收件附件

在已連線的原 Bot A 收到帶 photo 或文件的 update 時，只在本次 Host 協商 gateway.media 後隨 gateway.inbound 附上原 application。游標照舊等待 admission。Host 選定原 event/slot 後才用 A 的 getFile(file_id) 及相同 Bot 的下載端點；分塊回傳同一內容雜湊。即使 getUpdates 正在長輪詢，或上一筆入站正在等 receipt，callback 仍應得到回覆。

先觀察原生 HTTP 次數：首塊一次 getFile 和一次檔案 GET，後續頁不得重抓；另一 Bot、tenant、錯 namespace、跳頁或換來源都拒絕且不出網。檔案超限、截斷、HTTP 錯誤或不安全 file_path 不回成功頁，不追隨轉址。關閉 stdio 時取消使用中的長輪詢。半份內容只在有時限的記憶體中，不入庫、不落盤。

Windows 對照分清兩層：執行打包的 Rust binary 與受控平台/stdio 對端，可證平台取件及傳輸行為；真正 Host 對原 event/slot 的授權及中途撤權，需以公開安裝配置另驗。發送、撤回與 typing 也另計。

重現平台層：`python ci/check.py EXT-004 --preparation --out <new-directory>`。
重現 Host 安裝層：將 `YUKI_HOST_CANDIDATE` 指向與 `compat/core-038-main` 相符的官方候選 ZIP，
以新目錄執行 `python tests/peers/telegram_media_host.py <repo> <new-output> <packaged-binary> <binary-sha256>`。
舊 host-01 在預設 hybrid 設定缺 embedding 時停止；host-02 明選原 lexical-only 模式，
沒有配置付費模型。兩組回條各自保留原始狀態。

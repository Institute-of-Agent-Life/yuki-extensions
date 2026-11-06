# EXT-005 富文字與原生貼紙

基線 `329ca7c` 的 `src/yuki/gateway/providers/feishu_ingress.py` 定義富文字的
標題、列界、連結、原生提及、表情與媒體順序，也明列貼紙不支援 Bot 資源下載。

在 HJW 取上一版 Windows 實際套件與釘住的 CORE-038 Host。飛書傳未包
語言的 post，Lark 傳包在 zh_cn 下的同一內容，再測兩個域各一張帶 file_key 的
原生貼紙。先核舊版丟失的內容和錯誤的媒體類型，再比對修正版的每個 segment。
同鍵重投必須回讀原事件；writer 前斷線沒有平台成功 ACK；錯租戶遭拒。
貼紙交出原文字標記，不得產生可供 gateway.media 選取的附件。這裡驗的是
入站清單，沒有請求網頁、下載貼紙或呼叫模型。

沿用 EXT-005 文字案例的 Host ZIP 和兩個 fixture wheel。以同一份已核套件
在不同輸出目錄執行 `tests/cases/EXT-005.py::prepare`，使用
`contract="core-038-main"` 和
`message_sample=lambda app: sample(kind, app)`。從
`tests/peers/feishu_rich_message.py` 匯入 `sample`，kind 分別取 `post` 與 `sticker`。

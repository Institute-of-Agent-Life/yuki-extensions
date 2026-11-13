# 飛書原帳號提及重放

Host 從同應用的原 account 與原名稱觀測供應文字及提及頁。插件先驗完整 SHA-256、UTF-8 byte 範圍與原帳號欄位，再依原 OpenID 產生 native at 標記。分段以原文字為索引，保留整個提及，原引用仍只放在首個可見段。長文字與附件附言共用這條路徑。

真 Host 重放包含長名稱、明確 account token、兩個域、群話題、私聊、XML 字元與多段附言。真 Host 另驗派發失回應與拒收後停止後續段。實際插件的分頁重放涵蓋錯頁、錯摘要、重疊或越界範圍、來源遺忘、晚到頁及換應用。核心的同名選取、來源擦除與原階段撤銷證據隨 #117 三端候選交付。未知名稱保留原文字，插件不把顯示名稱推測成 OpenID。每一個物理請求保留原 Host 回執，冷啟查回原結果。

SDK alpha.21 的候選先供本地開發對拍。正式驗收使用核心三端來源固定的包，並沿用本卡 owner-disposition。

正常入口執行 `python ci/check.py EXT-006 --out <獨立產物目錄>`，輸出 owner、30 個文字／撤回、32 個上傳及 22 個提及情境。開發候選完成後，入口會列出待公開合同驗收的項目。獨立重放提及可用 `python ci/feishu_delivery_check.py --mentions --out <獨立產物目錄>`。`YUKI_HOST_CANDIDATE` 選取對應平台的固定 Host ZIP，crate、wheel 與編譯快取沿既有本地 CI 設定。

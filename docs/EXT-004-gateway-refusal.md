# EXT-004 安裝只有入站權時的拒絕回讀

在固定的 PR #97 簽署 Host 安裝已驗 ZIP 的 Telegram alpha.4 與 web-fetch alpha.2。原 chat 進入 Main，再用原 handle 擷取頁面、分頁讀回原件，然後要求向原 chat 發送。Telegram 的安裝只授 gateway.inbound。核原 Main 的 failed operation 與 gateway_send_not_granted，計畫、逐片派發和 Bot HTTP 發送均須為零。殺掉兩個真插件、關閉宿主，冷啟後用原 operation、namespace 及 Person 回讀，重投原更新也不補送。

`tests/peers/joint_base.py ROOT PACKAGES HOST_ZIP OUTPUT --case denied-send`。PACKAGES 含獨立的 telegram/、web-fetch/ 發行目錄。版本、SDK 與 schema 取自兩個鎖檔。消費者沿用原 SDK，與新包的 Rust 來源逐成員比對，只允許已核實的 VCS 元資料差異。

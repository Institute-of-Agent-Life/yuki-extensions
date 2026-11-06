# EXT-031：原處理器回條送回同一 Main

固定 Host source `0ef956a9c6d90fae79c0d4488296c064ccf29f54`、SDK alpha.13、
三平台 ZIP／全部成員已核，見 `compat/core-038-main` 與 main-producer-intake。
消費者保持原 candidate-03 的 Rust binary `2d0e7e9b910789bf34b8d263475c71a720a2ee650628fc88a3292a64e26d454c`、
SDK alpha.4、document_reader.py 和 FFmpeg，不重編／升版／改寫後端。

正常：核舊 source.zip／package／codec 來源後，在 HJW 以本倉透明 stdio relay
啟動真 Host 和原 binary。原 QQ 入站有兩個附件，slot 0 為 UNSELECTED；Main
明選 event/slot 1。PDF 頁文必須出現在同一正常 Main 的下一筆模型 HTTP；影片
必須有原 0、5 秒兩幀，按原順序出現在該 Main 的原續輪。選讀／續輪兩筆模型
HTTP、一次 media.process，另有一筆 capability 查詢供公開 cache-file fixture
取得原 execution；沒有另購 vision 輪。逐方法 transcript 核原 handle／operation／
revision、來源版本、publish artifact 與實際 HTTP bytes。

故障：未選擇不解碼，沒有原生 vision 時影片不解碼；原來源在第二塊讀取後
forget，不得把本文／影格放入之後的模型請求，原 forget 回調需完成。沒有新
合格回條的故障不採計。兩平台 producer 的測試數不代替本倉消費證據。

核心已提供以同一原 binary 執行的兩份 Windows Main request；先核原 binary、
輸入與實際 request，再以本倉 peer 補完整 wire。舊 producer transport 指向的
ZIP 若已不在，不宣稱重新核過該 ZIP；現存 proof 的 bytes／雜湊另外記錄。
全卡的公開發版、原 gateway 入站和平台端互動依各自實證，沒有因此計為正式完成。

## 已核的原生回條

- `main-consumer-05/pdf`：原頁文、原 version、原 operation 在同一 Main 續輪逐字段相同。
- `video-consumer-06/video`：原 0/5 秒影格、publish 的 immutable id/version，與模型
  HTTP 實收兩張 data URL bytes 逐一對上。Main 的 images 是 id/ordinal/ready 投影，
  SDK 回條保 id/version；不宣稱兩種 DTO 完全相同。
- `faults-07`：已授權原件但未選擇零處理；無 vision 影片零處理；壞 PDF 一次處理、
  結構化失敗。其後 Main forget 於第二塊延遲時返回 SQLite 787 FOREIGN KEY constraint
  failed，沒有成功清除回執。此段 BLOCKED，沒有重送或直接修 DB。
- `audit-09`：Windows 核原 ZIP/manifest、原 runtime/SDK、逐方法配對、實收頁文／
  像素、五個具名正反例及原 FK 錯誤；全部 14 邊界和 media 選擇器通過。

01 只因 README 與舊 source snapshot 文檔不同而停止，runtime/build bindings 相同。
02 沒有授權原 byte source，被核心先拒絕。03/04/05 的 PDF 已過，影片被 fixture
標為 file/octet-stream 而不解碼；不是 PDF observer 或核心 decoder 修復。06 改用
原生 video 類型後成功。08 的 audit 誤把 SDK immutable refs 與 Main ready 投影當成
相同 DTO；09 保留兩份原資料，核 id、version、ordinal 與實際影像 bytes，不改回條。

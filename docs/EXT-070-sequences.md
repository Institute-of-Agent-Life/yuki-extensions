# EXT-070 原 Connector 改址與原 journal

輸入固定在 `compat/wire4/address_cases/source.lock.json`：原 commit
329ca7c、CI 41554925880／artifact 13194877063、11 份原回條及對應 JUnit。
舊產物只作歷史對照。新測試使用安裝後的原 Connector wheel、原 Journal、原
LocalTerminal；只以臨時 WSS wire4 對端控制輸入，不替換核心 Host 或宣稱 Work 授權。

## 正常時序

1. 在隔離安裝寫既有 token／device／instance／service marker；執行原 CLI `server`。
   僅 URL 改寫，原 secret、instance 與服務登記不變，未建立 journal 或連線。
2. 對原 receipt v0/v1 與 `[url,device]` namespace 副本啟動原 CLI；TLS hello 前已升級
   為原 device namespace，原操作、unknown／未 ACK 事件不變，重新開啟仍一致。
3. 原 CLI 連線 WSS A，啟動真 pipe shell；用原 CLI 保存 WSS B，不中斷當前 socket
   或 shell。原 run 收 stdin 並以 exit=0 結束，原 request/run 與一次實體啟動保留。
4. 停止本次測試的前景 Connector 後以同一 device 重啟到 WSS B；查原 operation，
   只補 A 未確認的原 event ID。B 的 fixture 先持久記錄後 ACK；已 ACK 事件不補送。

## 故障時序

- 三種非 TLS 遠端／錯 scheme 由原 CLI 拒絕，設定原 bytes 保留，不連真端點。
- 同一資料目錄配置另一 device，原 CLI 在出站前拒絕，原 namespace／操作／事件保留。
- 原協議不相容的 1008 不被當作可重派；撤權停止此測試的 owner，不轉成成功。
- 離線 unknown 原樣回讀，不以重連、ACK 或改址升格 succeeded，不再跑原 prompt。
- Windows 另在唯一隔離目錄用原 UserService 註冊 LeastPrivilege／InteractiveToken
  測試任務，立即禁用且不啟動。改址前後核實原 Task XML、實際 action、非 running
  及原 device／token，finally 只刪已核對 action 的本次任務，確認原本不存在／清除後不存在。
  不動任何既有服務，不探 native daemon，不呼叫模型或付費供應者。

新 Windows 回條須逐份對上 11 份舊資料的語義與新 wire／PID／receipt，保留失敗。
EXT-011 未發布與公開服務部署另判；本卡不把 wire fixture 當核心業務權限見證。

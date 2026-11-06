# EXT-011：原 Connector 憑據與 wire4 catalog

消費 CORE-033 `c85a00b121d0`／SDK alpha.12 未發布候選，固定包見
`compat/core-033-connector`。原 Python Connector 與 native driver 不改寫。
Rust 插件只持裝置／instance catalog；Person、憑據、grant、generation、連線 epoch
及 journal namespace 均取核心原權威，不從 hello 自報欄位決定。

## 正常時序

1. `/agents/v1/pair` 沿原一次性碼回原裝置憑據；本機只存 device ID。
2. `/agents/v1/connect` 在 WebSocket 升級前將原 Bearer 交核心私有 exchange，
   purpose=connector、明選本安裝且省略 Work；安裝 ID 由
   `YUKI_LOCAL_AGENT_INSTALLATION` 指定，不能拿 SDK namespace 代替。
   短效 proof 只經公開 `device.connect`。
3. 原核心 handle／device ID／namespace／epoch 綁本連線，不落 raw secret。
   接受 hello／catalog 前逐次 `device.check`，核當前本地 epoch fence。
4. 原 wire4 hello 的 protocol=4、device ID 必須與原權威一致；完整 catalog 原子取代
   該裝置 instances，空 instances 仍保留裝置。能力欄位只作 native 目錄資料。
5. 斷線只標記該 epoch 離線，保留原裝置和 journal namespace；重新連線取得新
   核心 epoch。舊連線的 catalog／close 不得改新連線。Work/native 回流沿原 Work
   授權，沒有獲准的效果不 ACK、不刪 Connector 原 journal。
6. handle 固定候選有效 300 秒；240 秒後下一個訊框先複核再關閉，原 Connector
   預設 20 秒 WebSocket ping 會在到期前觸發。原憑據重連後才取新 epoch，
   舊 socket 不在背景換 proof 而搶回新連線。完全靜默的 socket 到下一訊框才處理。

## 故障與驗收

- chat token、無憑據、重複 Authorization、錯／過期 proof 不建立 catalog。
- 偽造 hello device ID 或非 wire4 拒絕；不生成新 Person、entry、Work 或模型請求。
- A→B 合併及帳號換人保留原 device／namespace；撤設備／停用人物後，下一個
  catalog／native 回調先被原 device.check 拒絕，不能發布新狀態。
- 接受新 epoch 後釋放舊 catalog／close，舊資料及離線回報不能覆蓋新 snapshot。
- 先用 schema1 catalog 副本升級，保留原 membership；未知 schema 拒絕，不重設水位。
- HJW Windows 跑真 Host、真 Rust 插件與鎖定的 Python Connector；證據只保留
  proof／handle／Bearer 的不可逆 digest，不寫秘密到 ordinary wire／回條。
- 原 Python TLS 預設以隔離 CA 驗證 loopback WSS，記錄實收 TLS version、
  CERT_REQUIRED／hostname check；透明 TLS 入口不改寫 wire，沒有關閉憑證驗證。

原 Connector 的 SQLite journal 沿原 CLI 的 device ID namespace；核心另給本安裝的
授權 namespace。兩者分欄保存，不拿核心 namespace 重設原 Connector journal。

先核原公開方法、正常／故障 wire 與實收 catalog，三平台 CI／正式發布另判。
本卡不以 device grant 冒充 Work/input/native 效果授權，也不把候選當穩定交付。

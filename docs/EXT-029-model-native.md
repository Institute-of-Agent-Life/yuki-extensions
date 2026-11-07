# EXT-029 模型原生搜尋

本倉依維護者的範圍變更採用核心的模型原生 `web_search`。v3.2 原卡的選裝 Tavily 後端已退出本倉交付範圍。CORE-024 擁有搜尋、授權、快取及原根工作帳本。擴展倉提供可選部署配置與真 Host 回歸。

部署者可將 [原生搜尋配置](../deploy/search/model-native.example.toml) 的兩個區段合入指定 owner 的 `yuki.toml`。已有同名區段時更新原區段。填入支援原生網頁搜尋的 Responses 端點和模型 ID，在宿主進程環境中設定 `YUKI_NATIVE_SEARCH_KEY`。這條路徑使用獨立的搜尋連線；Main 仍使用自己的配置。

## 正常及故障時序

1. Main 明調一次 `web_search`。Rust Host 在獨立模型連線送一次含 `web_search` 的請求，Main 從原工具回條取得供應者回傳的來源。原聊天私文不進搜尋請求。
2. 模型只返回普通文字與 URL 時，讀回空來源。HTTP 429 時，核對公開結果、原根用量和實際請求數。
3. 端點收件後斷線。冷啟 Host，以同一根、actor 和 operation 讀回原 unknown，核對沒有第二次模型搜尋。全程核對已安裝插件與 Main 工具目錄，沒有 Tavily 憑據或後備外掛。

以 Python 3.12 執行 `python ci/check.py EXT-029 --out artifacts/EXT-029/local`，環境變數 `YUKI_STABLE_BASE_ZIP` 指向本平台公開 B0 原包。驗收只使用本機回環模型端點，沒有外部搜尋費用。

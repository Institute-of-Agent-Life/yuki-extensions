# EXT-004 / EXT-006 原收件取件

固定 CORE-038 source `0ef956a9c6d9`、Windows Host 與三個已建置 Rust 執行檔。從公開 `doctor` 解析安裝設定。`[plugins.gateway_media]` 的 `application` 指原 Bot 或 app，飛書與 Lark 同時指定 `tenant`。

正常順序為原平台訊息、gateway.inbound 回條、Main 明選原 event/slot、Host 呼叫同一安裝的 gateway.media、原生 GET、分塊長度與 SHA 複核、原處理器結果。平台及模型皆使用回環測試端點。三次執行使用獨立 owner；飛書和 Lark 使用同名原生資源鍵及不同檔案雜湊。

故障邊界沿用原入站授權、跨身分拒絕、讀取中斷與分塊錯誤回條。新案例要核每個 callback 的安裝、來源、offset、實收位元組及實際原生 GET 次數。只登記實際到達的步驟，保留第一個失敗的原始對話。禁止以 cache-file 注入代替平台取件。

HJW 重現時設定 `YUKI_HOST_CANDIDATE` 為鎖定的 Windows ZIP，`UV_FIND_LINKS` 為含 `tests/peers/lark-fixture.lock.json` 所列 wheel 的目錄。以 Python 3.12 執行：

```text
python tests/peers/gateway_selected_native.py <telegram|feishu|lark> <checkout> <EXT-031-candidate-03-source-bundle> <原平台exe> <新目錄>
```

另以新目錄附上 `--wrong-slot`：原訊息只有 slot 0，選 slot 1 時應得到原 failed receipt，三端的 gateway callback、取件 HTTP 及處理器呼叫均為零。來源包根目錄內是 `src/artifacts/EXT-031/candidate-03/packages` 與 `work/codecs`，保留其相對位置。附件是兩頁 PDF，同名測試檔依區域填充不同內容。最終模型請求須讀得第二頁，逐塊重新組合的 gateway 與 processor 位元組及版本 SHA 均相符。全程使用隔離 owner 與 loopback。

# 飛書與 Lark 的原 owner 證據

先驗空私有目錄與固定 v4 的合成資料。舊版原生重放須從原 SQLite 讀回相同接納／效果回條，保留原 app、presence、transport namespace 與事件鍵。原資料和部署 secret 引用各自留給其權威 owner。新插件的暫存頁、tenant token 與未完成 WebSocket 分片沿原生命週期清除。

故障驗收包括私有目錄缺失、出現未知資料、來源雜湊改變與 SQLite schema 缺件。以上情況產生具體的待核或 blocked 結果，原檔案保持可讀。合成目錄與舊資料的檢查前後雜湊必須相同。

固定基線為 `329ca7c487414d2f54ddd98ff4727446ed2446cd`。隔離副本已通過 55 項 Feishu 邊界與真 SQLite 重放測試。舊 reader 的兩筆原回條及完整合成 SQLite 位於 `tests/fixtures/feishu-owner/`，source lock 綁定來源與 runner。原 receipt schema 沒有 tenant 欄位，實例 tenant／secret 引用由部署資料與 CORE-041 映射補核。

本卡產物分列可重建記憶體狀態、其他權威 owner 與現場待核項目。實際部署目錄的盤點及 CORE-041 實例映射交 EXT-041 重驗。

獨立重現使用 `python ci/feishu_owner_check.py --out artifacts/EXT-006/owner-local/`。正常卡入口 `python ci/check.py EXT-006 --out artifacts/EXT-006/local/` 同步產出兩份 owner-disposition 與總索引，結構化提及和公開合同驗收完成前，卡狀態維持 blocked。三種 SQLite sidecar 任一存在時，要求提供關閉後的一致快照，原檔案保留。

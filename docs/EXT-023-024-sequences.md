# EXT-023 / EXT-024 真 Host 與原 Monty 對拍

本次先消費 CORE-034 `f74ecdd86b73` 未發布候選；三平台 ZIP、成員與
producer SDK 鎖在 `artifacts/EXT-023/feed-fix-intake/`。先用原已建置 Rust
consumer 重現，分開判斷 Host 修正與後續插件變更。SDK alpha.5 的 crate
封裝雜湊變了，實際來源只有 `.cargo_vcs_info.json` 改動，逐成員比較另存。

## 正常時序

1. 在 Windows 新 owner 啟動真 Host，由公開 operator 建原 Person、帳號與入站。
2. 固定模型對端讓 Main 接納原 root，再呼叫 Rust Code 插件；它從公開
   catalog/schema 取得凍結投影，在 HJW Arch 的原隔離映像啟動 Monty。
3. 同一 feed 0 的兩筆相同參數 send 使用 engine call 0、1，子 ordinal 0、1。
   每筆執行前保存原父與 native snapshot；實收持久回執後餵入 VM，保存
   post-answer snapshot，再確認原回執。實收效果應為兩筆，各自不同 operation。
4. 結束後保留逐方法 wire、兩筆 binding 實收、模型回應、Host 日誌及各 digest。

## 故障時序與斷言

- 第一筆已派發但回執未餵：停止本次插件，再由公開恢復路徑讀原子回執；
  不重發第一筆。未知結果不得新增重試權。
- 第一筆已餵並確認、第二筆尚未派發：停止後恢復兩次；原 feed、call ID、
  子 ordinal、根預留與 VM 累積用量延續，不能重餵或跳過第二筆。
- worker/ABI/codec 不匹配或原快照不可讀：報不可恢復，保留原身份；不改走 direct。
- 已配對 partial 或原 code_stop 不復活；尚未配對、仍有授權的等待只續原 run。
- 相同越權項目在 direct 與 Code 都由 Host 拒絕；普通拒絕不冒充未知，後續
  獨立呼叫仍各自授權。
- 取消、EOF、forget 都停止真正 worker 並確認清除；清除失敗不 ACK。
- 原隔離與 runtime 缺失檢查沿用同 digest 的具名證據；改 worker 或映像才重驗。

公開恢復入口、結果分頁與授權語義不足時留下具體阻塞，不以測試對端
代替 Host，也不修改核心私庫。候選對拍成功不代表正式發布或全卡驗收。

## HJW 重現及已驗範圍

Windows 使用 Python 3.12，先準備已驗 Host、runtime-config、原 isolation
profile 與本次 Linux Rust binary；不在檢查入口安裝或升級工具。
設定 `YUKI_CODE_FIXTURE_ROOT=D:/yuki-extension-tests/core034-public-help`、
`YUKI_CODE_LINUX_PLUGIN=/var/tmp/yuki-ext023/feed-recovery-02/target/debug/yuki-codemode`、
`YUKI_CODE_PLUGIN_SHA256=23f888dc639f01754f4122dd606bfeebddf9e77f84757bee8db8fc318e05bb47`。
然後各執行 `python ci/check.py EXT-023 --out <新目錄>` 與
`python ci/check.py EXT-024 --out <新目錄>`。前置 setup 只恢復本案例原有的
專用 daemon/profile；原 Windows Host 與 native plugin 的 digest 均先核對。

`candidate-03` 已實測正常兩筆 send、缺 runtime、壞訊框清除、第一筆回執
餵入前 kill、餵入後雙重啟，以及 unknown 已配對後兩次重啟不重發。
每個案例比較同一專用 daemon 的容器集合，測後回到測前集合。
固定模型 HTTP 皆為三筆；原父 operation、feed 0、engine call 0/1、
子 ordinal 0/1 與 snapshot SHA 可從 wire 重算。

原 native restore 也計一次 suspension。正常結束累計 2，兩種恢復案例
結束為 3；不是重設到零，也不應假定 restore 免費。具體計數與原生位置
見 EXT-024 `evidence-analysis-01`。根預算的完整帳本仍需公開見證。

早期 `case-before-feed-01` 是測試 transport 在接收方向等待時未持續讀 EOF，
造成清理等待失敗；修正只影響故障注入器。`case-before-feed-02` 和最終
`candidate-03` 已重驗。舊證據保留，沒有把該失敗算作核心或 VM 缺陷。

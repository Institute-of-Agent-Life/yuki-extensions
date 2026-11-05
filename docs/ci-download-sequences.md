# 固定 CI 資產的讀取與拒絕

正常：從既有 contracts.lock 指定的同一 URL 取得發布資產，再沿原 SHA-256、
checksum list、來源 commit、版本、receipt、schema 及成員能力核對。完成整套核對前不得使用。

故障：只有 GET 遇到 HTTP 502／503／504 且未帶 Retry-After 時，在原 URL
最多嘗試三次，兩次等待分別為 1、2 秒。每次保留原 timeout；超過次數仍失敗。
其他 HTTP 錯誤、TLS 錯誤或帶 Retry-After 的回覆直接失敗，不忽略服務端等待要求。
200 回應中的錯誤 digest、版本或 receipt 不能靠重下載換成通過，也不能改用本地候選。

Windows 測試用本機 HTTP 重放 502→504→原固定 ZIP、連續 504、403／404、Retry-After，
並核對相同 method／URL／headers。另驗 TLS 錯誤不重試、POST 不送出，以及壞 digest
只讀一次且不落入資產目錄。這是 CI transport 回歸，不重跑已驗的 EXT-002 消費者。

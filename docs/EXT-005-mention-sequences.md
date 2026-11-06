# EXT-005 原群事件的相鄰提及鍵

v4 的 `feishu_ingress.py::text_with_mentions` 在同一位置優先匹配較長的已知鍵。
在 HJW 重放同一段原生文字，事件表列 `@_user_1`（本應用）與
`@_user_10`（另一成員）。飛書先列短鍵，Lark 反向排列。連續兩次
出現的長鍵都應交出另一成員的 open_id，短鍵才指向本應用。
原文另含無對應項的 `@_user_100`，須保留文字，不能借用短鍵的身份。

先用已核的 Windows alpha.2 發行單元重放，保存線路上的原始 segments；
再用修正過的套件跑同一輸入。在原 Host writer 前斷開時，平台收不到成功 ACK。
重投時核對原事件回條與逐段 open_id，另一安裝調換提及表順序並用同一原生
message_id，核對各自的應用 ID 與不同的 Host event。這個案例驗到入站接納；
下游的群啟用、Person 指派與記憶寫入各有自己的案例。

從本倉根目錄使用 Python 3.12。先將 `YUKI_HOST_CANDIDATE` 指向
`compat/core-038-main/source.lock.json` 釘住的本平台 ZIP，`UV_FIND_LINKS` 指向
`tests/peers/lark-fixture.lock.json` 的兩個原 wheel。以下重跑候選場景並保留 wire：

```python
from pathlib import Path
import json, runpy, sys

root = Path.cwd()
sys.path.insert(0, str(root / "ci"))
case = runpy.run_path(str(root / "tests/cases/EXT-005.py"))
out = root / "artifacts/EXT-005/mention-rerun"
out.mkdir()
name, report = case["prepare"](root, out, contract="core-038-main")
(out / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
```

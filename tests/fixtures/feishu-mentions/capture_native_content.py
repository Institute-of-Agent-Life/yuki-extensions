"""Capture native text and split boundaries from a fixed, clean legacy checkout."""

import argparse
from pathlib import Path
import hashlib, json, subprocess, sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--legacy", type=Path, required=True)
arguments = parser.parse_args()
legacy = arguments.legacy.resolve()
sys.path.insert(0, str(legacy / "src"))
from yuki.gateway.providers.feishu_social import _text_content, _text_parts
from yuki.gateway.social import TransportMention, TransportMessage

baseline = "329ca7c487414d2f54ddd98ff4727446ed2446cd"
assert (
    subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=legacy, text=True).strip()
    == baseline
)
assert subprocess.run(["git", "diff", "--quiet"], cwd=legacy).returncode == 0
cases = []
for name, unit, count, marker, native in [
    ("unicode", "雪 @小雪", 1, "@小雪", "ou_original"),
    ("escaped", "前 @ A<&\"' 後", 1, "@ A<&\"'", 'ou_"<&'),
    ("boundary", "雪" * 49900 + " @小雪 ", 5, "@小雪", "ou_original"),
    ("many", "@小雪 雪\n", 10000, "@小雪", "ou_original"),
]:
    text = unit * count
    mentions = []
    offset = 0
    while (start := text.find(marker, offset)) >= 0:
        mentions.append(
            TransportMention(
                "cli_original:" + native,
                "小雪",
                start,
                start + len(marker),
                account_id="original",
            )
        )
        offset = start + len(marker)
    message = TransportMessage(text, tuple(mentions))
    parts = _text_parts(message)
    cases.append(
        {
            "name": name,
            "unit": unit,
            "repeat": count,
            "marker": marker,
            "native": native,
            "parts": [
                {
                    "text_bytes": len(part.text.encode()),
                    "text_sha256": hashlib.sha256(part.text.encode()).hexdigest(),
                    "content_sha256": hashlib.sha256(
                        _text_content(part, "cli_original").encode()
                    ).hexdigest(),
                }
                for part in parts
            ],
        }
    )
output = arguments.output
output.write_text(
    json.dumps(
        {
            "baseline": baseline,
            "source_sha256": hashlib.sha256(
                (legacy / "src/yuki/gateway/providers/feishu_social.py").read_bytes()
            ).hexdigest(),
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "cases": cases,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n"
)
assert subprocess.run(["git", "diff", "--quiet"], cwd=legacy).returncode == 0
print([(case["name"], len(case["parts"])) for case in cases])

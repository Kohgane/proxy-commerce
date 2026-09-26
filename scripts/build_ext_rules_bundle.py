"""F50 — `src/collectors/ext_rules.json` → 확장 번들 `kgp-rules.js`의 BUNDLED 한 줄을 다시 쓴다.

규칙 JSON을 고쳤으면 이걸 한 번 돌린다(번들 = 서버를 못 받을 때의 기본값). 계약이 둘을 대조한다.
    python scripts/build_ext_rules_bundle.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.collectors.ext_rules import load  # noqa: E402

JS = ROOT / "extensions" / "chrome-collector" / "kgp-rules.js"


def main():
    got = load()
    line = "  var BUNDLED = " + json.dumps(got, ensure_ascii=False, sort_keys=True) + ";   // @generated build_ext_rules_bundle.py"
    src = JS.read_text(encoding="utf-8")
    new = re.sub(r"^  var BUNDLED = .*$", lambda _m: line, src, count=1, flags=re.M)
    JS.write_text(new, encoding="utf-8")
    print("bundled", got["version"], got["hash"][:12])


if __name__ == "__main__":
    main()

"""names.py 의 NAMES 리스트를 docs/index.html 의 JS 배열로 동기화한다.

사용법: 프로젝트 루트에서
    python tools/sync_names.py

names.py 가 단일 소스(source of truth)이며, index.html 안의
// NAMES-START ... // NAMES-END 블록을 다시 생성한다.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from names import NAMES  # noqa: E402

HTML_PATH = ROOT / "docs" / "index.html"
START = "// NAMES-START"
END = "// NAMES-END"


def build_js_array(names: list[str], per_line: int = 10) -> str:
    lines = []
    for i in range(0, len(names), per_line):
        chunk = ", ".join(f'"{n}"' for n in names[i : i + per_line])
        lines.append("    " + chunk + ("," if i + per_line < len(names) else ""))
    return "  var NAMES = [\n" + "\n".join(lines) + "\n  ];"


def main() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END), flags=re.DOTALL
    )
    if not pattern.search(html):
        raise SystemExit(f"{HTML_PATH} 에서 {START} / {END} 마커를 찾지 못했습니다.")
    replacement = f"{START}\n{build_js_array(NAMES)}\n  {END}"
    HTML_PATH.write_text(pattern.sub(replacement, html), encoding="utf-8")
    print(f"동기화 완료: {len(NAMES)}명 → {HTML_PATH}")


if __name__ == "__main__":
    main()

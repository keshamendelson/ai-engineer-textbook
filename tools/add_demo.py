#!/usr/bin/env python3
"""Вставляет готовое демо из specs/demos в собранную главу.

Демо пишутся и проверяются отдельными страницами, потом попадают в главу: либо
через спеку блоком html, либо этим скриптом, если глава уже собрана.

    python3 tools/add_demo.py demo-conv.html ch28 kernel          # показать
    python3 tools/add_demo.py demo-conv.html ch28 kernel --write

Разметка демо встаёт в конец указанного раздела, скрипт перед закрытием body.
Повторный запуск ничего не дублирует.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DEMOS = ROOT / "specs" / "demos"


def parts(name: str) -> tuple[str, str]:
    src = (DEMOS / name).read_text(encoding="utf-8")
    html = re.search(r'<div class="demo">.*?\n</div>', src, re.S)
    script = re.search(r"<script>.*?</script>", src, re.S)
    if not html or not script:
        raise SystemExit(f"в {name} не нашлись блок demo и script")
    return html.group(0), script.group(0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("demo", help="имя файла в specs/demos")
    ap.add_argument("chapter", help="например ch28")
    ap.add_argument("section", help="id раздела, в конец которого встанет демо")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    page = SITE / f"{args.chapter}.html"
    html = page.read_text(encoding="utf-8")
    demo_html, demo_script = parts(args.demo)

    marker = re.search(r'<span class="dt">([^<]*)</span>', demo_html).group(1)
    if marker in html:
        print("демо уже стоит в главе")
        return 0

    m = re.search(rf'<h2 id="{re.escape(args.section)}"', html)
    if not m:
        print(f"раздел {args.section} не найден")
        return 1
    tail = re.search(r'\n\s*(<h2 |<div class="recap">|<div class="quiz">)', html[m.end():])
    pos = m.end() + tail.start() if tail else html.find('<div class="recap">')

    out = html[:pos] + "\n\n      " + demo_html + html[pos:]
    out = out.replace("</body>", demo_script + "\n</body>", 1)

    print(f"{args.chapter}: демо «{marker}» встаёт в конец раздела {args.section}")
    if args.write:
        page.write_text(out, encoding="utf-8")
        print("записано, дальше прогоните tools/estimate_time.py --write")
    else:
        print("режим просмотра")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

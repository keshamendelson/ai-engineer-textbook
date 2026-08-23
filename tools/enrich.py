#!/usr/bin/env python3
"""Дополняет уже собранные главы: выводы формул, ссылки на источники, задания.

Главы 0-8 написаны руками, пересобирать их нельзя. Этот скрипт вставляет в них
новые блоки точечно, не трогая остальной текст.

Операции берутся из JSON-файла:

    [{"file": "ch01", "at": "vector", "type": "deeper",
      "title": "Вывод: откуда берётся формула косинуса",
      "brief": "…", "steps": ["…", "…"], "words": 280},
     {"file": "ch01", "at": "recap", "type": "sources",
      "items": [{"ref": "…", "url": "…", "note": "…"}]},
     {"file": "ch14", "at": "recap", "type": "practice",
      "title": "Сделайте руками · 90 минут", "brief": "…", "words": 150}]

Значение "at" это id раздела: блок встаёт в конец этого раздела. Особое значение
"recap" ставит блок прямо перед итогами главы.

    python3 tools/enrich.py specs/enrich.json            # показать, что вставится
    python3 tools/enrich.py specs/enrich.json --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from write_chapter import ask  # noqa: E402  (нужен API-ключ, поэтому импорт после пути)

SITE = ROOT / "site"


def build_deeper(op: dict) -> str:
    steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(op["steps"]))
    body = ask(
        f"Глава учебника по AI-инженерии. Ниже вывод, который надо развернуть в связный "
        f"текст примерно на {op.get('words', 280)} слов. Идти строго по шагам, в том же "
        f"порядке, с теми же обозначениями. Своих шагов не добавлять, обозначения не "
        f"менять, чисел не придумывать. Формулы и обозначения оборачивать в <code>. "
        f"Абзацы в <p>.\n\nЧто выводим: {op['brief']}\n\nШаги вывода:\n{steps}"
    )
    return (f'      <details class="deeper">\n        <summary>{op["title"]}</summary>\n'
            f'        <div class="deeper-body">\n{body}\n        </div>\n      </details>')


def build_sources(op: dict) -> str:
    items = []
    for it in op["items"]:
        ref = (f'<a href="{it["url"]}" target="_blank" rel="noopener">{it["ref"]}</a>'
               if it.get("url") else it["ref"])
        note = f'. {it["note"]}' if it.get("note") else ""
        items.append(f"          <li>{ref}{note}</li>")
    title = op.get("title", "Где про это написано подробнее")
    return ('      <div class="sources">\n        <span class="ct">' + title + "</span>\n"
            "        <ul>\n" + "\n".join(items) + "\n        </ul>\n      </div>")


def build_practice(op: dict) -> str:
    body = ask(
        f"Глава учебника по AI-инженерии. Напиши текст задания для читателя примерно на "
        f"{op.get('words', 150)} слов. Задание разбей на шаги по абзацам, каждый шаг "
        f"начинай с того, что делать. Абзацы в <p>. Заголовок врезки уже стоит, "
        f"повторять его не нужно.\n\nЗадание:\n{op['brief']}"
    )
    return (f'      <div class="callout practice">\n        <span class="ct">{op["title"]}</span>\n'
            f"{body}\n      </div>")


BUILDERS = {"deeper": build_deeper, "sources": build_sources, "practice": build_practice}


def already_there(html: str, op: dict) -> bool:
    if op["type"] == "deeper":
        return f'<summary>{op["title"]}</summary>' in html
    if op["type"] == "sources":
        return 'class="sources"' in html
    if op["type"] == "practice":
        # к заголовку могли дописать пометку про требования, сверяем по началу
        import re as _re
        head = _re.escape(op["title"].split(" · ")[0])
        return bool(_re.search(rf'<span class="ct">{head}[^<]*</span>', html))
    return False


def insert_at(html: str, at: str, fragment: str) -> str | None:
    """Вставка в конец раздела с данным id либо перед итогами главы."""
    if at == "recap":
        m = re.search(r'\n\s*<div class="recap">', html)
        return html[: m.start()] + "\n\n" + fragment + html[m.start():] if m else None

    m = re.search(rf'<h2 id="{re.escape(at)}"', html)
    if not m:
        return None
    tail = re.search(r'\n\s*(<h2 |<div class="recap">|<div class="quiz">)', html[m.end():])
    pos = m.end() + tail.start() if tail else html.find('<div class="recap">')
    if pos <= 0:
        return None
    return html[:pos] + "\n\n" + fragment + html[pos:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ops", help="JSON со списком операций")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", help="взять только операции для этой главы")
    args = ap.parse_args()

    ops = json.loads(Path(args.ops).read_text(encoding="utf-8"))
    if args.only:
        ops = [o for o in ops if o["file"] == args.only]

    pending = []
    for op in ops:
        path = SITE / f"{op['file']}.html"
        if not path.exists():
            print(f"{op['file']}: главы нет, пропуск")
            continue
        if already_there(path.read_text(encoding="utf-8"), op):
            print(f"{op['file']}: «{op.get('title', op['type'])}» уже стоит, пропуск")
            continue
        pending.append(op)

    if not pending:
        print("нечего вставлять")
        return 0

    print(f"собираю {len(pending)} блоков в {args.workers} потоков")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        fragments = list(pool.map(lambda o: BUILDERS[o["type"]](o), pending))

    touched = {}
    for op, frag in zip(pending, fragments):
        path = SITE / f"{op['file']}.html"
        html = touched.get(op["file"]) or path.read_text(encoding="utf-8")
        new = insert_at(html, op["at"], frag)
        if new is None:
            print(f"{op['file']}: не нашёл место «{op['at']}», блок не вставлен")
            continue
        touched[op["file"]] = new
        print(f"{op['file']}: {op['type']} «{op.get('title', '')}» -> раздел {op['at']}")

    if args.write:
        for name, html in touched.items():
            (SITE / f"{name}.html").write_text(html, encoding="utf-8")
        print(f"\nзаписано глав: {len(touched)}")
    else:
        print("\nрежим просмотра, ничего не записано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

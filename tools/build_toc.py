#!/usr/bin/env python3
"""Добавляет в оглавление новые части и главы из specs/plan.json.

В toc.js попадают только те главы, у которых уже собран HTML: иначе в меню
появятся ссылки в пустоту. Скрипт идемпотентен, повторный запуск ничего не
дублирует, а существующие записи оставляет как есть.

    python3 tools/build_toc.py            # показать, что добавится
    python3 tools/build_toc.py --write
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOC = ROOT / "site" / "assets" / "toc.js"
PLAN = ROOT / "specs" / "plan.json"
APPENDIX_ANCHOR = '  {\n    part: "Приложения",'


def entry(ch: dict, tags: str) -> str:
    blurb = ch["blurb"]
    return (
        "      {\n"
        f'        id: "{ch["id"]}",\n'
        f'        num: "{ch["num"]}",\n'
        f'        title: "{ch["title"]}",\n'
        "        blurb:\n"
        f'          "{blurb}",\n'
        f'        tags: "{tags}",\n'
        "      },\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    raw = TOC.read_text(encoding="utf-8")
    if APPENDIX_ANCHOR not in raw:
        print("не нашёл блок приложений в toc.js, вставлять некуда")
        return 1

    added, blocks = [], []
    for part in plan["parts"]:
        items = []
        for ch in part["chapters"]:
            if not (ROOT / "site" / f"{ch['id']}.html").exists():
                continue
            if f'id: "{ch["id"]}"' in raw:
                continue
            tags = ch.get("code", "") or "теория"
            items.append(entry(ch, tags))
            added.append(ch["id"])
        if not items:
            continue
        if f'part: "{part["part"]}"' in raw:
            # часть уже есть, дописываем главы в её конец
            m = re.search(
                re.escape(f'part: "{part["part"]}"') + r".*?\n    \],\n",
                raw,
                re.S,
            )
            if m:
                cut = raw.rindex("      },\n", m.start(), m.end()) + len("      },\n")
                raw = raw[:cut] + "".join(items) + raw[cut:]
                continue
        blocks.append(
            "  {\n"
            f'    part: "{part["part"]}",\n'
            "    items: [\n" + "".join(items) + "    ],\n"
            "  },\n"
        )

    if blocks:
        raw = raw.replace(APPENDIX_ANCHOR, "".join(blocks) + APPENDIX_ANCHOR)

    if not added:
        print("нечего добавлять: либо главы уже в оглавлении, либо HTML ещё не собран")
        return 0

    print("добавляется: " + ", ".join(added))
    if args.write:
        TOC.write_text(raw, encoding="utf-8")
        print("записано в toc.js, дальше прогоните tools/estimate_time.py --write")
    else:
        print("режим просмотра")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

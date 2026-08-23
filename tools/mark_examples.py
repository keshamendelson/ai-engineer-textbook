#!/usr/bin/env python3
"""Помечает курсивом английские языковые примеры внутри русского текста.

В главах про NLP примеры на английском неизбежны: разбор слова back по частям
речи на русском не показать. Такие примеры надо отличать от порчи текста, когда
модель вставляет одиночное английское слово в русскую фразу. Правило простое:
подряд идущие английские слова это цитата, её оборачиваем в <i lang="en">,
одиночное слово оставляем как есть, и его поймает линтер.

    python3 tools/mark_examples.py site/ch20.html            # показать находки
    python3 tools/mark_examples.py site/ch20.html --write
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# три и больше английских слова подряд, возможно с запятыми внутри
RUN = re.compile(r"(?<![\w>/=\"'-])((?:[A-Za-z][A-Za-z'-]*)(?:[ ,]+[A-Za-z][A-Za-z'-]*){2,})(?![\w<-])")

# служебные куски HTML, куда лезть нельзя
SKIP = re.compile(r"<(pre|svg|script|style|code|i|em|a)\b.*?</\1>|<[^>]+>", re.S)


def mark(html: str) -> tuple[str, list[str]]:
    out, found, pos = [], [], 0
    for m in SKIP.finditer(html):
        chunk = html[pos:m.start()]
        new = []
        last = 0
        for r in RUN.finditer(chunk):
            phrase = r.group(1).strip()
            if len(phrase.split()) < 3:
                continue
            found.append(phrase)
            new.append(chunk[last:r.start(1)])
            new.append(f'<i lang="en">{phrase}</i>')
            last = r.end(1)
        new.append(chunk[last:])
        out.append("".join(new))
        out.append(m.group(0))
        pos = m.end()
    out.append(html[pos:])
    return "".join(out), found


def mark_words(html: str, words: list[str]) -> tuple[str, list[str]]:
    """Пометить курсивом отдельные слова, названные списком.

    Нужно для разбора конкретного слова: «английское слово back выступает и
    существительным, и глаголом». Список задаётся руками после вычитки главы,
    автоматика тут ошибается.
    """
    out, found, pos = [], [], 0
    rx = re.compile(r"(?<![\w>/=\"'-])(" + "|".join(re.escape(w) for w in words) + r")(?![\w<-])")
    for m in SKIP.finditer(html):
        chunk = html[pos:m.start()]
        new, last = [], 0
        for r in rx.finditer(chunk):
            found.append(r.group(1))
            new.append(chunk[last:r.start(1)])
            new.append(f'<i lang="en">{r.group(1)}</i>')
            last = r.end(1)
        new.append(chunk[last:])
        out.append("".join(new))
        out.append(m.group(0))
        pos = m.end()
    out.append(html[pos:])
    return "".join(out), found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--words", help="через запятую: отдельные слова, которые тоже пометить курсивом")
    args = ap.parse_args()

    total = 0
    for f in args.files:
        p = Path(f)
        html = p.read_text(encoding="utf-8")
        new, found = mark(html)
        if args.words:
            new, extra = mark_words(new, [w.strip() for w in args.words.split(",") if w.strip()])
            found += extra
        if not found:
            continue
        total += len(found)
        print(f"{p.name}: {len(found)} примеров")
        for phrase in found[:10]:
            print("  ·", phrase)
        if len(found) > 10:
            print(f"  … и ещё {len(found) - 10}")
        if args.write:
            p.write_text(new, encoding="utf-8")
    print(f"\nвсего помечено: {total}" + ("" if args.write else ", режим просмотра"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

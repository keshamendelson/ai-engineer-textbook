#!/usr/bin/env python3
"""Достаёт кусок первоисточника из корпуса, чтобы писать спеку по книге, а не по памяти.

Корпус лежит в rag/corpus/{udl,slp3}/part-NNNN.md, каждый файл это примерно тысяча
слов с пометкой раздела в шапке. Скрипт собирает все куски нужной главы книги
в один файл, который дальше идёт в промпт при написании спеки.

    python3 tools/source_extract.py --list slp3
    python3 tools/source_extract.py --book slp3 --chapter 18
    python3 tools/source_extract.py --book udl --chapter 10 --out /tmp/udl10.txt
    python3 tools/source_extract.py --book slp3 --grep "CTC" --max-words 4000
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "rag" / "corpus"
BOOKS = {
    "slp3": "Speech and Language Processing, 3rd ed. (Jurafsky & Martin)",
    "udl": "Understanding Deep Learning (Simon J.D. Prince)",
}


def parts(book: str) -> list[tuple[str, str, str]]:
    """Список (файл, раздел, текст) по книге."""
    out = []
    for f in sorted((CORPUS / book).glob("part-*.md")):
        raw = f.read_text(encoding="utf-8")
        m = re.search(r"Раздел:\s*(.*)", raw)
        section = m.group(1).strip() if m else ""
        body = raw.split("\n\n", 1)[1] if "\n\n" in raw else raw
        out.append((f.name, section, body))
    return out


def chapter_of(section: str) -> str | None:
    """Номер главы книги по заголовку раздела.

    Заголовки в корпусе шумные: pdftotext затягивает туда колонтитулы вида
    «18 C HAPTER 1 • I NTRODUCTION», где 18 это номер страницы. Считаем надёжным
    только вид «18.2 Название», а «18 Название» принимаем, если дальше идёт
    обычный текст, а не колонтитул.
    """
    if re.search(r"C\s?HAPTER", section):
        return None
    m = re.match(r"(\d+)\.\d+\s+\S", section)
    if m:
        return m.group(1)
    m = re.match(r"(\d+)\s+[A-Z][a-z]", section)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", metavar="BOOK", help="показать разделы книги")
    ap.add_argument("--book", choices=sorted(BOOKS))
    ap.add_argument("--chapter", help="номер главы книги, например 18")
    ap.add_argument("--grep", help="искать куски по регулярному выражению")
    ap.add_argument("--max-words", type=int, default=0, help="обрезать по числу слов")
    ap.add_argument("--out", help="куда сложить, по умолчанию в stdout")
    args = ap.parse_args()

    if args.list:
        seen = []
        for name, section, _ in parts(args.list):
            if section and section not in seen:
                seen.append(section)
                print(f"{name}  {section}")
        return 0

    if not args.book or not (args.chapter or args.grep):
        ap.error("нужен --book вместе с --chapter или --grep, либо --list")

    # Заголовок раздела в корпусе отстаёт от текста: сборщик брал ближайший
    # заголовок, встреченный внутри куска, а не в его начале. Поэтому к каждому
    # найденному куску добавляем предыдущий, иначе начало главы теряется.
    picked = []
    allp = parts(args.book)
    hits = set()
    for i, (name, section, body) in enumerate(allp):
        hit = False
        if args.chapter:
            hit = chapter_of(section) == str(args.chapter)
            if not hit:
                # pdftotext рвёт колонтитул на «C HAPTER 18», ловим и такую форму
                head = re.escape(str(args.chapter))
                hit = bool(re.search(rf"C\s?HAPTER\s+{head}\b", body))
        if not hit and args.grep:
            hit = bool(re.search(args.grep, body, re.I))
        if hit:
            hits.add(i)
            if i > 0:
                hits.add(i - 1)
    for i in sorted(hits):
        picked.append(allp[i])

    if not picked:
        print("ничего не найдено", file=sys.stderr)
        return 1

    chunks = [f"# {BOOKS[args.book]}"]
    words = 0
    for name, section, body in picked:
        if args.max_words and words >= args.max_words:
            chunks.append(f"\n[обрезано: осталось {len(picked)} кусков]")
            break
        chunks.append(f"\n\n===== {name} · {section or 'без раздела'} =====\n{body}")
        words += len(body.split())

    text = "".join(chunks)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{len(picked)} кусков, {words} слов -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

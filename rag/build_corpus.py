#!/usr/bin/env python3
"""Собирает поисковый корпус из PDF-исходников учебника.

Что делает:
  1. Гонит pdftotext по каждому PDF в sources/
  2. Чистит артефакты вёрстки (переносы, колонтитулы, номера страниц)
  3. Режет на чанки ~1200 слов с перекрытием 150 слов
  4. Пишет корпус двумя способами:
       corpus/<книга>/part-NNN.md  — файлы под загрузку в OpenAI vector store
       corpus/chunks.jsonl         — те же чанки одной строкой на чанк

Запуск:
    python3 rag/build_corpus.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
CORPUS = ROOT / "rag" / "corpus"

# Сколько слов в чанке и сколько слов перекрытия между соседними чанками.
# 1200 слов ≈ 1600–1800 токенов: влезает в окно эмбеддера с запасом,
# и при этом чанк остаётся осмысленным куском текста, а не обрывком.
CHUNK_WORDS = 1200
OVERLAP_WORDS = 150

BOOKS = {
    "udl": {
        "file": "udl.pdf",
        "title": "Understanding Deep Learning (Simon J.D. Prince)",
        "url": "https://udlbook.github.io/udlbook/",
    },
    "slp3": {
        "file": "slp3.pdf",
        "title": "Speech and Language Processing, 3rd ed. (Jurafsky & Martin)",
        "url": "https://web.stanford.edu/~jurafsky/slp3/",
    },
}


def extract_text(pdf: Path) -> str:
    """pdftotext -layout сохраняет структуру формул лучше, чем режим по умолчанию."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-nopgbrk", str(pdf), "-"],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def clean(text: str) -> str:
    # Склеиваем слова, разорванные переносом на конце строки
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)
    # Строки, состоящие из одного числа, — это номера страниц
    text = re.sub(r"\n\s*\d{1,4}\s*\n", "\n", text)
    # Колонтитулы вида "Draft of ..." и "Copyright ..."
    text = re.sub(r"(?im)^\s*(draft of|copyright|all rights reserved).*$", "", text)
    # Больше двух пустых строк подряд не нужно
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Лигатуры, которые pdftotext иногда оставляет как есть
    for bad, good in (("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬀ", "ff"), ("ﬃ", "ffi")):
        text = text.replace(bad, good)
    return text


def find_headings(text: str) -> list[tuple[int, str]]:
    """Возвращает (позиция в символах, заголовок) для строк вида '12.3 Название'."""
    out = []
    for m in re.finditer(r"(?m)^\s{0,8}(\d{1,2}(?:\.\d{1,2})?)\s+([A-Z][^\n]{3,70})$", text):
        out.append((m.start(), f"{m.group(1)} {m.group(2).strip()}"))
    return out


def nearest_heading(headings: list[tuple[int, str]], pos: int) -> str:
    best = ""
    for start, title in headings:
        if start <= pos:
            best = title
        else:
            break
    return best


def chunk(text: str, book_id: str, meta: dict) -> list[dict]:
    words = text.split()
    headings = find_headings(text)

    # Чтобы привязать чанк к разделу, нужна позиция чанка в исходном тексте.
    # Считаем её приблизительно: доля слов, пройденных до начала чанка.
    total_words = len(words) or 1
    total_chars = len(text)

    chunks = []
    step = CHUNK_WORDS - OVERLAP_WORDS
    for idx, start in enumerate(range(0, total_words, step)):
        piece = words[start : start + CHUNK_WORDS]
        if len(piece) < 80:  # хвост короче 80 слов не заводим отдельным чанком
            break
        approx_pos = int(total_chars * start / total_words)
        chunks.append(
            {
                "id": f"{book_id}-{idx:04d}",
                "book": book_id,
                "title": meta["title"],
                "url": meta["url"],
                "section": nearest_heading(headings, approx_pos),
                "text": " ".join(piece),
            }
        )
    return chunks


def main() -> int:
    CORPUS.mkdir(parents=True, exist_ok=True)
    all_chunks: list[dict] = []

    for book_id, meta in BOOKS.items():
        pdf = SOURCES / meta["file"]
        if not pdf.exists():
            print(f"пропускаю {book_id}: нет файла {pdf}", file=sys.stderr)
            continue

        print(f"[{book_id}] извлекаю текст…")
        raw = clean(extract_text(pdf))
        (CORPUS / f"{book_id}.txt").write_text(raw, encoding="utf-8")

        pieces = chunk(raw, book_id, meta)
        print(f"[{book_id}] {len(raw.split()):,} слов, {len(pieces)} чанков")

        book_dir = CORPUS / book_id
        book_dir.mkdir(exist_ok=True)
        for c in pieces:
            header = (
                f"# {c['title']}\n"
                f"Раздел: {c['section'] or 'не определён'}\n"
                f"Источник: {c['url']}\n\n"
            )
            (book_dir / f"part-{c['id'].split('-')[1]}.md").write_text(
                header + c["text"], encoding="utf-8"
            )
        all_chunks.extend(pieces)

    with (CORPUS / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for c in all_chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"\nготово: {len(all_chunks)} чанков в {CORPUS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

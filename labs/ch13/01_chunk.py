"""Шаг 1. Режем документы на куски и приписываем каждому куску его адрес.

На входе четыре внутренних документа компании в папке data. На выходе файл
chunks.json: список кусков, у каждого свой номер, текст, имя файла и заголовок
раздела, из которого кусок взят.

Заголовок хранится не для красоты. Кусок, вырванный из середины документа,
теряет контекст: фраза «срок 30 дней» без строки «Возврат бракованного товара»
непонятна ни человеку, ни модели.

Запуск:  ./.venv/bin/python ch13/01_chunk.py
"""

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "chunks.json"

MAX_WORDS = 60      # верхняя граница куска
OVERLAP = 12        # сколько слов конца прошлого куска повторяется в начале нового

chunks = []
for path in sorted(DATA.glob("*.md")):
    doc_title = ""
    section = ""
    buffer = []

    def flush():
        """Сложить накопленный текст в кусок и очистить буфер."""
        if not buffer:
            return
        text = " ".join(buffer).strip()
        if text:
            chunks.append({"id": len(chunks), "file": path.name,
                           "doc": doc_title, "section": section, "text": text})

    for block in path.read_text(encoding="utf-8").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        # Заголовок и текст под ним лежат в одном блоке, потому что пустой строки
        # между ними нет. Отрезаем первую строку, остальное это текст раздела.
        if block.startswith("#"):
            head, _, rest = block.partition("\n")
            if head.startswith("## "):
                section = head[3:].strip()
            else:
                doc_title = head.lstrip("# ").strip()
                section = ""
            block = rest.strip()
            if not block:
                continue

        words = block.split()
        # длинный раздел режем на части с перекрытием, короткий кладём целиком
        start = 0
        while start < len(words):
            piece = words[start:start + MAX_WORDS]
            buffer = piece
            flush()
            buffer = []
            if start + MAX_WORDS >= len(words):
                break
            start += MAX_WORDS - OVERLAP

OUT.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"документов: {len(list(DATA.glob('*.md')))}")
print(f"кусков: {len(chunks)}")
print(f"слов в куске: от {min(len(c['text'].split()) for c in chunks)} "
      f"до {max(len(c['text'].split()) for c in chunks)}")
print(f"\nзаписано в {OUT.name}\n")
print("Первый кусок целиком:")
c = chunks[0]
print(f"  файл:    {c['file']}")
print(f"  документ: {c['doc']}")
print(f"  раздел:  {c['section']}")
print(f"  текст:   {c['text'][:120]}...")

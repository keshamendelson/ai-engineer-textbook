#!/usr/bin/env python3
"""Загрузка корпуса в OpenAI vector store и поиск по нему.

Ключ берётся из переменной окружения OPENAI_API_KEY. Если её нет,
скрипт читает ключ из ~/projects/claude-tg-bot/.env (ключ не копируется
в этот репозиторий).

    python3 rag/openai_store.py upload            # создать хранилище и залить корпус
    python3 rag/openai_store.py ask "что такое induction head"
    python3 rag/openai_store.py ask "..." --store vs_abc123

ID созданного хранилища пишется в rag/.store_id, дальше подставляется сам.
"""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "rag" / "corpus"
STORE_ID_FILE = ROOT / "rag" / ".store_id"
FALLBACK_ENV = Path.home() / "projects" / "claude-tg-bot" / ".env"


def api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    if FALLBACK_ENV.exists():
        for line in FALLBACK_ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit("Не найден OPENAI_API_KEY: задайте переменную окружения.")


def client():
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("Нет пакета openai. Установите: pip3 install openai")
    return OpenAI(api_key=api_key())


def upload(args) -> int:
    cl = client()
    files = sorted(CORPUS.rglob("part-*.md"))
    if not files:
        sys.exit(f"Корпус пуст. Сначала: python3 rag/build_corpus.py")

    store = cl.vector_stores.create(name="ai-engineer-textbook-sources")
    print(f"хранилище: {store.id}")
    STORE_ID_FILE.write_text(store.id, encoding="utf-8")

    # Батчами по 100 файлов: столько принимает upload_and_poll за раз
    batch_size = 100
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]
        handles = [open(p, "rb") for p in batch]
        try:
            result = cl.vector_stores.file_batches.upload_and_poll(
                vector_store_id=store.id, files=handles
            )
            print(f"  {i + len(batch)}/{len(files)} — статус {result.status}")
        finally:
            for h in handles:
                h.close()
        time.sleep(0.5)

    print(f"\nготово. ID сохранён в {STORE_ID_FILE}")
    return 0


def ask(args) -> int:
    cl = client()
    store_id = args.store or (
        STORE_ID_FILE.read_text(encoding="utf-8").strip()
        if STORE_ID_FILE.exists()
        else None
    )
    if not store_id:
        sys.exit("Нет ID хранилища. Сначала: python3 rag/openai_store.py upload")

    response = cl.responses.create(
        model=args.model,
        input=(
            "Ответь по-русски, опираясь только на найденные фрагменты. "
            "В конце перечисли, из каких разделов взят ответ.\n\n"
            f"Вопрос: {args.question}"
        ),
        tools=[{"type": "file_search", "vector_store_ids": [store_id]}],
    )
    print(response.output_text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_up = sub.add_parser("upload", help="залить корпус в новое хранилище")
    p_up.set_defaults(func=upload)

    p_ask = sub.add_parser("ask", help="задать вопрос корпусу")
    p_ask.add_argument("question")
    p_ask.add_argument("--store", help="ID существующего хранилища")
    p_ask.add_argument("--model", default="gpt-4.1-mini")
    p_ask.set_defaults(func=ask)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

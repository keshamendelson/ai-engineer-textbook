"""Общие части конвейера: загрузка индекса, гибридный поиск, вызов модели.

Файл 03_search.py намеренно повторяет поиск у себя, там разбирается разница между
способами. Здесь то же самое собрано в готовые функции, чтобы файлы 04 и 05 были
короткими.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
import warnings
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

chunks = json.loads((HERE / "chunks.json").read_text(encoding="utf-8"))
vectors = np.load(HERE / "vectors.npy")
embedder = TextEmbedding(MODEL)
bm25 = BM25Okapi([re.findall(r"\w+", f"{c['section']} {c['text']}".lower()) for c in chunks])


def search(query, k=3):
    """Гибридный поиск: складываем места куска в двух списках."""
    s_words = bm25.get_scores(re.findall(r"\w+", query.lower()))
    q = np.array(list(embedder.embed([query]))[0], dtype=np.float32)
    s_vec = vectors @ (q / np.linalg.norm(q))
    rw = {i: p for p, i in enumerate(np.argsort(s_words)[::-1])}
    rv = {i: p for p, i in enumerate(np.argsort(s_vec)[::-1])}
    fused = {i: 1 / (10 + rw[i]) + 1 / (10 + rv[i]) for i in range(len(chunks))}
    return sorted(fused, key=fused.get, reverse=True)[:k]


def gateway():
    """Адрес шлюза, ключ и имя модели из переменных окружения."""
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    if not (base and key and model):
        raise SystemExit(
            "Не заданы переменные окружения. Выполните в терминале три строки:\n"
            "  export LLM_BASE_URL=https://адрес-вашего-шлюза\n"
            "  export LLM_API_KEY=ваш-ключ\n"
            "  export LLM_MODEL=имя-модели-у-этого-шлюза")
    return base, key, model


def ask_model(system, user, timeout=120, retries=3):
    """Один запрос к модели по протоколу, который понимают почти все шлюзы.

    Шлюз иногда отвечает ошибкой сервера или обрывает соединение. Это нормальная
    жизнь, поэтому запрос повторяется, а вместо трёхэтажного сообщения об ошибке
    печатается одна понятная строка.
    """
    base, key, model = gateway()
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.2,
    }).encode("utf-8")

    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            f"{base}/v1/chat/completions", data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip(), data.get("usage", {})
        except urllib.error.HTTPError as e:
            reason = {401: "шлюз не принял ключ, проверьте LLM_API_KEY",
                      404: "шлюз не знает такой модели, проверьте LLM_MODEL",
                      429: "слишком много запросов, шлюз просит подождать",
                      500: "ошибка на стороне шлюза, вашей вины тут нет",
                      502: "шлюз не дозвонился до модели",
                      503: "шлюз перегружен"}.get(e.code, "шлюз ответил ошибкой")
            print(f"  попытка {attempt} из {retries}: {e.code}, {reason}")
            if e.code in (401, 404):
                raise SystemExit("Дальше пробовать нет смысла, исправьте настройку.")
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  попытка {attempt} из {retries}: соединение не состоялось, {e}")
        if attempt < retries:
            time.sleep(3 * attempt)

    raise SystemExit("Шлюз не ответил ни разу. Попробуйте позже или смените шлюз.")

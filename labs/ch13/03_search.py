"""Шаг 3. Три способа найти нужный кусок и разница между ними.

Поиск по словам (BM25) ищет совпадение букв. Поиск по векторам ищет совпадение
смысла. У каждого есть слепое пятно, и оно видно на двух вопросах ниже.
Гибрид складывает места, которые кусок занял в обоих списках.

Запуск:  ./.venv/bin/python ch13/03_search.py
"""

import json
import re
from pathlib import Path

import warnings

import numpy as np
from fastembed import TextEmbedding
from rank_bm25 import BM25Okapi

# библиотека предупреждает о способе усреднения векторов, на результат это не влияет
warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

chunks = json.loads((HERE / "chunks.json").read_text(encoding="utf-8"))
vectors = np.load(HERE / "vectors.npy")
embedder = TextEmbedding(MODEL)

# для поиска по словам текст разбирается на слова в нижнем регистре
tokenized = [re.findall(r"\w+", f"{c['section']} {c['text']}".lower()) for c in chunks]
bm25 = BM25Okapi(tokenized)


def search_words(query, k=3):
    scores = bm25.get_scores(re.findall(r"\w+", query.lower()))
    return list(np.argsort(scores)[::-1][:k]), scores


def search_vectors(query, k=3):
    q = np.array(list(embedder.embed([query]))[0], dtype=np.float32)
    q /= np.linalg.norm(q)
    scores = vectors @ q
    return list(np.argsort(scores)[::-1][:k]), scores


def search_hybrid(query, k=3):
    """Складываем места в двух списках. Кусок, который высоко в обоих, побеждает."""
    _, s_words = search_words(query, k)
    _, s_vec = search_vectors(query, k)
    rank_words = {idx: place for place, idx in enumerate(np.argsort(s_words)[::-1])}
    rank_vec = {idx: place for place, idx in enumerate(np.argsort(s_vec)[::-1])}
    # 10 это сглаживание: чем число больше, тем меньше преимущество первых мест.
    # Для больших индексов берут 60, для нашего в 18 кусков этого много.
    fused = {i: 1 / (10 + rank_words[i]) + 1 / (10 + rank_vec[i]) for i in range(len(chunks))}
    top = sorted(fused, key=fused.get, reverse=True)[:k]
    places = {i: (rank_words[i] + 1, rank_vec[i] + 1) for i in top}
    return top, fused, places


def show(title, idxs, scores, places=None):
    print(f"  {title}")
    for place, i in enumerate(idxs, 1):
        c = chunks[i]
        extra = ""
        if places:
            pw, pv = places[i]
            extra = f" (по словам {pw}-е, по векторам {pv}-е)"
        print(f"    {place}. [{scores[i]:.3f}] {c['file']} · {c['section']}: "
              f"{c['text'][:60]}...{extra}")


questions = [
    "как получить деньги за неотгулянный отпуск",       # других слов, тот же смысл
    "client_max_body_size",                             # точное слово из документа
    "сколько ждать возврат денег на карту",
]

for q in questions:
    print(f"\nВопрос: {q}")
    show("по словам", *search_words(q))
    show("по векторам", *search_vectors(q))
    show("гибрид", *search_hybrid(q))

print("\nПервый вопрос задан не теми словами, что в документе: слова «неотгулянный»")
print("там нет вообще. Поиск по словам ставит на первое место кусок про возврат")
print("товара, потому что там совпало «получить» и «дней». Поиск по векторам")
print("находит нужный кусок про компенсацию.")
print("\nВторой вопрос это точное имя параметра. Поиск по словам даёт 2.03 у нужного")
print("куска и ровно 0 у всех остальных: совпадение либо есть, либо его нет. Поиск")
print("по векторам тоже угадал, но разрыв между первым и вторым местом там куда")
print("меньше, а значит на другом наборе документов он мог и промахнуться.")
print("\nГибрид не выигрывает ни один из двух случаев с большим отрывом, зато не")
print("проигрывает ни одного. В продукте берут его.")

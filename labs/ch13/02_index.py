"""Шаг 2. Превращаем куски в векторы.

Вектор это список чисел, который описывает смысл текста. Два текста про одно и
то же дают похожие списки, даже если слова в них разные. Именно поэтому поиск по
векторам находит «деньги за неотгулянный отпуск» в куске, где написано
«компенсация за неиспользованный отпуск».

Модель считает векторы прямо на вашем процессоре. В первый запуск она скачивается,
это 220 мегабайт и несколько минут. Дальше интернет не нужен.

Запуск:  ./.venv/bin/python ch13/02_index.py
"""

import json
import time
from pathlib import Path

import warnings

import numpy as np
from fastembed import TextEmbedding

# библиотека предупреждает о способе усреднения векторов, на результат это не влияет
warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

chunks = json.loads((HERE / "chunks.json").read_text(encoding="utf-8"))

# к тексту куска приклеиваем заголовок раздела: так вектор точнее ловит тему
texts = [f"{c['doc']}. {c['section']}. {c['text']}" for c in chunks]

print(f"кусков к обработке: {len(texts)}")
print(f"модель: {MODEL}")
print("первый запуск скачивает модель, дальше она берётся с диска\n")

embedder = TextEmbedding(MODEL)
start = time.time()
vectors = np.array(list(embedder.embed(texts)), dtype=np.float32)
spent = time.time() - start

# нормируем длину каждого вектора к единице, тогда косинусная близость
# считается одним умножением матриц
vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
np.save(HERE / "vectors.npy", vectors)

print(f"готово за {spent:.2f} секунды")
print(f"размер таблицы векторов: {vectors.shape[0]} строк на {vectors.shape[1]} чисел")
print(f"на диске: {(HERE / 'vectors.npy').stat().st_size / 1024:.0f} килобайт")
print("\nПервые пять чисел первого вектора:")
print(" ", np.round(vectors[0][:5], 4))
print("\nСмысла в отдельных числах нет. Смысл появляется при сравнении векторов,")
print("этим занимается 03_search.py.")

"""
Лабораторная работа 7: Эмбеддинги и векторное сходство.
Скрипт вычисляет эмбеддинги трёх русских фраз с помощью fastembed,
строит матрицу косинусного сходства и показывает, что перефразированная
фраза ближе к исходной, чем фраза на другую тему.
Запуск: python 01_embeddings_similarity.py
"""

import numpy as np
from fastembed import TextEmbedding

# Фиксированный набор фраз
phrases = [
    "Я заварил крепкий чай",
    "Приготовил налитый чай",  # перефразировка
    "На улице идёт снег"        # другая тема
]

# Инициализация модели эмбеддингов
model = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# Получаем эмбеддинги
embeddings = np.array(list(model.embed(phrases)), dtype=np.float32)

# Нормализуем векторы для косинусного сходства
norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
embeddings_norm = embeddings / norms

# Матрица косинусного сходства (скалярное произведение нормированных векторов)
sim_matrix = embeddings_norm @ embeddings_norm.T

# Вывод
print("ЭмBEDDINGИ вычислены. Матрица косинусного сходства:")
print("         Фраза 0   Фраза 1   Фраза 2")
for i, row in enumerate(sim_matrix):
    print(f"Фраза {i}: {row[0]:.4f}   {row[1]:.4f}   {row[2]:.4f}")

# Проверка гипотезы: сходство перефразировки с исходной больше, чем с посторонней фразой
sim_paraphrase = sim_matrix[0, 1]
sim_unrelated = sim_matrix[0, 2]
print(f"\nСходство исходной фразы с перефразировкой: {sim_paraphrase:.4f}")
print(f"Сходство исходной фразы с посторонней фразой: {sim_unrelated:.4f}")
if sim_paraphrase > sim_unrelated:
    print("Перефразированная фраза действительно ближе к исходной, чем фраза на другую тему.")
else:
    print("Ожидалось, что перефразировка будет ближе, но результат иной.")

"""Шаг 3. Как выглядит переобучение, если посмотреть на него своими глазами.

Делим 60 квартир на две части: на первых 45 модель учится, последние 15 она не
видит вообще. Потом даём модели всё больше свободы: сначала три признака, затем
их квадраты, кубы и так далее. Ошибка на обучающей части падает всегда. Ошибка
на отложенной части сначала падает, потом растёт. Момент разворота и есть
переобучение.

Запуск:  ./.venv/bin/python ch02/03_overfit.py
"""

import csv
from pathlib import Path

import numpy as np

rows = list(csv.DictReader((Path(__file__).parent / "data/apartments.csv").open(encoding="utf-8")))
X = np.array([[float(r["area"]), float(r["metro_min"]), float(r["floor"])] for r in rows])
y = np.array([float(r["price"]) for r in rows]) / 1e6

# делим один раз и больше к этому не возвращаемся
X_train, X_test = X[:45], X[45:]
y_train, y_test = y[:45], y[45:]
print(f"учимся на {len(y_train)} квартирах, проверяем на {len(y_test)}\n")


def features(X, power):
    """Признаки со степенями: при power=1 три штуки, при power=4 уже двенадцать."""
    cols = [np.ones(len(X))]
    for p in range(1, power + 1):
        cols.append(((X - X.mean(axis=0)) / X.std(axis=0)) ** p)
    return np.column_stack(cols)


def fit(A, y):
    """Точное решение методом наименьших квадратов, без цикла обучения."""
    return np.linalg.lstsq(A, y, rcond=None)[0]


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


table = []
for power in range(1, 15):
    A_train = features(X_train, power)
    A_test = features(X_test, power)
    w = fit(A_train, y_train)
    table.append((power, A_train.shape[1],
                  rmse(A_train @ w, y_train), rmse(A_test @ w, y_test)))

best = min(table, key=lambda r: r[3])[0]
print("степень  признаков  ошибка на обучении  ошибка на отложенных")
for power, cols, e_train, e_test in table:
    mark = "  <- лучшая точка" if power == best else ""
    print(f"{power:5}   {cols:8}   {e_train:16.3f}   {e_test:18.3f}{mark}")

first, last = table[0], table[-1]
print(f"\nОшибка считается в миллионах рублей. На обучающих квартирах она падает")
print(f"с {first[2]:.2f} до {last[2]:.2f}: модель постепенно запоминает эти 45 сделок наизусть.")
print(f"На отложенных 15 квартирах она уходит с {first[3]:.2f} до {last[3]:.2f}, то есть модель")
print(f"стала хуже в {last[3] / first[3]:.0f} раз. Лучшая точка на степени {best}, дальше начинается")
print("переобучение. Отложенную часть для того и держат нетронутой до самого конца.")

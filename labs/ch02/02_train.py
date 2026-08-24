"""Шаг 2. Модель подбирает веса сама.

Тот же файл с квартирами. Начинаем с нулевых весов и двести раз повторяем одно
действие: посмотреть, куда наклонена ошибка, и сдвинуть веса против наклона.
Это градиентный спуск из главы 4, здесь он в самом простом виде.

Запуск:  ./.venv/bin/python ch02/02_train.py
"""

import csv
from pathlib import Path

import numpy as np

rows = list(csv.DictReader((Path(__file__).parent / "data/apartments.csv").open(encoding="utf-8")))
X = np.array([[float(r["area"]), float(r["metro_min"]), float(r["floor"])] for r in rows])
y = np.array([float(r["price"]) for r in rows])

# Приводим признаки к одному масштабу. Площадь измеряется десятками, цена
# миллионами, и без этой правки шаг обучения, подходящий одному признаку,
# разносит другой. Запоминаем среднее и разброс, они понадобятся в конце.
mean, std = X.mean(axis=0), X.std(axis=0)
Xs = (X - mean) / std
y_scale = 1e6
ys = y / y_scale

w = np.zeros(3)
b = 0.0
step = 0.1          # скорость обучения: насколько сильно двигаем веса за раз
n = len(ys)

print("шаг      ошибка (в миллионах рублей в квадрате)")
show = {0, 1, 2, 3, 5, 8, 12, 20, 40, 80, 200}
for i in range(201):
    pred = Xs @ w + b
    error = pred - ys
    loss = float(np.mean(error ** 2))

    # производные ошибки по каждому весу: куда наклонена поверхность ошибки
    grad_w = 2 / n * (Xs.T @ error)
    grad_b = 2 / n * error.sum()

    # шаг против наклона: вниз по склону
    w -= step * grad_w
    b -= step * grad_b

    if i in show:
        print(f"{i:4}     {loss:.4f}")

print()
# возвращаем веса в исходные единицы, чтобы их можно было прочитать словами
w_real = w * y_scale / std
b_real = (b - (mean / std) @ w) * y_scale
print(f"квадратный метр стоит примерно {w_real[0]:,.0f} рублей".replace(",", " "))
print(f"каждая минута пешком до метро отнимает примерно {-w_real[1]:,.0f} рублей".replace(",", " "))
print(f"каждый этаж вверх добавляет примерно {w_real[2]:,.0f} рублей".replace(",", " "))
print(f"свободный член {b_real / 1e6:.2f} млн")

pred_full = X @ w_real + b_real
print(f"\nсредний промах модели: {np.abs(pred_full - y).mean() / 1e6:.2f} млн рублей")
print("Данные придуманы по правилу 130 тысяч за метр, минус 60 тысяч за минуту до")
print("метро, плюс 40 тысяч за этаж, со случайным разбросом. Модель нашла это сама,")
print("видя только таблицу.")

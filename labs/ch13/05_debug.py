"""Шаг 5. Где именно сломалось, если ответ неправильный.

Три проверки подряд, ровно как в схеме главы. Каждая отвечает на один вопрос, и
чинить надо там, где первая проверка дала «нет». Менять текст запроса к модели,
не дойдя до третьей проверки, бесполезно.

Запуск:  ./.venv/bin/python ch13/05_debug.py
         ./.venv/bin/python ch13/05_debug.py "вопрос" "слово-из-нужного-куска"
"""

import sys

from common import chunks, search

question = sys.argv[1] if len(sys.argv) > 1 else "какой пароль считается достаточно длинным"
needle = sys.argv[2] if len(sys.argv) > 2 else "12 символов"

print(f"Вопрос: {question}")
print(f"Ожидаем увидеть в ответе: {needle}\n")

# Проверка 1: попал ли нужный текст в индекс вообще
in_index = [c for c in chunks if needle.lower() in c["text"].lower()]
print(f"1. Кусок с нужным фактом есть в индексе: {'да' if in_index else 'нет'}")
if not in_index:
    print("   Чинить нарезку и загрузку документов. Дальше идти нет смысла:")
    print("   поиск не может найти то, чего в индексе нет.")
    raise SystemExit(0)
target = in_index[0]
print(f"   это кусок {target['id']}: {target['file']} · {target['section']}")

# Проверка 2: поднял ли его поиск в первые пять
top = search(question, k=5)
place = top.index(target["id"]) + 1 if target["id"] in top else None
print(f"\n2. Поиск поднял его в первую пятёрку: {'да, место ' + str(place) if place else 'нет'}")
if not place:
    print("   Чинить поиск: перефразировать запрос, поднять число кандидатов,")
    print("   добавить переспрашивание или реранкер. Промпт тут ни при чём.")
    print("   Что нашлось вместо него:")
    for n, i in enumerate(top[:3], 1):
        print(f"     {n}. {chunks[i]['file']} · {chunks[i]['section']}")
    raise SystemExit(0)

# Проверка 3: попал ли он в те куски, которые реально уходят модели
sent = search(question, k=3)
print(f"\n3. Кусок попал в контекст, который уходит модели: "
      f"{'да' if target['id'] in sent else 'нет'}")
if target["id"] not in sent:
    print("   Кусок нашёлся, но его отрезала граница контекста. Чинить сборку:")
    print("   брать больше кусков или ставить реранкер перед обрезкой.")
    raise SystemExit(0)

print("\nВсе три проверки пройдены. Если ответ всё равно неправильный, дело в самой")
print("модели или в тексте запроса к ней, и только теперь имеет смысл его менять.")

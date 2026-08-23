#!/usr/bin/env python3
"""Литературная правка глав учебника моделью gpt-5.6-luna через шлюз Lenec.

Что делает:
  1. Достаёт из HTML только текстовые узлы (абзацы, подписи, пункты списков,
     заголовки, пояснения к ответам квиза). Разметку, код и SVG не трогает.
  2. Гонит их пачками через luna со сводом правил из скиллов ai-copywriter
     и humanizer-ru.
  3. Проверяет каждый переписанный фрагмент. Не прошёл проверку, остаётся
     оригинал. Правка может только улучшить текст или ничего не изменить.

Запуск:
    python3 tools/polish.py site/ch01.html            # одна глава
    python3 tools/polish.py site/*.html --dry-run     # показать, не записывать
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path.home() / "projects" / "claude-tg-bot" / ".env"
MODEL = "gpt-5.6-luna"
BATCH = 12

SYSTEM = """Ты редактор русскоязычного учебника по AI-инженерии. Тебе дают фрагменты
текста из главы. Твоя работа: убрать признаки машинного текста, сохранив смысл целиком.

ЖЁСТКИЕ ЗАПРЕТЫ (нарушение = брак):
1. Никакого длинного тире (—) и среднего тире (–). Вообще. Заменяй точкой, запятой,
   двоеточием или переписывай фразу.
2. Никаких антитез «не X, а Y», «не просто X», «больше чем X», «X это не Y, это Z».
   Говори прямо, что есть.
3. Никакого микса языков в терминах: «коммуникационный overhead», «production-нагрузка».
   Устоявшиеся сокращения (API, HTTP, JSON, RAG, LLM, GPU, MCP, BPE, SFT, LoRA) оставляй.
4. Не выдумывай фактов. Ни одного числа, названия, имени или утверждения, которого
   нет в исходном фрагменте. Все цифры, формулы, имена моделей и названия библиотек
   переноси дословно.
5. HTML-теги внутри фрагмента (<code>, <b>, <a href=...>) сохраняй дословно
   вместе с их содержимым.

УБИРАЙ:
- Раздутую значимость: «играет ключевую роль», «знаменует», «открывает горизонты»,
  «главная идея всего», «в этом весь фокус».
- Канцелярит: «является», «осуществляет», «в рамках», «данный», «представляет собой».
- Заглушки уверенности: «безусловно», «стоит отметить», «важно подчеркнуть», «очевидно».
- Размытые ссылки: «эксперты считают», «исследования показывают» без имени.
- Афоризмы-формулы: «X это язык Y», «X это валюта Y», «X становится ловушкой».
- Метрономный ритм: три предложения подряд одной длины, все абзацы по 4 строки,
  все списки ровно из трёх пунктов.
- Риторические вопросы-переходы: «Но что это значит?», «Зачем это нужно?».

ДЕЛАЙ:
- Меняй длину предложений. Короткое рядом с длинным. Неполное предложение допустимо.
- Ставь читателя в кадр: «вы», «посмотрите», конкретный инженер в конкретной ситуации.
- Держи технический регистр учебника. Это не пост в блоге и не реклама.
  Без панибратства, без восклицаний, без обращений «друзья».
- Если фрагмент уже хороший, верни его почти без изменений. Не редактируй ради редактуры.

ФОРМАТ ОТВЕТА: строгий JSON-массив строк той же длины, что и входной массив,
в том же порядке. Никакого текста вокруг, никаких markdown-ограждений."""


def api_config() -> tuple[str, str]:
    key = os.environ.get("OPUS_API_KEY", "")
    base = os.environ.get("OPUS_BASE_URL", "")
    if not (key and base) and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPUS_API_KEY=") and not key:
                key = line.split("=", 1)[1].strip().strip("\"'")
            if line.startswith("OPUS_BASE_URL=") and not base:
                base = line.split("=", 1)[1].strip().strip("\"'")
    if not (key and base):
        sys.exit("Нет OPUS_API_KEY / OPUS_BASE_URL")
    return key, base.rstrip("/")


def call_model(payload: list[str], key: str, base: str) -> list[str] | None:
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)},
        ],
        "temperature": 0.4,
        "max_tokens": 8000,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"    сеть: {e}", file=sys.stderr)
        return None

    if "choices" not in data:
        print(f"    ответ без choices: {str(data)[:200]}", file=sys.stderr)
        return None

    text = data["choices"][0]["message"]["content"].strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return None
        try:
            out = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return out if isinstance(out, list) and len(out) == len(payload) else None


# --- проверки, после которых правка принимается ---

# Длинное тире не отбраковываем, а чиним: правило дома, а не претензия к модели.
def fix_dashes(text: str) -> str:
    # «слово — это» → «слово это»
    text = re.sub(r"\s+[—–]\s+(это\b)", r" \1", text)
    # тире между двумя пробелами внутри предложения → запятая
    text = re.sub(r"(\w)\s+[—–]\s+(?=[а-яёa-z])", r"\1, ", text)
    # тире перед заглавной буквы → точка
    text = re.sub(r"(\w)\s+[—–]\s+(?=[А-ЯЁA-Z])", r"\1. ", text)
    # всё, что осталось
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    return re.sub(r",\s*,", ",", text)


# что обязано пережить правку дословно
KEEP = re.compile(r"<[^>]+>|\d+[.,]?\d*|[A-Za-z][A-Za-z0-9_.\-]{2,}")


def accept(old: str, new: str) -> tuple[bool, str]:
    if not new or not new.strip():
        return False, "пусто"
    ratio = len(new) / max(1, len(old))
    if not (0.55 <= ratio <= 1.6):
        return False, f"длина изменилась в {ratio:.2f} раза"
    # все теги, числа и латинские идентификаторы должны остаться
    lost = set(KEEP.findall(old)) - set(KEEP.findall(new))
    lost = {x for x in lost if len(x) > 2}
    if lost:
        return False, "потеряно: " + ", ".join(sorted(lost)[:4])
    return True, ""


# --- извлечение текстовых узлов ---

# элементы, чьё СОДЕРЖИМОЕ правим. Внутри не должно быть блочной вёрстки.
TARGETS = re.compile(
    r"<(p|li|figcaption|h2|h3)(\s[^>]*)?>(?P<body>(?:(?!</?(?:p|li|figcaption|h2|h3|div|table|pre|svg|ul|ol)\b).)*?)</\1>",
    re.S,
)

SKIP_INSIDE = re.compile(r"<(pre|code|svg|script|style)\b", re.I)


def segments(src: str) -> list[tuple[int, int, str]]:
    out = []
    for m in TARGETS.finditer(src):
        body = m.group("body")
        text = body.strip()
        if len(text) < 45:
            continue
        if SKIP_INSIDE.search(text):
            continue
        if "<" in text and not re.fullmatch(r"[^<]*(?:<(?:code|b|i|a|span|em|strong)\b[^>]*>[^<]*</(?:code|b|i|a|span|em|strong)>[^<]*)*", text, re.S):
            continue
        out.append((m.start("body"), m.end("body"), body))
    return out


def polish_file(path: Path, key: str, base: str, dry: bool) -> None:
    src = path.read_text(encoding="utf-8")
    segs = segments(src)
    if not segs:
        print(f"{path.name}: нечего править")
        return

    print(f"{path.name}: {len(segs)} фрагментов")
    replacements: dict[int, tuple[int, str]] = {}
    accepted = rejected = 0

    for i in range(0, len(segs), BATCH):
        chunk = segs[i : i + BATCH]
        payload = [s[2].strip() for s in chunk]
        result = call_model(payload, key, base)
        if result is None:
            print(f"  пачка {i // BATCH + 1}: пропущена")
            continue
        for (start, end, old), new in zip(chunk, result):
            new = fix_dashes(str(new).strip())
            ok, why = accept(old.strip(), new)
            if ok:
                if new != old.strip():
                    replacements[start] = (end, new)
                accepted += 1
            else:
                rejected += 1
                if rejected <= 3:
                    print(f"    отклонено ({why}): {old.strip()[:60]}…")
        print(f"  пачка {i // BATCH + 1}/{(len(segs) + BATCH - 1) // BATCH}: "
              f"принято {accepted}, отклонено {rejected}")

    if not replacements:
        print("  правок нет\n")
        return

    out = src
    for start in sorted(replacements, reverse=True):
        end, new = replacements[start]
        out = out[:start] + "\n        " + new + "\n      " + out[end:]

    if dry:
        print(f"  [dry-run] заменил бы {len(replacements)} фрагментов\n")
        for start in sorted(replacements):
            end, new = replacements[start]
            print("  БЫЛО:  " + " ".join(src[start:end].split())[:300])
            print("  СТАЛО: " + " ".join(new.split())[:300] + "\n")
        return
    path.write_text(out, encoding="utf-8")
    print(f"  записано: {len(replacements)} фрагментов изменено\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key, base = api_config()
    for f in args.files:
        polish_file(Path(f), key, base, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

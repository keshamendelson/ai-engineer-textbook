#!/usr/bin/env python3
"""Сборка главы учебника: структуру и схемы даёт спека, прозу пишет gpt-5.6-luna.

Разделение труда:
  спека (JSON)  — заголовки, порядок разделов, SVG-схемы, таблицы, код, квизы
  luna          — все абзацы, подписи к схемам, тексты врезок, итоги главы
  этот скрипт   — параллельные вызовы модели и сборка HTML

Вызовы к модели идут одновременно: один поток на блок текста. Порядок в готовой
главе сохраняется, потому что результат кладётся по индексу блока.

Запуск:
    python3 tools/write_chapter.py specs/ch09.json
    python3 tools/write_chapter.py specs/*.json --workers 10
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = Path.home() / "projects" / "claude-tg-bot" / ".env"
MODEL = "gpt-5.6-luna"

VOICE = """Ты пишешь главу русскоязычного учебника по AI-инженерии. Читатель это студент
первого курса или разработчик без опыта в машинном обучении. Он умеет программировать
на Python и больше ничего не знает.

РЕГИСТР. Учебник, а не блог и не реклама. Спокойно, конкретно, по делу. Обращение
к читателю на «вы». Без восклицательных знаков, без «друзья», без «давайте разберёмся».

ЖЁСТКИЕ ЗАПРЕТЫ:
1. Длинное тире (—) и среднее тире (–). Ни одного. Точка, запятая, двоеточие.
2. Антитезы «не X, а Y», «не просто X», «больше чем X», «X это не Y, это Z».
3. Микс языков в терминах: «коммуникационный overhead», «production-нагрузка».
   Устоявшиеся сокращения (API, HTTP, JSON, RAG, LLM, GPU, MCP, BPE, SFT, LoRA, GQA,
   RoPE, KV) оставляй как есть.
4. Канцелярит: является, осуществляет, представляет собой, в рамках, данный.
5. Раздутая значимость: играет ключевую роль, знаменует, открывает горизонты,
   главная идея всего, в этом весь фокус, фундаментальный принцип.
6. Заглушки: стоит отметить, важно подчеркнуть, безусловно, очевидно, как известно.
7. Афоризмы-формулы: «X это язык Y», «X это валюта Y», «X становится ловушкой».
8. Размытые ссылки: эксперты считают, исследования показывают, аналитики отмечают.
9. Заголовки вида «Термин: пояснение через двоеточие».
10. Выдуманные факты. Числа, названия моделей и библиотек бери только из задания.

ДЕЛАЙ:
- Меняй длину предложений. Короткое рядом с длинным. Неполное предложение допустимо.
- Давай конкретику: числа, имена библиотек, реальные ситуации из работы инженера.
- Объясняй с нуля. Термин вводится один раз и сразу расшифровывается.
- Живой глагол вместо отглагольного существительного.
- Пиши сплошным текстом. Списки только если их просит задание.

ФОРМАТ. Возвращай ТОЛЬКО готовый HTML-фрагмент без обёрток и без markdown.
Разрешённые теги: <p>, <code>, <b>, <a href>. Каждый абзац в своём <p>.
Никаких <h1>-<h6>, <div>, <ul>, если задание не просит иного."""


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


KEY, BASE = api_config()


def fix_dashes(text: str) -> str:
    # диапазон чисел: 300–3400 Гц должен остаться диапазоном, а не стать перечислением
    text = re.sub(r"(\d)\s*[—–]\s*(\d)", r"\1-\2", text)
    text = re.sub(r"\s+[—–]\s+(это\b)", r" \1", text)
    text = re.sub(r"(\w)\s+[—–]\s+(?=[а-яёa-z])", r"\1, ", text)
    text = re.sub(r"(\w)\s+[—–]\s+(?=[А-ЯЁA-Z])", r"\1. ", text)
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    return re.sub(r",\s*,", ",", text)


def ask(prompt: str, retries: int = 3) -> str:
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": VOICE},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 12000,
    }).encode("utf-8")

    for attempt in range(retries):
        req = urllib.request.Request(
            f"{BASE}/v1/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            text = data["choices"][0]["message"]["content"].strip()
            text = re.sub(r"^```(?:html)?\s*|\s*```$", "", text).strip()
            text = fix_dashes(text)
            # выкидываем заголовки, если модель их всё-таки поставила
            text = re.sub(r"</?h[1-6][^>]*>", "", text)
            # Шлюз обрывает ответ по лимиту токенов, и тогда абзац кончается
            # на середине слова. Такой кусок в главу пускать нельзя.
            cut = data["choices"][0].get("finish_reason") == "length"
            ragged = bool(text) and not re.search(r"[.!?:»)\]]\s*(</p>)?\s*$", text)
            if text and not (cut or ragged):
                return text
            if attempt == retries - 1 and text:
                print("    ответ обрезан, чиню по последнему целому предложению",
                      file=sys.stderr)
                return trim_to_sentence(text)
        except Exception as e:  # сеть рвётся, шлюз отдаёт обрывок, ключа нет в ответе
            time.sleep(2 + 4 * attempt)  # соединение рвётся пачками, повтор в лоб бесполезен
            if attempt == retries - 1:
                print(f"    сбой после {retries} попыток: {e}", file=sys.stderr)
                return "<p></p>"
    return "<p></p>"


def trim_to_sentence(text: str) -> str:
    """Обрезать оборванный ответ до последнего целого предложения и закрыть теги."""
    text = re.sub(r"<p>[^<]*$", "", text).rstrip()
    m = list(re.finditer(r"[.!?»](?=\s|<|$)", text))
    if m:
        text = text[: m[-1].end()]
    if text.count("<p>") > text.count("</p>"):
        text += "</p>"
    return text


def strip_repeated_title(body: str, title: str) -> str:
    """Модель любит начинать врезку с повтора её заголовка. Убираем."""
    norm = re.sub(r"\s+", " ", title).strip().lower()
    def first_para_matches(m):
        inner = re.sub(r"<[^>]+>", "", m.group(1))
        return re.sub(r"\s+", " ", inner).strip().lower() == norm
    m = re.match(r"\s*<p>(.*?)</p>", body, re.S)
    if m and first_para_matches(m):
        return body[m.end():].lstrip()
    return body


# ---------- сборка блоков ----------

def prose_prompt(ctx: str, brief: str, words: int) -> str:
    return (
        f"{ctx}\n\nНапиши примерно {words} слов основного текста на тему ниже. "
        f"Только абзацы в <p>, без заголовков.\n\nЧто раскрыть:\n{brief}"
    )


def build_block(block: dict, ctx: str) -> str:
    kind = block.get("type")

    if kind == "prose":
        return ask(prose_prompt(ctx, block["brief"], block.get("words", 160)))

    if kind == "figure":
        cap = ask(
            f"{ctx}\n\nНапиши подпись к схеме. Формат: сначала <b>одно короткое утверждение</b>, "
            f"затем 2-3 предложения пояснения. Всего до 65 слов. Верни один <p> без тега <p>: "
            f"только внутреннее содержимое.\n\nЧто на схеме:\n{block['caption']}"
        )
        cap = re.sub(r"</?p>", "", cap).strip()
        return f'<figure>\n{block["svg"]}\n<figcaption>\n{cap}\n</figcaption>\n</figure>'

    if kind == "callout":
        # «see» подставляет в промпт буквальный текст соседнего блока (обычно код),
        # чтобы модель описывала то, что там действительно написано.
        extra = ""
        if block.get("see"):
            extra = ("\n\nВот код, о котором идёт речь. Описывай только то, что в нём есть, "
                     "ничего не додумывай:\n```\n" + block["see"] + "\n```")
        body = ask(
            f"{ctx}\n\nНапиши текст врезки «{block['title']}» примерно на {block.get('words', 90)} слов. "
            f"Абзацы в <p>. Заголовок врезки уже проставлен, повторять его в тексте не нужно."
            f"\n\nСодержание:\n{block['brief']}{extra}"
        )
        body = strip_repeated_title(body, block["title"])
        return (f'<div class="callout {block["kind"]}">\n'
                f'<span class="ct">{block["title"]}</span>\n{body}\n</div>')

    if kind == "deeper":
        # Раскрывающийся вывод формулы. Шаги берутся из спеки буквально: модель
        # только разворачивает их в связный текст, не добавляя своих выкладок.
        steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(block["steps"]))
        body = ask(
            f"{ctx}\n\nРазверни вывод ниже в связный текст примерно на "
            f"{block.get('words', 260)} слов. Идти строго по шагам, в том же порядке, "
            f"с теми же обозначениями. Своих шагов не добавлять, обозначения не менять, "
            f"числа не придумывать. Формулы и обозначения оборачивай в <code>. "
            f"Абзацы в <p>.\n\nЧто выводим: {block['brief']}\n\nШаги вывода:\n{steps}"
        )
        return (f'<details class="deeper">\n<summary>{block["title"]}</summary>\n'
                f'<div class="deeper-body">\n{body}\n</div>\n</details>')

    if kind == "sources":
        # Ссылки на первоисточники. Пишутся руками в спеке и не проходят через модель:
        # выдуманная ссылка хуже отсутствующей.
        items = []
        for it in block["items"]:
            ref = f'<a href="{it["url"]}" target="_blank" rel="noopener">{it["ref"]}</a>' \
                if it.get("url") else it["ref"]
            note = f'. {it["note"]}' if it.get("note") else ""
            items.append(f"<li>{ref}{note}</li>")
        title = block.get("title", "Где про это написано подробнее")
        return ('<div class="sources">\n<span class="ct">' + title + "</span>\n<ul>\n"
                + "\n".join(items) + "\n</ul>\n</div>")

    if kind == "table":
        return f'<div class="table-wrap">\n{block["html"]}\n</div>'

    if kind == "code":
        label = f'<div class="code-label">{block.get("label", "python")}</div>\n'
        return label + f'<pre><code>{block["code"]}</code></pre>'

    if kind == "html":
        return block["html"]

    if kind == "formula":
        note = ask(
            f"{ctx}\n\nПоясни формулу <code>{block['fx']}</code> в 40-60 словах. "
            f"Верни только текст без тегов.\n\nЧто пояснить:\n{block['brief']}"
        )
        note = re.sub(r"</?p>", "", note).strip()
        return (f'<div class="formula"><span class="fx">{block["fx"]}</span>'
                f'<span class="fnote">{note}</span></div>')

    raise ValueError(f"неизвестный тип блока: {kind}")


def build_quiz(questions: list[dict], ctx: str) -> str:
    def one(idx_q):
        idx, q = idx_q
        why = ask(
            f"{ctx}\n\nНапиши объяснение правильного ответа на вопрос квиза, 45-70 слов. "
            f"Без тегов, только текст. Объясни, почему верен правильный вариант "
            f"и чем плохи остальные.\n\n"
            f"Вопрос: {q['q']}\nПравильный ответ: {q['opts'][q['right']]}\n"
            f"Другие варианты: {'; '.join(o for i, o in enumerate(q['opts']) if i != q['right'])}\n"
            f"Опора: {q.get('hint', '')}"
        )
        why = re.sub(r"</?p>", "", why).strip()
        opts = "\n".join(
            f'<label class="opt"{" data-correct=\"1\"" if i == q["right"] else ""}>'
            f'<input type="radio" name="q{idx + 1}">{o}</label>'
            for i, o in enumerate(q["opts"])
        )
        return (f'<div class="q">\n<p class="qt">{idx + 1}. {q["q"]}</p>\n{opts}\n'
                f'<div class="why">{why}</div>\n</div>')

    with ThreadPoolExecutor(max_workers=8) as pool:
        blocks = list(pool.map(one, enumerate(questions)))

    return ('<div class="quiz">\n<h3>Проверьте себя</h3>\n'
            f'<p class="quiz-sub">{len(questions)} вопроса. Ответ показывается сразу с объяснением.</p>\n'
            + "\n".join(blocks) +
            '\n<div class="quiz-actions">\n<button class="btn ghost quiz-reset">Пройти заново</button>\n'
            '<span class="quiz-score"></span>\n</div>\n</div>')


PAGE = """<!doctype html>
<html lang="ru" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Глава {num}. {title} · AI-инженер с нуля</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>

<header class="topbar">
  <button class="icon-btn" id="menu-toggle" aria-label="Меню">☰</button>
  <a class="brand" href="index.html">AI-инженер <span>с нуля</span></a>
  <div class="spacer"></div>
  <div class="search-wrap">
    <input id="search-input" type="search" placeholder="Поиск   ⌘K" autocomplete="off">
    <div id="search-results"></div>
  </div>
  <button class="icon-btn" id="theme-toggle">Тёмная</button>
</header>

<div class="layout">
  <nav class="sidebar" id="sidebar"></nav>

  <main>
    <article>

      <header class="chapter-head">
        <div class="kicker">{part} · глава {num}</div>
        <h1>{title}</h1>
        <p class="standfirst">{standfirst}</p>
        <div class="chapter-meta">{meta}</div>
      </header>

{body}

{recap}

{quiz}

      <button class="mark-read" id="mark-read">Отметить главу как пройденную</button>
      <nav class="chapter-nav" id="chapter-nav"></nav>

    </article>
  </main>

  <aside class="on-page" id="on-page"></aside>
</div>

<div id="tooltip"></div>

<script src="assets/toc.js"></script>
<script src="assets/glossary.js"></script>
<script src="assets/search-index.js"></script>
<script src="assets/app.js"></script>
{scripts}
</body>
</html>
"""


def build_chapter(spec: dict, workers: int) -> str:
    ctx = (f"Глава {spec['num']} учебника, называется «{spec['title']}». "
           f"О чём глава: {spec['about']}. "
           f"Читатель уже прошёл предыдущие главы, поэтому термины оттуда можно "
           f"использовать без повторного объяснения: {spec.get('known', 'нет')}.")

    # плоский список всех задач на генерацию, чтобы гнать их одним пулом
    jobs: list[tuple[int, int, dict]] = []
    for si, sec in enumerate(spec["sections"]):
        for bi, blk in enumerate(sec["blocks"]):
            jobs.append((si, bi, blk))

    print(f"глава {spec['num']}: {len(spec['sections'])} разделов, "
          f"{len(jobs)} блоков, {workers} потоков")

    section_ctx = {
        si: ctx + f" Сейчас пишется раздел «{sec['h2']}»: {sec.get('brief', '')}"
        for si, sec in enumerate(spec["sections"])
    }

    def run(job):
        si, bi, blk = job
        return (si, bi, build_block(blk, section_ctx[si]))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        done = list(pool.map(run, jobs))

    built: dict[tuple[int, int], str] = {(si, bi): html for si, bi, html in done}

    # standfirst, итоги и квиз параллельно с остальным не гоняем: они зависят от темы целиком
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_stand = pool.submit(
            ask, f"{ctx}\n\nНапиши лид главы: 2-3 предложения, до 45 слов, что читатель "
                 f"поймёт к концу. Только текст без тегов."
        )
        f_recap = pool.submit(
            ask, f"{ctx}\n\nНапиши итоги главы: {len(spec['recap'])} пунктов, каждый "
                 f"одно-два предложения. Верни только <li>…</li> подряд, без <ol>.\n\n"
                 f"О чём пункты по порядку:\n" + "\n".join(f"- {r}" for r in spec["recap"])
        )
        f_quiz = pool.submit(build_quiz, spec["quiz"], ctx)
        standfirst = re.sub(r"</?p>", "", f_stand.result()).strip()
        recap_items = f_recap.result()
        quiz = f_quiz.result()

    parts = []
    for si, sec in enumerate(spec["sections"]):
        parts.append(f'      <h2 id="{sec["id"]}">{sec["h2"]}</h2>')
        for bi in range(len(sec["blocks"])):
            parts.append(built[(si, bi)])

    recap = ('<div class="recap">\n<h3>Коротко</h3>\n<ol>\n'
             + re.sub(r"</?ol>", "", recap_items).strip() + "\n</ol>\n</div>")

    return PAGE.format(
        num=spec["num"],
        title=spec["title"],
        part=spec["part"],
        standfirst=standfirst,
        meta="".join(f"<span>{m}</span>" for m in spec["meta"]),
        body="\n\n".join(parts),
        recap=recap,
        quiz=quiz,
        scripts=spec.get("scripts", ""),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "site"))
    args = ap.parse_args()

    for s in args.specs:
        spec = json.loads(Path(s).read_text(encoding="utf-8"))
        html = build_chapter(spec, args.workers)
        dest = Path(args.out) / f"{spec['id']}.html"
        dest.write_text(html, encoding="utf-8")
        print(f"  записано: {dest}  ({len(html):,} байт)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

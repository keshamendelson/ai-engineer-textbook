#!/usr/bin/env python3
"""Пересчёт времени чтения и практики по фактическому объёму глав.

Считает по каждой главе: слова прозы, схемы, демо, вопросы квиза и трудоёмкость
заданий. Из этого получаются две раздельные цифры, «N минут чтения» и «M часов
с практикой». Обе прописываются в chapter-meta главы, в tags в assets/toc.js
и в плашки на главной.

    python3 tools/estimate_time.py            # показать таблицу, ничего не менять
    python3 tools/estimate_time.py --write    # записать пересчитанные цифры
    python3 tools/estimate_time.py --json out.json

Формула чтения: слова / 160 плюс минута на схему, две минуты на интерактивное
демо, минута на вопрос квиза. Из подсчёта слов исключены код, подписи внутри
SVG, тексты демо и квиза, навигация и боковое меню: это либо считается отдельно,
либо не читается подряд.
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

WPM = 160  # слов в минуту, темп чтения учебного текста на родном языке
MIN_PER_FIGURE = 1
MIN_PER_DEMO = 2
MIN_PER_QUIZ = 1

# трудоёмкость практики, когда в подписи к заданию нет явного времени
DEFAULT_PRACTICE_MIN = 30
PRACTICE_PHRASES = [
    (r"проект на выходны", 480),
    (r"проект на вечер", 180),
    (r"за один день", 360),
    (r"на вечер", 180),
]

WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё‑-]*")
TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------- разбор HTML


def _matching_end(html: str, from_idx: int, tag: str) -> int:
    """Индекс сразу за парным закрывающим тегом, с учётом вложенности."""
    pat = re.compile(rf"<(/?){tag}\b", re.I)
    depth, i = 1, from_idx
    while depth:
        m = pat.search(html, i)
        if not m:
            return len(html)
        depth += -1 if m.group(1) else 1
        i = m.end()
    gt = html.find(">", i)
    return gt + 1 if gt != -1 else len(html)


def drop_blocks(html: str, open_pattern: str, tag: str) -> str:
    """Вырезать все элементы tag, чьё открытие совпало с open_pattern."""
    out, pos = [], 0
    for m in re.finditer(open_pattern, html, re.I):
        if m.start() < pos:
            continue
        out.append(html[pos : m.start()])
        pos = _matching_end(html, m.end(), tag)
    out.append(html[pos:])
    return "".join(out)


def article_of(html: str) -> str:
    m = re.search(r"<article\b[^>]*>", html)
    if not m:
        return html
    return html[m.end() : _matching_end(html, m.end(), "article")]


def reading_text(article: str) -> str:
    """Оставить только то, что читается подряд глазами."""
    body = article
    for pattern, tag in [
        (r"<svg\b", "svg"),
        (r"<pre\b", "pre"),
        (r'<div class="quiz"', "div"),
        (r'<div class="demo"', "div"),
        (r'<div class="chapter-meta"', "div"),
        (r"<nav\b", "nav"),
        (r"<script\b", "script"),
        (r"<style\b", "style"),
        (r'<button\b', "button"),
    ]:
        body = drop_blocks(body, pattern, tag)
    body = TAG_RE.sub(" ", body)
    return html_mod.unescape(body)


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def practice_minutes(article: str) -> tuple[int, list[str]]:
    """Трудоёмкость заданий в конце главы плюс подписи, откуда она взялась."""
    total, labels = 0, []
    for m in re.finditer(r'<div class="callout practice"', article):
        block = article[m.start() : _matching_end(article, m.end(), "div")]
        ct = re.search(r'<span class="ct">(.*?)</span>', block, re.S)
        label = html_mod.unescape(TAG_RE.sub("", ct.group(1))).strip() if ct else ""
        low = label.lower()
        minutes = None
        hours_m = re.search(r"(\d+)\s*час", low)
        mins_m = re.search(r"(\d+)\s*мин", low)
        if mins_m:
            minutes = int(mins_m.group(1))
        elif hours_m:
            minutes = int(hours_m.group(1)) * 60
        else:
            for phrase, val in PRACTICE_PHRASES:
                if re.search(phrase, low):
                    minutes = val
                    break
        if minutes is None:
            minutes = DEFAULT_PRACTICE_MIN
            label = (label or "без подписи") + " (взято по умолчанию)"
        total += minutes
        labels.append(f"{label}: {minutes} мин")
    return total, labels


def measure(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    art = article_of(raw)
    words = count_words(reading_text(art))
    figures = len(re.findall(r"<figure\b", art))
    demos = len(re.findall(r'<div class="demo"', art))
    quiz = len(re.findall(r'<div class="q">', art))
    code_lines = sum(
        block.count("\n") for block in re.findall(r"<pre\b.*?</pre>", art, re.S)
    )
    prac, labels = practice_minutes(art)
    # всё, что напечатано в главе: проза плюс квиз, код и подписи в схемах.
    # Эта цифра больше, но она не про темп чтения, а про объём материала.
    all_words = count_words(html_mod.unescape(TAG_RE.sub(" ", art)))
    read_min = round(
        words / WPM + figures * MIN_PER_FIGURE + demos * MIN_PER_DEMO + quiz * MIN_PER_QUIZ
    )
    return {
        "id": path.stem,
        "words": words,
        "all_words": all_words,
        "figures": figures,
        "demos": demos,
        "quiz": quiz,
        "code_lines": code_lines,
        "read_min": read_min,
        "practice_min": prac,
        "practice_labels": labels,
        "total_min": read_min + prac,
    }


# ------------------------------------------------------------------- вывод


def fmt_hours(minutes: int) -> str:
    """Часы с шагом в полчаса, десятичная запятая."""
    h = round(minutes / 30) / 2
    if h < 0.5:
        h = 0.5
    return (f"{h:.1f}".rstrip("0").rstrip(".") if h % 1 else f"{int(h)}").replace(".", ",")


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русское согласование числительного: 21 минута, 22 минуты, 25 минут."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def meta_time(st: dict) -> str:
    n = st["read_min"]
    return f"{n} {plural(n, 'минута', 'минуты', 'минут')} чтения"


def meta_practice(st: dict) -> str:
    return f"{fmt_hours(st['total_min'])} ч с практикой"


# ------------------------------------------------------------------ запись


def patch_chapter_meta(path: Path, st: dict, write: bool) -> str | None:
    raw = path.read_text(encoding="utf-8")
    m = re.search(r'(<div class="chapter-meta">)(.*?)(</div>)', raw, re.S)
    if not m:
        return None
    body = m.group(2)
    spans = re.findall(r"<span>(.*?)</span>", body, re.S)
    if not spans:
        return None
    spans = [" ".join(s.split()) for s in spans]
    # если прошлые прогоны надобавляли повторов времени, оставляем один
    seen_time = False
    uniq = []
    for sp in spans:
        is_time = bool(re.match(r"^[~\d][\d.,]*\s*(минут|мин)", sp))
        if is_time and seen_time:
            continue
        seen_time = seen_time or is_time
        uniq.append(sp)
    spans = uniq
    old = list(spans)
    # первый пункт плашки это время чтения, но в свежих спеках его может не быть:
    # тогда вставляем, а не затираем требования к главам
    if re.match(r"^[~\d][\d.,]*\s*(минут|мин|час|ч)", spans[0]):
        spans[0] = meta_time(st)
    else:
        spans.insert(0, meta_time(st))
    prac_txt = meta_practice(st)
    idx = next((i for i, s in enumerate(spans) if "с практикой" in s), None)
    if st["practice_min"] > 0:
        if idx is None:
            spans.insert(1, prac_txt)
        else:
            spans[idx] = prac_txt
    elif idx is not None:
        spans.pop(idx)

    if "\n" in body:
        ind = re.search(r"\n([ \t]*)<span>", body)
        indent = ind.group(1) if ind else "          "
        tail = re.search(r"\n([ \t]*)$", body)
        tail_ind = tail.group(1) if tail else indent[:-2]
        new_body = "".join(f"\n{indent}<span>{s}</span>" for s in spans) + f"\n{tail_ind}"
    else:
        new_body = "".join(f"<span>{s}</span>" for s in spans)

    if new_body == body:
        return None
    if write:
        path.write_text(raw[: m.start(2)] + new_body + raw[m.end(2) :], encoding="utf-8")
    return f"{old[0]} -> {spans[0]}" + (
        f" + {prac_txt}" if st["practice_min"] > 0 else " (практики в главе нет)"
    )


def patch_toc(stats: dict[str, dict], write: bool) -> list[str]:
    path = SITE / "assets" / "toc.js"
    raw = path.read_text(encoding="utf-8")
    changes = []

    def new_tags(cid: str, old: str) -> str:
        st = stats[cid]
        parts = [p.strip() for p in old.split("·") if p.strip()]
        rest = [
            p
            for p in parts
            if not re.match(r"^[~\d]+[\d,\.]*\s*(минут|мин|час|ч)\b", p)
            and "с практикой" not in p
        ]
        head = [f"{st['read_min']} мин чтения"]
        if st["practice_min"] > 0:
            head.append(f"{fmt_hours(st['total_min'])} ч с практикой")
        return " · ".join(head + rest)

    out, pos = [], 0
    for m in re.finditer(r'id:\s*"(ch\d+)"', raw):
        cid = m.group(1)
        if cid not in stats:
            continue
        tm = re.search(r'tags:\s*"([^"]*)"', raw[m.end() :])
        if not tm:
            continue
        s, e = m.end() + tm.start(1), m.end() + tm.end(1)
        old = raw[s:e]
        new = new_tags(cid, old)
        if new != old:
            changes.append(f"{cid}: {old} -> {new}")
        out.append(raw[pos:s])
        out.append(new)
        pos = e
    out.append(raw[pos:])
    if write and changes:
        path.write_text("".join(out), encoding="utf-8")
    return changes


def patch_index(stats: dict[str, dict], write: bool) -> str | None:
    path = SITE / "index.html"
    raw = path.read_text(encoding="utf-8")
    m = re.search(r'(<div class="stats">)(.*?)(</div>\s*</section>)', raw, re.S)
    if not m:
        return None
    chapters = len(stats)
    apps = len(list(SITE.glob("app-*.html")))
    svgs = sum(f.read_text(encoding="utf-8").count("<svg") for f in SITE.glob("*.html"))
    quiz = sum(s["quiz"] for s in stats.values())
    read_h = sum(s["read_min"] for s in stats.values()) / 60
    total_h = sum(s["total_min"] for s in stats.values()) / 60
    tiles = [
        (str(chapters), f"{plural(chapters, 'глава', 'главы', 'глав')} и {apps} "
                        f"{plural(apps, 'приложение', 'приложения', 'приложений')}"),
        (str(svgs), f"{plural(svgs, 'схема', 'схемы', 'схем')} и "
                    f"{plural(svgs, 'иллюстрация', 'иллюстрации', 'иллюстраций')}"),
        (str(quiz), f"{plural(quiz, 'вопрос', 'вопроса', 'вопросов')} с разбором"),
        (f"~{round(read_h)} ч", "чтения без практики"),
        (f"~{round(total_h)} ч", "вместе с задачами"),
    ]
    body = "\n" + "\n".join(
        f'        <div class="stat"><b>{b}</b><span>{s}</span></div>' for b, s in tiles
    ) + "\n      "
    new_raw = raw[: m.start(2)] + body + raw[m.end(2) :]
    new_raw, routes = patch_routes(new_raw, stats)
    if new_raw == raw:
        return None
    new_raw = re.sub(r'(<meta name="description" content="[^"]*?)\d+ глав[а-я]*',
                     lambda m: f"{m.group(1)}{chapters} "
                               f"{plural(chapters, 'глава', 'главы', 'глав')}", new_raw)
    if write:
        path.write_text(new_raw, encoding="utf-8")
    line = (
        f"главная: {chapters} глав, {svgs} схем, {quiz} вопросов, "
        f"~{round(read_h)} ч чтения, ~{round(total_h)} ч с практикой"
    )
    return line + ("\n  маршруты: " + ", ".join(routes) if routes else "")


def patch_routes(raw: str, stats: dict[str, dict]) -> tuple[str, list[str]]:
    """Проставить в трёх маршрутах часы, посчитанные по входящим главам."""
    out, pos, report = [], 0, []
    for m in re.finditer(r"<b>([А-Яа-яЁё]+(?: [а-яё]+)?),\s*([^<]*?)\.?</b>(.*?)</p>", raw, re.S):
        name, tail = m.group(1), m.group(3)
        nums = re.findall(r"\b(\d{1,2})\b", tail.split(".")[0])
        ids = [f"ch{int(n):02d}" for n in nums] if nums else list(stats)
        ids = [i for i in ids if i in stats]
        if not ids:
            continue
        h = round(sum(stats[i]["total_min"] for i in ids) / 60)
        label = f"{name}, около {h} {plural(h, 'часа', 'часов', 'часов')}."
        out.append(raw[pos : m.start()])
        out.append(f"<b>{label}</b>{tail}</p>")
        pos = m.end()
        report.append(f"{name} {h} ч по {len(ids)} главам")
    out.append(raw[pos:])
    return "".join(out), report


# -------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="записать изменения")
    ap.add_argument("--json", metavar="PATH", help="сохранить замеры в JSON")
    ap.add_argument("--verbose", action="store_true", help="показать разбор практики")
    args = ap.parse_args()

    files = sorted(SITE.glob("ch*.html"))
    if not files:
        print("не найдено ни одной главы в site/", file=sys.stderr)
        return 1
    stats = {f.stem: measure(f) for f in files}

    head = f"{'глава':7} {'слов':>6} {'схем':>5} {'демо':>5} {'вопр':>5} {'кода':>5} {'чтение':>8} {'практика':>9} {'итого':>7}"
    print(head)
    print("-" * len(head))
    for cid, s in stats.items():
        print(
            f"{cid:7} {s['words']:>6} {s['figures']:>5} {s['demos']:>5} {s['quiz']:>5} "
            f"{s['code_lines']:>5} {s['read_min']:>6} мин {s['practice_min']:>6} мин "
            f"{fmt_hours(s['total_min']):>5} ч"
        )
    tw = sum(s["words"] for s in stats.values())
    tr = sum(s["read_min"] for s in stats.values())
    tp = sum(s["practice_min"] for s in stats.values())
    print("-" * len(head))
    print(
        f"{'всего':7} {tw:>6} "
        f"{sum(s['figures'] for s in stats.values()):>5} "
        f"{sum(s['demos'] for s in stats.values()):>5} "
        f"{sum(s['quiz'] for s in stats.values()):>5} "
        f"{sum(s['code_lines'] for s in stats.values()):>5} "
        f"{tr:>6} мин {tp:>6} мин {fmt_hours(tr + tp):>5} ч"
    )
    ta = sum(s["all_words"] for s in stats.values())
    print(
        f"\nчтение {tr / 60:.1f} ч, практика {tp / 60:.1f} ч, вместе {(tr + tp) / 60:.1f} ч"
    )
    print(
        f"слов прозы {tw}, всего печатных слов в главах {ta} "
        f"(проза плюс квиз, код и подписи в схемах)"
    )

    empty = [cid for cid, s in stats.items() if s["practice_min"] == 0]
    if empty:
        print(f"без блока практики: {', '.join(empty)}")
    if args.verbose:
        for cid, s in stats.items():
            for lab in s["practice_labels"]:
                print(f"  {cid}: {lab}")

    print()
    for f in files:
        r = patch_chapter_meta(f, stats[f.stem], args.write)
        if r:
            print(f"{f.stem}: {r}")
    for line in patch_toc(stats, args.write):
        print(line)
    idx = patch_index(stats, args.write)
    if idx:
        print(idx)
    print("\nрежим просмотра, ничего не записано" if not args.write else "\nзаписано")

    if args.json:
        Path(args.json).write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

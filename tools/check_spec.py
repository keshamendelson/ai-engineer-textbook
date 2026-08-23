#!/usr/bin/env python3
"""Проверка спеки главы до сборки: дешевле поймать ошибку здесь, чем после генерации.

Смотрит обязательные поля, типы блоков, оформление SVG, ключи к квизу и объём прозы.

    python3 tools/check_spec.py specs/ch20.json
    python3 tools/check_spec.py specs/*.json --fail
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOP = ["id", "num", "part", "title", "about", "known", "meta", "sections", "recap", "quiz"]

BLOCK_FIELDS = {
    "prose": ["brief"],
    "figure": ["caption", "svg"],
    "callout": ["kind", "title", "brief"],
    "table": ["html"],
    "code": ["code"],
    "html": ["html"],
    "formula": ["fx", "brief"],
    "deeper": ["title", "brief", "steps"],
    "sources": ["items"],
}

CALLOUT_KINDS = {"info", "analogy", "warn", "practice", "math", "danger"}

# классы оформления схем, объявленные в style.css
SVG_CLASSES = {
    "s-bg", "s-box", "s-box-a", "s-box-w", "s-box-g", "s-box-v",
    "s-line", "s-line-a", "s-line-d",
    "s-t", "s-t-s", "s-t-xs", "s-t-b", "s-t-a",
    "s-fill-a", "s-fill-2", "s-fill-3", "s-mono",
}

DASH_RE = re.compile(r"[—–]")

# Те же правила стиля, что и в lint.py, только применяются к заданиям для модели:
# антитеза в задании почти всегда превращается в антитезу в готовом тексте.
STYLE = [
    (re.compile(r"\bне просто\b", re.I), "антитеза «не просто»"),
    (re.compile(r"\bне [^.,;:!?]{2,60}, а (?:не\s+)?[а-яё]", re.I), "антитеза «не X, а Y»"),
    (re.compile(r"[а-яё]{3,}, а не [а-яё]", re.I), "антитеза «X, а не Y»"),
    (re.compile(r"\b(являет|являют)ся\b", re.I), "канцелярит «является»"),
    (re.compile(r"\bпредставля[ею]т собой\b", re.I), "канцелярит «представляет собой»"),
    (re.compile(r"\bв рамках\b", re.I), "канцелярит «в рамках»"),
    (re.compile(r"\bосуществля[ею]т", re.I), "канцелярит «осуществляет»"),
    (re.compile(r"\bиграет (?:ключевую|важную|значимую|решающую)\b", re.I), "раздутая значимость"),
]


def walk_strings(node, path="") -> list[tuple[str, str]]:
    out = []
    if isinstance(node, str):
        out.append((path, node))
    elif isinstance(node, dict):
        for k, v in node.items():
            out += walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += walk_strings(v, f"{path}[{i}]")
    return out


def check(path: Path, css_classes: set[str]) -> list[str]:
    errs: list[str] = []
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"не разобрался JSON: {e}"]

    for f in TOP:
        if f not in spec:
            errs.append(f"нет поля {f}")
    if errs:
        return errs

    if spec["id"] != path.stem:
        errs.append(f"id {spec['id']} не совпал с именем файла {path.stem}")
    if not str(spec["num"]) or not str(spec["num"]).isdigit():
        errs.append("num должен быть числом строкой")

    # разделы и блоки
    sec_ids, svg_ids, prose_words = set(), set(), 0
    for si, sec in enumerate(spec["sections"]):
        for f in ("id", "h2", "blocks"):
            if f not in sec:
                errs.append(f"раздел {si}: нет поля {f}")
        sid = sec.get("id", "")
        if sid in sec_ids:
            errs.append(f"раздел {si}: повтор id «{sid}»")
        sec_ids.add(sid)
        if not re.fullmatch(r"[a-z0-9-]+", sid or ""):
            errs.append(f"раздел {si}: id «{sid}» не из латиницы в нижнем регистре")

        for bi, blk in enumerate(sec.get("blocks", [])):
            where = f"раздел {si} «{sec.get('h2', '')}», блок {bi}"
            kind = blk.get("type")
            if kind not in BLOCK_FIELDS:
                errs.append(f"{where}: неизвестный тип «{kind}»")
                continue
            for f in BLOCK_FIELDS[kind]:
                if f not in blk:
                    errs.append(f"{where} ({kind}): нет поля {f}")
            if kind == "prose":
                prose_words += blk.get("words", 160)
            if kind == "callout" and blk.get("kind") not in CALLOUT_KINDS:
                errs.append(f"{where}: врезка вида «{blk.get('kind')}» не существует")
            if kind == "deeper":
                if not isinstance(blk.get("steps"), list) or len(blk.get("steps", [])) < 2:
                    errs.append(f"{where}: в deeper нужен список steps хотя бы из двух шагов")
                prose_words += blk.get("words", 260)
            if kind == "sources":
                for it in blk.get("items", []):
                    if "ref" not in it:
                        errs.append(f"{where}: у источника нет поля ref")
                    if it.get("url", "").startswith("http") is False and "url" in it:
                        errs.append(f"{where}: url «{it['url']}» не похож на ссылку")
            if kind == "figure":
                svg = blk.get("svg", "")
                if "viewBox" not in svg:
                    errs.append(f"{where}: в SVG нет viewBox")
                if 'role="img"' not in svg or "aria-label" not in svg:
                    errs.append(f"{where}: в SVG нет role=img и aria-label")
                for cls in re.findall(r'class="([^"]+)"', svg):
                    for c in cls.split():
                        if c not in css_classes:
                            errs.append(f"{where}: класс «{c}» не объявлен в style.css")
                        elif c not in SVG_CLASSES:
                            errs.append(f"{where}: класс «{c}» не из набора для схем")
                for eid in re.findall(r'\sid="([^"]+)"', svg):
                    if eid in svg_ids:
                        errs.append(f"{where}: повтор id «{eid}» в SVG главы")
                    svg_ids.add(eid)
                if re.search(r"font-size|fill=\"#|stroke=\"#", svg):
                    errs.append(f"{where}: в SVG зашит цвет или размер, тёмная тема сломается")

    # квиз
    for qi, q in enumerate(spec["quiz"]):
        if not all(f in q for f in ("q", "opts", "right")):
            errs.append(f"вопрос {qi}: нужны поля q, opts, right")
            continue
        if len(q["opts"]) < 3:
            errs.append(f"вопрос {qi}: меньше трёх вариантов")
        if not 0 <= q["right"] < len(q["opts"]):
            errs.append(f"вопрос {qi}: right вне диапазона")
        if not q.get("hint"):
            errs.append(f"вопрос {qi}: нет hint, объяснение придётся выдумывать модели")
    if len(spec["quiz"]) < 5:
        errs.append(f"в квизе {len(spec['quiz'])} вопросов, надо хотя бы 5")
    if len(spec["recap"]) < 4:
        errs.append(f"в итогах {len(spec['recap'])} пунктов, надо хотя бы 4")

    # тире, стиль и объём
    for where, s in walk_strings(spec):
        if ".svg" in where or ".html" in where or ".code" in where:
            continue
        if DASH_RE.search(s):
            errs.append(f"длинное тире в {where}: …{s[max(0, DASH_RE.search(s).start() - 30):][:60]}…")
        for rx, why in STYLE:
            m = rx.search(s)
            if m:
                errs.append(f"{why} в {where}: …{' '.join(s[max(0, m.start() - 40):m.start() + 60].split())}…")
    if prose_words < 2000:
        errs.append(f"проза на {prose_words} слов, для новой главы мало")

    print(f"{path.name}: {prose_words} слов прозы, {len(spec['sections'])} разделов, "
          f"{sum(1 for s in spec['sections'] for b in s['blocks'] if b['type'] == 'figure')} схем, "
          f"{len(spec['quiz'])} вопросов")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--fail", action="store_true", help="ненулевой код при находках")
    args = ap.parse_args()

    css = (Path(__file__).resolve().parent.parent / "site" / "assets" / "style.css").read_text(
        encoding="utf-8"
    )
    css_classes = set(re.findall(r"\.([a-z][a-z0-9-]*)", css)) | SVG_CLASSES

    total = 0
    for s in args.specs:
        errs = check(Path(s), css_classes)
        total += len(errs)
        for e in errs:
            print(f"  · {e}")
    print(f"\nвсего находок: {total}")
    return 1 if (args.fail and total) else 0


if __name__ == "__main__":
    raise SystemExit(main())

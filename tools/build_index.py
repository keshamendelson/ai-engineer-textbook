#!/usr/bin/env python3
"""Собирает поисковый индекс по готовым главам в assets/search-index.js.

Индексируется каждый раздел главы отдельно, чтобы поиск вёл сразу к нужному
месту, а не к началу страницы. Работает без сервера: индекс подключается
обычным тегом script.
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def clean(fragment: str) -> str:
    fragment = re.sub(r"<(pre|svg|script|style)\b.*?</\1>", " ", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    return re.sub(r"\s+", " ", fragment).strip()


def title_of(src: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", src, re.S)
    return clean(m.group(1)) if m else ""


def sections(src: str):
    """Режет статью по h2, возвращает (якорь, заголовок, текст)."""
    body = re.search(r"<article>(.*?)</article>", src, re.S)
    if not body:
        return
    art = body.group(1)

    heads = list(re.finditer(r'<h2[^>]*id="([^"]+)"[^>]*>(.*?)</h2>', art, re.S))
    if not heads:
        yield "", "", clean(art)
        return

    intro = clean(art[: heads[0].start()])
    if len(intro) > 80:
        yield "", "", intro

    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(art)
        yield m.group(1), clean(m.group(2)), clean(art[m.end():end])


def main() -> None:
    records = []
    files = sorted(SITE.glob("ch*.html")) + sorted(SITE.glob("app-*.html"))

    for path in files:
        src = path.read_text(encoding="utf-8")
        chapter = title_of(src)
        for anchor, head, text in sections(src):
            if len(text) < 60:
                continue
            records.append({
                "href": path.name + (f"#{anchor}" if anchor else ""),
                "chapter": chapter,
                "title": head or chapter,
                "body": text[:1800],
            })

    js = "window.SEARCH_INDEX = " + json.dumps(records, ensure_ascii=False) + ";\n"
    out = SITE / "assets" / "search-index.js"
    out.write_text(js, encoding="utf-8")
    size = out.stat().st_size / 1024
    print(f"индекс: {len(records)} разделов из {len(files)} файлов, {size:.0f} КБ")


if __name__ == "__main__":
    main()

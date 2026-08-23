#!/usr/bin/env python3
"""Подчёркивает термины из глоссария в тексте глав, чтобы работали подсказки.

Помечается только первое вхождение термина в главе и только в обычных абзацах.
Код, схемы, заголовки, ссылки и уже помеченные места не трогаются.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glossary_data import TERMS, slug_map  # noqa: E402

SLUGS = slug_map()

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

# Длинные термины идут первыми, чтобы «многоголовое внимание» не съелось «вниманием».
NAMES = sorted({t[0] for t in TERMS}, key=len, reverse=True)

# Куски, внутри которых заменять нельзя.
PROTECTED = re.compile(
    r"<(pre|svg|script|style|code|title|h1|h2|h3|h4|a|figcaption)\b.*?</\1>|<[^>]+>",
    re.S,
)


def term_link(name: str, shown: str) -> str:
    """Термин в тексте это ссылка на статью глоссария плюс подсказка при наведении."""
    key = name.lower()
    href = f' href="app-a.html#t-{SLUGS[key]}"' if key in SLUGS else ""
    return f'<a class="term"{href} data-term="{key}">{shown}</a>'


def relink(src: str) -> tuple[str, int]:
    """Старая разметка терминов тегом span превращается в ссылку на глоссарий."""
    n = 0

    def one(m: re.Match) -> str:
        nonlocal n
        n += 1
        return term_link(m.group(1), m.group(2))

    return re.sub(r'<span class="term" data-term="([^"]+)">(.*?)</span>', one, src, flags=re.S), n


def mark(src: str) -> tuple[str, int]:
    used: set[str] = set()
    count = 0

    # Разбиваем документ на куски: защищённые и обычные.
    parts: list[tuple[bool, str]] = []
    pos = 0
    for m in PROTECTED.finditer(src):
        if m.start() > pos:
            parts.append((False, src[pos:m.start()]))
        parts.append((True, m.group(0)))
        pos = m.end()
    parts.append((False, src[pos:]))

    out: list[str] = []
    for protected, chunk in parts:
        if protected or not chunk.strip():
            out.append(chunk)
            continue
        for name in NAMES:
            if name in used:
                continue
            # только целое слово, с учётом русской морфологии не заморачиваемся:
            # берём точное написание термина
            pattern = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
            m = pattern.search(chunk)
            if not m:
                continue
            chunk = chunk[:m.start()] + term_link(name, m.group(0)) + chunk[m.end():]
            used.add(name)
            count += 1
        out.append(chunk)

    return "".join(out), count


def main() -> None:
    total = new_links = 0
    for path in sorted(SITE.glob("ch*.html")):
        src = path.read_text(encoding="utf-8")
        if '<span class="term"' in src:
            src, n = relink(src)
            path.write_text(src, encoding="utf-8")
            new_links += n
            print(f"{path.name}: {n} терминов переведено в ссылки")
            continue
        if 'class="term"' in src:
            print(f"{path.name}: уже размечено, пропускаю")
            continue
        marked, n = mark(src)
        path.write_text(marked, encoding="utf-8")
        total += n
        print(f"{path.name}: {n} терминов")
    print(f"\nновых подсказок: {total}, старых переведено в ссылки: {new_links}")


if __name__ == "__main__":
    main()

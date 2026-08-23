#!/usr/bin/env python3
"""Проверка ссылок: выдуманная ссылка на источник хуже отсутствующей.

Собирает все http-ссылки из указанных файлов и дёргает каждую. Работает и по
спекам, и по готовым главам.

    python3 tools/check_links.py specs/*.json
    python3 tools/check_links.py site/*.html --fail
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL_RE = re.compile(r'https?://[^\s"<>\\)]+')
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 textbook-link-check"


def check(url: str) -> tuple[str, str]:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return url, f"{r.status} ок"
        except urllib.error.HTTPError as e:
            if e.code in (403, 405) and method == "HEAD":
                continue
            return url, f"{e.code} {e.reason}"
        except Exception as e:  # сеть, таймаут, сертификат
            if method == "HEAD":
                continue
            return url, f"сбой: {type(e).__name__}"
    return url, "сбой"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    where: dict[str, set[str]] = {}
    for f in args.files:
        text = Path(f).read_text(encoding="utf-8")
        for u in URL_RE.findall(text):
            where.setdefault(u.rstrip(".,;"), set()).add(Path(f).name)

    if not where:
        print("ссылок не найдено")
        return 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(check, sorted(where)))

    bad = 0
    for url, status in results:
        if "ок" in status:
            continue
        bad += 1
        print(f"{status:22} {url}   [{', '.join(sorted(where[url]))}]")
    print(f"\nпроверено {len(results)}, битых {bad}")
    return 1 if (args.fail and bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())

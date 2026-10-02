#!/usr/bin/env bash
# Финиш включения помощника. Запускать ПОСЛЕ `npx wrangler login`.
# Делает всё сам: деплой Worker'а → ключи в секреты → адрес в виджет → коммит и пуш.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"   # .../worker
root="$(cd "$here/.." && pwd)"          # корень репозитория
cd "$here"

echo "== 1/4 деплой Worker'а =="
out="$(npx wrangler deploy 2>&1)" || { echo "$out"; echo "!! деплой упал"; exit 1; }
echo "$out"
url="$(printf '%s\n' "$out" | grep -oE 'https://[a-z0-9._-]+\.workers\.dev' | head -1)"
[ -n "$url" ] || { echo "!! не нашёл URL воркера в выводе деплоя"; exit 1; }
url="${url%/}"
echo "   URL: $url"

echo "== 2/4 ключи в секреты (значения из .dev.vars, в лог не печатаются) =="
if [ -f .dev.vars ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in \#*|"") continue;; esac
    name="${line%%=*}"; val="${line#*=}"
    case "$name" in
      GONKA_API_KEY|GONKA_GATEWAYS|GEMINI_API_KEY)
        printf '%s' "$val" | npx wrangler secret put "$name" >/dev/null
        echo "   секрет записан: $name"
        ;;
    esac
  done < .dev.vars
else
  echo "!! .dev.vars не найден — секреты не записаны"; exit 1
fi

echo "== 3/4 адрес в виджет ask.js =="
python3 - "$url" "$root/site/assets/ask.js" <<'PY'
import sys, re, pathlib
url, path = sys.argv[1].rstrip('/'), pathlib.Path(sys.argv[2])
s = path.read_text(encoding="utf-8")
s2 = re.sub(r'var DEFAULT_ENDPOINT = "[^"]*";',
            f'var DEFAULT_ENDPOINT = "{url}";', s, count=1)
if s2 == s:
    sys.exit("!! не удалось подставить DEFAULT_ENDPOINT в ask.js")
path.write_text(s2, encoding="utf-8")
print("   ask.js -> " + url)
PY

echo "== 4/4 коммит и пуш (main → GitHub Pages пересоберётся) =="
cd "$root"
git add site/assets/ask.js
git commit -m "feat(помощник): включён — адрес развёрнутого Worker'а прописан в виджет

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push origin main

echo "== ГОТОВО. Помощник живой на сайте через 1-2 минуты (сборка Pages). =="
echo "   Проверить сам Worker:"
echo "   curl -sN -X POST $url -H 'Origin: https://operhueper.github.io' -H 'Content-Type: application/json' -d '{\"question\":\"привет\",\"quote\":\"тест\"}'"

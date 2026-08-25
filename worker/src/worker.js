/* Прокси между учебником и языковой моделью.
   Браузер не может ходить в Gonka напрямую: у шлюза нет CORS, а ключ в
   исходниках страницы означал бы, что им пользуется кто угодно. Поэтому
   ключи живут здесь, в переменных Worker'а, а наружу торчит один POST /ask.

   Порядок попыток: шлюзы Gonka по кругу (их несколько, каждый со своим
   ключом), затем бесплатный тариф Gemini как страховка. Ответ уходит
   потоком: первый токен приходит примерно через полторы секунды, ждать
   целиком не нужно.

   Наружу отдаётся собственный простой формат, а не сырой ответ шлюза:
     data: {"t":"кусок текста"}
     data: {"src":"gonka/joingonka"}   — кто ответил, приходит первым
     data: {"err":"человеческий текст ошибки"}
     data: [DONE]
   Клиенту тогда всё равно, Gonka ответила или Gemini. */

const DEFAULT_GATEWAYS = [
  {
    label: "joingonka",
    baseUrl: "https://gate.joingonka.ai/v1",
    model: "deepseek-ai/DeepSeek-V4-Flash-0731",
  },
  {
    label: "gonkagate",
    baseUrl: "https://api.gonkagate.com/v1",
    model: "deepseek-ai/deepseek-v4-flash-0731",
  },
];

const DEFAULT_ORIGINS = [
  "https://operhueper.github.io",
  "http://localhost:8899",
  "http://127.0.0.1:8899",
];

/* Потолки. Нужны не ради денег — ответ стоит десятые доли копейки — а чтобы
   прокси нельзя было использовать как бесплатную болталку общего назначения. */
const MAX_QUESTION = 600;
const MAX_QUOTE = 3000;
const MAX_CONTEXT = 4000;
const MAX_TOKENS = 1200;
const GATEWAY_TIMEOUT_MS = 25000;

/* Сколько прошлых кругов разговора тащим с собой. Без них «я не понял» и
   «а если наоборот?» приходят к модели без всякого «чего именно не понял». */
const MAX_HISTORY_TURNS = 3;
const MAX_HISTORY_Q = 300;
const MAX_HISTORY_A = 900;

const SYSTEM = `Ты помощник-репетитор внутри учебника «AI-инженер с нуля» на русском языке.
Читатель застрял на фрагменте главы и спрашивает по нему.

Главное правило: отвечай ровно на то, что спросили.
— Первой фразой давай прямой ответ. Не разгоняйся издалека и не пересказывай
  фрагмент — читатель его только что прочитал.
— Если в вопросе несколько частей («а если удалю? а если добавлю?»), ответь на
  каждую отдельно, своим абзацем или пунктом. Ни одну не пропускай.
— «Я не понял», «а если…», «почему тогда…» — это продолжение прошлого ответа.
  Смотри, что уже было сказано выше, и объясняй именно непонятое место заново,
  другими словами, а не повторяй прежний текст.
— Спрашивают «что будет, если…» — разбери механику по шагам: что произойдёт
  сразу, что придётся пересчитать, а что останется как было.

Что можно и чего нельзя:
— Фрагмент главы — отправная точка, а не потолок. Нет в нём ответа — объясняй
  сам: своими знаниями, примером, разбором механики.
— Спрашивают про конкретные продукты и подходы — OpenAI, Google, чужие
  библиотеки, чем один вариант отличается от другого — отвечай по существу и
  сравнивай честно. Одной фразой предупреди, что у поставщиков всё меняется и
  точные детали стоит сверить с их документацией.
— Отказывайся, только если вопрос вообще из другой области: не про модели,
  данные, поиск, код и инженерию. Тогда — одна вежливая строка.
— Не выдумывай числа, даты, ссылки и названия статей. Не помнишь точно — так и
  скажи и объясни принцип.

Как писать:
— По-русски, простым языком, без канцелярита и без англицизмов там, где есть
  русское слово.
— Обычно три-пять абзацев. Механику и сравнения лучше списком. Не растекайся,
  но и не обрывай на середине: недоговорённый ответ хуже длинного.
— Формулы — словами или простым текстом. Разметку используй скупо: **жирный**,
  \`код\`, списки. Заголовки не ставь.`;

const MODES = {
  simpler: "Объясни это проще, на бытовом примере, как будто я слышу термин впервые.",
  example: "Приведи конкретный пример с числами или коротким кодом, чтобы стало понятно.",
  why: "Объясни, почему это устроено именно так и что было бы, если сделать иначе.",
  wider:
    "Расскажи, как эту задачу решают за пределами главы: какие есть подходы и " +
    "готовые сервисы, чем они отличаются друг от друга и что из этого выбрать новичку.",
};

/* ---------- вспомогательное ---------- */

function gateways(env) {
  const key = env.GONKA_API_KEY;
  let list = DEFAULT_GATEWAYS;
  if (env.GONKA_GATEWAYS) {
    try {
      const parsed = JSON.parse(env.GONKA_GATEWAYS);
      if (Array.isArray(parsed) && parsed.length) list = parsed;
    } catch (e) {
      // битый JSON в переменной не должен ронять сервис — берём умолчания
    }
  }
  return list
    .map((g, i) => ({
      label: g.label || `gw${i}`,
      baseUrl: String(g.baseUrl || "").replace(/\/+$/, ""),
      model: g.model || DEFAULT_GATEWAYS[0].model,
      key: g.key || key,
    }))
    .filter((g) => g.baseUrl && g.key);
}

function origins(env) {
  if (!env.ALLOWED_ORIGINS) return DEFAULT_ORIGINS;
  return env.ALLOWED_ORIGINS.split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function corsHeaders(origin, env) {
  const allowed = origins(env);
  const ok = origin && allowed.indexOf(origin) >= 0;
  return {
    "Access-Control-Allow-Origin": ok ? origin : allowed[0],
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function clip(value, limit) {
  return String(value == null ? "" : value).slice(0, limit).trim();
}

function jsonError(message, status, headers) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8" },
  });
}

/* ---------- сборка запроса к модели ---------- */

function buildUserMessage(body) {
  const title = clip(body.title, 200);
  const section = clip(body.section, 200);
  const quote = clip(body.quote, MAX_QUOTE);
  const context = clip(body.context, MAX_CONTEXT);
  const question = clip(body.question, MAX_QUESTION);
  const mode = MODES[body.mode] || "";

  const parts = [];
  if (title) parts.push(`Глава учебника: «${title}»`);
  if (section) parts.push(`Раздел: ${section}`);
  if (context) parts.push(`Фрагмент главы:\n"""\n${context}\n"""`);
  if (quote) parts.push(`Читатель выделил в этом фрагменте:\n"""\n${quote}\n"""`);
  parts.push(`Вопрос читателя: ${question || mode || "Объясни выделенное."}`);
  if (mode && question) parts.push(`Формат ответа: ${mode}`);
  return parts.join("\n\n");
}

/* Прошлые круги разговора. Фрагмент главы в них не повторяем — он и так едет
   в свежем сообщении, а лишние три тысячи знаков на круг съели бы всё окно. */
function history(body) {
  const raw = Array.isArray(body.history) ? body.history : [];
  return raw
    .slice(-MAX_HISTORY_TURNS)
    .map((turn) => ({
      q: clip(turn && turn.q, MAX_HISTORY_Q),
      a: clip(turn && turn.a, MAX_HISTORY_A),
    }))
    .filter((turn) => turn.q && turn.a);
}

/* ---------- разбор потоков ---------- */

/* И Gonka, и Gemini отдают SSE, но с разным содержимым внутри data:.
   Обе ветки сводятся к одному: вернуть очередной кусок текста или null. */

function gonkaChunk(payload) {
  const delta = payload?.choices?.[0]?.delta;
  return delta?.content || null;
}

function geminiChunk(payload) {
  const parts = payload?.candidates?.[0]?.content?.parts;
  if (!Array.isArray(parts)) return null;
  const text = parts.map((p) => p.text || "").join("");
  return text || null;
}

/* MiniMax и родня иногда кладут рассуждения прямо в текст ответа.
   Читателю они не нужны, поэтому вырезаем на лету. */
function makeThinkFilter() {
  let inside = false;
  return function (text) {
    let out = "";
    let rest = text;
    while (rest) {
      if (inside) {
        const end = rest.indexOf("</think>");
        if (end < 0) return out;
        inside = false;
        rest = rest.slice(end + 8);
        continue;
      }
      const start = rest.indexOf("<think>");
      if (start < 0) {
        out += rest;
        return out;
      }
      out += rest.slice(0, start);
      inside = true;
      rest = rest.slice(start + 7);
    }
    return out;
  };
}

/* ---------- попытки достучаться до моделей ---------- */

async function openGonka(gw, ask) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GATEWAY_TIMEOUT_MS);
  const messages = [{ role: "system", content: SYSTEM }];
  for (const turn of ask.past) {
    messages.push({ role: "user", content: turn.q });
    messages.push({ role: "assistant", content: turn.a });
  }
  messages.push({ role: "user", content: ask.message });
  try {
    const res = await fetch(`${gw.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${gw.key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: gw.model,
        stream: true,
        temperature: 0.3,
        max_tokens: MAX_TOKENS,
        messages,
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok || !res.body) {
      const text = res.body ? await res.text() : "";
      return { ok: false, reason: `HTTP ${res.status} ${text.slice(0, 160)}` };
    }
    return { ok: true, body: res.body, pick: gonkaChunk, src: `gonka/${gw.label}` };
  } catch (e) {
    clearTimeout(timer);
    return { ok: false, reason: `сеть: ${e?.message || e}` };
  }
}

async function openGemini(env, ask) {
  if (!env.GEMINI_API_KEY) return { ok: false, reason: "ключ Gemini не задан" };
  const model = env.GEMINI_MODEL || "gemini-2.5-flash";
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:streamGenerateContent` +
    `?alt=sse&key=${encodeURIComponent(env.GEMINI_API_KEY)}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GATEWAY_TIMEOUT_MS);
  const contents = [];
  for (const turn of ask.past) {
    contents.push({ role: "user", parts: [{ text: turn.q }] });
    contents.push({ role: "model", parts: [{ text: turn.a }] });
  }
  contents.push({ role: "user", parts: [{ text: ask.message }] });
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        systemInstruction: { parts: [{ text: SYSTEM }] },
        contents,
        generationConfig: { temperature: 0.3, maxOutputTokens: MAX_TOKENS },
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok || !res.body) {
      const text = res.body ? await res.text() : "";
      return { ok: false, reason: `HTTP ${res.status} ${text.slice(0, 160)}` };
    }
    return { ok: true, body: res.body, pick: geminiChunk, src: "gemini" };
  } catch (e) {
    clearTimeout(timer);
    return { ok: false, reason: `сеть: ${e?.message || e}` };
  }
}

/* Три попытки, как договорились: шлюзы Gonka по очереди, потом Gemini.
   Переключаемся только пока не пошёл текст — если поток уже начался и
   оборвался, начинать заново нельзя, читатель увидит ответ дважды. */
async function openStream(env, ask) {
  const failures = [];
  for (const gw of gateways(env)) {
    const attempt = await openGonka(gw, ask);
    if (attempt.ok) return attempt;
    failures.push(`${gw.label}: ${attempt.reason}`);
  }
  const fallback = await openGemini(env, ask);
  if (fallback.ok) return fallback;
  failures.push(`gemini: ${fallback.reason}`);
  return { ok: false, failures };
}

/* ---------- перекладывание потока наружу ---------- */

function relay(upstream, pick, src) {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const strip = makeThinkFilter();
  const reader = upstream.getReader();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (obj) =>
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
      send({ src });

      let buffer = "";
      let sentAnything = false;
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let cut;
          while ((cut = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, cut).trim();
            buffer = buffer.slice(cut + 1);
            if (!line.startsWith("data:")) continue;
            const payload = line.slice(5).trim();
            if (payload === "[DONE]") continue;
            let parsed;
            try {
              parsed = JSON.parse(payload);
            } catch (e) {
              continue;
            }
            const text = pick(parsed);
            if (!text) continue;
            const clean = strip(text);
            if (!clean) continue;
            sentAnything = true;
            send({ t: clean });
          }
        }
        if (!sentAnything) send({ err: "Модель вернула пустой ответ. Попробуйте ещё раз." });
      } catch (e) {
        send({ err: "Ответ оборвался на полпути. Попробуйте ещё раз." });
      } finally {
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
        try {
          reader.releaseLock();
        } catch (e) {
          /* поток уже закрыт */
        }
      }
    },
    cancel() {
      reader.cancel().catch(() => {});
    },
  });

  return stream;
}

/* ---------- точка входа ---------- */

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(origin, env);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }
    if (request.method !== "POST") {
      return jsonError("Только POST", 405, cors);
    }
    if (origins(env).indexOf(origin) < 0) {
      return jsonError("Запрос не с сайта учебника", 403, cors);
    }

    let body;
    try {
      body = await request.json();
    } catch (e) {
      return jsonError("Тело запроса не разобралось", 400, cors);
    }

    const question = clip(body.question, MAX_QUESTION);
    const quote = clip(body.quote, MAX_QUOTE);
    if (!question && !MODES[body.mode]) {
      return jsonError("Пустой вопрос", 400, cors);
    }
    if (!quote && !clip(body.context, MAX_CONTEXT)) {
      return jsonError("Нет фрагмента главы", 400, cors);
    }

    /* Лимит по адресу. Считает сам Cloudflare, хранилище не нужно.
       Если привязка не настроена, ограничения просто нет. */
    if (env.RATE_LIMITER) {
      const ip = request.headers.get("CF-Connecting-IP") || "нет-адреса";
      const { success } = await env.RATE_LIMITER.limit({ key: ip });
      if (!success) {
        return jsonError(
          "На сегодня вопросов хватит: сработал лимит. Загляните завтра.",
          429,
          cors,
        );
      }
    }

    const opened = await openStream(env, {
      message: buildUserMessage(body),
      past: history(body),
    });
    if (!opened.ok) {
      console.log("все шлюзы отказали:", opened.failures.join(" | "));
      return jsonError(
        "Ни один шлюз сейчас не отвечает. Попробуйте через минуту.",
        503,
        cors,
      );
    }

    return new Response(relay(opened.body, opened.pick, opened.src), {
      headers: {
        ...cors,
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  },
};

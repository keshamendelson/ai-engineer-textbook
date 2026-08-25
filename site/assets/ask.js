/* Помощник на полях: выделил непонятное место — спросил — получил разбор.

   Вопрос уходит не в модель напрямую, а в прокси (папка worker/ в репозитории):
   у шлюза нет CORS, да и ключ в исходниках страницы означал бы, что им
   пользуется кто угодно. Ответ приходит потоком и печатается по мере набора.

   Пока адрес прокси не прописан, помощник не показывается вовсе: лучше
   отсутствие кнопки, чем кнопка, которая ничего не делает. */

(function () {
  "use strict";

  /* Сюда вписать адрес развёрнутого Worker'а, например
     https://aieng-ask.ИМЯ.workers.dev/  — один раз после первого деплоя. */
  var DEFAULT_ENDPOINT = "https://aieng-ask.operhueper.workers.dev";

  var LS_ENDPOINT = "aieng.ask.endpoint";
  var LS_LOG = "aieng.ask.log.";
  var LS_WIDTH = "aieng.ask.width";
  var LS_HEIGHT = "aieng.ask.height";
  var LS_DOCK = "aieng.ask.dock";
  var MAX_HISTORY = 20;

  /* Размеры панели. Ширина в пикселях, чтобы её можно было тянуть мышью;
     потолок тот же, что в стилях, иначе значение и картинка разойдутся. */
  var MIN_W = 320;
  var MAX_W = 768;
  var MIN_H = 260;
  var DEF_W = 432;
  /* Уже этого окно делить на текст и панель бессмысленно: от главы останется
     колонка в три слова. Тогда панель просто ложится поверх. */
  var DOCK_MIN_VIEWPORT = 1000;
  /* Сколько прошлых кругов уезжает вместе с вопросом. Без них «я не понял» и
     «а если наоборот?» приходят к модели без всякого «чего именно не понял». */
  var SEND_HISTORY = 3;
  var MAX_QUESTION = 600;

  var QUICK = [
    { mode: "simpler", label: "Объясни проще" },
    { mode: "example", label: "Дай пример" },
    { mode: "why", label: "Почему так?" },
    { mode: "wider", label: "А как у других?" },
  ];

  var endpoint = "";
  var article = null;
  var pill = null;
  var panel = null;
  var quoteBox = null;
  var input = null;
  var thread = null;
  var sendBtn = null;
  var fab = null;
  var handle = null;
  var dockBtn = null;

  var quote = ""; // что читатель выделил
  var context = ""; // абзацы вокруг выделения
  var section = ""; // ближайший подзаголовок
  var busy = false;
  var abort = null;
  var docked = true; // панель стоит рядом с текстом, а не поверх него

  /* ---------- мелочи ---------- */

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function chapterId() {
    var f = location.pathname.split("/").pop() || "index.html";
    return f.replace(".html", "");
  }

  function chapterTitle() {
    var h = document.querySelector("article h1");
    return h ? h.textContent.trim() : document.title;
  }

  function remember(key, value) {
    try {
      localStorage.setItem(key, String(value));
    } catch (e) {
      /* приватный режим или переполненное хранилище — размер просто не запомнится */
    }
  }

  function recall(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  /* ---------- размер панели ---------- */

  /* На узком экране панель выезжает снизу во всю ширину, и тянут её за верхний
     край: меняется высота, а не ширина. */
  function isNarrow() {
    return window.innerWidth <= 700;
  }

  function setWidth(px) {
    var top = Math.min(MAX_W, Math.round(window.innerWidth * 0.92));
    var w = Math.max(MIN_W, Math.min(top, Math.round(px)));
    document.documentElement.style.setProperty("--ask-w", w + "px");
    remember(LS_WIDTH, w);
  }

  function setHeight(px) {
    var top = Math.round(window.innerHeight * 0.92);
    var h = Math.max(MIN_H, Math.min(top, Math.round(px)));
    document.documentElement.style.setProperty("--ask-h", h + "px");
    remember(LS_HEIGHT, h);
  }

  function restoreSize() {
    var w = parseInt(recall(LS_WIDTH) || "", 10);
    setWidth(w > 0 ? w : DEF_W);
    var h = parseInt(recall(LS_HEIGHT) || "", 10);
    if (h > 0) setHeight(h);
    docked = recall(LS_DOCK) !== "0";
  }

  /* Прижимать текст есть чем только на широком экране. Если места мало, выбор
     читателя не теряется — просто не применяется, и кнопка прячется. */
  function canDock() {
    return !isNarrow() && window.innerWidth >= DOCK_MIN_VIEWPORT;
  }

  function applyDock() {
    var on = panel.classList.contains("open") && docked && canDock();
    document.body.classList.toggle("ask-docked", on);
    if (!dockBtn) return;
    dockBtn.hidden = !canDock();
    dockBtn.setAttribute("aria-pressed", docked ? "true" : "false");
    dockBtn.textContent = docked ? "рядом" : "поверх";
    dockBtn.title = docked
      ? "Панель стоит рядом с текстом и поджимает страницу. Нажмите, чтобы положить её поверх."
      : "Панель лежит поверх текста. Нажмите, чтобы поставить её рядом.";
  }

  /* Тянем за край. Пока тянут, отключаем переход и выделение текста: иначе
     панель едет за мышью с задержкой, а по дороге выделяется полглавы. */
  function startResize(e) {
    e.preventDefault();
    var vertical = isNarrow();
    handle.classList.add("dragging");
    panel.classList.add("sizing");
    document.body.classList.add("ask-resizing");

    var move = function (ev) {
      if (vertical) setHeight(window.innerHeight - ev.clientY);
      else setWidth(window.innerWidth - ev.clientX);
    };
    var stop = function () {
      handle.classList.remove("dragging");
      panel.classList.remove("sizing");
      document.body.classList.remove("ask-resizing");
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
      document.removeEventListener("pointercancel", stop);
    };

    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
    document.addEventListener("pointercancel", stop);
  }

  /* Клавиатурой — стрелками, с тем же шагом, что у мыши на глаз. */
  function nudgeSize(e) {
    var step = e.shiftKey ? 64 : 24;
    var w = panel.getBoundingClientRect().width;
    var h = panel.getBoundingClientRect().height;
    if (e.key === "ArrowLeft") setWidth(w + step);
    else if (e.key === "ArrowRight") setWidth(w - step);
    else if (e.key === "ArrowUp") setHeight(h + step);
    else if (e.key === "ArrowDown") setHeight(h - step);
    else return;
    e.preventDefault();
  }

  /* Разметки в ответе немного: жирный, код, списки, абзацы.
     Полноценный разборщик markdown сюда тащить незачем. */
  function render(text) {
    var blocks = String(text).split(/\n{2,}/);
    var html = "";
    blocks.forEach(function (block) {
      var lines = block.split("\n").filter(function (l) {
        return l.trim();
      });
      if (!lines.length) return;
      var isList = lines.every(function (l) {
        return /^\s*([-*•]|\d+[.)])\s+/.test(l);
      });
      if (isList) {
        html += "<ul>";
        lines.forEach(function (l) {
          html += "<li>" + inline(l.replace(/^\s*([-*•]|\d+[.)])\s+/, "")) + "</li>";
        });
        html += "</ul>";
      } else {
        html += "<p>" + inline(lines.join("\n")).replace(/\n/g, "<br>") + "</p>";
      }
    });
    return html;
  }

  function inline(s) {
    return esc(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  }

  /* ---------- что именно спрашивают ---------- */

  /* Модели нужен не только выделенный кусок, но и то, что вокруг: одна фраза
     без соседних абзацев объясняется плохо. Берём родительский блок и его
     соседей, пока не наберётся полторы тысячи знаков. */
  function grabContext(range) {
    var node = range.commonAncestorContainer;
    if (node.nodeType === 3) node = node.parentNode;
    var block = node.closest("p, li, pre, td, blockquote, .callout, .demo, figure");
    if (!block || !article.contains(block)) block = node;

    var texts = [textOf(block)];
    var back = block;
    var fwd = block;
    var total = texts[0].length;
    while (total < 1500) {
      back = back && back.previousElementSibling;
      fwd = fwd && fwd.nextElementSibling;
      if (!back && !fwd) break;
      if (back) {
        var t = textOf(back);
        if (t) {
          texts.unshift(t);
          total += t.length;
        }
      }
      if (fwd && total < 1500) {
        var t2 = textOf(fwd);
        if (t2) {
          texts.push(t2);
          total += t2.length;
        }
      }
    }
    return texts.join("\n\n").slice(0, 4000);
  }

  function textOf(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.tagName === "SVG" || el.tagName === "svg") return "";
    return (el.textContent || "").replace(/\s+/g, " ").trim();
  }

  /* Ближайший заголовок выше выделения — чтобы модель знала, о каком разделе речь. */
  function findSection(range) {
    var node = range.commonAncestorContainer;
    if (node.nodeType === 3) node = node.parentNode;
    var heads = Array.prototype.slice.call(article.querySelectorAll("h2, h3"));
    var found = "";
    heads.forEach(function (h) {
      if (h.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING) {
        found = h.textContent.trim();
      }
    });
    return found;
  }

  /* ---------- всплывающая кнопка у выделения ---------- */

  function hidePill() {
    if (pill) pill.classList.remove("show");
  }

  function onSelection() {
    if (busy) return;
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return hidePill();
    var range = sel.getRangeAt(0);
    var text = sel.toString().replace(/\s+/g, " ").trim();
    if (text.length < 3 || !article.contains(range.commonAncestorContainer)) {
      return hidePill();
    }

    quote = text.slice(0, 3000);
    context = grabContext(range);
    section = findSection(range);

    /* Панель уже открыта — пилюля поверх неё была бы лишней, но выделение
       подхватываем: в режиме «рядом с текстом» читатель отмечает новое место,
       не закрывая помощника, и просто спрашивает дальше. */
    if (panel.classList.contains("open")) {
      hidePill();
      paintQuote();
      return;
    }

    var r = range.getBoundingClientRect();
    pill.classList.add("show");
    var top = window.scrollY + r.top - pill.offsetHeight - 10;
    pill.style.top = (top < window.scrollY + 8 ? window.scrollY + r.bottom + 10 : top) + "px";
    pill.style.left =
      Math.max(
        8,
        Math.min(
          window.innerWidth - pill.offsetWidth - 8,
          r.left + r.width / 2 - pill.offsetWidth / 2,
        ),
      ) + "px";
  }

  /* ---------- панель ---------- */

  function openPanel(prefillMode) {
    panel.classList.add("open");
    hidePill();
    if (fab) fab.classList.add("hidden");
    applyDock();
    paintQuote();
    if (prefillMode) ask("", prefillMode);
    else setTimeout(function () {
      input.focus();
    }, 120);
  }

  function closePanel() {
    panel.classList.remove("open");
    if (fab) fab.classList.remove("hidden");
    document.body.classList.remove("ask-docked");
    if (abort) abort.abort();
  }

  function paintQuote() {
    if (!quote) {
      quoteBox.innerHTML =
        '<span class="ask-quote-empty">Вопрос по главе целиком. Выделите фрагмент в тексте, ' +
        "чтобы спросить точечно.</span>";
      return;
    }
    var short = quote.length > 220 ? quote.slice(0, 220) + "…" : quote;
    quoteBox.innerHTML =
      "<blockquote>" +
      esc(short) +
      '</blockquote><button class="ask-quote-drop" type="button">убрать выделение</button>';
    quoteBox.querySelector(".ask-quote-drop").addEventListener("click", function () {
      quote = "";
      paintQuote();
      input.focus();
    });
  }

  /* ---------- история ---------- */

  function logKey() {
    return LS_LOG + chapterId();
  }

  function readLog() {
    try {
      return JSON.parse(localStorage.getItem(logKey()) || "[]");
    } catch (e) {
      return [];
    }
  }

  function writeLog(items) {
    try {
      localStorage.setItem(logKey(), JSON.stringify(items.slice(-MAX_HISTORY)));
    } catch (e) {
      /* переполнилось хранилище — history не важнее самого учебника */
    }
  }

  function paintThread() {
    var items = readLog();
    if (!items.length) {
      thread.innerHTML =
        '<div class="ask-hello">Выделите непонятное место в тексте и спросите. ' +
        "Переспрашивать можно: помощник помнит предыдущие ответы в этой главе.</div>";
      return;
    }
    thread.innerHTML = items
      .map(function (it) {
        return (
          '<div class="ask-turn">' +
          (it.q ? '<div class="ask-q">' + esc(it.q) + "</div>" : "") +
          (it.quote
            ? '<div class="ask-cited">' + esc(it.quote.slice(0, 140)) + "</div>"
            : "") +
          '<div class="ask-a">' +
          render(it.a) +
          "</div></div>"
        );
      })
      .join("");
    thread.scrollTop = thread.scrollHeight;
  }

  /* ---------- запрос ---------- */

  function ask(question, mode) {
    if (busy) return;
    question = (question || "").trim().slice(0, MAX_QUESTION);
    if (!question && !mode) return;
    if (!quote && !context) {
      context = textOf(article.querySelector("p")) || chapterTitle();
    }

    busy = true;
    sendBtn.disabled = true;
    input.value = "";
    autogrow();

    var turn = document.createElement("div");
    turn.className = "ask-turn";
    var label = question || QUICK.filter(function (q) {
      return q.mode === mode;
    }).map(function (q) {
      return q.label;
    })[0];
    turn.innerHTML =
      '<div class="ask-q">' +
      esc(label) +
      "</div>" +
      (quote ? '<div class="ask-cited">' + esc(quote.slice(0, 140)) + "</div>" : "") +
      '<div class="ask-a"><span class="ask-dots"><i></i><i></i><i></i></span></div>';
    if (thread.querySelector(".ask-hello")) thread.innerHTML = "";
    thread.appendChild(turn);
    thread.scrollTop = thread.scrollHeight;
    var out = turn.querySelector(".ask-a");

    var answer = "";
    var painted = false;
    var paint = function () {
      out.innerHTML = render(answer);
      thread.scrollTop = thread.scrollHeight;
    };

    abort = new AbortController();
    stream(
      { question: question, mode: mode || "" },
      function (chunk) {
        answer += chunk;
        painted = true;
        paint();
      },
      function (err) {
        busy = false;
        sendBtn.disabled = false;
        abort = null;
        if (err) {
          out.innerHTML = '<div class="ask-err">' + esc(err) + "</div>";
          return;
        }
        if (!painted) {
          out.innerHTML = '<div class="ask-err">Пустой ответ. Попробуйте переспросить.</div>';
          return;
        }
        var items = readLog();
        items.push({ q: label, quote: quote, a: answer, at: Date.now() });
        writeLog(items);
      },
    );
  }

  function stream(extra, onChunk, onDone) {
    var body = {
      chapter: chapterId(),
      title: chapterTitle(),
      section: section,
      quote: quote,
      context: context,
      question: extra.question,
      mode: extra.mode,
      history: readLog()
        .slice(-SEND_HISTORY)
        .map(function (it) {
          return { q: it.q, a: it.a };
        }),
    };

    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: abort.signal,
    })
      .then(function (res) {
        if (!res.ok) {
          return res
            .json()
            .catch(function () {
              return {};
            })
            .then(function (d) {
              throw new Error(d.error || "Сервер ответил " + res.status);
            });
        }
        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        var failed = "";

        var pump = function () {
          return reader.read().then(function (r) {
            if (r.done) return onDone(failed);
            buffer += decoder.decode(r.value, { stream: true });
            var cut;
            while ((cut = buffer.indexOf("\n")) >= 0) {
              var line = buffer.slice(0, cut).trim();
              buffer = buffer.slice(cut + 1);
              if (line.indexOf("data:") !== 0) continue;
              var payload = line.slice(5).trim();
              if (payload === "[DONE]") continue;
              try {
                var d = JSON.parse(payload);
                if (d.t) onChunk(d.t);
                else if (d.err) failed = d.err;
              } catch (e) {
                /* обрывок строки, придёт целиком следующим куском */
              }
            }
            return pump();
          });
        };
        return pump();
      })
      .catch(function (e) {
        if (e && e.name === "AbortError") return onDone("");
        onDone(e && e.message ? e.message : "Не получилось связаться с помощником.");
      });
  }

  /* ---------- разметка ---------- */

  /* Вопросительный знак линиями, а не картинкой: масштабируется без потерь и
     красится текущим цветом кнопки. Книжку со знаком внутри пробовали — в
     сорока пикселях страницы и знак слипаются в кляксу. */
  var ASK_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
    '<path d="M9 9a3 3 0 1 1 4.2 2.75c-.9.4-1.45 1.15-1.45 2.05v.7"/>' +
    '<path d="M11.75 18h.01"/>' +
    "</svg>";

  function build() {
    pill = document.createElement("button");
    pill.id = "ask-pill";
    pill.type = "button";
    pill.textContent = "Спросить";
    document.body.appendChild(pill);

    fab = document.createElement("button");
    fab.id = "ask-fab";
    fab.type = "button";
    fab.title = "Спросить по главе";
    fab.setAttribute("aria-label", "Спросить по главе");
    fab.innerHTML = ASK_ICON;
    document.body.appendChild(fab);

    panel = document.createElement("aside");
    panel.id = "ask-panel";
    panel.innerHTML =
      '<div class="ask-resize" id="ask-resize" role="separator" tabindex="0" ' +
      'aria-label="Размер панели" title="Потяните, чтобы изменить размер"></div>' +
      '<div class="ask-head">' +
      "<b>Помощник по главе</b>" +
      '<button class="ask-mode" id="ask-dock" type="button" aria-pressed="true">рядом</button>' +
      '<button class="ask-close" type="button" aria-label="Закрыть">×</button>' +
      "</div>" +
      '<div class="ask-thread" id="ask-thread"></div>' +
      '<div class="ask-foot">' +
      '<div class="ask-quote" id="ask-quote"></div>' +
      '<div class="ask-chips">' +
      QUICK.map(function (q) {
        return '<button type="button" data-mode="' + q.mode + '">' + q.label + "</button>";
      }).join("") +
      "</div>" +
      '<div class="ask-row">' +
      '<textarea id="ask-input" rows="2" maxlength="' +
      MAX_QUESTION +
      '" placeholder="Что именно непонятно?"></textarea>' +
      '<button class="ask-send" id="ask-send" type="button">→</button>' +
      "</div>" +
      '<div class="ask-note">Отвечает языковая модель. Может ошибаться — сверяйтесь с текстом главы.</div>' +
      "</div>";
    document.body.appendChild(panel);

    thread = panel.querySelector("#ask-thread");
    quoteBox = panel.querySelector("#ask-quote");
    input = panel.querySelector("#ask-input");
    sendBtn = panel.querySelector("#ask-send");
    handle = panel.querySelector("#ask-resize");
    dockBtn = panel.querySelector("#ask-dock");
  }

  /* Поле растёт под длинный вопрос и сжимается обратно: две строки по
     умолчанию мало для «а если я сделаю так, а потом вот так?». */
  function autogrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 144) + "px";
  }

  function wire() {
    pill.addEventListener("mousedown", function (e) {
      e.preventDefault(); // иначе выделение слетит раньше, чем мы его прочитаем
    });
    pill.addEventListener("click", function () {
      openPanel();
    });

    panel.querySelector(".ask-close").addEventListener("click", closePanel);

    panel.querySelectorAll(".ask-chips button").forEach(function (b) {
      b.addEventListener("click", function () {
        ask("", b.getAttribute("data-mode"));
      });
    });

    sendBtn.addEventListener("click", function () {
      ask(input.value);
    });

    input.addEventListener("input", autogrow);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey || !e.shiftKey)) {
        e.preventDefault();
        ask(input.value);
      }
    });

    /* Кнопка в правом нижнем углу. Если в тексте что-то выделено прямо сейчас,
       спрашиваем про выделенное; если нет — про главу целиком. */
    fab.addEventListener("click", function () {
      if (panel.classList.contains("open")) return closePanel();
      var sel = window.getSelection();
      var live = sel && !sel.isCollapsed && sel.toString().trim().length >= 3;
      if (!live) {
        quote = "";
        context = "";
        section = "";
      }
      openPanel();
    });

    handle.addEventListener("pointerdown", startResize);
    handle.addEventListener("keydown", nudgeSize);
    handle.addEventListener("dblclick", function () {
      if (isNarrow()) setHeight(Math.round(window.innerHeight * 0.6));
      else setWidth(DEF_W);
    });

    dockBtn.addEventListener("click", function () {
      docked = !docked;
      remember(LS_DOCK, docked ? "1" : "0");
      applyDock();
    });

    /* Окно поменяли — ширина могла стать больше самого окна, а прижимать текст
       могло стать негде. */
    window.addEventListener("resize", function () {
      setWidth(panel.getBoundingClientRect().width);
      applyDock();
    });

    document.addEventListener("mouseup", function () {
      setTimeout(onSelection, 10);
    });
    document.addEventListener("selectionchange", function () {
      var sel = window.getSelection();
      if (!sel || sel.isCollapsed) hidePill();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        hidePill();
        if (panel.classList.contains("open")) closePanel();
      }
    });

  }

  /* ---------- запуск ---------- */

  function boot() {
    endpoint = (localStorage.getItem(LS_ENDPOINT) || DEFAULT_ENDPOINT).replace(/\/+$/, "");
    if (!endpoint) return; // прокси не настроен — помощника нет
    article = document.querySelector("article");
    if (!article) return;
    restoreSize();
    build();
    wire();
    applyDock();
    paintThread();
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

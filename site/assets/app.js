/* Движок учебника: навигация, прогресс, квизы, поиск, подсказки к терминам.
   Работает без сборки и без сервера: достаточно открыть файл в браузере. */

(function () {
  "use strict";

  var LS_THEME = "aieng.theme";
  var LS_DONE = "aieng.done";

  /* ---------- тема ---------- */

  function initTheme() {
    var saved = localStorage.getItem(LS_THEME);
    if (!saved) {
      saved = window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    document.documentElement.setAttribute("data-theme", saved);
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    var paint = function () {
      btn.textContent =
        document.documentElement.getAttribute("data-theme") === "dark"
          ? "Светлая"
          : "Тёмная";
    };
    paint();
    btn.addEventListener("click", function () {
      var next =
        document.documentElement.getAttribute("data-theme") === "dark"
          ? "light"
          : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem(LS_THEME, next);
      paint();
    });
  }

  /* ---------- прогресс ---------- */

  function readDone() {
    try {
      return JSON.parse(localStorage.getItem(LS_DONE) || "{}");
    } catch (e) {
      return {};
    }
  }

  function writeDone(map) {
    localStorage.setItem(LS_DONE, JSON.stringify(map));
  }

  function countable() {
    return window.FLAT_TOC.filter(function (c) {
      return c.id.indexOf("app-") !== 0;
    });
  }

  /* ---------- боковое меню ---------- */

  function currentId() {
    var f = location.pathname.split("/").pop() || "index.html";
    return f.replace(".html", "");
  }

  function buildSidebar() {
    var host = document.getElementById("sidebar");
    if (!host || !window.TOC) return;
    var done = readDone();
    var cur = currentId();
    var total = countable().length;
    var read = countable().filter(function (c) {
      return done[c.id];
    }).length;
    var pct = total ? Math.round((read / total) * 100) : 0;

    var html =
      '<div class="progress-box">' +
      '<div class="label"><span>Пройдено</span><span>' +
      read +
      " из " +
      total +
      "</span></div>" +
      '<div class="progress-bar"><i style="width:' +
      pct +
      '%"></i></div>' +
      "</div>";

    window.TOC.forEach(function (part) {
      html += '<div class="part">' + part.part + "</div>";
      part.items.forEach(function (it) {
        var cls = [];
        if (it.id === cur) cls.push("current");
        if (done[it.id]) cls.push("done");
        html +=
          '<a class="' +
          cls.join(" ") +
          '" href="' +
          it.id +
          '.html"><span class="num">' +
          (done[it.id] ? "" : it.num) +
          "</span><span>" +
          it.title +
          "</span></a>";
      });
    });
    host.innerHTML = html;
  }

  function initMarkRead() {
    var btn = document.getElementById("mark-read");
    if (!btn) return;
    var id = currentId();
    var paint = function () {
      var done = readDone();
      if (done[id]) {
        btn.classList.add("done");
        btn.textContent = "Глава пройдена. Снять отметку";
      } else {
        btn.classList.remove("done");
        btn.textContent = "Отметить главу как пройденную";
      }
    };
    paint();
    btn.addEventListener("click", function () {
      var done = readDone();
      if (done[id]) delete done[id];
      else done[id] = Date.now();
      writeDone(done);
      paint();
      buildSidebar();
    });
  }

  /* ---------- переход к соседним главам ---------- */

  function buildChapterNav() {
    var host = document.getElementById("chapter-nav");
    if (!host || !window.FLAT_TOC) return;
    var cur = currentId();
    var idx = window.FLAT_TOC.findIndex(function (c) {
      return c.id === cur;
    });
    if (idx < 0) return;
    var prev = window.FLAT_TOC[idx - 1];
    var next = window.FLAT_TOC[idx + 1];
    var html = "";
    if (prev)
      html +=
        '<a href="' +
        prev.id +
        '.html"><span class="dir">← Предыдущая</span><span class="ttl">' +
        prev.title +
        "</span></a>";
    if (next)
      html +=
        '<a class="next" href="' +
        next.id +
        '.html"><span class="dir">Следующая →</span><span class="ttl">' +
        next.title +
        "</span></a>";
    host.innerHTML = html;
  }

  /* ---------- оглавление главы справа ---------- */

  function buildOnPage() {
    var host = document.getElementById("on-page");
    if (!host) return;
    var heads = document.querySelectorAll("article h2, article h3");
    if (heads.length < 3) {
      host.style.display = "none";
      return;
    }
    var html = '<div class="opt-title">В этой главе</div>';
    heads.forEach(function (h, i) {
      if (!h.id) h.id = "s" + i;
      html +=
        '<a href="#' +
        h.id +
        '" class="' +
        (h.tagName === "H3" ? "lvl3" : "") +
        '">' +
        h.textContent +
        "</a>";
    });
    host.innerHTML = html;

    var links = host.querySelectorAll("a");
    var spy = function () {
      var pos = window.scrollY + 120;
      var active = 0;
      heads.forEach(function (h, i) {
        if (h.offsetTop <= pos) active = i;
      });
      links.forEach(function (a, i) {
        a.classList.toggle("active", i === active);
      });
    };
    window.addEventListener("scroll", spy, { passive: true });
    spy();
  }

  /* ---------- квизы ---------- */

  function initQuizzes() {
    document.querySelectorAll(".quiz").forEach(function (quiz) {
      var questions = quiz.querySelectorAll(".q");

      questions.forEach(function (q) {
        q.querySelectorAll(".opt").forEach(function (opt) {
          opt.addEventListener("click", function () {
            if (q.classList.contains("answered")) return;
            q.classList.add("answered");
            var right = opt.getAttribute("data-correct") === "1";
            opt.classList.add(right ? "right" : "wrong");
            if (!right) {
              var good = q.querySelector('.opt[data-correct="1"]');
              if (good) good.classList.add("right");
            }
            q.setAttribute("data-result", right ? "1" : "0");
            updateScore(quiz);
          });
        });
      });

      var reset = quiz.querySelector(".quiz-reset");
      if (reset)
        reset.addEventListener("click", function () {
          questions.forEach(function (q) {
            q.classList.remove("answered");
            q.removeAttribute("data-result");
            q.querySelectorAll(".opt").forEach(function (o) {
              o.classList.remove("right", "wrong");
            });
          });
          updateScore(quiz);
        });
    });
  }

  function updateScore(quiz) {
    var box = quiz.querySelector(".quiz-score");
    if (!box) return;
    var qs = quiz.querySelectorAll(".q");
    var answered = 0;
    var right = 0;
    qs.forEach(function (q) {
      var r = q.getAttribute("data-result");
      if (r !== null) {
        answered++;
        if (r === "1") right++;
      }
    });
    if (!answered) {
      box.textContent = "";
      return;
    }
    box.textContent = "Верно " + right + " из " + answered;
    box.style.color =
      right === answered ? "var(--practice)" : right * 2 >= answered ? "var(--ink-2)" : "var(--danger)";
  }

  /* ---------- поиск ---------- */

  function initSearch() {
    var input = document.getElementById("search-input");
    var out = document.getElementById("search-results");
    if (!input || !out) return;

    var render = function (items, query) {
      if (!items.length) {
        out.innerHTML = '<div class="empty">Ничего не нашлось. Попробуйте одно слово.</div>';
        out.classList.add("open");
        return;
      }
      out.innerHTML = items
        .slice(0, 12)
        .map(function (r) {
          return (
            '<a href="' +
            r.href +
            '"><span class="r-ch">' +
            r.chapter +
            '</span><br><span class="r-t">' +
            hl(r.title, query) +
            '</span><br><span class="r-s">' +
            hl(r.snippet, query) +
            "</span></a>"
          );
        })
        .join("");
      out.classList.add("open");
    };

    var hl = function (text, q) {
      if (!q) return text;
      var safe = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return text.replace(new RegExp("(" + safe + ")", "gi"), "<mark>$1</mark>");
    };

    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      if (q.length < 2) {
        out.classList.remove("open");
        return;
      }
      var index = window.SEARCH_INDEX || [];
      var hits = [];
      index.forEach(function (rec) {
        var score = 0;
        var t = rec.title.toLowerCase();
        var b = rec.body.toLowerCase();
        if (t.indexOf(q) >= 0) score += 10;
        if (b.indexOf(q) >= 0) score += 3;
        q.split(/\s+/).forEach(function (w) {
          if (w.length > 2 && b.indexOf(w) >= 0) score += 1;
        });
        if (score > 0) {
          var pos = b.indexOf(q);
          var start = Math.max(0, pos - 60);
          hits.push({
            score: score,
            href: rec.href,
            chapter: rec.chapter,
            title: rec.title,
            snippet:
              (start > 0 ? "…" : "") +
              rec.body.slice(start, start + 170).trim() +
              "…",
          });
        }
      });
      hits.sort(function (a, b) {
        return b.score - a.score;
      });
      render(hits, q);
    });

    document.addEventListener("click", function (e) {
      if (!out.contains(e.target) && e.target !== input) out.classList.remove("open");
    });

    document.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        input.focus();
        input.select();
      }
      if (e.key === "Escape") out.classList.remove("open");
    });
  }

  /* ---------- подсказки к терминам ---------- */

  function initTooltips() {
    var tip = document.getElementById("tooltip");
    if (!tip || !window.GLOSSARY) return;
    document.querySelectorAll(".term").forEach(function (el) {
      var key = (el.getAttribute("data-term") || el.textContent).toLowerCase();
      var entry = window.GLOSSARY[key];
      if (!entry) return;
      el.addEventListener("mouseenter", function () {
        tip.textContent = entry;
        if (el.getAttribute("href")) {
          var more = document.createElement("span");
          more.className = "tip-more";
          more.textContent = "нажмите, чтобы открыть статью глоссария";
          tip.appendChild(more);
        }
        tip.classList.add("show");
        var r = el.getBoundingClientRect();
        var top = window.scrollY + r.top - tip.offsetHeight - 8;
        tip.style.top = (top < window.scrollY ? window.scrollY + r.bottom + 8 : top) + "px";
        tip.style.left =
          Math.max(8, Math.min(window.innerWidth - tip.offsetWidth - 8, r.left)) + "px";
      });
      el.addEventListener("mouseleave", function () {
        tip.classList.remove("show");
      });
    });
  }

  /* ---------- мобильное меню ---------- */

  function initMenu() {
    var btn = document.getElementById("menu-toggle");
    var bar = document.getElementById("sidebar");
    if (!btn || !bar) return;
    btn.addEventListener("click", function () {
      bar.classList.toggle("open");
    });
    bar.addEventListener("click", function (e) {
      if (e.target.tagName === "A") bar.classList.remove("open");
    });
  }

  /* ---------- главная ---------- */

  function buildHomeToc() {
    var host = document.getElementById("toc-grid");
    if (!host || !window.TOC) return;
    var done = readDone();
    var html = "";
    window.TOC.forEach(function (part) {
      html += '<div class="toc-part">' + part.part + "</div>";
      part.items.forEach(function (it) {
        html +=
          '<a class="toc-card ' +
          (done[it.id] ? "is-done" : "") +
          '" href="' +
          it.id +
          '.html"><span class="n">Глава ' +
          it.num +
          '</span><h3>' +
          it.title +
          "</h3><p>" +
          it.blurb +
          '</p><div class="tags">' +
          it.tags +
          "</div></a>";
      });
    });
    host.innerHTML = html;

    var reset = document.getElementById("reset-progress");
    if (reset)
      reset.addEventListener("click", function () {
        if (confirm("Сбросить отметки о пройденных главах?")) {
          localStorage.removeItem(LS_DONE);
          buildHomeToc();
          buildSidebar();
        }
      });
  }

  /* ---------- подпись автора ---------- */

  /* Футер и метатег автора ставятся движком, а не переписываются в 53 файлах
     руками: страницы собираются генератором, и любая ручная правка шаблона
     теряется при следующей пересборке главы. */
  function buildFooter() {
    if (!document.querySelector("meta[name=author]")) {
      var meta = document.createElement("meta");
      meta.name = "author";
      meta.content = "Евгений Миронов";
      document.head.appendChild(meta);
    }
    var main = document.querySelector("main");
    if (!main || document.querySelector(".site-footer")) return;
    var home = /(^|\/)index\.html$/.test(location.pathname) ||
      /\/$/.test(location.pathname);
    var f = document.createElement("footer");
    f.className = "site-footer";
    f.innerHTML =
      "<p><b>Евгений Миронов</b>, автор русскоязычной адаптации</p>" +
      (home
        ? ""
        : '<p>Учебник «AI-инженер с нуля». Источники и лицензии на ' +
          '<a href="index.html">главной</a> и в ' +
          '<a href="app-c.html">приложении C</a></p>');
    main.appendChild(f);
  }

  /* ---------- запуск ---------- */

  function boot() {
    initTheme();
    buildFooter();
    buildSidebar();
    buildHomeToc();
    buildChapterNav();
    buildOnPage();
    initMarkRead();
    initQuizzes();
    initSearch();
    initTooltips();
    initMenu();
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

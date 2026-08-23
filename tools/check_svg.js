/* Проверка вёрстки схем: наложение подписей и выход элементов за viewBox.

   Оценить ширину текста по числу символов нельзя, промахивается на десятки
   пикселей. Единственный честный способ измерить SVG-текст это getBBox в
   настоящем браузере, поэтому проверка живёт в виде скрипта для консоли,
   а не в конвейере на питоне.

   Как запускать:
     cd site && python3 -m http.server 8899
     открыть http://localhost:8899, консоль браузера, вставить этот файл целиком

   Повёрнутые подписи пропускаются: у них getBBox возвращает координаты до
   поворота, и любая проверка по ним даёт ложные срабатывания. */

(async () => {
  const toc = await (await fetch('assets/toc.js')).text();
  const ids = [...toc.matchAll(/id:\s*"(ch\d+|app-[a-d])"/g)].map((m) => m[1]);
  const pages = ['index', ...new Set(ids)];

  const host = document.createElement('div');
  host.style.cssText = 'position:absolute;left:-9999px;width:900px';
  document.body.appendChild(host);

  const bad = [];
  let total = 0;

  for (const page of pages) {
    let html;
    try {
      html = await (await fetch(page + '.html')).text();
    } catch {
      continue;
    }
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const svgs = [...doc.querySelectorAll('figure svg')];

    svgs.forEach((src, i) => {
      total++;
      host.innerHTML = '';
      const svg = src.cloneNode(true);
      host.appendChild(svg);
      const vb = svg.viewBox.baseVal;
      const where = `${page} схема ${i + 1}`;

      const texts = [...svg.querySelectorAll('text')].filter(
        (e) => e.textContent.trim() && !e.hasAttribute('transform')
      );

      // наложение подписей, стоящих на одной строке
      const rows = {};
      texts.forEach((e) => {
        const b = e.getBBox();
        const key = Math.round(b.y / 5);
        (rows[key] = rows[key] || []).push({
          x: b.x,
          end: b.x + b.width,
          t: e.textContent.trim(),
        });
      });
      Object.values(rows).forEach((row) => {
        row.sort((a, b) => a.x - b.x);
        for (let j = 0; j < row.length - 1; j++) {
          const over = row[j].end - row[j + 1].x;
          if (over > 0.5)
            bad.push(
              `${where}: «${row[j].t}» налезает на «${row[j + 1].t}» на ${Math.round(over)}px`
            );
        }
      });

      // выход за границы холста
      [...texts, ...svg.querySelectorAll('rect')].forEach((e) => {
        const b = e.getBBox();
        if (
          b.x + b.width > vb.x + vb.width + 1.5 ||
          b.x < vb.x - 1.5 ||
          b.y + b.height > vb.height + 1.5
        )
          bad.push(
            `${where}: <${e.tagName}> «${(e.textContent || '').trim().slice(0, 40)}» за границей viewBox`
          );
      });
    });
  }

  host.remove();
  bad.forEach((b) => console.warn(b));
  console.log(`схем проверено: ${total}, находок: ${bad.length}`);
})();

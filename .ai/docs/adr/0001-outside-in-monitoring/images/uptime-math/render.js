// Purpose: Renders the uptime formula cards (dashboards, ADR 0001) and the burn-rate card (ADR 0004)
// Renders the cards to standalone SVG (all glyphs as paths, white card, dark ink) for Grafana text panels.
// Usage: npm i mathjax-full@3 && node render.js <outDir>, then rsvg-convert -z 2 (docs) or -z 1.5 plus a
//   24-colour quantize to keep the PNGs small
const fs = require('fs');
const path = require('path');
const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { SVG } = require('mathjax-full/js/output/svg.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');
const { AllPackages } = require('mathjax-full/js/input/tex/AllPackages.js');
require('mathjax-full/js/input/tex/textmacros/TextMacrosConfiguration.js');

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const doc = mathjax.document('', {
  InputJax: new TeX({ packages: AllPackages.concat('textmacros') }),
  OutputJax: new SVG({ fontCache: 'global' }),
});

const C = { ink: '#1c1c1e', muted: '#6b6b70', accent: '#2e6b4c', danger: '#b3261e', line: '#e5e2db',
  card: '#ffffff', soft: '#faf9f6', okBg: '#f2f8f4', okLine: '#c4dccd', badBg: '#fdf4f3', badLine: '#f0cdc9' };

function tex2svg(tex, sizePx, color) {
  const node = doc.convert(tex, { display: true });
  const svg = adaptor.firstChild(node);
  const [vx, vy, vw, vh] = adaptor.getAttribute(svg, 'viewBox').split(/\s+/).map(Number);
  const s = sizePx / 1000;
  const inner = adaptor.innerHTML(svg).replace(/currentColor/g, color);
  return { w: vw * s, h: vh * s, render: (x, y) =>
    `<svg x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${(vw * s).toFixed(2)}" height="${(vh * s).toFixed(2)}" viewBox="${vx} ${vy} ${vw} ${vh}" overflow="visible">${inner}</svg>` };
}

// blocks: {tex, size, color, gap} or {box: 'ok'|'bad'|'soft', blocks:[...], gap}
function layout(blocks, pad = 16) {
  const items = [];
  let y = 0, w = 0;
  for (const b of blocks) {
    y += items.length ? (b.gap ?? 12) : 0;
    if (b.box) {
      const inner = layout(b.blocks, 0);
      const bp = 14;
      items.push({ y, kind: 'box', box: b.box, inner, bp });
      w = Math.max(w, inner.w + 2 * bp);
      y += inner.h + 2 * bp;
    } else {
      const m = tex2svg(b.tex, b.size ?? 19, b.color ?? C.ink);
      items.push({ y, kind: 'tex', m });
      w = Math.max(w, m.w);
      y += m.h;
    }
  }
  return { w, h: y, items, render(x0, y0, width) {
    return items.map(it => {
      if (it.kind === 'tex') return it.m.render(x0, y0 + it.y);
      const [fill, stroke] = { ok: [C.okBg, C.okLine], bad: [C.badBg, C.badLine], soft: [C.soft, C.line] }[it.box];
      const bw = width ?? (it.inner.w + 2 * it.bp);
      return `<rect x="${x0}" y="${(y0 + it.y).toFixed(2)}" width="${bw.toFixed(2)}" height="${(it.inner.h + 2 * it.bp).toFixed(2)}" rx="10" fill="${fill}" stroke="${stroke}"/>`
        + it.inner.render(x0 + it.bp, y0 + it.y + it.bp, bw - 2 * it.bp);
    }).join('\n');
  } };
}

function card(blocks, minW = 560) {
  const pad = 28;
  doc.outputJax.fontCache.clearCache();
  const L = layout(blocks);
  const defs = adaptor.outerHTML(doc.outputJax.fontCache.getCache());
  const W = Math.ceil(Math.max(minW, L.w + 2 * pad));
  const H = Math.ceil(L.h + 2 * pad);
  return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<rect x="0.5" y="0.5" width="${W - 1}" height="${H - 1}" rx="14" fill="${C.card}" stroke="${C.line}"/>
${defs}
${L.render(pad, pad, W - 2 * pad)}
</svg>\n`;
}

// helpers for the TeX
const T = s => `\\text{${s}}`;
const hex = c => c.slice(1).toUpperCase();
const col = (c, s) => `{\\color{${c}}{${s}}}`;
const R = s => col(C.accent, `\\mathbf{${s}}`);      // a result
const BAD = s => col(C.danger, `\\mathbf{${s}}`);
const kicker = s => ({ tex: `\\textbf{${s}}`, size: 13, color: C.accent });
const title = s => ({ tex: `\\textbf{${s}}`, size: 22, color: C.ink, gap: 6 });
const question = s => ({ tex: `\\textsf{${s}}`, size: 16, color: C.muted, gap: 6 });
const math = (s, gap = 18) => ({ tex: s, size: 20, gap });
const caption = (s, gap = 16) => ({ tex: `\\textsf{${s.replace(/%/g, '\\%')}}`, size: 14.5, color: C.muted, gap });


const X = s => `\\text{${s}}`;
const cards = {
  'alert-burn-rate': [
    kicker('WHEN AN ALERT FIRES'), title('Burn rate: how fast downtime is piling up'),
    question('Grafana compares recent downtime with the downtime a 95% objective allows over 14 days.'.replace('95%', '95\\%')),
    math(String.raw`
\begin{aligned}
\text{Allowed downtime} &= (1 - \text{Objective}) \times \text{Window} = 0.05 \times 14\ \text{days} = ${R('16.8\\ \\text{hours}')} \\[10pt]
\text{Burn rate} &= \frac{1 - \text{Uptime over a recent period}}{1 - \text{Objective}}
\end{aligned}`, 20),
    caption('A burn rate of 1 uses the allowed downtime exactly by the end of the 14 days. Higher uses it up sooner.', 12),
    { box: 'soft', gap: 16, blocks: [
      { tex: String.raw`\textbf{The four conditions Grafana generated (each needs a long and a short period to agree)}`, size: 15 },
      { tex: String.raw`
\begin{array}{llll}
\textbf{Fast burn} & \text{burn rate} \ge 14.4 & \text{last 1 hour and last 5 minutes} & \text{more than 72\% down} \\[6pt]
 & \text{burn rate} \ge 6 & \text{last 6 hours and last 30 minutes} & \text{more than 30\% down} \\[10pt]
\textbf{Slow burn} & \text{burn rate} \ge 3 & \text{last 1 day and last 2 hours} & \text{more than 15\% down} \\[6pt]
 & \text{burn rate} \ge 1 & \text{last 3 days and last 6 hours} & \text{more than 5\% down}
\end{array}`, size: 16, gap: 12 } ] },
    { box: 'ok', gap: 14, blocks: [
      { tex: String.raw`\textbf{Example: one failed 20-minute run in the last hour, 1 location}`, size: 15, color: C.accent },
      { tex: String.raw`
\text{Uptime over the last hour} = \frac{8\ \text{readings up}}{12\ \text{readings expected}} = 66.7\% \qquad
\text{Burn rate} = \frac{1 - 0.667}{1 - 0.95} = ${R('6.7')} < 14.4`, size: 18, gap: 10 },
      caption('No alert from a single bad run. It takes most of an hour down, or a third of six hours, to page.', 10) ] },
  ],

  'uptime-1-formula': [
    kicker('HOW UPTIME IS CALCULATED'), title('Uptime over the last 14 days'),
    question('Of the readings the schedule promised, what share were up?'),
    { box: 'soft', gap: 16, blocks: [
      { tex: String.raw`\textbf{Reading:}\ \text{every 5 minutes, each check location reports the latest result of its check.}`, size: 15 },
      { tex: String.raw`\text{A check runs every 20 minutes, so one run is read 4 times.}`, size: 15, gap: 6 },
      { tex: String.raw`\textbf{Up:}\ \text{the latest result passed.}\qquad \textbf{Down:}\ \text{it failed, or no result arrived.}`, size: 15, gap: 10 } ] },
    math(String.raw`
\begin{aligned}
\text{Readings expected} &= \frac{\text{Locations} \times \text{Minutes measured}}{5\ \text{minutes}} \\[10pt]
\text{Uptime} &= \frac{\text{Readings up}}{\text{Readings expected}}
\end{aligned}`, 20),
    { box: 'ok', gap: 18, blocks: [
      { tex: String.raw`\textbf{Example: 1 location, measured for 3 days (4{,}320 minutes), 858 readings up}`, size: 15, color: C.accent },
      { tex: String.raw`
\begin{aligned}
\text{Readings expected} &= \frac{1 \times 4{,}320}{5} = ${R('864')} \\[8pt]
\text{Uptime} &= \frac{858}{864} = ${R('99.31\\%')}
\end{aligned}`, size: 19, gap: 12 } ] },
  ],
  'uptime-2-downtime': [
    kicker('DOWNTIME'), title('How long it was down'),
    question('Turn the readings that were down back into minutes.'),
    math(String.raw`
\begin{aligned}
\text{Readings down} &= \text{Readings expected} - \text{Readings up} \\[10pt]
\text{Downtime} &= \frac{\text{Readings down} \times 5\ \text{minutes}}{\text{Locations}}
\end{aligned}`, 20),
    { box: 'ok', gap: 18, blocks: [
      { tex: String.raw`\textbf{Same example}`, size: 15, color: C.accent },
      { tex: String.raw`
\begin{aligned}
\text{Readings down} &= 864 - 858 = ${R('6')} \\[8pt]
\text{Downtime} &= \frac{6 \times 5\ \text{minutes}}{1} = ${R('30\\ \\text{minutes}')}
\end{aligned}`, size: 19, gap: 12 } ] },
    caption('With two locations, one failing while the other passes counts as half that time down.'),
  ],
  'uptime-3-missing': [
    kicker('MISSING RESULTS AND NEW CHECKS'), title('Silence counts as down; the window fills up over time'),
    question('Example: the monitor goes offline for 1 hour. 12 readings never arrive, and nothing failed.'),
    { box: 'bad', gap: 16, blocks: [
      { tex: String.raw`\textbf{Counting only results that arrived: hides the hour}`, size: 15, color: C.danger },
      { tex: String.raw`\text{Uptime} = \frac{\text{Readings up}}{\text{Readings that arrived}} = \frac{852}{852} = 100.00\%`, size: 19, gap: 10 } ] },
    { box: 'ok', gap: 12, blocks: [
      { tex: String.raw`\textbf{Counting the readings the schedule expected: shows the hour}`, size: 15, color: C.accent },
      { tex: String.raw`\text{Uptime} = \frac{\text{Readings up}}{\text{Readings expected}} = \frac{852}{864} = ${R('98.61\\%')} \qquad \text{Downtime} = ${R('60\\ \\text{minutes}')}`, size: 19, gap: 10 } ] },
    math(String.raw`
\text{Days measured} = \frac{\text{Readings expected}}{\text{Locations} \times 288\ \text{readings per day}} = \frac{864}{1 \times 288} = ${R('3')}\ \text{of 14 days}`, 22),
    caption('Monitoring started recently, so the 14-day window is not full yet. Until it is, uptime covers only the days measured.'),
  ],
};
const out = process.argv[2];
fs.mkdirSync(out, { recursive: true });
for (const [name, blocks] of Object.entries(cards)) fs.writeFileSync(path.join(out, name + '.svg'), card(blocks, 760).replace(/(\d+\.\d)\d+/g, '$1').replace(/\n\s*/g, ''));
console.log('wrote', Object.keys(cards).length);

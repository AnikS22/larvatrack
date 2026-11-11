// Shared helpers for the tool pages: page chrome, stats, a bar chart, CSV out.
// Everything runs in the browser; nothing is uploaded anywhere.
"use strict";
const EMAIL = "asahai2024@fau.edu";

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// ---- page chrome -----------------------------------------------------------
function chrome() {
  const top = document.createElement("div");
  top.className = "top";
  top.innerHTML = `<div class="wrap"><a class="brand" href="../../"><b>FlyBench</b></a>
    <div class="college">Drosophila Data Analysis Tool Suite<br>Made by <b class="by">Anik Sahai</b></div>
    <a class="back" href="../../">← All tools</a></div>`;
  document.body.prepend(top);
  const f = document.createElement("footer");
  f.innerHTML = `<div class="wrap"><b>FlyBench</b>, made by Anik Sahai (Harriet L. Wilkes Honors College, Florida Atlantic University).
    Runs entirely in your browser: your files never leave this computer.
    Need automatic analysis instead? <a href="mailto:${EMAIL}?subject=FlyBench%20analysis%20request">Request AI analysis: ${EMAIL}</a></div>`;
  document.body.append(f);
}

// ---- stats -----------------------------------------------------------------
const mean = a => a.length ? a.reduce((s, x) => s + x, 0) / a.length : NaN;
const sd = a => { if (a.length < 2) return NaN; const m = mean(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); };
const sem = a => sd(a) / Math.sqrt(a.length);

function lgamma(x) {  // Lanczos
  const g = 7, c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
    -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - lgamma(1 - x);
  x -= 1; let a = c[0]; const t = x + g + 0.5;
  for (let i = 1; i < 9; i++) a += c[i] / (x + i);
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}
function betacf(a, b, x) {  // continued fraction for the incomplete beta (Numerical Recipes)
  let qab = a + b, qap = a + 1, qam = a - 1, c = 1, d = 1 - qab * x / qap;
  d = 1 / (Math.abs(d) < 1e-300 ? 1e-300 : d); let h = d;
  for (let m = 1; m <= 300; m++) {
    const m2 = 2 * m; let aa = m * (b - m) * x / ((qam + m2) * (a + m2));
    d = 1 + aa * d; d = 1 / (Math.abs(d) < 1e-300 ? 1e-300 : d); c = 1 + aa / c; c = Math.abs(c) < 1e-300 ? 1e-300 : c; h *= d * c;
    aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
    d = 1 + aa * d; d = 1 / (Math.abs(d) < 1e-300 ? 1e-300 : d); c = 1 + aa / c; c = Math.abs(c) < 1e-300 ? 1e-300 : c;
    const del = d * c; h *= del; if (Math.abs(del - 1) < 1e-12) break;
  }
  return h;
}
function ibeta(a, b, x) {
  if (x <= 0) return 0; if (x >= 1) return 1;
  const bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
  return x < (a + 1) / (a + b + 2) ? bt * betacf(a, b, x) / a : 1 - bt * betacf(b, a, 1 - x) / b;
}
function gammaQ(a, x) {  // upper regularized gamma, for chi-square p
  if (x <= 0) return 1;
  if (x < a + 1) { let s = 1 / a, t = s; for (let n = 1; n < 500; n++) { t *= x / (a + n); s += t; if (t < s * 1e-14) break; }
    return 1 - s * Math.exp(-x + a * Math.log(x) - lgamma(a)); }
  let b = x + 1 - a, c = 1e300, d = 1 / b, h = d;
  for (let i = 1; i < 500; i++) { const an = -i * (i - a); b += 2; d = an * d + b; d = 1 / (Math.abs(d) < 1e-300 ? 1e-300 : d);
    c = b + an / c; c = Math.abs(c) < 1e-300 ? 1e-300 : c; const del = d * c; h *= del; if (Math.abs(del - 1) < 1e-14) break; }
  return Math.exp(-x + a * Math.log(x) - lgamma(a)) * h;
}
// Welch two-sample t-test, two-sided.
function welch(a, b) {
  if (a.length < 2 || b.length < 2) return { t: NaN, df: NaN, p: NaN };
  const va = sd(a) ** 2 / a.length, vb = sd(b) ** 2 / b.length;
  if (va + vb === 0) return { t: NaN, df: NaN, p: NaN };
  const t = (mean(a) - mean(b)) / Math.sqrt(va + vb);
  const df = (va + vb) ** 2 / (va ** 2 / (a.length - 1) + vb ** 2 / (b.length - 1));
  return { t, df, p: ibeta(df / 2, 0.5, df / (df + t * t)) };
}
// Chi-square test of independence on a table of counts (rows = groups, cols = categories).
function chisq(table) {
  const R = table.length, C = table[0].length, rs = table.map(r => r.reduce((s, x) => s + x, 0));
  const cs = table[0].map((_, j) => table.reduce((s, r) => s + r[j], 0)), N = rs.reduce((s, x) => s + x, 0);
  let x2 = 0;
  for (let i = 0; i < R; i++) for (let j = 0; j < C; j++) { const e = rs[i] * cs[j] / N; if (e > 0) x2 += (table[i][j] - e) ** 2 / e; }
  const df = (R - 1) * (C - 1);
  return { x2, df, p: df > 0 ? gammaQ(df / 2, x2 / 2) : NaN };
}
// Chi-square goodness of fit: observed counts vs expected proportions (any scale, e.g. 9:3:3:1).
function chisqGOF(obs, ratio) {
  const N = obs.reduce((s, x) => s + x, 0), R = ratio.reduce((s, x) => s + x, 0);
  const exp = ratio.map(r => N * r / R); let x2 = 0;
  obs.forEach((o, i) => { if (exp[i] > 0) x2 += (o - exp[i]) ** 2 / exp[i]; });
  const df = obs.length - 1;
  return { x2, df, p: df > 0 ? gammaQ(df / 2, x2 / 2) : NaN, exp };
}
// One-sample t-test against mu (two-sided).
function ttest1(a, mu = 0) {
  if (a.length < 2 || !(sd(a) > 0)) return { t: NaN, df: NaN, p: NaN };
  const t = (mean(a) - mu) / sem(a), df = a.length - 1;
  return { t, df, p: ibeta(df / 2, 0.5, df / (df + t * t)) };
}
// First time a rising curve [[t, fraction]] reaches `level`, by linear interpolation; NaN if never.
function timeTo(curve, level = 0.5) {
  for (let i = 0; i < curve.length; i++) {
    const [t, f] = curve[i]; if (f < level) continue;
    if (i === 0) return t;
    const [t0, f0] = curve[i - 1]; return t0 + (level - f0) / (f - f0) * (t - t0);
  }
  return NaN;
}
const fmt = (x, d = 2) => Number.isFinite(x) ? x.toFixed(d) : "–";
const fmtp = p => !Number.isFinite(p) ? "–" : p < 0.001 ? "< 0.001" : p.toFixed(3);

// ---- grouping --------------------------------------------------------------
// "Male control: 1-8, 10" lines -> {label: [1..8,10]}
function parseGroups(text) {
  const out = {};
  for (const line of text.split(/\n/)) {
    const m = line.match(/^\s*([^:]+):\s*(.+)$/); if (!m) continue;
    const ids = [];
    for (const part of m[2].split(/[,\s]+/)) {
      const r = part.match(/^(\d+)(?:-(\d+))?$/); if (!r) continue;
      for (let i = +r[1]; i <= +(r[2] || r[1]); i++) ids.push(i);
    }
    if (ids.length) out[m[1].trim()] = ids;
  }
  return out;
}
function byGroup(rows, key, val) {  // -> [{group, values}]
  const m = new Map();
  for (const r of rows) { const g = r[key]; if (g == null || g === "" || !Number.isFinite(r[val])) continue; if (!m.has(g)) m.set(g, []); m.get(g).push(r[val]); }
  return [...m].map(([group, values]) => ({ group, values }));
}

// ---- bar chart (mean ± error, dots for replicates) ---------------------------
const PALETTE = ["#003366", "#cc0000", "#4f7cac", "#e3a33b", "#2e8b57", "#7a4fa3", "#8a8f98", "#d1495b"];
function barChart(el, groups, { ylabel = "", err = "sem", title = "" } = {}) {
  const W = 720, H = 360, L = 64, B = 70, T = title ? 34 : 14, R = 14;
  const vals = groups.flatMap(g => g.values), ms = groups.map(g => mean(g.values));
  const es = groups.map(g => (err === "sd" ? sd : sem)(g.values) || 0);
  const ymax = Math.max(1e-9, ...vals, ...ms.map((m, i) => m + es[i])) * 1.12;
  const y = v => T + (H - T - B) * (1 - v / ymax), bw = (W - L - R) / Math.max(1, groups.length);
  const tick = niceStep(ymax / 5);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title || ylabel)}" font-family="Source Sans 3, system-ui, sans-serif">`;
  if (title) s += `<text x="${W / 2}" y="22" text-anchor="middle" font-size="16" font-weight="700" fill="#1b2430">${esc(title)}</text>`;
  for (let v = 0; v <= ymax + 1e-9; v += tick) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e6e9ee"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="12" fill="#556170">${+v.toFixed(6)}</text>`;
  s += `<text transform="translate(16 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" font-size="13" fill="#1b2430">${esc(ylabel)}</text>`;
  groups.forEach((g, i) => {
    const x = L + i * bw + bw * 0.18, w = bw * 0.64, c = PALETTE[i % PALETTE.length];
    if (Number.isFinite(ms[i])) s += `<rect x="${x}" y="${y(ms[i])}" width="${w}" height="${y(0) - y(ms[i])}" fill="${c}" opacity=".85"/>`;
    if (es[i]) { const cx = x + w / 2; s += `<path d="M${cx} ${y(ms[i] - es[i])}V${y(ms[i] + es[i])}M${cx - 7} ${y(ms[i] + es[i])}h14M${cx - 7} ${y(ms[i] - es[i])}h14" stroke="#1b2430" stroke-width="1.5"/>`; }
    g.values.forEach((v, k) => s += `<circle cx="${x + w / 2 + ((k % 5) - 2) * 5}" cy="${y(v)}" r="3" fill="#fff" stroke="#1b2430"/>`);
    s += `<text x="${x + w / 2}" y="${H - B + 18}" text-anchor="middle" font-size="13" fill="#1b2430">${esc(g.group)}</text>`;
    s += `<text x="${x + w / 2}" y="${H - B + 34}" text-anchor="middle" font-size="11" fill="#556170">n = ${g.values.length}</text>`;
  });
  s += `<line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="#1b2430"/>`;
  s += `<text x="${W - R}" y="${H - 8}" text-anchor="end" font-size="11" fill="#556170">bars: mean ± ${err.toUpperCase()}; dots: replicates</text></svg>`;
  el.innerHTML = s;
}
// Stacked 100% bars: rows = [{group, parts:[fractions summing to 1]}], labels bottom-to-top.
function stackedChart(el, rows, labels, { title = "", ylabel = "% of flies" } = {}) {
  const W = 720, H = 360, L = 64, B = 60, T = title ? 34 : 14, R = 150, bw = (W - L - R) / Math.max(1, rows.length);
  const shades = ["#9fbcdc", "#5b8cc0", "#2a5f95", "#003366", "#001a33"];
  const y = f => T + (H - T - B) * (1 - f);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}" font-family="Source Sans 3, system-ui, sans-serif">`;
  if (title) s += `<text x="${(W - R + L) / 2}" y="22" text-anchor="middle" font-size="16" font-weight="700" fill="#1b2430">${esc(title)}</text>`;
  for (let v = 0; v <= 1.0001; v += 0.25) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e6e9ee"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="12" fill="#556170">${v * 100}%</text>`;
  s += `<text transform="translate(16 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" font-size="13">${esc(ylabel)}</text>`;
  rows.forEach((r, i) => {
    const x = L + i * bw + bw * 0.18, w = bw * 0.64; let acc = 0;
    r.parts.forEach((f, k) => { if (f > 0) s += `<rect x="${x}" y="${y(acc + f)}" width="${w}" height="${y(acc) - y(acc + f)}" fill="${shades[k % shades.length]}" stroke="#fff"/>`; acc += f; });
    s += `<text x="${x + w / 2}" y="${H - B + 18}" text-anchor="middle" font-size="13">${esc(r.group)}</text>`;
    if (r.n != null) s += `<text x="${x + w / 2}" y="${H - B + 34}" text-anchor="middle" font-size="11" fill="#556170">n = ${r.n}</text>`;
  });
  labels.forEach((lab, k) => { const yy = T + 10 + (labels.length - 1 - k) * 22; s += `<rect x="${W - R + 14}" y="${yy}" width="14" height="14" fill="${shades[k % shades.length]}"/><text x="${W - R + 34}" y="${yy + 12}" font-size="12">${esc(lab)}</text>`; });
  el.innerHTML = s + "</svg>";
}
function niceStep(x) { const p = 10 ** Math.floor(Math.log10(x)), f = x / p; return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p; }

// ---- summary table + CSV ---------------------------------------------------
function summaryTable(el, groups, unit = "", err = "sem") {
  let h = `<table><tr><th>Group</th><th class="n">n</th><th class="n">Mean${unit ? " (" + esc(unit) + ")" : ""}</th><th class="n">SD</th><th class="n">SEM</th></tr>`;
  for (const g of groups) h += `<tr><td>${esc(g.group)}</td><td class="n">${g.values.length}</td><td class="n">${fmt(mean(g.values))}</td><td class="n">${fmt(sd(g.values))}</td><td class="n">${fmt(sem(g.values))}</td></tr>`;
  if (groups.length >= 2) {
    h += `<tr><th colspan="5">Welch t-test, each pair (two-sided)</th></tr>`;
    for (let i = 0; i < groups.length; i++) for (let j = i + 1; j < groups.length; j++) {
      const w = welch(groups[i].values, groups[j].values);
      h += `<tr><td colspan="2">${esc(groups[i].group)} vs ${esc(groups[j].group)}</td><td class="n">t = ${fmt(w.t)}</td><td class="n">df = ${fmt(w.df, 1)}</td><td class="n">p = ${fmtp(w.p)}</td></tr>`;
    }
  }
  el.innerHTML = h + "</table>";
}
function downloadCSV(name, rows) {
  if (!rows.length) return;
  const cols = Object.keys(rows[0]);
  const q = v => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const csv = [cols.join(","), ...rows.map(r => cols.map(c => q(r[c])).join(","))].join("\n");
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: name });
  document.body.append(a); a.click(); a.remove();
}

// ---- canvas helpers ----------------------------------------------------------
function canvasPoint(cv, e) { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * cv.width / r.width, (e.clientY - r.top) * cv.height / r.height]; }
function loadImageFile(file) { return new Promise((ok, bad) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => bad(new Error("Could not open that image")); im.src = URL.createObjectURL(file); }); }

// ---- self-check: `node docs/tools/suite.js` --------------------------------
if (typeof module !== "undefined" && require.main === module) {
  const near = (a, b, tol) => { if (Math.abs(a - b) > tol) throw new Error(`${a} != ${b}`); };
  near(mean([1, 2, 3]), 2, 1e-12); near(sd([2, 4, 4, 4, 5, 5, 7, 9]), 2.13809, 1e-4);
  const w = welch([27.5, 21.0, 19.0, 23.6, 17.0, 17.9, 16.9, 20.1, 21.9, 22.6, 23.1, 19.6, 19.0, 21.7, 21.4],
                  [27.1, 22.0, 20.8, 23.4, 23.4, 23.5, 25.8, 22.0, 24.8, 20.2, 21.9, 22.1, 22.9, 20.5, 24.4]);
  near(w.t, -2.46, 0.01); near(w.p, 0.0210, 0.001);          // Wikipedia Welch example 1 (scipy: p = 0.02101)
  const c = chisq([[10, 20, 30], [20, 20, 20]]); near(c.x2, 5.3333, 1e-3); near(c.p, 0.0695, 1e-3);  // by hand: E = 15,20,25 per row
  near(gammaQ(1, 2), Math.exp(-2), 1e-10);
  const gof = chisqGOF([315, 108, 101, 32], [9, 3, 3, 1]); near(gof.x2, 0.470, 1e-3); near(gof.p, 0.925, 1e-3);  // Mendel's peas
  const t1 = ttest1([1, 2, 3, 4, 5], 0); near(t1.t, 4.2426, 1e-3); near(t1.p, 0.01324, 1e-4);   // scipy ttest_1samp
  near(timeTo([[0, 0], [10, 0.4], [20, 0.8]]), 12.5, 1e-9); if (!Number.isNaN(timeTo([[0, 0], [5, 0.3]]))) throw new Error("timeTo");
  const g = parseGroups("Male control: 1-3, 7\nbad line\nF caf: 10");
  if (JSON.stringify(g) !== '{"Male control":[1,2,3,7],"F caf":[10]}') throw new Error(JSON.stringify(g));
  console.log("suite.js self-check OK");
}

"""One review page for everything auto-annotated: climbing videos + fly paper photos.

  cd ~/Downloads/geotaxis_results && python3 ~/Desktop/PCB4054C-01H/fly/review_all.py

Reads geotaxis/Folder */ (+ cache/*.auto.json from geotaxis.py) and photos/ (+ cache/fly_paper_points.json
from fly_paper.py). Writes review_all.html and opens it. Click = add / remove a fly. Edits stay in the browser;
"Download" buttons give the corrected CSVs.
"""
import base64, glob, json, os, re, webbrowser
import cv2

# fly paper: which sheet / phenotype each photo shows (tube labels Oct 22, writing on sheet Oct 29)
PAPER = {"IMG_6491": "Hey ♀", "IMG_6492": "Hey ♀", "IMG_6500": "Hey ♀", "IMG_6493": "w1118", "IMG_6494": "w1118",
         "IMG_6501": "w1118", "IMG_6495": "M1", "IMG_6502": "M1", "IMG_6496": "f ♂", "IMG_6497": "f ♂", "IMG_6503": "f ♂",
         "IMG_6498": "CS ♂", "IMG_6504": "CS ♂", "IMG_6561": "w1118 ♂", "IMG_6563": "CS ♂", "IMG_6564": "CS ♂",
         "IMG_6565": "M1 ♂", "IMG_6566": "f ♂", "IMG_6567": "Hey ♂"}   # IMG_6499 = overview of all 5 cut sheets, left out
VIEW = 0.4   # fly paper image size in the page (fraction of the 12 MP photo)


def climbing():
    items = []
    for folder in sorted(glob.glob("geotaxis/Folder *"), key=lambda f: int(f.split()[1])):
        m = re.match(r"Folder (\d+) - (Oct \d+) - (.+) \(left to right\)", os.path.basename(folder))
        labels = [x.strip() for x in m.group(3).split("+")]
        for trial, v in enumerate(sorted(p for p in glob.glob(folder + "/*") if p.lower().endswith(".mov")), 1):
            name = os.path.splitext(os.path.basename(v))[0]
            d = json.load(open(f"cache/{name}.auto.json"))
            items.append({"kind": "climb", "name": name, "label": f"Set {m.group(1)} ({m.group(2)}) trial {trial}",
                          "group": f"Folder {m.group(1)}", "vials": labels, "rois": d["rois"], "frames": d["frames"]})
    return items


def paper():
    pts = json.load(open("cache/fly_paper_points.json"))
    items = []
    for photo, p in sorted(pts.items()):
        name = os.path.splitext(photo)[0]
        if name not in PAPER:
            continue
        path = glob.glob(f"photos/*/{photo}")[0]
        k = VIEW / p["scale"]
        im = cv2.imread(path); im = cv2.resize(im, None, fx=VIEW, fy=VIEW, interpolation=cv2.INTER_AREA)
        jpg = base64.b64encode(cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 82])[1]).decode()
        items.append({"kind": "paper", "name": name, "label": f"{PAPER[name]} ({path.split('/')[1]})",
                      "date": path.split("/")[1], "phenotype": PAPER[name], "horiz": p["horiz"],
                      "lines": [v * k for v in p["lines"]],
                      "frames": [{"img": "data:image/jpeg;base64," + jpg, "pts": [[x * k, y * k] for x, y in p["pts"]]}]})
    return items


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Fly Data Review</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f6f6f4;--fg:#1d1d1b;--muted:#6b6b66;--line:#d9d9d4;--card:#fff;--accent:#c62828;--warn:#fff3cd}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ececea;--muted:#9a9a94;--line:#33332f;--card:#1f1f1d;--accent:#ff6b6b;--warn:#4a3d10}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 -apple-system,system-ui,sans-serif}
header{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:1}
header b{font-size:15px;margin-right:4px}
button,select{font:inherit;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--muted)} .dl{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.tab.on{background:var(--fg);color:var(--bg)}
main{display:flex;flex-wrap:wrap;gap:16px;padding:16px}
canvas{display:block;max-width:100%;cursor:crosshair;border-radius:6px}
#side{flex:1;min-width:300px}
h2{font-size:16px;margin:0 0 6px}
table{border-collapse:collapse;width:100%;background:var(--card);font-variant-numeric:tabular-nums}
th,td{border:1px solid var(--line);padding:4px 6px;text-align:center}
th{color:var(--muted);font-weight:500}
tr.cur td{outline:2px solid var(--accent);outline-offset:-2px}
td.off{background:var(--warn)}
.hint{color:var(--muted);margin:8px 0}
#t{font-weight:600;min-width:60px;display:inline-block;text-align:center}
#prog{color:var(--muted)}
</style></head><body>
<header><b>Fly data review</b>
<button class="tab" data-k="climb">Climbing</button><button class="tab" data-k="paper">Fly paper</button>
<select id="item"></select>
<button id="prev">&larr; item</button><button id="next">item &rarr;</button>
<span id="secs"><button id="pf">&larr; sec</button><span id="t"></span><button id="nf">sec &rarr;</button></span>
<button id="reset">Reset to auto</button>
<button class="dl" id="dlc">Download climbing CSV</button><button class="dl" id="dlp">Download fly paper CSV</button>
<span id="prog"></span>
</header>
<main><div><canvas id="c"></canvas></div>
<div id="side"><h2 id="title"></h2>
<p class="hint">Click a missed fly to add it, click a circle to remove it. Keys: <b>space / &rarr;</b> next, <b>&larr;</b> back, <b>] [</b> next / previous item. Edits save in this browser.</p>
<p class="hint" id="hint2"></p><div id="tbl"></div></div></main>
<script>
const D = __DATA__;
let kind = "climb", vi = 0, s = 0;
const items = () => D.filter(d => d.kind === kind);
const cur = () => items()[vi];
const key = (it, t) => it.kind === "climb" ? "geo:" + it.name + ":" + t : "paper:" + it.name;
function pts(it, t) {
  try { const e = localStorage.getItem(key(it, t)); if (e) return JSON.parse(e); } catch (_) {}
  return it.frames[t].pts.map(p => p.slice());
}
function save(it, t, p) { try { localStorage.setItem(key(it, t), JSON.stringify(p)); } catch (_) {} }
function edited(it) { try { return it.frames.some((_, t) => localStorage.getItem(key(it, t))); } catch (_) { return false; } }
const sum = a => a.reduce((x, y) => x + y, 0);
function quads(roi, p) {             // climbing: Q1 = top quarter of the vial
  const [x, y, w, h] = roi, q = [0, 0, 0, 0];
  for (const [px, py] of p) if (px >= x && px <= x + w && py >= y && py <= y + h) q[Math.min(3, Math.floor((py - y) / h * 4))]++;
  return q;
}
function zones(it, p) {              // fly paper: zone 1 = top (or left), split by the red lines
  const z = [0, 0, 0];
  for (const [px, py] of p) { const v = it.horiz ? py : px; z[Math.min(2, it.lines.filter(l => v > l).length)]++; }
  return z;
}
function usual(it, r) {
  const c = {}; it.frames.forEach((_, t) => { const n = sum(quads(it.rois[r], pts(it, t))); c[n] = (c[n] || 0) + 1; });
  return +Object.keys(c).sort((a, b) => c[b] - c[a] || b - a)[0];
}
const cv = document.getElementById("c"), cx = cv.getContext("2d"), img = new Image();
let sc = 1;
function draw() {
  const it = cur(), p = pts(it, s);
  sc = Math.min((innerHeight - 110) / img.height, (innerWidth * 0.62) / img.width, 2.2);
  cv.width = img.width * sc; cv.height = img.height * sc;
  cx.drawImage(img, 0, 0, cv.width, cv.height); cx.font = "bold 15px system-ui";
  if (it.kind === "climb") {
    it.rois.forEach((r, i) => {
      const [x, y, w, h] = r.map(v => v * sc);
      cx.lineWidth = 1.5; cx.strokeStyle = "#2e7d32"; cx.setLineDash([]); cx.strokeRect(x, y, w, h);
      cx.strokeStyle = "rgba(25,118,210,.8)"; cx.setLineDash([5, 4]);
      for (let k = 1; k < 4; k++) { cx.beginPath(); cx.moveTo(x, y + h * k / 4); cx.lineTo(x + w, y + h * k / 4); cx.stroke(); }
      cx.setLineDash([]);
      const q = quads(r, p);
      cx.fillStyle = "#1565c0"; q.forEach((n, k) => cx.fillText("Q" + (4 - k) + ": " + n, x + w + 4, y + h * (k + .5) / 4 + 5));
      cx.fillStyle = "#c62828"; cx.fillText((it.vials[i] || "vial " + (i + 1)) + " - " + sum(q), x, y - 6);
    });
  } else {
    cx.strokeStyle = "rgba(25,118,210,.9)"; cx.lineWidth = 2; cx.setLineDash([8, 5]);
    it.lines.forEach(l => { cx.beginPath(); if (it.horiz) { cx.moveTo(0, l * sc); cx.lineTo(cv.width, l * sc); } else { cx.moveTo(l * sc, 0); cx.lineTo(l * sc, cv.height); } cx.stroke(); });
    cx.setLineDash([]);
    const z = zones(it, p), b = [0, ...it.lines.map(l => l * sc), it.horiz ? cv.height : cv.width];
    cx.fillStyle = "#1565c0";
    z.forEach((n, k) => { const m = (b[k] + b[k + 1]) / 2; it.horiz ? cx.fillText("Interval " + (4 - k) + ": " + n, 8, m) : cx.fillText("Interval " + (4 - k) + ": " + n, m - 40, 24); });
  }
  cx.strokeStyle = "#e53935"; cx.lineWidth = 2;
  for (const [px, py] of p) { cx.beginPath(); cx.arc(px * sc, py * sc, 9, 0, 7); cx.stroke(); }
  document.getElementById("t").textContent = s + " s";
  document.getElementById("secs").style.display = it.kind === "climb" ? "" : "none";
  document.getElementById("item").value = vi;
  document.getElementById("title").textContent = it.label + "  -  " + it.name;
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("on", b.dataset.k === kind));
  const n = items().filter(edited).length;
  document.getElementById("prog").textContent = n + " / " + items().length + " edited";
  table();
}
function table() {
  const it = cur(); let h;
  if (it.kind === "climb") {
    document.getElementById("hint2").textContent = "Q4 = top quarter of the vial, Q1 = bottom (as in the lab handout). A yellow total differs from that vial's usual total (a fly is probably missed or extra).";
    const U = it.rois.map((_, r) => usual(it, r));
    h = "<table><tr><th>sec</th>" + it.rois.map((_, r) => `<th colspan="5">${it.vials[r] || "vial " + (r + 1)}</th>`).join("") + "</tr><tr><th></th>" +
      it.rois.map(() => "<th>Q4 top</th><th>Q3</th><th>Q2</th><th>Q1 bot</th><th>tot</th>").join("") + "</tr>";
    it.frames.forEach((_, t) => {
      const p = pts(it, t);
      h += `<tr class="${t === s ? "cur" : ""}" onclick="s=${t};load()"><td>${t}</td>` + it.rois.map((r, i) => {
        const q = quads(r, p), n = sum(q);
        return q.map(x => `<td>${x}</td>`).join("") + `<td class="${n !== U[i] ? "off" : ""}">${n}</td>`;
      }).join("") + "</tr>";
    });
  } else {
    document.getElementById("hint2").textContent = "Only real flies (small brown specks) count - the big black flies are printed on the paper. Flies inside the glass tube don't count. Dashed blue lines = the red lines. Interval 4 = top of the sheet, Interval 2 = bottom; Interval 1 (flies in the water) is not on the paper.";
    const z = zones(it, pts(it, 0));
    h = `<table><tr><th>Interval 4 (top)</th><th>Interval 3</th><th>Interval 2 (bottom of paper)</th><th>Total on paper</th></tr><tr>${z.map(x => `<td>${x}</td>`).join("")}<td>${sum(z)}</td></tr></table>`;
  }
  document.getElementById("tbl").innerHTML = h + (h.endsWith("</table>") ? "" : "</table>");
}
function load() { const it = cur(); if (s >= it.frames.length) s = 0; img.onload = draw; img.src = it.frames[s].img; }
cv.onclick = e => {
  const it = cur(), b = cv.getBoundingClientRect(), k = cv.width / b.width;
  const x = (e.clientX - b.left) * k / sc, y = (e.clientY - b.top) * k / sc, p = pts(it, s);
  let best = -1, bd = (12 / sc) ** 2;
  p.forEach(([px, py], i) => { const d = (px - x) ** 2 + (py - y) ** 2; if (d < bd) { bd = d; best = i; } });
  if (best >= 0) p.splice(best, 1); else p.push([+x.toFixed(1), +y.toFixed(1)]);
  save(it, s, p); draw();
};
function fill() { document.getElementById("item").innerHTML = items().map((d, i) => `<option value="${i}">${d.label} - ${d.name}</option>`).join(""); }
const go = (dv, ds) => {
  const n = items().length, it = cur();
  if (dv) { vi = (vi + dv + n) % n; s = 0; }
  else { s += ds; if (s >= it.frames.length) { s = 0; vi = (vi + 1) % n; } if (s < 0) s = 0; }
  load();
};
document.querySelectorAll(".tab").forEach(b => b.onclick = () => { kind = b.dataset.k; vi = 0; s = 0; fill(); load(); });
document.getElementById("item").onchange = e => { vi = +e.target.value; s = 0; load(); };
document.getElementById("prev").onclick = () => go(-1, 0);
document.getElementById("next").onclick = () => go(1, 0);
document.getElementById("pf").onclick = () => go(0, -1);
document.getElementById("nf").onclick = () => go(0, 1);
document.getElementById("reset").onclick = () => { try { cur().frames.forEach((_, t) => { if (t === s || cur().kind === "paper") localStorage.removeItem(key(cur(), t)); }); } catch (_) {} draw(); };
onkeydown = e => {
  if (e.key === " " || e.key === "ArrowRight") { e.preventDefault(); kind === "climb" ? go(0, 1) : go(1, 0); }
  else if (e.key === "ArrowLeft") kind === "climb" ? go(0, -1) : go(-1, 0);
  else if (e.key === "]") go(1, 0); else if (e.key === "[") go(-1, 0);
};
onresize = draw;
function csvDownload(rows, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([rows.map(r => r.join(",")).join("\n") + "\n"], { type: "text/csv" }));
  a.download = name; a.click();
}
document.getElementById("dlc").onclick = () => {
  const rows = [["group", "video", "vial", "phenotype", "t_s", "Q1_bottom", "Q2", "Q3", "Q4_top", "total"]];
  D.filter(d => d.kind === "climb").forEach(it => it.rois.forEach((r, j) => it.frames.forEach((_, t) => {
    const q = quads(r, pts(it, t)); rows.push([it.group, it.name, j + 1, it.vials[j], t, ...q.slice().reverse(), sum(q)]);
  })));
  csvDownload(rows, "fly_climbing_reviewed.csv");
};
document.getElementById("dlp").onclick = () => {
  const rows = [["photo", "date", "phenotype", "interval2_bottom", "interval3", "interval4_top", "total_on_paper"]];
  D.filter(d => d.kind === "paper").forEach(it => { const z = zones(it, pts(it, 0)); rows.push([it.name, it.date, it.phenotype, ...z.slice().reverse(), sum(z)]); });
  csvDownload(rows, "fly_paper_reviewed.csv");
};
if (location.hash === "#paper") kind = "paper";   // review_all.html#paper opens the fly paper tab
fill(); load();
</script></body></html>"""

if __name__ == "__main__":
    data = climbing() + paper()
    open("review_all.html", "w").write(PAGE.replace("__DATA__", json.dumps(data)))
    print(f"wrote review_all.html: {sum(d['kind'] == 'climb' for d in data)} climbing videos, "
          f"{sum(d['kind'] == 'paper' for d in data)} fly paper photos")
    webbrowser.open("file://" + os.path.abspath("review_all.html"))

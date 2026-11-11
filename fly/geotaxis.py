"""Negative-geotaxis fly counter: auto-detect in Python, check/fix in the browser.

  python geotaxis.py mine/*.MOV hers/*.MOV

1. Each new video: drag a box per vial (bottom of plug to bottom of vial), ENTER after each, ESC when done.
   Flies are auto-detected at 0,1,2,3,4,5 s after the first shake (cached in VIDEO.auto.json).
2. review.html opens (in the folder you run from). Click a missed fly to add it, click a wrong circle to
   remove it. Each vial is split into 4 equal quadrants, Q1 = top. Edits save in the browser.
3. "Download CSV" there = group, video, vial, second, Q1..Q4, total. group = the video's folder name.
Folders = groups: sort videos into folders, then run on the ones you want.
Caches go in ./cache by video name; delete cache/VIDEO.auto.json to re-detect a video.
"""
import base64, glob, json, os, sys, webbrowser
import cv2
import numpy as np

SECONDS = 5        # report 0..SECONDS s after the first shake, one frame per second
MASK_S = 20        # but use up to this many seconds of video to learn what never moves (marker lines)
DARK = 25          # how much darker than local background a fly pixel must be
PEAK = 50          # a blob's darkest pixel must beat this; glass-rim glints peak ~30-40, real flies 55+
MIN_AREA = 12      # px, smaller blobs are noise


def small(f):
    """4K phones: shrink to 1080 wide so a fly is the same few px the thresholds were tuned on."""
    return cv2.resize(f, None, fx=1080 / f.shape[1], fy=1080 / f.shape[1], interpolation=cv2.INTER_AREA) if f is not None and f.shape[1] > 1080 else f


def motion(path):
    """Mean abs frame diff per frame, downscaled. Hand + shake = big spike."""
    cap = cv2.VideoCapture(path)
    prev, out = None, []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(f, (90, 160)), cv2.COLOR_BGR2GRAY).astype(np.int16)
        out.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
    return np.array(out), cap.get(cv2.CAP_PROP_FPS)


def tap_frame(m, fps, thresh=4.0, shake=10.0, settle=0.5, gap=5.0):
    """Frame where the FIRST shake has ended. The shake starts at the first big spike (> `shake`;
    a hand just hovering stays ~3-6) and ends once motion stays under `thresh` for `gap` s (= the scored
    5 s must be still; a shake that is redone right away counts from the redo). Plus `settle` s."""
    big = np.where(m > shake)[0]
    busy = np.where(m > thresh)[0]
    busy = busy[busy >= (big[0] if len(big) else 0)]
    if len(busy) == 0:
        return 0
    end = busy[-1]
    for a, b in zip(busy, busy[1:]):
        if b - a > gap * fps:
            end = a
            break
    return min(int(end + settle * fps), len(m) - 1)


# 2 fps: hover blip at 0, shake 6-7, still, second shake at 13 -> first shake ends at 7, +1 s settle = 9
assert tap_frame(np.array([5, 0, 0, 0, 0, 0, 20, 9, 0, 0, 0, 0, 0, 20, 0.]), 2, settle=1, gap=2) == 9


def darkness(gray):
    """How much darker each pixel is than its local background (flies are smaller than the kernel)."""
    return cv2.medianBlur(gray, 31).astype(np.int16) - gray


def count(d, static, single):
    # static removed FIRST, then peak test: otherwise a faint rim touching a marker line inherits its darkness
    mask = ((d > DARK) & (static == 0)).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    peak = np.zeros(n, np.int16)
    np.maximum.at(peak, lab.ravel(), d.ravel())
    flies = []
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < MIN_AREA or peak[i] < PEAK:
            continue
        k = max(1, round(a / single)) if single else 1   # clumps count as several flies
        # fan clump flies out sideways so each is its own visible, clickable circle in the editor
        flies += [(cent[i][0] + 8 * (j - (k - 1) / 2), cent[i][1]) for j in range(k)]
    return flies


def detect(path, rois):
    """Auto-detect flies at 0..SECONDS s after the shake -> dict with cropped JPEGs + points (crop coords)."""
    m, fps = motion(path)
    t0 = tap_frame(m, fps)
    print(f"{os.path.basename(path)}: shake ends at {t0 / fps:.1f}s, detecting...")
    cap = cv2.VideoCapture(path)
    frames = []   # every 0.25 s; every 4th one is a whole second
    for k in range(4 * MASK_S + 1):
        fi = t0 + int(round(k * fps / 4))
        if fi >= len(m):
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ok, f = cap.read()
        f = small(f)
        frames.append(f if ok else frames[-1])

    # camera/vials drift a few px over a clip; undo it so marker lines stay put for the static mask
    bx0 = min(r[0] for r in rois); bx1 = max(r[0] + r[2] for r in rois)
    by0 = min(r[1] for r in rois); by1 = max(r[1] + r[3] for r in rois)
    gray = lambda f: np.float32(cv2.cvtColor(f[by0:by1, bx0:bx1], cv2.COLOR_BGR2GRAY))
    ref, win = gray(frames[0]), cv2.createHanningWindow((bx1 - bx0, by1 - by0), cv2.CV_32F)
    for k, f in enumerate(frames):
        (dx, dy), _ = cv2.phaseCorrelate(ref, gray(f), win)
        frames[k] = cv2.warpAffine(f, np.float32([[1, 0, -dx], [0, 1, -dy]]), f.shape[1::-1], borderMode=cv2.BORDER_REPLICATE)

    # static dark stuff (marker lines, labels, vial rim) = dark in >=50% of frames over MASK_S s.
    # ponytail: a fly that never moves the whole time gets masked too; add it by clicking in review.html.
    ds = [[darkness(cv2.cvtColor(f[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)) for x, y, w, h in rois] for f in frames]
    static = [cv2.dilate((np.mean([d[v] > DARK for d in ds], 0) >= 0.5).astype(np.uint8), np.ones((5, 5), np.uint8))
              for v in range(len(rois))]
    areas = [s[cv2.CC_STAT_AREA] for d in ds for v in range(len(rois))
             for s in cv2.connectedComponentsWithStats(((d[v] > DARK) & (static[v] == 0)).astype(np.uint8), 8)[2][1:]
             if s[cv2.CC_STAT_AREA] >= MIN_AREA]
    single = float(np.median(areas)) if areas else 0

    H, W = frames[0].shape[:2]
    X0, Y0 = max(0, bx0 - 60), max(0, by0 - 60)
    X1, Y1 = min(W, bx1 + 60), min(H, by1 + 40)
    out = {"rois": [[x - X0, y - Y0, w, h] for x, y, w, h in rois], "frames": []}
    for s in range(SECONDS + 1):
        k = min(4 * s, len(frames) - 1)
        jpg = cv2.imencode(".jpg", frames[k][Y0:Y1, X0:X1], [cv2.IMWRITE_JPEG_QUALITY, 90])[1]
        pts = [[round(x + cx - X0, 1), round(y + cy - Y0, 1)]
               for v, (x, y, w, h) in enumerate(rois) for cx, cy in count(ds[k][v], static[v], single)]
        out["frames"].append({"img": "data:image/jpeg;base64," + base64.b64encode(jpg).decode(), "pts": pts})
    return out


def pick_rois(path):
    m, fps = motion(path)
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, tap_frame(m, fps))
    _, f = cap.read()
    f = small(f)
    s = 0.5
    r = cv2.selectROIs(f"{os.path.basename(path)}: box each vial (plug to bottom), ENTER after each, ESC when done",
                       cv2.resize(f, None, fx=s, fy=s))
    cv2.destroyAllWindows()
    return [[int(v / s) for v in b] for b in r]


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Fly Climbing Review</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f6f6f4;--fg:#1d1d1b;--muted:#6b6b66;--line:#d9d9d4;--card:#fff;--accent:#c62828;--warn:#fff3cd}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ececea;--muted:#9a9a94;--line:#33332f;--card:#1f1f1d;--accent:#ff6b6b;--warn:#4a3d10}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 -apple-system,system-ui,sans-serif}
header{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:1}
header b{font-size:15px;margin-right:8px}
button,select{font:inherit;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--muted)}
#dl{background:var(--fg);color:var(--bg);border-color:var(--fg)}
main{display:flex;flex-wrap:wrap;gap:16px;padding:16px}
#wrap{position:relative}
canvas{display:block;max-width:100%;cursor:crosshair;border-radius:6px}
#side{flex:1;min-width:300px}
table{border-collapse:collapse;width:100%;background:var(--card);font-variant-numeric:tabular-nums}
th,td{border:1px solid var(--line);padding:4px 6px;text-align:center}
th{color:var(--muted);font-weight:500}
tr.cur td{outline:2px solid var(--accent);outline-offset:-2px}
td.off{background:var(--warn)}
.hint{color:var(--muted);margin:8px 0}
#t{font-weight:600;min-width:60px;display:inline-block;text-align:center}
</style></head><body>
<header><b>Fly climbing</b>
<select id="vid"></select>
<button id="pv">&larr; video</button><button id="nv">video &rarr;</button>
<button id="pf">&larr; sec</button><span id="t"></span><button id="nf">sec &rarr;</button>
<button id="reset">Reset frame to auto</button>
<button id="dl">Download CSV</button>
</header>
<main><div id="wrap"><canvas id="c"></canvas></div>
<div id="side">
<p class="hint">Click a missed fly to add it. Click a circle to remove it. Keys: <b>space / &rarr;</b> next second, <b>&larr;</b> back, <b>] [</b> next / previous video. Edits save in this browser automatically.</p>
<p class="hint">Q1 = top quarter of the vial, Q4 = bottom. Yellow total = differs from that vial's usual total (a fly is probably missed or extra).</p>
<div id="tbl"></div></div></main>
<script>
const D = __DATA__;
const S = D[0].frames.length;
let vi = 0, s = 0;
const key = (v, t) => "geo:" + D[v].video + ":" + t;
function pts(v, t) {
  try { const e = localStorage.getItem(key(v, t)); if (e) return JSON.parse(e); } catch (_) {}
  return D[v].frames[t].pts.map(p => p.slice());
}
function save(v, t, p) { try { localStorage.setItem(key(v, t), JSON.stringify(p)); } catch (_) {} }
function quads(roi, p) {           // counts per quadrant for one vial, Q1 = top
  const [x, y, w, h] = roi, q = [0, 0, 0, 0];
  for (const [px, py] of p) if (px >= x && px <= x + w && py >= y && py <= y + h) q[Math.min(3, Math.floor((py - y) / h * 4))]++;
  return q;
}
const sum = a => a.reduce((x, y) => x + y, 0);
function usual(v, r) {             // most common total for vial r of video v (flies never change)
  const c = {}; for (let t = 0; t < S; t++) { const n = sum(quads(D[v].rois[r], pts(v, t))); c[n] = (c[n] || 0) + 1; }
  return +Object.keys(c).sort((a, b) => c[b] - c[a] || b - a)[0];
}
const cv = document.getElementById("c"), cx = cv.getContext("2d"), img = new Image();
let sc = 1;
function draw() {
  const p = pts(vi, s);
  sc = Math.min((innerHeight - 110) / img.height, 2.2);
  cv.width = img.width * sc; cv.height = img.height * sc;
  cx.drawImage(img, 0, 0, cv.width, cv.height);
  cx.lineWidth = 1.5; cx.font = "bold 15px system-ui";
  D[vi].rois.forEach((r, i) => {
    const [x, y, w, h] = r.map(v => v * sc);
    cx.strokeStyle = "#2e7d32"; cx.setLineDash([]); cx.strokeRect(x, y, w, h);
    cx.strokeStyle = "rgba(25,118,210,.8)"; cx.setLineDash([5, 4]);
    for (let k = 1; k < 4; k++) { cx.beginPath(); cx.moveTo(x, y + h * k / 4); cx.lineTo(x + w, y + h * k / 4); cx.stroke(); }
    cx.setLineDash([]);
    const q = quads(r, p);
    cx.fillStyle = "#1565c0";
    q.forEach((n, k) => cx.fillText("Q" + (k + 1) + ": " + n, x + w + 4, y + h * (k + .5) / 4 + 5));
    cx.fillStyle = "#c62828"; cx.fillText("vial " + (i + 1) + " — " + sum(q) + " flies", x, y - 6);
  });
  cx.strokeStyle = "#e53935"; cx.lineWidth = 2;
  for (const [px, py] of p) { cx.beginPath(); cx.arc(px * sc, py * sc, 9, 0, 7); cx.stroke(); }
  document.getElementById("t").textContent = s + " s";
  document.getElementById("vid").value = vi;
  table();
}
function table() {
  const R = D[vi].rois.length, U = D[vi].rois.map((_, r) => usual(vi, r));
  let h = "<table><tr><th>sec</th>" + D[vi].rois.map((_, r) => `<th colspan="5">vial ${r + 1}</th>`).join("") + "</tr><tr><th></th>" +
    D[vi].rois.map(() => "<th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>tot</th>").join("") + "</tr>";
  for (let t = 0; t < S; t++) {
    const p = pts(vi, t);
    h += `<tr class="${t === s ? "cur" : ""}" onclick="s=${t};load()"><td>${t}</td>` + D[vi].rois.map((r, i) => {
      const q = quads(r, p), n = sum(q);
      return q.map(x => `<td>${x}</td>`).join("") + `<td class="${n !== U[i] ? "off" : ""}">${n}</td>`;
    }).join("") + "</tr>";
  }
  document.getElementById("tbl").innerHTML = h + "</table>";
}
function load() { img.onload = draw; img.src = D[vi].frames[s].img; }
cv.onclick = e => {
  const b = cv.getBoundingClientRect(), k = cv.width / b.width;
  const x = (e.clientX - b.left) * k / sc, y = (e.clientY - b.top) * k / sc, p = pts(vi, s);
  let best = -1, bd = (12 / sc) ** 2;
  p.forEach(([px, py], i) => { const d = (px - x) ** 2 + (py - y) ** 2; if (d < bd) { bd = d; best = i; } });
  if (best >= 0) p.splice(best, 1); else p.push([+x.toFixed(1), +y.toFixed(1)]);
  save(vi, s, p); draw();
};
const go = (dv, ds) => {
  if (dv) { vi = (vi + dv + D.length) % D.length; s = 0; }
  else { s += ds; if (s >= S) { s = 0; vi = (vi + 1) % D.length; } if (s < 0) s = 0; }
  load();
};
document.getElementById("vid").innerHTML = D.map((v, i) => `<option value="${i}">${v.group} / ${v.video}</option>`).join("");
document.getElementById("vid").onchange = e => { vi = +e.target.value; s = 0; load(); };
document.getElementById("pv").onclick = () => go(-1, 0);
document.getElementById("nv").onclick = () => go(1, 0);
document.getElementById("pf").onclick = () => go(0, -1);
document.getElementById("nf").onclick = () => go(0, 1);
document.getElementById("reset").onclick = () => { try { localStorage.removeItem(key(vi, s)); } catch (_) {} draw(); };
onkeydown = e => {
  if (e.key === " " || e.key === "ArrowRight") { e.preventDefault(); go(0, 1); }
  else if (e.key === "ArrowLeft") go(0, -1);
  else if (e.key === "]") go(1, 0);
  else if (e.key === "[") go(-1, 0);
};
onresize = draw;
document.getElementById("dl").onclick = () => {
  const rows = [["group", "video", "vial", "t_s", "Q1_top", "Q2", "Q3", "Q4_bottom", "total"]];
  D.forEach((v, i) => v.rois.forEach((r, j) => { for (let t = 0; t < S; t++) { const q = quads(r, pts(i, t)); rows.push([v.group, v.video, j + 1, t, ...q, sum(q)]); } }));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([rows.map(r => r.join(",")).join("\n") + "\n"], { type: "text/csv" }));
  a.download = "fly_climbing.csv"; a.click();
};
load();
</script></body></html>"""


if __name__ == "__main__":
    videos = sorted(p for a in sys.argv[1:] for p in glob.glob(a) if p.lower().endswith((".mov", ".mp4", ".m4v")))
    if not videos:
        sys.exit(__doc__)
    data = []
    for p in videos:
        # caches live in ./cache by video name, so videos can be moved between folders freely
        base = os.path.join("cache", os.path.splitext(os.path.basename(p))[0])
        os.makedirs("cache", exist_ok=True)
        cache = base + ".auto.json"
        if not os.path.exists(cache):
            rf = base + ".rois.json"
            rois = json.load(open(rf)) if os.path.exists(rf) else pick_rois(p)
            if not rois:
                sys.exit("no vials boxed")
            json.dump(rois, open(rf, "w"))
            json.dump(detect(p, rois), open(cache, "w"))
        d = json.load(open(cache))
        d.update(group=os.path.basename(os.path.dirname(os.path.abspath(p))), video=os.path.basename(base))
        data.append(d)
    open("review.html", "w").write(PAGE.replace("__DATA__", json.dumps(data)))
    print(f"wrote review.html ({len(data)} videos)")
    webbrowser.open("file://" + os.path.abspath("review.html"))

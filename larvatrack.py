#!/usr/bin/env python3
"""Live path-length tracker for ONE Drosophila larva. for gene rover/sitter assay.

    python3 larvatrack.py            # opens http://localhost:8000 - pick camera there
    python3 larvatrack.py --demo     # self-check, no camera needed

The browser owns the camera (it lists real device names and holds a Continuity
Camera connection properly, which OpenCV on macOS does not). It posts frames
here at --sample-hz; this file does the tracking and writes the files.
Nothing is recorded - only the final CSVs and an overlay PNG are saved.
"""
import argparse, csv, io, json, math, os, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from scipy.optimize import linear_sum_assignment
import cv2, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# A larva is a stubby oval: a few times longer than wide, never a streak. Shadow
# bands and dish-rim arcs are 20:1 and up, dust and bubbles are round - both out.
LARVA_ELONG = (1.3, 6.0)

class TrackingError(Exception):
    """Something about this clip or these settings makes tracking impossible."""

# Background estimate for flattening uneven light. Must be well WIDER than a larva
# or the larva gets absorbed into its own background and disappears.
FLAT_SIGMA = 51

DUMP = True   # /lock saves what OpenCV saw; the self-check turns this off

# A larva's silhouette in mm^2: 1st instar up to a fat wandering 3rd, generously.
# Once the dish gives us mm/px this beats any pixel guess - it rejects the big
# shadow blobs that are the usual thing a tracker locks onto by mistake.
LARVA_MM2 = (0.3, 12.0)

def area_bounds(mm_per_px):
    """Plausible larva area in px, from the dish scale. None if uncalibrated."""
    if not mm_per_px or mm_per_px == 1.0:
        return None
    return tuple(round(a / mm_per_px ** 2) for a in LARVA_MM2)

# ---- calibration knobs (the physical world needs tuning) ----------------------
# These are the defaults the web page starts with; change them there, live.
D = dict(
    mm_per_px=1.0,      # calibrate in the page: click two points, type the mm
    invert=0,           # 1 if the larva is BRIGHTER than the plate (auto-lock sets it)
    thresh=0,           # 0 = auto (Otsu). Set 1-254 if auto picks up junk.
    min_area=30,        # px, ignore specks, condensation, yeast flecks
    max_area=8000,      # px, ignore plate edge, shadows, your hand
    max_speed=4.0,      # mm/s ceiling. A larva crawls ~1 mm/s; anything faster is
                        # the tracker snapping to a different object, not an animal.
    max_jump=60,        # px fallback when there is no mm/px scale yet
    noise_floor=1.5,    # px floor; see noise_px() - it also enforces a mm floor,
                        # because centroid jitter at 2 Hz otherwise accumulates into
                        # tens of mm of pure noise over a 5 minute run
    edge_pct=90,        # % of the dish radius kept. Larvae wall-follow, so raising
                        # this recovers the outer rim - but keeping more of the rim
                        # also gave a smear-swap in the self-check, so it is opt-in.
    sample_hz=2.0,      # sampling rate; larval path length is scale-dependent,
                        # so keep this IDENTICAL across every animal you compare
)

def background(gray, sigma=None):
    """Blurred background estimate, computed on a downscaled copy.

    A sigma-51 Gaussian needs a ~300-tap kernel: 186 ms on a 160 px window, which
    was essentially the entire cost of tracking. Downscaling first makes it ~2 ms
    for a background estimate that is, by definition, low-frequency anyway."""
    sigma = sigma or FLAT_SIGMA
    f = max(1, int(sigma / 4))
    if f == 1:
        return cv2.GaussianBlur(gray, (0, 0), sigma)
    h, w = gray.shape[:2]
    small = cv2.resize(gray, (max(2, w // f), max(2, h // f)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), max(1.0, sigma / f))
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

def mark_offplane(areas, focus, grow=1.15, soften=0.75, run_len=3):
    """Which samples the animal was off the agar for - on the lid, or up the wall.

    A larva that climbs moves a centimetre or two nearer the lens: it gets bigger
    and, being off the focused plane, softer. Both at once, sustained, is the
    signature. Judged against that animal's OWN baseline; comparing sizes between
    larvae just measures how big each larva is."""
    n = len(areas)
    if n < run_len:
        return [False] * n
    base_a = sorted(areas)[n // 2]
    base_f = sorted(focus)[n // 2]
    def roll(arr, k):
        seg = sorted(arr[max(0, k - 4):k + 5])
        return seg[len(seg) // 2]
    hit = [roll(areas, k) > grow * base_a and roll(focus, k) < soften * base_f
           for k in range(n)]
    out, run = [False] * n, 0
    for k in range(n):                               # only sustained changes count
        run = run + 1 if hit[k] else 0
        if run >= run_len:
            for j in range(k - run + 1, k + 1):
                out[j] = True
    return out

def sharpness(gray, cx, cy, rad):
    """How crisp the edges are around a detection.

    A larva on the underside of the lid sits a centimetre or two above the agar,
    outside the plane the phone focused on, so its edges are soft. Normalising the
    gradient energy by local contrast keeps this a focus measure rather than a
    brightness measure."""
    x0, y0 = max(0, int(cx - rad)), max(0, int(cy - rad))
    p = gray[y0:y0 + 2 * int(rad), x0:x0 + 2 * int(rad)]
    if p.size < 25:
        return 0.0
    lap = cv2.Laplacian(p, cv2.CV_64F)
    return float(np.mean(np.abs(lap)) / (p.std() + 1.0))

def kernels(c):
    """Morphology kernels scaled to the SMALLEST larva we accept.

    Fixed 5px/7px kernels were tuned for a larva ~30 px wide. On a wide shot the
    animal is 4-5 px across and a 5x5 opening deletes it outright - the mask has
    the larva in it, the cleanup step removes it, and nothing is ever found."""
    width = math.sqrt(max(c["min_area"], 1) / 3.0)       # a larva is ~3x longer than wide
    ko = int(max(1, min(7, round(width / 1.5))))
    kc = int(max(3, min(11, round(width))))
    return (np.ones((ko, ko), np.uint8) if ko > 1 else None,
            np.ones((kc + (kc + 1) % 2,) * 2, np.uint8))

def detect(gray, c):
    """Blobs that could be the larva, biggest first.

    Dark blob on a bright yeast plate. Not background subtraction: a sitter that
    sits still gets absorbed into the background and vanishes."""
    gray = cv2.medianBlur(gray, 5)                                     # kill speckle
    # High-pass around mid-grey, NOT a divide: divide pins the background at 255,
    # which clips every pale object away. Larvae here are paler than the dish.
    bg = background(gray)
    flat = np.clip(gray.astype(np.int16) - bg.astype(np.int16) + 128, 0, 255).astype(np.uint8)
    if c["thresh"]:
        _, m = cv2.threshold(flat, c["thresh"], 255, cv2.THRESH_BINARY_INV)
    else:
        _, m = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if c["invert"]:
        m = cv2.bitwise_not(m)
    ko, kc = kernels(c)
    if ko is not None:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ko)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kc)
    out = []
    for cnt in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        a = cv2.contourArea(cnt)
        if c["min_area"] <= a <= c["max_area"]:
            M = cv2.moments(cnt)
            (bw, bh) = cv2.minAreaRect(cnt)[1]
            elong = max(bw, bh) / max(min(bw, bh), 1e-6)   # larva ~3-5:1, dust ~1:1
            hole = np.zeros(flat.shape, np.uint8)
            cv2.drawContours(hole, [cnt], -1, 255, -1)
            contrast = abs(cv2.mean(flat, hole)[0] - 128)  # how far it stands off the dish
            out.append((a, M["m10"] / M["m00"], M["m01"] / M["m00"], elong, contrast,
                        cv2.approxPolyDP(cnt, 1.0, True).reshape(-1, 2)))
    return sorted(out, key=lambda b: -b[0])

def mask_dish(frame, cx, cy, r, shrink=0.97):
    """Blank everything outside the dish to the dish's own average shade, so the
    rim, the ruler and the bench cannot be mistaken for a larva.

    shrink=0.97 keeps almost the whole dish. It used to be 0.90 to hide the bright
    rim highlight, which out-contrasted the larva - but the rim is a long thin arc
    and now fails the LARVA_ELONG gate on shape, so blanking it is no longer worth
    losing 3 mm of dish. Larvae wall-follow, and that is exactly when they cover
    the most ground."""
    m = np.zeros(frame.shape[:2], np.uint8)
    cv2.circle(m, (int(cx), int(cy)), int(r * shrink), 255, -1)
    mean = cv2.mean(frame, m)
    if frame.ndim == 2:                              # grayscale, not just BGR
        return np.where(m > 0, frame, np.uint8(mean[0]))
    out = np.full_like(frame, np.uint8(mean[:3]))
    return np.where(m[:, :, None] > 0, frame, out)

def track_plate(gray, cx, cy, r, scale=4):
    """Where the dish rim is now, given roughly where it was.

    Aligning on the dish is the whole basis for saying a larva moved: the reference
    plane has to be the agar. Phase correlation on a low-texture agar plate drifts
    - it reported twice the shift that re-detecting the rim did - so find the rim
    itself, on a downscaled copy for speed."""
    g = cv2.resize(gray, (gray.shape[1] // scale, gray.shape[0] // scale),
                   interpolation=cv2.INTER_AREA)
    rr = r / scale
    cir = cv2.HoughCircles(cv2.medianBlur(g, 3), cv2.HOUGH_GRADIENT, 1.4,
                           max(8, int(rr)), param1=110, param2=45,
                           minRadius=int(rr * 0.85), maxRadius=int(rr * 1.15))
    if cir is None:
        return None
    best, bd = None, 0.35 * r                       # must be near where it was
    for x, y, rad in cir[0]:
        d = math.hypot(x * scale - cx, y * scale - cy)
        if d < bd:
            best, bd = (float(x * scale), float(y * scale)), d
    return best

def find_plates(gray, want=8):
    """Every petri dish rim in the frame, biggest-confidence first."""
    g = cv2.medianBlur(gray, 5)
    h, w = g.shape
    lo, hi = min(h, w) // 10, min(h, w) // 2
    for method, p1, p2 in ((cv2.HOUGH_GRADIENT_ALT, 300, 0.72), (cv2.HOUGH_GRADIENT, 120, 55)):
        cir = cv2.HoughCircles(g, method, 1.5, min(h, w) // 4, param1=p1, param2=p2,
                               minRadius=lo, maxRadius=hi)
        if cir is None:
            continue
        out = []
        for x, y, r in cir[0]:
            if all(math.hypot(x - a, y - b) > 0.7 * max(r, c) for a, b, c in out):
                out.append((float(x), float(y), float(r)))
            if len(out) >= want:
                break
        if out:
            return out
    return []

def find_plate(gray):
    """The petri dish rim, by Hough circle. Gives the tracking area AND, with the
    diameter you type in, the mm/px scale - so no ruler and no clicking."""
    g = cv2.medianBlur(gray, 5)
    h, w = g.shape
    lo, hi = min(h, w) // 8, min(h, w) // 2
    for method, p1, p2 in ((cv2.HOUGH_GRADIENT_ALT, 300, 0.75), (cv2.HOUGH_GRADIENT, 120, 60)):
        cir = cv2.HoughCircles(g, method, 1.5, min(h, w), param1=p1, param2=p2,
                               minRadius=lo, maxRadius=hi)
        if cir is not None:
            x, y, r = cir[0][0]
            return float(x), float(y), float(r)
    return None

def find_motion(a, b):
    """Where the picture changed between two frames a second or so apart.

    On a foraging plate the yeast smears are pale, elongated and larva-sized -
    brightness and shape cannot tell them from the animal. Only one of them moves.
    """
    d = cv2.absdiff(cv2.GaussianBlur(a, (0, 0), 2), cv2.GaussianBlur(b, (0, 0), 2))
    if int(d.max()) < 8:
        return None                                  # nothing budged; camera is steady
    _, m = cv2.threshold(d, max(10, int(d.max() * 0.5)), 255, cv2.THRESH_BINARY)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.dilate(m, np.ones((9, 9), np.uint8))     # join the before/after lobes
    n, _, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < 12:
        return None
    return float(cent[i][0]), float(cent[i][1])

def candidates(gray, c):
    """Every (invert, threshold, blob) worth considering in this image.

    The threshold is swept as a CONTRAST OFFSET from the high-pass background level
    of 128, not as an absolute grey level: a pale larva needs flat > 128+delta, a
    dark one flat < 128-delta. Sweeping absolute levels across both polarities was
    the bug that broke tracking - e.g. thresh=120 with invert=1 asks for "brighter
    than 120", which selects ~98% of the dish as one blob. Inside a tight dragged
    box that flood is still small enough to pass max_area and look like a great
    detection; in the larger tracking window it is one huge blob that gets binned,
    so the larva was locked and then instantly LOST on every frame."""
    out = []
    for inv in (0, 1):
        for delta in range(6, 84, 4):
            t = 128 + delta if inv else 128 - delta
            for b in detect(gray, dict(c, thresh=t, invert=inv)):
                if LARVA_ELONG[0] <= b[3] <= LARVA_ELONG[1]:
                    out.append((inv, t, b))
    return out

def autotune(gray, c, near=None):
    """Find the polarity + threshold that isolate the larva, and the blob itself.

    near=(x,y) from find_motion: the answer is then the blob CLOSEST to what moved,
    not the brightest one around - on a yeast-smeared plate the smears out-contrast
    the animal, so proximity to the movement is the only trustworthy signal."""
    ranked = rank(gray, c, near)
    return ranked[0] if ranked else None

def rank(gray, c, near=None):
    """Candidates best-first. Same scoring as autotune, but keeps the runners-up so
    a caller can fall back when the best one fails to survive validation."""
    off = (0, 0)
    if near is not None:
        pad = max(30, int(2.5 * math.sqrt(max(c["max_area"], 1))))
        x0, y0 = max(0, int(near[0] - pad)), max(0, int(near[1] - pad))
        x1, y1 = min(gray.shape[1], int(near[0] + pad)), min(gray.shape[0], int(near[1] + pad))
        if x1 - x0 < 30 or y1 - y0 < 30:
            return []
        gray, off, near = gray[y0:y1, x0:x1], (x0, y0), (near[0] - x0, near[1] - y0)

    scored = []
    for inv, t, b in candidates(gray, c):
        # Bin the contrast, then prefer the BIGGER blob. Ranking on raw contrast
        # picks the brightest sliver of the animal's core; binning lets a slightly
        # softer threshold that captures the whole body win, which gives a real
        # outline and a steadier centroid.
        if near is None:
            key = (-round(b[4] / 5), -b[0])
        else:
            key = (round(math.hypot(b[1] - near[0], b[2] - near[1]) / 5),
                   -round(b[4] / 5), -b[0])
        scored.append((key, inv, t,
                       (b[0], b[1] + off[0], b[2] + off[1], b[3], b[4], b[5] + off)))
    scored.sort(key=lambda s: s[0])
    return [(inv, t, b) for _, inv, t, b in scored]

def survives_window(gray, inv, t, b, c):
    """Would this (polarity, threshold) still find the same blob in the bigger window
    that tracking actually uses? A setting tuned on a tight box that cannot answer
    yes here is worthless - it locks and then loses the animal immediately."""
    pad = int(c["max_jump"]) + 25
    x0, y0 = max(0, int(b[1] - pad)), max(0, int(b[2] - pad))
    x1, y1 = min(gray.shape[1], int(b[1] + pad)), min(gray.shape[0], int(b[2] + pad))
    if x1 - x0 < 40 or y1 - y0 < 40:
        return False
    for f in detect(gray[y0:y1, x0:x1], dict(c, thresh=t, invert=inv)):
        if (math.hypot(f[1] + x0 - b[1], f[2] + y0 - b[2]) < 12
                and 0.4 * b[0] <= f[0] <= 2.5 * b[0]):
            return True
    return False

def pick_larva(blobs, last, area, c, taken=()):
    """One larva. First sample: the most larva-shaped blob (elongated, then big).
    After that: stay locked - nearest to where it was, penalised for changing
    size, so a shadow drifting past can't steal the lock. No IDs to swap."""
    blobs = [b for b in blobs
             if all(math.hypot(b[1] - tx, b[2] - ty) > 6 for tx, ty in taken)]
    if not blobs:
        return None
    if last is None:
        shaped = [b for b in blobs if LARVA_ELONG[0] <= b[3] <= LARVA_ELONG[1]]
        return max(shaped or blobs, key=lambda b: b[0])
    near = [b for b in blobs if math.hypot(b[1] - last[0], b[2] - last[1]) <= c["max_jump"]]
    if not near:
        return None                          # lost this sample; keep the old position
    a0 = area or near[0][0]
    # ponytail: 40 px is what one whole area doubling is "worth" in distance. Tune
    # it up if a passing shadow steals the lock, down if the larva outruns it.
    return min(near, key=lambda b: math.hypot(b[1] - last[0], b[2] - last[1])
                                   + 40 * abs(b[0] - a0) / max(a0, 1))

NOISE_MM = 0.15                     # centroid wobble on a larva-sized blob
SMOOTH_S = 0.5                      # trajectory smoothing window, in seconds
BRIDGE_MAX_MM = 25.0                # furthest a lost track may be rejoined across

def smooth_xy(pts, hz):
    """Moving average over a fixed span of TIME, not of samples.

    Path length has to come out the same whether you sample at 2 Hz or 30 Hz. A
    per-step distance threshold cannot do that: at 30 Hz a larva moves less
    between samples than the threshold itself, so nearly every step is discarded
    and the total collapses. Smoothing the trajectory over a fixed half-second and
    then measuring is sample-rate invariant, which is a property you can test."""
    w = max(1, int(round(SMOOTH_S * hz)) | 1)        # odd window
    if w < 3 or len(pts) < w:
        return pts
    h, out = w // 2, []
    for i in range(len(pts)):
        lo_i, hi_i = max(0, i - h), min(len(pts), i + h + 1)
        seg = pts[lo_i:hi_i]
        out.append((pts[i][0], sum(p[1] for p in seg) / len(seg),
                    sum(p[2] for p in seg) / len(seg)))
    return out

def path_length(pts, c, offplane=None):
    """Cumulative mm along a smoothed trajectory, skipping gaps and off-agar runs.

    If the larva was lost for a while, the straight line between where it vanished
    and where it reappeared is NOT a path - we never saw the route it took. Adding
    that chord was inflating totals by roughly tenfold on a real clip. Skipped
    segments are reported separately as gap time, so the undercount is visible
    instead of silently baked into the number."""
    mpp = c["mm_per_px"]
    hz = max(c["sample_hz"], 1e-3)
    sm = smooth_xy(pts, hz)
    span = 1.5 / hz                                  # a step longer than this is a gap
    floor = c["noise_floor"] if (not mpp or mpp == 1.0) else 0.0
    total, cum, gap = 0.0, [0.0], 0.0
    for i, ((t0, x0, y0), (t1, x1, y1)) in enumerate(zip(sm, sm[1:])):
        # A step measured while the animal was off the agar is at a different
        # magnification, so its length in mm is simply wrong. Treat it as a gap.
        if offplane and (offplane[i] or offplane[i + 1]):
            gap += t1 - t0
        elif t1 - t0 > span:
            gap += t1 - t0
        else:
            d = math.hypot(x1 - x0, y1 - y0)
            total += d * mpp if d >= floor else 0.0
        cum.append(total)
    return total, cum, gap

def reach_px(L, c, t):
    """How far the larva could REALLY have gone since we last saw it.

    Search width and accepted displacement are different things. Widening the
    window after a miss is right - the animal kept moving while we lost it - but
    the jump we accept must still obey its top speed, or the tracker teleports
    across the dish and calls it path length. Measured on a real 4.5 min clip:
    unbounded widening produced 165 px steps (15 mm/s) and inflated path length
    about tenfold. The floor covers centroid wobble, which does not shrink just
    because the sample rate went up."""
    one = 1.0 / max(c["sample_hz"], 1e-3)
    dt = t - (L.get("t_last") or (t - one))
    if dt <= 0:                                      # clock reset, or a re-run
        dt = one
    if c["mm_per_px"] and c["mm_per_px"] != 1.0:
        return max(5.0, c["max_speed"] * dt / c["mm_per_px"])
    return c["max_jump"] * max(1.0, dt * c["sample_hz"])

def step_one(L, gray, c, t, taken=()):
    """Advance one tracked larva by one sample.

    Two things keep it locked over a five-minute run. It searches a window around
    where the larva just was, widening that window each time it misses instead of
    giving up and re-hunting the whole dish. And if the threshold fixed at lock
    time stops segmenting the animal - light drifts, the larva rears or curls, it
    crawls onto a shadow band - it re-tunes the threshold in that window and keeps
    the new one. A threshold chosen once at t=0 does not hold for five minutes."""
    last = L["last"]
    if not last:
        hit = pick_larva(detect(gray, c), None, None, c, taken)
        if hit:
            L["last"], L["area"], L["misses"] = hit[1:3], hit[0], 0
            L["pts"].append((t, *hit[1:3]))
        else:
            L["misses"] = L.get("misses", 0) + 1
        return hit

    reach = reach_px(L, c, t)                        # what physics allows
    pad = int(reach) + 25 + 10 * min(L["misses"], 4)  # search wider, accept no further
    # Centre the search where the larva is GOING. A crawling animal keeps its
    # heading, so after a miss it is further along the path, not still at `last`.
    if len(L["pts"]) >= 2 and not L["misses"]:
        (_, ax, ay), (_, bx, by) = L["pts"][-2], L["pts"][-1]
        qx, qy = bx + (bx - ax), by + (by - ay)
    else:
        qx, qy = last
    x0, y0 = max(0, int(qx - pad)), max(0, int(qy - pad))
    x1, y1 = min(gray.shape[1], int(qx + pad)), min(gray.shape[0], int(qy + pad))
    if x1 - x0 < 40 or y1 - y0 < 40:
        x0, y0, x1, y1 = 0, 0, gray.shape[1], gray.shape[0]
    win = gray[y0:y1, x0:x1]
    shift = lambda b: (b[0], b[1] + x0, b[2] + y0, b[3], b[4], b[5] + [x0, y0])
    wc = dict(c, max_jump=reach)   # pick_larva gates on this

    hit = pick_larva([shift(b) for b in detect(win, c)], last, L["area"], wc, taken)

    if hit is None:
        # Re-tune in the window. Accept only a blob that is near enough and still
        # the same size as the animal we locked - otherwise a shadow edge wins.
        for inv, th, b in rank(win, c, near=(last[0] - x0, last[1] - y0))[:6]:
            f = shift(b)
            # Judge size against the blob we locked at t=0. Judging against last
            # frame's size lets 3x-per-step tolerance compound, so the lock walks
            # off onto ever-bigger junk and tracking decays over a long run.
            a0 = L.get("area0") or L["area"] or f[0]
            if (math.hypot(f[1] - last[0], f[2] - last[1]) <= reach
                    and 0.35 * a0 <= f[0] <= 3.0 * a0
                    and all(math.hypot(f[1] - tx, f[2] - ty) > 6 for tx, ty in taken)):
                L["thresh"], L["invert"] = th, inv     # keep what just worked
                hit = f
                break

    if hit:
        L["last"], L["area"], L["misses"], L["t_last"] = hit[1:3], hit[0], 0, t
        L["pts"].append((t, *hit[1:3]))
    else:
        L["misses"] = L.get("misses", 0) + 1
    return hit

def larva_cfg(S, L):
    """Config for one larva: its own polarity/threshold, and its own DISH's scale -
    two dishes in frame can sit at different distances, so mm/px is per dish."""
    d = S["dishes"].get(L.get("dish"))
    return dict(S["cfg"], thresh=L["thresh"], invert=L["invert"],
                mm_per_px=(d or S["cfg"])["mm_per_px"] if d else S["cfg"]["mm_per_px"],
                min_area=(d["min_area"] if d else S["cfg"]["min_area"]),
                max_area=(d["max_area"] if d else S["cfg"]["max_area"]))

def step_all(S, frame, t):
    """One sample for every larva in every dish. Full-frame coordinates throughout."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    S["frame"], out, taken = frame, [], []
    for lid, L in S["larvae"].items():
        c = larva_cfg(S, L)
        hit = step_one(L, gray, c, t, taken)
        if hit:
            taken.append(hit[1:3])
        d = S["dishes"].get(L.get("dish"))
        gap_s = path_length(L["pts"], c)[2]
        since = (t - L["t_last"]) if (hit is None and L.get("t_last")) else 0.0
        out.append({"id": lid, "name": L["name"], "color": L["color"],
                    "gap_s": round(gap_s, 1), "since": round(since, 1),
                    "dish": L.get("dish"), "dish_name": d["name"] if d else "",
                    "found": hit is not None,
                    "x": hit[1] if hit else None, "y": hit[2] if hit else None,
                    "poly": hit[5].tolist() if hit is not None else None,
                    "path": round(path_length(L["pts"], c)[0], 2),
                    "n": len(L["pts"])})
    return out

def draw(frame, pts, c, elapsed):
    unit = "mm" if c["mm_per_px"] != 1.0 else "px"
    if pts:
        xy = np.array([[x, y] for _, x, y in pts], np.int32)
        cv2.polylines(frame, [xy], False, (0, 0, 255), 2)
        cv2.circle(frame, tuple(xy[-1]), 8, (0, 255, 0), 2)
    cv2.putText(frame, f"{elapsed:.0f}s   path {path_length(pts, c)[0]:.1f} {unit}",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 0), 2)
    return frame

def save(stem, pts, frame, c):
    total, cum, _gap = path_length(pts, c)
    dur = pts[-1][0] - pts[0][0]
    with open(stem + "_track.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "x_px", "y_px", "cum_path_mm"])
        for (t, x, y), s in zip(pts, cum):
            w.writerow([f"{t:.2f}", f"{x:.1f}", f"{y:.1f}", f"{s:.2f}"])
    with open(stem + "_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["duration_s", "samples", "mm_per_px", "path_length_mm", "mean_speed_mm_s"])
        w.writerow([f"{dur:.1f}", len(pts), c["mm_per_px"], f"{total:.2f}",
                    f"{total / dur:.3f}" if dur else ""])
    if frame is not None:
        cv2.imwrite(stem + "_overlay.png", draw(frame.copy(), pts, c, dur))
    unit = "mm" if c["mm_per_px"] != 1.0 else "px"
    return dict(stem=os.path.basename(stem), path=round(total, 2), unit=unit,
                duration=round(dur, 1), samples=len(pts))

# ---- localhost app -----------------------------------------------------------
# ponytail: one global tracking state. It's a single-user tool on 127.0.0.1;
# add a session dict if you ever want two plates in two tabs.
S = {"dishes": {}, "larvae": {}, "next_id": 1, "next_dish": 1,
     "frame": None, "cfg": dict(D)}

PALETTE = ["#ff4d4d", "#4dd2ff", "#7dff4d", "#ffd24d", "#e04dff", "#4d6bff",
           "#ff934d", "#4dffc3"]

def bgr(hexcolor):
    h = hexcolor.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (4, 2, 0))

def save(stem, S):
    unit = "mm" if any(d["mm_per_px"] != 1.0 for d in S["dishes"].values()) \
                   or S["cfg"]["mm_per_px"] != 1.0 else "px"
    rows = []
    dn = lambda L: (S["dishes"].get(L.get("dish")) or {}).get("name", "")
    with open(stem + "_tracks.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["dish", "larva", "name", "t_s", "x_px", "y_px", f"cum_path_{unit}"])
        for lid, L in S["larvae"].items():
            c = larva_cfg(S, L)
            for (t, x, y), cum in zip(L["pts"], path_length(L["pts"], c)[1]):
                w.writerow([dn(L), lid, L["name"], f"{t:.2f}",
                            f"{x:.1f}", f"{y:.1f}", f"{cum:.2f}"])
    with open(stem + "_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["dish", "larva", "name", "duration_s", "gap_s", "samples",
                    "mm_per_px", f"path_length_{unit}", f"mean_speed_{unit}_per_s",
                    f"spread_{unit}", "off_agar_s", f"est_5min_{unit}"])
        for lid, L in S["larvae"].items():
            if len(L["pts"]) < 2:
                continue
            c = larva_cfg(S, L)
            dur = L["pts"][-1][0] - L["pts"][0][0]
            total, _c, gap = path_length(L["pts"], c, L.get("offplane"))
            seen = max(dur - gap, 1e-9)
            # How far it ever got from where it started. A real trail spreads out;
            # a jitter cluster on a droplet or a speck never leaves a few mm. This
            # is reported, not filtered - a genuine sitter also stays put, and
            # deciding which is which is the experiment, not the tracker's call.
            # Spread must be measured over the SAME samples path length used, or a
            # single excluded jump makes spread exceed path, which is impossible.
            offp = L.get("offplane") or [False] * len(L["pts"])
            usable = [p for p, o in zip(L["pts"], offp) if not o]
            p0 = usable[0] if usable else L["pts"][0]
            spread = (max(math.hypot(p[1] - p0[1], p[2] - p0[2]) for p in usable)
                      if usable else 0.0) * c["mm_per_px"]
            # Mean speed is stable across sample rate (1.35-1.40 mm/s for the same
            # animal at 2-30 Hz); the TOTAL depends on how long we managed to follow
            # it. So project the standard 5 minute assay figure from the speed, and
            # label it an estimate - it assumes the animal crawled the same during
            # the stretches we lost.
            est5 = total / seen * 300.0
            w.writerow([dn(L), lid, L["name"], f"{dur:.1f}", f"{gap:.1f}", len(L["pts"]),
                        c["mm_per_px"], f"{total:.2f}", f"{total / seen:.3f}",
                        f"{spread:.2f}", f"{L.get('off_s', 0.0):.1f}", f"{est5:.1f}"])
            rows.append({"name": L["name"], "dish": dn(L), "path": round(total, 2),
                         "est5": round(est5, 1),
                         "duration": round(dur, 1), "gap_s": round(gap, 1),
                         "spread": round(spread, 1), "samples": len(L["pts"]),
                         "off_s": round(L.get("off_s", 0.0), 1)})
    frame = S.get("frame")
    if frame is not None:
        im = frame.copy()
        for d in S["dishes"].values():
            cv2.circle(im, (int(d["cx"]), int(d["cy"])), int(d["r"]), (90, 200, 90), 2)
            cv2.putText(im, d["name"], (int(d["cx"] - d["r"]), int(d["cy"] - d["r"]) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (90, 200, 90), 2)
        for L in S["larvae"].values():
            if len(L["pts"]) > 1:
                xy = np.array([[x, y] for _, x, y in L["pts"]], np.int32)
                cv2.polylines(im, [xy], False, bgr(L["color"]), 2)
                cv2.putText(im, L["name"], tuple(xy[-1] + 8), cv2.FONT_HERSHEY_SIMPLEX,
                            .5, bgr(L["color"]), 2)
        cv2.imwrite(stem + "_overlay.png", im)
    return {"stem": os.path.basename(stem), "unit": unit, "larvae": rows}

def dish_crop(frame, q):
    """The page sends the dish's bounding box; blank the corners outside the rim."""
    r = float(q.get("dish_r") or 0)
    if r <= 0:
        return frame
    h, w = frame.shape[:2]
    return mask_dish(frame, w / 2, h / 2, r,
                     shrink=max(50, min(100, float(q.get("edge_pct") or 90))) / 100.0)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                  # the page is the UI, not the terminal

    def _send(self, code, body, ctype="application/json"):
        body = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path != "/":
            return self._send(404, b"not found", "text/plain")
        with open(os.path.join(HERE, "index.html"), "rb") as f:
            self._send(200, f.read(), "text/html; charset=utf-8")

    def do_POST(self):
        route = urlparse(self.path).path
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        for k, v in q.items():                        # sliders in the page drive the knobs
            if k in D:
                S["cfg"][k] = type(D[k])(float(v))
        frame = None if route == "/video" else (
            cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR) if body else None)
        if frame is not None and route in ("/frame", "/plate", "/add"):
            frame = dish_crop(frame, q)

        if route == "/reset":
            which = q.get("id")
            # Clear the path but KEEP the lock: dropping `last` would send the next
            # frame hunting the whole dish again, and a yeast smear could win it.
            for lid, L in S["larvae"].items():
                if not which or lid == which:
                    L.update(pts=[], misses=0, t_last=None)
            return self._send(200, json.dumps({"ok": True}))

        if route == "/remove":
            S["larvae"].pop(q.get("id"), None)
            return self._send(200, json.dumps({"ok": True}))

        if route == "/rename":
            L = S["larvae"].get(q.get("id"))
            if L:
                L["name"] = q.get("name", L["name"])[:40]
                L["color"] = q.get("color", L["color"])[:9]
            return self._send(200, json.dumps({"ok": bool(L)}))

        if route == "/plate":
            cir = find_plate(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)) if frame is not None else None
            if not cir:
                return self._send(200, json.dumps({"found": False}))
            x, y, r = cir
            mm = float(q.get("dish_mm") or 0)
            out = {"found": True, "cx": x, "cy": y, "r": r}
            if mm > 0:
                out["mm_per_px"] = mpp = round(mm / (2 * r), 6)
                out["min_area"], out["max_area"] = area_bounds(mpp)
            return self._send(200, json.dumps(out))

        if route in ("/add", "/relock"):
            if frame is None:
                return self._send(400, json.dumps({"error": "bad frame"}))
            if DUMP:
                cv2.imwrite(os.path.join(HERE, "lock_debug.png"), frame)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            bx, by = int(float(q.get("bx", 0))), int(float(q.get("by", 0)))
            bw, bh = int(float(q.get("bw", 0))), int(float(q.get("bh", 0)))
            x0, y0 = max(0, bx), max(0, by)
            x1, y1 = min(gray.shape[1], bx + bw), min(gray.shape[0], by + bh)
            if x1 - x0 < 8 or y1 - y0 < 8:
                return self._send(200, json.dumps({"found": False, "why": "box too small"}))
            # You drew the box, so the box IS the answer to "which one": take the
            # best larva-shaped blob inside it. No motion wait, no yeast ambiguity.
            # Rank candidates inside the box, then keep the first that still works in
            # the bigger window tracking uses. Without this check a box-only winner can
            # lock and then be LOST on the very next frame.
            got = None
            for inv0, t0, b0 in rank(gray[y0:y1, x0:x1], S["cfg"])[:40]:
                cand = (inv0, t0, (b0[0], b0[1] + x0, b0[2] + y0, b0[3], b0[4], b0[5] + [x0, y0]))
                if survives_window(gray, cand[0], cand[1], cand[2], S["cfg"]):
                    got = cand
                    break
            if not got:
                return self._send(200, json.dumps({"found": False,
                    "why": "found nothing that keeps tracking outside your box - draw it tighter round the larva"}))
            inv, th, b = got
            if route == "/relock":
                # Re-point a larva that got lost, WITHOUT discarding what it has
                # already walked. Deleting and re-adding would restart its path at
                # zero and silently lose the measurement so far.
                lid = q.get("id")
                L = S["larvae"].get(lid)
                if not L:
                    return self._send(200, json.dumps({"found": False,
                                                       "why": "no such larva"}))
                L.update(thresh=th, invert=inv, last=(b[1], b[2]), area=b[0],
                         misses=0, t_last=None)
                return self._send(200, json.dumps({"found": True, "id": lid,
                    "name": L["name"], "color": L["color"], "x": b[1], "y": b[2],
                    "area": round(b[0]), "elong": round(b[3], 1), "invert": inv,
                    "thresh": th, "poly": b[5].tolist(), "relocked": True}))
            lid = str(S["next_id"])
            S["next_id"] += 1
            S["larvae"][lid] = {
                "name": q.get("name") or f"larva {lid}",
                "color": q.get("color") or PALETTE[(int(lid) - 1) % len(PALETTE)],
                "thresh": th, "invert": inv, "pts": [], "misses": 0,
                "last": (b[1], b[2]), "area": b[0]}
            return self._send(200, json.dumps({"found": True, "id": lid,
                "name": S["larvae"][lid]["name"], "color": S["larvae"][lid]["color"],
                "x": b[1], "y": b[2], "area": round(b[0]),
                "elong": round(b[3], 1), "invert": inv, "thresh": th,
                "poly": b[5].tolist()}))

        if route == "/frame":
            if frame is None:
                return self._send(400, json.dumps({"error": "bad frame"}))
            res = step_all(S, frame, float(q.get("t", 0)))
            return self._send(200, json.dumps({
                "unit": "mm" if S["cfg"]["mm_per_px"] != 1.0 else "px", "larvae": res}))

        if route == "/video":
            # Raw camera video, no overlay drawn on it - a clean backup you can
            # re-analyse later if the live tracking turns out to have drifted.
            ext = "mp4" if "mp4" in (q.get("mime") or "") else "webm"
            name = f"{q.get('out') or 'run'}_{time.strftime('%Y%m%d_%H%M%S')}.{ext}"
            with open(os.path.join(HERE, name), "wb") as f:
                f.write(body)
            return self._send(200, json.dumps({"file": name, "bytes": len(body)}))

        if route == "/save":
            if not any(len(L["pts"]) > 1 for L in S["larvae"].values()):
                return self._send(400, json.dumps({"error": "nothing tracked yet"}))
            stem = os.path.join(HERE, f"{q.get('out') or 'run'}_{time.strftime('%Y%m%d_%H%M%S')}")
            return self._send(200, json.dumps(save(stem, S)))

        self._send(404, json.dumps({"error": "no such route"}))

def serve(port, open_browser=True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print(f"larvatrack on {url}   (ctrl-C to stop)")
    print("the browser will ask for camera permission - allow it, then pick your iPhone")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")

# ---- offline path (tuning + self-check) --------------------------------------
def analyse_video(video, dish_mm, hz=2.0, max_larvae=12, stabilise=False,
                  expect=None, bridge_s=15.0, edge_pct=99.0, log=print):
    """Track every larva in a recorded clip, hands off.

    Decodes only the sampled frames (grab() skips the rest), cancels camera drift
    against the dish, finds the larvae by what moved across the whole clip, and
    tracks them all at once. This is what the raw video backup is for."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise TrackingError(f"cannot open {video!r}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, round(fps / hz))
    ok, f0 = cap.read()
    if not ok:
        raise TrackingError("empty video")
    cir = find_plate(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    if not cir:
        raise TrackingError("no petri dish rim found in the first frame - is the whole "
                            "dish in shot?")
    cx, cy, r = cir
    x0, y0, side = int(cx - r), int(cy - r), int(2 * r)
    sub = lambda f: f[max(0, y0):y0 + side, max(0, x0):x0 + side]
    g0f = cv2.cvtColor(sub(f0), cv2.COLOR_BGR2GRAY)
    mpp = dish_mm / (2 * r)
    lo, hi = area_bounds(mpp)
    # Keep nearly the whole dish. The live tracker blanks the outer 10% because it
    # segments a single frame and the bright rim out-contrasts a larva; here every
    # frame is differenced against a rolling median, so the static rim is already
    # gone and blanking that band only loses wall-following animals. Measured on a
    # synthetic larva pressed to the wall for 60% of a clip: -0.2% error at 97% of
    # the radius against an outright refusal to track at 90%.
    c = dict(D, mm_per_px=mpp, min_area=lo, max_area=hi, edge_pct=edge_pct,
             sample_hz=hz, max_jump=int(3.0 / mpp))     # 3 mm between samples
    log(f"dish r={r:.0f}px -> {mpp:.5f} mm/px | larva {lo}-{hi}px | "
        f"sampling {hz} Hz ({total / fps:.0f}s of video)")

    # Measure the rim first, smooth the series, THEN warp. Warping frame by frame
    # off a raw estimate was the worst bug in this pipeline: the rim only wanders
    # ~10 px over the whole clip, but a per-frame Hough estimate jitters +-35 px,
    # so "stabilising" injected far more motion than it removed and every track
    # came out following the camera.
    raw, centres = [], []
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    i = -1
    while True:
        if not cap.grab():
            break
        i += 1
        if i % step:
            continue
        ok, f = cap.retrieve()
        if not ok:
            break
        g = cv2.cvtColor(sub(f), cv2.COLOR_BGR2GRAY)
        if g.shape != g0f.shape:
            continue
        raw.append(g)
        centres.append(track_plate(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cx, cy, r, scale=2))
    cap.release()
    if len(raw) < 3:
        raise TrackingError(f"only {len(raw)} usable frames at {hz} Hz - clip too short, "
                            f"or lower --sample-hz")

    known = [k for k, p in enumerate(centres) if p]
    if known:
        for k, p in enumerate(centres):              # carry the rim through dropouts
            if not p:
                centres[k] = centres[min(known, key=lambda j: abs(j - k))]
    else:
        centres = [(cx, cy)] * len(raw)
    win = 9                                          # running median kills the jitter
    sm = []
    for k in range(len(centres)):
        lo_k, hi_k = max(0, k - win // 2), min(len(centres), k + win // 2 + 1)
        xs = sorted(p[0] for p in centres[lo_k:hi_k])
        ys = sorted(p[1] for p in centres[lo_k:hi_k])
        sm.append((xs[len(xs) // 2], ys[len(ys) // 2]))
    drift = [(p[0] - sm[0][0], p[1] - sm[0][1]) for p in sm]
    dmax = max(math.hypot(*d) for d in drift)
    resid = max(math.hypot(c[0] - t[0], c[1] - t[1]) for c, t in zip(centres, sm))
    log(f"{len(raw)} samples | dish wanders {dmax:.0f} px ({dmax * mpp:.1f} mm); "
        f"per-frame estimate noise {resid:.0f} px, smoothed out")

    if not stabilise:
        # Measured on a tripod-style rig: the rim wanders a few px while a per-frame
        # Hough estimate jitters an order of magnitude more. Correcting with an
        # estimate noisier than the signal adds motion to every track. Off unless
        # asked for, and worth asking for only if the camera was actually knocked.
        log("  not stabilising (estimator noise exceeds the drift; use --stabilise "
            "if the camera was actually bumped)")
        drift = [(0.0, 0.0)] * len(raw)

    frames = []
    for g, d in zip(raw, drift):
        if math.hypot(*d) > 1.0:                     # sub-pixel drift is not worth warping
            g = cv2.warpAffine(g, np.float32([[1, 0, -d[0]], [0, 1, -d[1]]]),
                               (g.shape[1], g.shape[0]), borderMode=cv2.BORDER_REPLICATE)
        frames.append(mask_dish(g, r, r, r, shrink=c["edge_pct"] / 100.0))

    # Everything that never moves - the pen writing, the rim, the bench, slow
    # condensation - is the per-pixel median over the clip. Subtract it and only
    # the animals are left. Lock-and-follow could not tell a marker stroke from a
    # larva; this does not have to.
    # A ROLLING median, not one for the whole clip. Condensation creeps across the
    # lid over four minutes, so a single global background leaves a slow-changing
    # residual everywhere and the detector reports dozens of "larvae". Each frame
    # is compared against the plate as it looked around that time.
    span = max(3, int(60 * hz))                      # +-30 s of context
    keys = list(range(0, len(frames), max(1, span // 2)))
    bgs = {}
    for k0 in keys:
        lo_k, hi_k = max(0, k0 - span), min(len(frames), k0 + span + 1)
        sel = frames[lo_k:hi_k:max(1, (hi_k - lo_k) // 15)]
        bgs[k0] = np.median(np.stack(sel), axis=0).astype(np.uint8)
    bg_for = lambda k: bgs[min(keys, key=lambda a: abs(a - k))]
    bg = bg_for(len(frames) // 2)
    ko, kc = kernels(c)
    lo, hi = c["min_area"], c["max_area"]

    # Threshold on how far above the NOISE a pixel sits, not on a percentile: a
    # percentile always returns that fraction of pixels, so it invents detections
    # on a frame where nothing is there.
    probe = cv2.GaussianBlur(cv2.absdiff(frames[len(frames) // 2], bg), (0, 0), 1.5)
    mad = float(np.median(np.abs(probe.astype(np.float32) - np.median(probe))))
    thr = max(16, int(np.median(probe) + 8 * 1.4826 * mad))
    log(f"background-difference threshold {thr} (noise MAD {mad:.1f})")

    dets = []
    for fi, g in enumerate(frames):
        d = cv2.GaussianBlur(cv2.absdiff(g, bg_for(fi)), (0, 0), 1.5)
        m = (d >= thr).astype(np.uint8)
        if ko is not None:
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ko)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kc)
        pts = []
        for cnt in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            a = cv2.contourArea(cnt)
            if not lo <= a <= hi:
                continue
            bw, bh = cv2.minAreaRect(cnt)[1]
            e = max(bw, bh) / max(min(bw, bh), 1e-6)
            if not (1.1 <= e <= LARVA_ELONG[1]):     # a curled larva is nearly round
                continue
            M = cv2.moments(cnt)
            if M["m00"]:
                px, py = M["m10"] / M["m00"], M["m01"] / M["m00"]
                pts.append((px, py, a, sharpness(g, px, py, max(6, math.sqrt(a)))))
        dets.append(pts)
    log(f"{sum(len(p) for p in dets) / max(len(dets), 1):.1f} detections per frame")

    # Link detections into tracks. Four ideas borrowed from the established
    # trackers, all aimed at the same weakness - fragmentation:
    #   Hungarian assignment (FIMTrack, TrackMate LAP) instead of greedy, so two
    #     tracks cannot both grab the nearest blob and one lose out arbitrarily;
    #   an area-ratio gate (Tierpsy's area_ratio_lim, wrMTrck's maxAreaChange), so
    #     a track cannot jump to a blob of a completely different size;
    #   constant-velocity prediction (ToxTrac uses a Kalman filter for this), so a
    #     crawling larva is looked for where it is going, not where it was;
    #   gap closing (TrackMate's second LAP stage, Tierpsy's gap bridging) to
    #     stitch fragments of the same animal back together afterwards.
    AREA_RATIO = 2.5
    hop = max(5.0, c["max_speed"] / hz / mpp)
    max_gap = max(3, int(round(3.0 * hz)))

    def predict(tr):
        """Where this track is heading, from its last observed step."""
        if len(tr["pts"]) >= 2 and tr["k"][-1] - tr["k"][-2] == 1:
            (_, x1, y1), (_, x0, y0) = tr["pts"][-1], tr["pts"][-2]
            return x1 + (x1 - x0), y1 + (y1 - y0)
        return tr["last"]

    ref_area = lambda tr: sorted(tr["areas"][-9:])[len(tr["areas"][-9:]) // 2]

    tracks = []
    for k, pts in enumerate(dets):
        t = k / hz
        live = [tr for tr in tracks if tr["gap"] <= max_gap]
        taken_j = set()
        if pts and live:
            BIG = 1e6
            C = np.full((len(live), len(pts)), BIG)
            for i, tr in enumerate(live):
                span = min(hop * (1 + tr["gap"]), 4 * hop)
                qx, qy = predict(tr)
                a0 = ref_area(tr) or 1.0
                for j, (x, y, a, _f) in enumerate(pts):
                    d = math.hypot(x - qx, y - qy)
                    if d > span:
                        continue
                    ratio = (a / a0) if a0 else 1.0
                    if not (1.0 / AREA_RATIO <= ratio <= AREA_RATIO):
                        continue
                    C[i, j] = d + 0.5 * span * abs(math.log(ratio))
            ri, ci = linear_sum_assignment(C)
            for i, j in zip(ri, ci):
                if C[i, j] >= BIG:
                    continue
                tr = live[i]
                taken_j.add(j)
                tr["last"] = pts[j][:2]
                tr["gap"] = 0
                tr["pts"].append((t, pts[j][0], pts[j][1]))
                tr["areas"].append(pts[j][2])
                tr["focus"].append(pts[j][3])
                tr["k"].append(k)
                tr["matched"] = True
        for tr in live:
            if tr.pop("matched", False):
                continue
            tr["gap"] += 1
        for j in range(len(pts)):
            if j in taken_j:
                continue
            tracks.append({"pts": [(t, pts[j][0], pts[j][1])], "last": pts[j][:2],
                           "gap": 0, "areas": [pts[j][2]], "focus": [pts[j][3]],
                           "k": [k]})

    # Gap closing: a larva that was missed for a couple of seconds comes back as a
    # brand new track. Join B onto A when B starts soon after A ended, close enough
    # that the animal could have crawled there, and at a consistent size.
    # Gap closing, ON by default - decided against ground truth, not by argument.
    # On a synthetic clip where the larva walks a circle of known circumference
    # (131.51 mm), measurement error at 2 Hz is -43% without it and -5.7% with it,
    # because a fragmented track keeps only one fragment. An earlier version of
    # this file had it off, reasoning that it hurt agreement between sample rates.
    # That was the wrong criterion: the disagreement was a symptom of the
    # fragmentation, and accuracy against a known answer outranks self-consistency.
    #
    # Solve the joins GLOBALLY, as TrackMate's second LAP stage does, not greedily.
    # Greedy stitching is order-dependent: one plausible-but-wrong merge blocks a
    # better one, and coverage went DOWN when the window was widened. One
    # assignment over all end-to-start pairs has no such ordering.
    bridge_k = int(round(bridge_s * hz))
    while bridge_k > 0:
        alive = [tr for tr in tracks if not tr.get("dead")]
        if len(alive) < 2:
            break
        BIG = 1e9
        C = np.full((len(alive), len(alive)), BIG)
        for i, a in enumerate(alive):
            aa = ref_area(a) or 1.0
            for j, b in enumerate(alive):
                if i == j:
                    continue
                dk = b["k"][0] - a["k"][-1]
                if not 0 < dk <= bridge_k:
                    continue
                d = math.hypot(b["pts"][0][1] - a["pts"][-1][1],
                               b["pts"][0][2] - a["pts"][-1][2])
                # Speed alone is too weak a gate over a long bridge: 30 s at
                # 4 mm/s permits a jump right across the dish, which would happily
                # weld two different animals together. Cap the join distance too.
                if d > min(c["max_speed"] * (dk / hz), BRIDGE_MAX_MM) / mpp:
                    continue
                ab = sorted(b["areas"])[len(b["areas"]) // 2]
                ratio = ab / aa if aa else 1.0
                if not (1.0 / AREA_RATIO <= ratio <= AREA_RATIO):
                    continue
                # Price the join in DISTANCE, not in frames: hop shrinks and dk
                # grows with the sample rate, so a frame-based penalty made long
                # bridges look progressively cheaper the faster you sampled, and
                # the same clip stopped giving the same answer.
                C[i, j] = d + 0.5 * c["max_speed"] * (dk / hz) / mpp
        ri, ci = linear_sum_assignment(C)
        joins = [(i, j) for i, j in zip(ri, ci) if C[i, j] < BIG]
        if not joins:
            break
        for i, j in joins:
            a, b = alive[i], alive[j]
            if a.get("dead") or b.get("dead"):
                continue
            for key in ("pts", "areas", "focus", "k"):
                a[key] = a[key] + b[key]
            a["last"] = b["last"]
            b["dead"] = True

    before = len(tracks)
    tracks = [tr for tr in tracks if not tr.get("dead")]
    log(f"linking: {before} raw tracks -> {len(tracks)} after gap closing")

    seen_frac = lambda tr: len(tr["pts"]) / max(len(frames), 1)
    def spread_px(tr):
        p0 = tr["pts"][0]
        return max(math.hypot(p[1] - p0[1], p[2] - p0[2]) for p in tr["pts"])
    cand = [tr for tr in tracks if seen_frac(tr) >= 0.20]
    log(f"{len(tracks)} candidate tracks, {len(cand)} seen in >=20% of frames")
    if expect:
        # You said how many animals are in the dish. Rank by how far each track
        # actually travelled: a larva crosses the plate, an artefact sits on a
        # shadow edge and jitters. Ties on travel go to the longer-lived track.
        cand.sort(key=lambda tr: (-spread_px(tr), -len(tr["pts"])))
        dropped = cand[expect:]
        good = cand[:expect]
        if dropped:
            log(f"keeping the {expect} furthest-travelled; dropped {len(dropped)} "
                f"(largest dropped travel {spread_px(dropped[0]) * mpp:.1f} mm vs "
                f"smallest kept {spread_px(good[-1]) * mpp:.1f} mm)")
    else:
        good = sorted(cand, key=lambda tr: -len(tr["pts"]))[:max_larvae]
    # PARALLAX. Frames were aligned on the dish rim, i.e. on the AGAR plane. An
    # object on the underside of the lid sits a centimetre or two nearer the lens,
    # so the same camera nudge moves it by a different amount - after we cancel the
    # agar-plane shift, a lid object keeps a residual that tracks the camera, while
    # a crawling larva's motion has nothing to do with it.
    for tr in good:
        vs, us = [], []
        for (ka, pa), (kb, pb) in zip(zip(tr["k"], tr["pts"]), zip(tr["k"][1:], tr["pts"][1:])):
            if kb - ka != 1:
                continue
            vs.append((pb[1] - pa[1], pb[2] - pa[2]))
            us.append((drift[kb][0] - drift[ka][0], drift[kb][1] - drift[ka][1]))
        num = sum(v[0] * u[0] + v[1] * u[1] for v, u in zip(vs, us))
        du = sum(u[0] * u[0] + u[1] * u[1] for u in us)
        dv = sum(v[0] * v[0] + v[1] * v[1] for v in vs)
        tr["parallax"] = num / math.sqrt(du * dv) if du > 0 and dv > 0 else 0.0
        tr["slope"] = num / du if du > 0 else 0.0
    # OFF THE AGAR (on the lid, or up the wall). A larva that climbs the wall onto
    # the underside of the lid moves a centimetre or two nearer the lens: it gets
    # bigger and, being off the focused plane, softer. Both at once, sustained, is
    # the signature. Judged WITHIN a track against that animal's own baseline -
    # comparing sizes between larvae just measures how big each larva is.
    for tr in good:
        tr["offplane"] = mark_offplane(tr["areas"], tr["focus"])
        tr["off_s"] = sum(tr["offplane"]) / hz

    log("parallax (motion that follows the camera; ~0 = on the agar):")
    for tr in good:
        fs = sorted(tr["focus"])
        log(f"   n={len(tr['pts']):4d}  parallax r={tr['parallax']:+.2f} "
            f"slope={tr['slope']:+.2f}  focus={fs[len(fs) // 2]:.3f}")
    allf = sorted(f for tr in good for f in tr["focus"])
    if allf:
        q = lambda p: allf[min(len(allf) - 1, int(p * len(allf)))]
        log(f"focus: p05={q(.05):.3f} p25={q(.25):.3f} median={q(.5):.3f} "
            f"p75={q(.75):.3f} p95={q(.95):.3f}")
        for tr in good:
            fs = sorted(tr["focus"])
            log(f"   track n={len(fs):4d} focus median={fs[len(fs)//2]:.3f} "
                f"min={fs[0]:.3f} max={fs[-1]:.3f}")
    if not good:
        # Say WHY. The commonest cause by far is a wrong --dish-mm: the plausible
        # larva size is derived from it, so a dish declared twice its real width
        # sets an area window that excludes every real animal.
        sizes = sorted(a for pl in dets for (_x, _y, a, _f) in pl)
        seen_hint = (f"blobs seen ranged {sizes[0]:.0f}-{sizes[-1]:.0f} px"
                     if sizes else "no blobs at all passed the size filter")
        raise TrackingError(
            f"no track lasted 20% of the clip. Larva size window was {lo}-{hi} px "
            f"(from --dish-mm {dish_mm:g}); {seen_hint}. If that window looks wrong "
            f"for your animals, --dish-mm is probably wrong.")

    larvae = {}
    for i, tr in enumerate(good, 1):
        larvae[str(i)] = {"name": f"larva {i}", "color": PALETTE[(i - 1) % len(PALETTE)],
                          "thresh": 0, "invert": 0, "pts": tr["pts"], "misses": 0,
                          "last": tr["last"], "area": tr["areas"][-1],
                          "area0": tr["areas"][0], "offplane": tr["offplane"],
                          "off_s": tr["off_s"]}
    off = [l for l in larvae.values() if l["off_s"] > 0]
    log(f"off the agar (bigger AND softer, sustained): "
        + (", ".join(f"{l['name']} {l['off_s']:.0f}s" for l in off) if off
           else "none detected in this clip"))
    log(f"tracked {len(larvae)} larvae")

    return ({"dishes": {}, "larvae": larvae, "cfg": c,
             "frame": cv2.cvtColor(frames[-1], cv2.COLOR_GRAY2BGR)}, cir)

def write_overlay_video(video, St, cir, out, hz, size=760, log=print):
    """Replay the clip with each trail drawn as it is laid down.

    Shows what the tracker believed at every moment: the path so far, where it
    thinks the animal is right now, and a hollow marker for samples it judged to
    be off the agar. Cropped to the dish, because that is the only part measured."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise TrackingError(f"cannot open {video!r}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cx, cy, r = cir
    x0, y0, side = int(cx - r), int(cy - r), int(2 * r)
    # The dish can run past the frame edge, so the crop is not always 2r square.
    # Measure it once from a real frame and map coordinates with what we got, not
    # with what we assumed - assuming cost every frame of the first attempt.
    ok, probe = cap.read()
    if not ok:
        raise TrackingError("empty video")
    ch, cw = probe[max(0, y0):y0 + side, max(0, x0):x0 + side].shape[:2]
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    sx, sy = size / float(cw), size / float(ch)
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (size, size))
    if not vw.isOpened():
        raise TrackingError(f"cannot write {out!r}")

    lar = []
    for L in St["larvae"].values():
        off = L.get("offplane") or [False] * len(L["pts"])
        lar.append({"name": L["name"], "bgr": bgr(L["color"]),
                    "pts": L["pts"], "off": off,
                    "cum": path_length(L["pts"], larva_cfg(St, L), off)[1]})
    unit = "mm" if St["cfg"]["mm_per_px"] != 1.0 else "px"
    P = lambda p: (int(round(p[1] * sx)), int(round(p[2] * sy)))

    i, n = -1, 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        i += 1
        t = i / fps
        crop = f[max(0, y0):y0 + side, max(0, x0):x0 + side]
        if crop.shape[0] != ch or crop.shape[1] != cw:
            continue
        im = cv2.resize(crop, (size, size))
        cv2.ellipse(im, (int((cx - max(0, x0)) * sx), int((cy - max(0, y0)) * sy)),
                    (int(r * sx), int(r * sy)), 0, 0, 360, (110, 110, 110), 1, cv2.LINE_AA)
        y_hud = 26
        for L in lar:
            k = 0
            while k < len(L["pts"]) and L["pts"][k][0] <= t:
                k += 1
            if k >= 2:
                cv2.polylines(im, [np.array([P(p) for p in L["pts"][:k]], np.int32)],
                              False, L["bgr"], 2, cv2.LINE_AA)
            if k >= 1:
                here, isoff = P(L["pts"][k - 1]), L["off"][k - 1]
                fresh = t - L["pts"][k - 1][0] < 1.0        # solid only while current
                cv2.circle(im, here, 11 if isoff else 8, L["bgr"],
                           2 if (isoff or not fresh) else -1, cv2.LINE_AA)
                if isoff:
                    cv2.putText(im, "off agar", (here[0] + 14, here[1] + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, .45, L["bgr"], 1, cv2.LINE_AA)
                elif fresh:
                    cv2.putText(im, L["name"], (here[0] + 12, here[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, .5, L["bgr"], 1, cv2.LINE_AA)
            cv2.putText(im, f"{L['name']}: {L['cum'][max(0, k - 1)]:6.1f} {unit}",
                        (10, y_hud), cv2.FONT_HERSHEY_SIMPLEX, .55, L["bgr"], 2, cv2.LINE_AA)
            y_hud += 24
        cv2.putText(im, f"{t:5.1f}s", (size - 92, 26), cv2.FONT_HERSHEY_SIMPLEX,
                    .6, (240, 240, 240), 2, cv2.LINE_AA)
        vw.write(im)
        n += 1
    cap.release()
    vw.release()
    log(f"wrote {out} ({n} frames, {n / fps:.0f}s)")
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8777)
    p.add_argument("--no-open", action="store_true", help="don't launch a browser")
    p.add_argument("--video", help="track a file instead of live, for tuning offline")
    p.add_argument("--out", default="run", help="output name prefix for --video")
    p.add_argument("--overlay-video", action="store_true",
                   help="also write a replay with the trails drawn as they happen")
    p.add_argument("--bridge-s", type=float, default=15.0,
                   help="rejoin tracks lost up to N seconds (0 = off)")
    p.add_argument("--larvae", type=int,
                   help="how many animals are actually in the dish")
    p.add_argument("--stabilise", action="store_true",
                   help="cancel camera drift (only if the camera was actually moved)")
    p.add_argument("--dish-mm", type=float, default=90.0,
                   help="dish diameter for --video (default 90)")
    p.add_argument("--demo", action="store_true", help="self-check, no camera needed")
    for k, v in D.items():
        p.add_argument("--" + k.replace("_", "-"), type=type(v), default=v)
    a = p.parse_args()
    if a.demo:
        return demo()
    if a.video:
      try:
        St, cir = analyse_video(a.video, a.dish_mm, hz=a.sample_hz,
                                stabilise=a.stabilise, expect=a.larvae,
                                bridge_s=a.bridge_s, edge_pct=a.edge_pct)
        r = save(os.path.splitext(a.video)[0], St)
        print()
        for row in sorted(r["larvae"], key=lambda x: -x["path"]):
            seen = max(row["duration"] - row["gap_s"], 1e-9)
            # Spread is straight-line distance, so it CANNOT exceed a fully observed
            # path. When it does, more was missed than seen and the total is not
            # worth quoting.
            flag = ("   <- gappy, path undercounts" if row["spread"] > row["path"]
                    else "" if row["spread"] >= 5 else "   <- stayed put, check it")
            print(f"  {row['name']:9s} {row['path'] / seen:4.2f} {r['unit']}/s"
                  f"  ->5min {row['est5']:6.1f} {r['unit']}"
                  f"  (seen {row['path']:6.1f} {r['unit']}"
                  f"  spread {row['spread']:5.1f})"
                  f"  tracked {seen:4.0f}/{row['duration']:.0f}s"
                  + (f"  off-agar {row['off_s']:.0f}s" if row['off_s'] else "") + flag)
        print(f"\nwrote {r['stem']}_tracks.csv, _summary.csv, _overlay.png")
        if a.overlay_video:
            write_overlay_video(a.video, St, cir,
                                os.path.splitext(a.video)[0] + "_tracked.mp4", a.sample_hz)
      except TrackingError as e:
        sys.exit(f"larvatrack: {e}")
      return
    serve(a.port, not a.no_open)

def demo():
    """Synthetic rig matching the real one: TWO pale larvae plus static yeast
    smears on a dark grey dish. Checks dish finding, box-add lock, two larvae
    tracked at once without swapping, and the HTTP round trip."""
    import urllib.request
    global DUMP
    DUMP = False                      # never clobber a real capture in lock_debug.png
    W, H, fps, n = 480, 400, 30, 300
    CX, CY, R = 240, 200, 170
    rng = np.random.default_rng(0)
    A0, B0 = (CX - 120, CY + 30), (CX - 100, CY - 70)      # the two larvae at t=0

    def synth(i):
        f = np.full((H, W, 3), 90, np.uint8)                    # bench
        cv2.circle(f, (CX, CY), R, (150, 150, 150), -1)         # dish interior
        cv2.circle(f, (CX, CY), R, (205, 205, 205), 3)          # rim
        cv2.line(f, (CX - 200, 40), (CX + 40, H), (128, 128, 128), 14)   # shadow bands
        cv2.line(f, (60, 150), (W, 120), (128, 128, 128), 12)
        cv2.ellipse(f, (W - 40, H - 40), (90, 80), 0, 0, 360, (60, 60, 60), -1)
        # static yeast smears: pale, elongated, larva-sized. Shape and brightness
        # cannot tell these from the animals - that is the whole difficulty.
        cv2.ellipse(f, (CX + 40, CY - 60), (16, 6), 55, 0, 360, (238, 238, 238), -1)
        cv2.ellipse(f, (CX - 30, CY + 85), (13, 5), 110, 0, 360, (235, 235, 235), -1)
        cv2.ellipse(f, (A0[0] + i // 2, A0[1]), (11, 5), 20, 0, 360, (232, 232, 232), -1)
        cv2.ellipse(f, (B0[0] + i // 3, B0[1] + i // 6), (10, 5), 70, 0, 360, (230, 230, 230), -1)
        return cv2.add(f, rng.integers(0, 7, f.shape, dtype=np.int16).astype(np.uint8))

    frame0 = synth(0)
    cir = find_plate(cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY))
    assert cir, "did not find the petri dish"
    assert math.hypot(cir[0] - CX, cir[1] - CY) < 25 and abs(cir[2] - R) < 30, \
        f"dish off: got {tuple(round(v) for v in cir)}"
    mpp = 60.0 / (2 * cir[2])
    lo, hi = area_bounds(mpp)
    print(f"dish: r={cir[2]:.0f} px -> {mpp:.5f} mm/px for a 60 mm dish; "
          f"larva area window {lo}-{hi} px")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    jpg = lambda im: cv2.imencode(".jpg", im)[1].tobytes()
    scale = f"min_area={lo}&max_area={hi}&mm_per_px={mpp}"
    knobs = f"dish_r={cir[2]:.1f}&{scale}"      # /plate must see the UNmasked frame
    post = lambda path, im: json.load(urllib.request.urlopen(base + path, jpg(im)))

    d = post(f"/plate?dish_mm=60&{scale}", frame0)
    assert d["found"] and d["mm_per_px"] > 0, "server did not find the dish"

    # drag a box round each larva, as the page does. Boxes deliberately loose and
    # containing a yeast smear, so "best blob in the box" has to earn it.
    added = {}
    for nm, (px, py) in (("rover", A0), ("sitter", B0)):
        box = f"bx={px - 40}&by={py - 40}&bw=80&bh=80"
        r = post(f"/add?{knobs}&{box}&name={nm}", frame0)
        assert r["found"], f"{nm}: box-add failed: {r.get('why')}"
        assert math.hypot(r["x"] - px, r["y"] - py) < 15, \
            f"{nm}: locked at ({r['x']:.0f},{r['y']:.0f}), expected ({px},{py}) - a smear?"
        added[nm] = r
        print(f"add {nm}: at ({r['x']:.0f},{r['y']:.0f}) area={r['area']} "
              f"elong={r['elong']} invert={r['invert']} thresh={r['thresh']}")
    assert added["rover"]["id"] != added["sitter"]["id"], "both boxes made the same larva"

    for k in range(0, n, 15):                                  # 2 Hz, as the page posts
        res = post(f"/frame?t={k / fps}&{knobs}", synth(k))
    by = {L["name"]: L for L in res["larvae"]}
    assert len(by) == 2, f"expected 2 larvae, got {list(by)}"
    for nm, (px, py), (dx, dy) in (("rover", A0, (n // 2, 0)), ("sitter", B0, (n // 3, n // 6))):
        L = by[nm]
        assert L["found"], f"{nm}: lost on the last frame"
        assert math.hypot(L["x"] - (px + dx), L["y"] - (py + dy)) < 20, \
            f"{nm}: ended at ({L['x']:.0f},{L['y']:.0f}), expected ({px + dx},{py + dy}) - swapped?"
        expect = math.hypot(dx, dy) * mpp
        assert abs(L["path"] - expect) < 0.2 * expect, \
            f"{nm}: path {L['path']} {res['unit']}, expected ~{expect:.2f}"
        print(f"{nm}: {L['path']} {res['unit']} over {L['n']} samples")

    # rename/colour, and "reset paths" must clear the track WITHOUT losing the lock
    post_empty = lambda p: json.load(urllib.request.urlopen(base + p, b""))
    rid = added["rover"]["id"]
    post_empty(f"/rename?id={rid}&name=rover-A&color=%23ff0000")
    assert S["larvae"][rid]["name"] == "rover-A", "rename did not stick"
    held = S["larvae"][rid]["last"]
    post_empty("/reset")
    assert S["larvae"][rid]["pts"] == [], "reset did not clear the path"
    assert S["larvae"][rid]["last"] == held, "reset threw away the lock"
    for k in range(n - 45, n, 15):          # carry on from where the run stopped
        res = post(f"/frame?t={k / fps}&{knobs}", synth(k))
    assert all(L["found"] for L in res["larvae"]), "lost a larva after reset"

    d = post(f"/save?{knobs}", frame0)
    assert len(d["larvae"]) == 2, f"save wrote {len(d['larvae'])} larvae"
    for f in ("_tracks.csv", "_summary.csv"):
        p = os.path.join(HERE, d["stem"] + f)
        assert os.path.exists(p), f"{f} not written"
        os.remove(p)
    os.remove(os.path.join(HERE, d["stem"] + "_overlay.png"))
    post_empty(f"/remove?id={rid}")
    assert rid not in S["larvae"] and len(S["larvae"]) == 1, "remove failed"
    # A real frame off the rig. thresh=120 with invert=1 selected 97.6% of it as one
    # blob: the lock looked fine inside a tight box and then tracked nothing at all.
    real = os.path.join(HERE, "testframe_real.png")
    if os.path.exists(real):
        rg = cv2.cvtColor(cv2.imread(real), cv2.COLOR_BGR2GRAY)
        rc = dict(D, mm_per_px=0.140482, min_area=15, max_area=608)
        pick = next(((i, t, bb) for i, t, bb in rank(rg, rc)[:40]
                     if survives_window(rg, i, t, bb, rc)), None)
        assert pick, "real frame: nothing survived the tracking window"
        ri, rt, rb = pick
        gb = cv2.medianBlur(rg, 5)
        fl = np.clip(gb.astype(np.int16)
                     - cv2.GaussianBlur(gb, (0, 0), FLAT_SIGMA).astype(np.int16) + 128, 0, 255)
        cover = float(((fl >= rt) if ri else (fl < rt)).mean())
        assert cover < 0.25, f"real frame: threshold floods {cover:.0%} of the dish"
        RL = {"pts": [], "last": (rb[1], rb[2]), "area": rb[0], "misses": 0}
        hits = sum(1 for k in range(12)
                   if step_one(RL, rg, dict(rc, thresh=rt, invert=ri), k * 0.5))
        assert hits == 12, f"real frame: only {hits}/12 samples tracked"
        print(f"real frame: invert={ri} thresh={rt}, selects {cover:.2%} of dish, 12/12 tracked")

    # Drift stress: light dims, the dish brightens and the larva fades over the run,
    # so the threshold picked at t=0 goes stale. This is the "tracked great, then
    # lost it" failure - it must re-tune and hold the animal for the whole run.
    def drift(i):
        f = np.full((H, W, 3), 90, np.uint8)
        dish = 150 + i // 6                                   # dish brightens
        cv2.circle(f, (CX, CY), R, (dish,) * 3, -1)
        cv2.circle(f, (CX, CY), R, (205, 205, 205), 3)
        cv2.ellipse(f, (CX + 40, CY - 60), (16, 6), 55, 0, 360, (238,) * 3, -1)
        lv = 232 - i // 5                                     # larva fades toward it
        cv2.ellipse(f, (CX - 120 + i // 2, CY + 30), (11, 5), 20, 0, 360, (lv,) * 3, -1)
        return cv2.add(f, rng.integers(0, 7, f.shape, dtype=np.int16).astype(np.uint8))

    cfg0 = dict(D, mm_per_px=mpp, min_area=lo, max_area=hi)    # as /plate sets them
    dg = lambda i: cv2.cvtColor(mask_dish(drift(i), *cir), cv2.COLOR_BGR2GRAY)
    d0 = next(((i, t2, bb) for i, t2, bb in rank(dg(0), cfg0)[:40]
               if survives_window(dg(0), i, t2, bb, cfg0)), None)
    assert d0, "drift: could not lock at t=0"
    DL = {"pts": [], "last": (d0[2][1], d0[2][2]), "area": d0[2][0],
          "misses": 0, "thresh": d0[1], "invert": d0[0]}
    got = sum(1 for i in range(0, n, 15)
              if step_one(DL, dg(i), dict(cfg0, thresh=DL["thresh"], invert=DL["invert"]),
                          i / fps))
    assert got == 20, f"drift: only {got}/20 samples tracked - it went stale again"
    endx = CX - 120 + (n - 15) // 2
    assert abs(DL["last"][0] - endx) < 20, \
        f"drift: ended at x={DL['last'][0]:.0f}, expected ~{endx} - it slid onto the smear"
    print(f"drift: 20/20 tracked through fading contrast, threshold "
          f"{d0[1]} -> {DL['thresh']}")

    # Agar plate off the rig: washed-out (std 8), larva only ~5 px wide and 68 px.
    # A fixed 5x5 opening deleted it entirely - mask had it, cleanup removed it.
    agar = os.path.join(HERE, "testframe_agar.png")
    if os.path.exists(agar):
        ag = cv2.cvtColor(cv2.imread(agar), cv2.COLOR_BGR2GRAY)
        amp = 60 / 396.0
        alo, ahi = area_bounds(amp)
        ac = dict(D, mm_per_px=amp, min_area=alo, max_area=ahi)
        AX, AY, ap = 306, 111, 30                      # the larva, as boxed by hand
        hit = next(((i, t2, (bb[0], bb[1] + AX - ap, bb[2] + AY - ap, bb[3], bb[4],
                             bb[5] + [AX - ap, AY - ap]))
                    for i, t2, bb in rank(ag[AY - ap:AY + ap, AX - ap:AX + ap], ac)[:40]), None)
        assert hit, "agar: nothing larva-shaped in the box (morphology eating it again?)"
        ai, at, ab = hit
        assert survives_window(ag, ai, at, ab, ac), "agar: lock does not survive the window"
        assert math.hypot(ab[1] - AX, ab[2] - AY) < 12, \
            f"agar: locked at ({ab[1]:.0f},{ab[2]:.0f}), larva is at ({AX},{AY})"
        AL = {"pts": [], "last": (ab[1], ab[2]), "area": ab[0], "misses": 0}
        ah = sum(1 for k in range(12)
                 if step_one(AL, ag, dict(ac, thresh=at, invert=ai), k * 0.5))
        assert ah == 12, f"agar: only {ah}/12 tracked"
        print(f"agar frame: locked area={ab[0]:.0f} px elong={ab[3]:.1f}, 12/12 tracked")

    # Long run: 5 real minutes at 2 Hz = 600 samples, with light drifting the whole
    # way. Checks that the lock does not RATCHET - the size gate is anchored to the
    # blob we locked at t=0, so a 3x-per-step tolerance cannot compound into the
    # tracker walking off onto ever-bigger junk.
    def longrun(i):
        f = np.full((H, W, 3), 90, np.uint8)
        cv2.circle(f, (CX, CY), R, (150 + i // 90,) * 3, -1)
        cv2.circle(f, (CX, CY), R, (205, 205, 205), 3)
        cv2.ellipse(f, (CX + 40, CY - 60), (16, 6), 55, 0, 360, (238,) * 3, -1)
        ang = i / 190.0                                   # larva loops round the dish
        x = int(CX + 95 * math.cos(ang)) - 30
        y = int(CY + 95 * math.sin(ang))
        cv2.ellipse(f, (x, y), (11, 5), int(20 + 40 * math.sin(ang)), 0, 360,
                    (232 - i // 120,) * 3, -1)
        return cv2.cvtColor(mask_dish(f, *cir), cv2.COLOR_BGR2GRAY), (x, y)

    g0, p0 = longrun(0)
    bx, by, bp = p0[0], p0[1], 30                      # a box round the larva, as you drag
    lk = next(((i, t2, (bb[0], bb[1] + bx - bp, bb[2] + by - bp, bb[3], bb[4],
                        bb[5] + [bx - bp, by - bp]))
               for i, t2, bb in rank(g0[by - bp:by + bp, bx - bp:bx + bp], cfg0)[:40]), None)
    assert lk, "long run: could not lock at t=0"
    assert math.hypot(lk[2][1] - p0[0], lk[2][2] - p0[1]) < 12, \
        f"long run: box lock landed at ({lk[2][1]:.0f},{lk[2][2]:.0f}), larva at {p0}"
    RL = {"pts": [], "last": (lk[2][1], lk[2][2]), "area": lk[2][0], "area0": lk[2][0],
          "misses": 0, "thresh": lk[1], "invert": lk[0]}
    a0, drift_err, miss = lk[2][0], [], 0
    for k in range(600):
        gk, pk = longrun(k)
        h = step_one(RL, gk, dict(cfg0, thresh=RL["thresh"], invert=RL["invert"]), k * 0.5)
        if h is None:
            miss += 1
        else:
            drift_err.append(math.hypot(RL["last"][0] - pk[0], RL["last"][1] - pk[1]))
    early = sum(drift_err[:50]) / max(len(drift_err[:50]), 1)
    late = sum(drift_err[-50:]) / max(len(drift_err[-50:]), 1)
    print(f"long run: {600 - miss}/600 samples tracked, area {a0:.0f} -> {RL['area']:.0f} px, "
          f"positional error early {early:.1f} px, late {late:.1f} px")
    assert miss <= 60, f"long run: lost {miss}/600 samples"
    assert 0.4 * a0 <= RL["area"] <= 2.5 * a0, \
        f"long run: area ratcheted {a0:.0f} -> {RL['area']:.0f}"
    assert late < early + 6, \
        f"long run: accuracy decayed over time ({early:.1f} px -> {late:.1f} px)"

    # GROUND TRUTH. A larva walks one lap of a circle whose circumference we know
    # exactly, so the measured path can be checked against a real answer rather
    # than against whether it looks plausible. This is the test that decided gap
    # closing should be on: without it the error here is about -40%.
    import tempfile as _tf
    TW = 640; TC = 320; TR = 300; TFPS = 10; TSEC = 60; TN = TFPS * TSEC
    TPR = 110.0
    tmpp = 90.0 / (2 * TR)
    true_mm = 2 * math.pi * TPR * tmpp
    tpath = os.path.join(_tf.mkdtemp(), "truth.mp4")
    tw = cv2.VideoWriter(tpath, cv2.VideoWriter_fourcc(*"mp4v"), TFPS, (TW, TW))
    for i in range(TN):
        f = np.full((TW, TW, 3), 70, np.uint8)
        cv2.circle(f, (TC, TC), TR, (150 + int(10 * math.sin(i / TN * math.pi)),) * 3, -1)
        cv2.circle(f, (TC, TC), TR, (200, 200, 200), 3)
        cv2.ellipse(f, (TC + 90, TC - 110), (16, 6), 40, 0, 360, (235,) * 3, -1)
        cv2.ellipse(f, (TC - 100, TC + 95), (14, 6), 100, 0, 360, (232,) * 3, -1)
        ang = 2 * math.pi * i / TN
        cv2.ellipse(f, (int(TC + TPR * math.cos(ang)), int(TC + TPR * math.sin(ang))),
                    (11, 5), int(math.degrees(ang)) + 90, 0, 360, (233,) * 3, -1)
        tw.write(cv2.add(f, rng.integers(0, 6, f.shape, dtype=np.int16).astype(np.uint8)))
    tw.release()
    TS, _ = analyse_video(tpath, 90.0, hz=2.0, expect=1, log=lambda *a: None)
    TL = list(TS["larvae"].values())[0]
    tc = larva_cfg(TS, TL)
    got, _, tgap = path_length(TL["pts"], tc, TL.get("offplane"))
    tdur = TL["pts"][-1][0] - TL["pts"][0][0]
    tseen = max(tdur - tgap, 1e-9)
    err = (got - true_mm) / true_mm
    speed_err = (got / tseen - true_mm / TSEC) / (true_mm / TSEC)
    print(f"ground truth: true {true_mm:.2f} mm, measured {got:.2f} mm ({err:+.1%}), "
          f"speed {speed_err:+.1%}, tracked {tseen:.0f}/{TSEC}s")
    assert abs(speed_err) < 0.15, f"speed off by {speed_err:+.1%} against a known answer"
    assert abs(err) < 0.25, f"path off by {err:+.1%} against a known answer"

    # WALL FOLLOWING. Larvae hug the dish wall, and that is when they cover the
    # most ground, so losing the outer band biases the assay against exactly the
    # animals it is meant to measure. This is the case the old 90% edge mask failed
    # outright: it refused to track at all.
    # Scale matters here: at r=190 px the 10 px larva merges with the rim and this
    # fails, at r=265 px it tracks perfectly right up to the wall. Real footage has
    # r~510 px. The test uses realistic proportions rather than the smallest frame
    # that runs quickly, because the small frame tests the wrong thing.
    WW = 560; WC = 280; WR = 265; WFPS = 10; WSEC = 60; WN = WFPS * WSEC
    wmpp = 90.0 / (2 * WR)
    wrad = 0.96 * WR                                 # pressed to the wall throughout
    wpos = lambda i: (WC + wrad * math.cos(2 * math.pi * 0.35 * i / WN),
                      WC + wrad * math.sin(2 * math.pi * 0.35 * i / WN))
    wtrue = sum(math.hypot(wpos(i)[0] - wpos(i - 1)[0], wpos(i)[1] - wpos(i - 1)[1])
                for i in range(1, WN)) * wmpp
    wpath = os.path.join(_tf.mkdtemp(), "wall.mp4")
    ww = cv2.VideoWriter(wpath, cv2.VideoWriter_fourcc(*"mp4v"), WFPS, (WW, WW))
    for i in range(WN):
        f = np.full((WW, WW, 3), 70, np.uint8)
        cv2.circle(f, (WC, WC), WR, (150,) * 3, -1)
        cv2.circle(f, (WC, WC), WR, (215,) * 3, 3)           # bright rim highlight
        cv2.ellipse(f, (WC + 70, WC - 110), (14, 6), 40, 0, 360, (235,) * 3, -1)
        wx, wy = wpos(i)
        cv2.ellipse(f, (int(wx), int(wy)), (10, 5),
                    int(math.degrees(math.atan2(wy - WC, wx - WC))) + 90,
                    0, 360, (233,) * 3, -1)
        ww.write(cv2.add(f, rng.integers(0, 6, f.shape, dtype=np.int16).astype(np.uint8)))
    ww.release()
    WS, _ = analyse_video(wpath, 90.0, hz=2.0, expect=1, log=lambda *a: None)
    WL = list(WS["larvae"].values())[0]
    wc_ = larva_cfg(WS, WL)
    wgot, _, wgap = path_length(WL["pts"], wc_, WL.get("offplane"))
    wdur = WL["pts"][-1][0] - WL["pts"][0][0]
    wseen = max(wdur - wgap, 1e-9)
    werr = (wgot - wtrue) / wtrue
    print(f"wall-following: true {wtrue:.1f} mm, measured {wgot:.1f} mm ({werr:+.1%}), "
          f"tracked {wseen:.0f}/{WSEC}s")
    assert wseen > 0.8 * WSEC, f"lost a wall-follower for {WSEC - wseen:.0f}s of {WSEC}s"
    assert abs(werr) < 0.20, f"wall-following path off by {werr:+.1%}"

    # FALSE POSITIVES. The same dish with the yeast smears and the lighting drift
    # but NO animal must yield nothing - including when the count says to expect
    # two. Inventing a track on an empty plate is the failure that would quietly
    # corrupt a dataset, because the number still looks like a measurement.
    epath = os.path.join(_tf.mkdtemp(), "empty.mp4")
    ew = cv2.VideoWriter(epath, cv2.VideoWriter_fourcc(*"mp4v"), TFPS, (TW, TW))
    for i in range(TFPS * 40):
        f = np.full((TW, TW, 3), 70, np.uint8)
        cv2.circle(f, (TC, TC), TR,
                   (150 + int(14 * math.sin(i / (TFPS * 40) * 2 * math.pi)),) * 3, -1)
        cv2.circle(f, (TC, TC), TR, (200, 200, 200), 3)
        cv2.ellipse(f, (TC + 90, TC - 110), (16, 6), 40, 0, 360, (235,) * 3, -1)
        cv2.ellipse(f, (TC - 80, TC + 120), (15, 6), 95, 0, 360, (233,) * 3, -1)
        ew.write(cv2.add(f, rng.integers(0, 6, f.shape, dtype=np.int16).astype(np.uint8)))
    ew.release()
    for want in (None, 2):
        try:
            ES, _ = analyse_video(epath, 90.0, hz=2.0, expect=want, log=lambda *a: None)
            raise AssertionError(
                f"invented {len(ES['larvae'])} larvae on an empty dish (--larvae {want})")
        except TrackingError:
            pass
    print("empty dish: nothing invented, with or without an expected count")

    # Cheap unit checks for the rules the video path depends on, so they are
    # covered without rebuilding a clip for each one.
    flat_a, flat_f = [100] * 40, [0.5] * 40
    assert not any(mark_offplane(flat_a, flat_f)), "off-agar fired on a steady track"
    lid_a = flat_a[:15] + [140] * 10 + flat_a[25:]
    lid_f = flat_f[:15] + [0.3] * 10 + flat_f[25:]
    marked = mark_offplane(lid_a, lid_f)
    assert 8 <= sum(marked) <= 12, f"lid climb marked {sum(marked)} of 10 samples"
    assert not any(marked[:14]) and not any(marked[26:]), "off-agar bled outside the climb"
    assert not any(mark_offplane(lid_a, flat_f)), "bigger alone must not count as off-agar"
    assert not any(mark_offplane(flat_a, lid_f)), "softer alone must not count as off-agar"

    lin = [(0.5, 0), (1.0, 0), (1.5, 0)]
    lin = [(t, x * 100, 0.0) for t, x, _ in ((0.0, 0, 0), (0.5, 1, 0), (1.0, 2, 0))]
    p1 = path_length(lin, dict(D, mm_per_px=0.1, sample_hz=2.0))[0]
    p2 = path_length(lin, dict(D, mm_per_px=0.2, sample_hz=2.0))[0]
    assert abs(p2 - 2 * p1) < 1e-9, f"path is not linear in scale: {p1} then {p2}"

    try:
        analyse_video(os.path.join(HERE, "does-not-exist.mp4"), 90.0, log=lambda *a: None)
        raise AssertionError("a missing video should raise TrackingError")
    except TrackingError:
        pass
    print("rules: off-agar needs BOTH bigger and softer; path scales linearly; "
          "bad input raises rather than exits")

    srv.shutdown()
    page = open(os.path.join(HERE, "index.html")).read()
    for r in ("/plate", "/add", "/frame", "/save", "/reset", "/remove", "/rename"):
        assert r in page, f"page never calls {r}"
    print("demo OK")

if __name__ == "__main__":
    main()

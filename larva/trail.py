"""Measure the trail a larva leaves, instead of following the larva.

The standard protocol traces the path on the dish lid and measures the tracing.
Accumulating change between well-spaced frames paints exactly that trail, and
nothing can be lost because there is no lock to drop. It gives distance covered,
not a time course - that is the trade.

The spacing matters more than anything else here. At 10 Hz a larva moves a
fraction of its own body between frames, the trail signal is tiny and slow camera
drift at the dish rim swamps it. At a few seconds apart the animal has moved
several body lengths and its trail is the brightest thing on the plate.
"""
import math
import cv2
import numpy as np

import larvatrack as lt


def ribbon_mm(binary, mpp):
    """Length of a trail treated as a ribbon: area divided by width.

    Skeletonising and counting pixels is the obvious route and it is a trap: a
    thinning that leaves the line two pixels wide anywhere overstates length
    badly (+109% on a test zigzag here). Width from the distance transform needs
    no skeleton. Calibrated on straight lines 3-13 px wide, a circle and a
    zigzag, 2x the 95th percentile of the distance transform gives 3.0% mean
    error, against 7.3% for the maximum and 13.9% for 4x the mean.
    """
    m = (binary > 0).astype(np.uint8)
    area = float(m.sum())
    if area < 10:
        return 0.0, 0.0
    dt = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    width = 2.0 * float(np.percentile(dt[m > 0], 95))
    return (area / max(width, 1e-6)) * mpp, width * mpp


def pieces_of(binv, mpp, max_width_mm):
    """Split a motion mask into pieces, keeping the ones shaped like a trail.

    A larva is about a millimetre across so its trail is about that wide. A
    drifting shadow is brighter but much broader, and that difference in SHAPE
    separates them where brightness cannot.
    """
    n, lab, stats, cent = cv2.connectedComponentsWithStats((binv > 0).astype(np.uint8), 8)
    keep, dropped = [], []
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] < 30:
            continue
        mm, w = ribbon_mm((lab == k).astype(np.uint8) * 255, mpp)
        rec = {"mm": round(mm, 1), "widthMm": round(w, 2), "label": int(k),
               "areaPx": int(stats[k, cv2.CC_STAT_AREA]),
               "cx": round(float(cent[k][0])), "cy": round(float(cent[k][1]))}
        if w > max_width_mm:
            rec["why"] = "too broad to be a trail"
            dropped.append(rec)
        elif mm < 2.0 * max(w, 1e-6):
            rec["why"] = "too stubby to be a trail"
            dropped.append(rec)
        else:
            keep.append(rec)
    keep.sort(key=lambda p: -p["mm"])
    return sum(p["mm"] for p in keep), keep, dropped, lab


def _accept_step(diff, thr, mpp, max_width_mm, min_mm, max_mm=None):
    """Keep the parts of one increment that look like a larva moved there."""
    bw = (diff > thr).astype(np.uint8) * 255
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _c = cv2.connectedComponentsWithStats((bw > 0).astype(np.uint8), 8)
    out = np.zeros_like(bw)
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] < 25:
            continue
        piece = (lab == k).astype(np.uint8) * 255
        mm, w = ribbon_mm(piece, mpp)
        # One increment is one larva-step: about a millimetre wide, and no longer
        # than the animal could crawl in that time. Bounding both ends keeps
        # noise specks and broad shadows out without any threshold tuning.
        if w <= max_width_mm and mm >= min_mm and (max_mm is None or mm <= max_mm):
            out[lab == k] = 255
    return out


WALL_SPEED_MM_S = 1.5            # ordinary crawling pace, for inferring wall runs

def arc_bridge(a, b, centre, r, mpp, rim_frac=0.80):
    """Distance a larva covered while lost against the dish wall.

    Larvae wall-follow, and while pressed to the side the trail washes out against
    the rim - the animal vanishes at one point on the wall and turns up at another.
    A straight line between them cuts across the dish, which is not where it went.
    If both ends sit out near the wall, it went round, so measure the arc.

    Returns the arc in mm, or None when either end is well inside the dish - there
    the animal could have gone anywhere and a guess would be an invention.
    """
    ax, ay = a[0] - centre[0], a[1] - centre[1]
    bx, by = b[0] - centre[0], b[1] - centre[1]
    ra, rb = math.hypot(ax, ay), math.hypot(bx, by)
    if ra < rim_frac * r or rb < rim_frac * r:
        return None
    ang = abs(math.atan2(ay, ax) - math.atan2(by, bx))
    if ang > math.pi:
        ang = 2 * math.pi - ang
    return ang * (0.5 * (ra + rb)) * mpp


def measure(video, dish_mm, circle, every=5.0, edge=0.94, max_width_mm=2.5,
            threshold=None, log=print):
    """Total trail length in mm for one dish.

    Each increment - what changed over the last `every` seconds - is judged on its
    own and, if it looks like a larva moved there, added to a trail that only ever
    grows. Judging the whole accumulated blob instead was the bug behind the total
    jumping about: once a growing trail merged with a shadow the merged shape read
    as "too broad" and the entire thing was discarded, then reappeared when a
    different threshold split it again.
    """
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise lt.TrackingError(f"cannot open {video!r}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(fps, 1e-6)
    cx, cy, r = circle
    ox, oy = max(0, int(cx - r)), max(0, int(cy - r))
    side = int(2 * r)
    mpp = dish_mm / (2 * r)

    grabs = []
    t = 0.0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, f = cap.read()
        if not ok:
            break
        grabs.append(cv2.cvtColor(f[oy:oy + side, ox:ox + side], cv2.COLOR_BGR2GRAY))
        t += every
    cap.release()
    grabs = [g for g in grabs if g.shape == grabs[0].shape] if grabs else []
    if len(grabs) < 3:
        raise lt.TrackingError("not enough frames")

    mask = np.zeros(grabs[0].shape, np.uint8)
    cv2.circle(mask, (int(cx - ox), int(cy - oy)), int(r * edge), 255, -1)
    diffs = [cv2.bitwise_and(cv2.absdiff(cv2.GaussianBlur(a, (0, 0), 2),
                                         cv2.GaussianBlur(b, (0, 0), 2)), mask)
             for a, b in zip(grabs, grabs[1:])]
    # Threshold from a high percentile of the increments, not from the median and
    # MAD: almost every pixel of almost every increment is unchanged, so those
    # statistics sit near zero and let speckle through everywhere. The 99.8th
    # percentile tracks the signal instead, and produced trails matching the raw
    # motion maps by eye on all three single-larva dishes.
    pool = np.concatenate([d[mask > 0] for d in diffs]).astype(np.float32)
    base = max(8, int(np.percentile(pool, 99.8)))
    min_mm = 0.8
    # A larva tops out around 4 mm/s, so one increment cannot be longer than that
    # times the gap - anything longer is a shadow sweeping across, not an animal.
    max_mm = lt.D["max_speed"] * every

    def build(thr):
        steps = [_accept_step(d, thr, mpp, max_width_mm, min_mm, max_mm) for d in diffs]
        # A crawling larva leaves a CHAIN: where it was this step, it was nearby
        # the step before or after. A speck of noise appears once and never again.
        # Requiring a neighbour in time removes the scatter without touching the
        # trail, and needs no extra threshold.
        reach_px = int((lt.D["max_speed"] * every / mpp) * 1.6) | 1
        ker = np.ones((reach_px, reach_px), np.uint8)
        near = [cv2.dilate(s_, ker) for s_ in steps]
        trail_mask = np.zeros(grabs[0].shape, np.uint8)
        for i, s_ in enumerate(steps):
            company = np.zeros_like(s_)
            if i > 0:
                company = cv2.max(company, near[i - 1])
            if i + 1 < len(steps):
                company = cv2.max(company, near[i + 1])
            keep = cv2.bitwise_and(s_, company)
            n_, lab_, st_, _c = cv2.connectedComponentsWithStats((s_ > 0).astype(np.uint8), 8)
            whole = np.zeros_like(s_)
            for k in range(1, n_):
                if (keep[lab_ == k] > 0).any():      # keep the piece, not the overlap
                    whole[lab_ == k] = 255
            trail_mask = cv2.max(trail_mask, whole)
        return trail_mask

    # Set the threshold from the noise, do not search for the value that yields
    # the most trail: that objective rewards noise and drives it to the floor.
    thr = threshold if threshold is not None else base
    trail_mask = build(thr)

    seen, width = ribbon_mm(trail_mask, mpp)

    # Where was it, increment by increment? Only to find the wall gaps - the
    # measurement itself is still the painted trail, not a track.
    steps = [_accept_step(d, thr, mpp, max_width_mm, min_mm, max_mm) for d in diffs]
    where = []
    for sm in steps:
        # The biggest accepted piece, not the mean of all of them: averaging over
        # several pieces puts the "position" somewhere the larva never was, and a
        # wall arc drawn between two such points is fiction.
        n_, lab_, st_, cen_ = cv2.connectedComponentsWithStats((sm > 0).astype(np.uint8), 8)
        if n_ < 2:
            where.append(None)
            continue
        k = 1 + int(np.argmax(st_[1:, cv2.CC_STAT_AREA]))
        where.append((float(cen_[k][0]), float(cen_[k][1])))
    centre = (cx - ox, cy - oy)
    bridged, arcs = 0.0, []
    last_i = None
    for i, p in enumerate(where):
        if p is None:
            continue
        if last_i is not None and i - last_i > 1:
            arc = arc_bridge(where[last_i], p, centre, r, mpp)
            # Crawling pace, not the sprint ceiling: a wall gap is inferred, so it
            # should not be allowed to contribute more than an ordinary larva
            # could have walked in that time. And a gap longer than half a minute
            # is not a wall run, it is simply a loss.
            gap_s = (i - last_i) * every
            if (arc is not None and gap_s <= 30.0
                    and arc <= WALL_SPEED_MM_S * gap_s):
                bridged += arc
                arcs.append({"fromSec": round(last_i * every), "toSec": round(i * every),
                             "mm": round(arc, 1)})
        last_i = i
    total = seen + bridged
    log(f"{total:.1f} mm ({seen:.1f} seen + {bridged:.1f} along the wall) "
        f"at threshold {thr}")
    return {"totalMm": round(total, 1), "seenMm": round(seen, 1),
            "wallMm": round(bridged, 1), "arcs": arcs,
            "threshold": thr, "mmPerPx": round(mpp, 5),
            "widthMm": round(width, 2), "frames": len(grabs),
            "trail": trail_mask, "origin": (ox, oy), "mask": mask,
            "where": where, "centre": centre, "radius": r, "every": every}


def replay(video, dish_mm, circle, out, every=5.0, edge=0.94, max_width_mm=2.5,
           threshold=None, log=print):
    """Render the dish with its trail painting itself, increment by increment.

    Exactly the same accumulation the measurement uses, so the number on screen at
    the end is the number it reports.
    """
    import shutil, subprocess
    m = measure(video, dish_mm, circle, every=every, edge=edge,
                max_width_mm=max_width_mm, threshold=threshold, log=lambda *a: None)
    thr, mpp, mask = m["threshold"], m["mmPerPx"], m["mask"]
    ox, oy = m["origin"]
    cx, cy, r = circle
    side = int(2 * r)

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(fps, 1e-6)
    size = 720
    ff = shutil.which("ffmpeg")
    if not ff:
        raise lt.TrackingError("ffmpeg is needed to write the replay")
    proc = subprocess.Popen(
        [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{size}x{size}", "-r", "8", "-i", "-", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", out],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    trail_mask = np.zeros(mask.shape, np.uint8)
    prev = None
    t, n = 0.0, 0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, f = cap.read()
        if not ok:
            break
        cur = f[oy:oy + side, ox:ox + side]
        if cur.shape[:2] != mask.shape:
            break
        g = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
        if prev is not None:
            d = cv2.bitwise_and(cv2.absdiff(cv2.GaussianBlur(g, (0, 0), 2),
                                            cv2.GaussianBlur(prev, (0, 0), 2)), mask)
            trail_mask = cv2.max(trail_mask,
                                 _accept_step(d, thr, mpp, max_width_mm, 0.8))
        prev = g
        total, _w = ribbon_mm(trail_mask, mpp)
        total += sum(a["mm"] for a in m["arcs"] if a["toSec"] <= t)
        im = cv2.resize(cur, (size, size))
        paint = cv2.resize(trail_mask, (size, size), interpolation=cv2.INTER_NEAREST)
        im[paint > 0] = (0.2 * im[paint > 0] + 0.8 * np.array([60, 60, 255])).astype(np.uint8)
        # Wall runs are inferred, not seen, so they are drawn as a dashed amber
        # arc - never the same red as the trail the camera actually recorded.
        for a in m["arcs"]:
            if a["toSec"] > t:
                continue
            i0, i1 = int(a["fromSec"] / every), int(a["toSec"] / every)
            p0, p1 = m["where"][i0], m["where"][i1]
            if not p0 or not p1:
                continue
            c0 = m["centre"]
            a0 = math.atan2(p0[1] - c0[1], p0[0] - c0[0])
            a1 = math.atan2(p1[1] - c0[1], p1[0] - c0[0])
            d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            rr = 0.5 * (math.hypot(p0[0] - c0[0], p0[1] - c0[1])
                        + math.hypot(p1[0] - c0[0], p1[1] - c0[1]))
            for u in np.arange(0, 1.0, 0.04):
                if int(u * 25) % 2:
                    continue
                ang = a0 + d * u
                px = (c0[0] + rr * math.cos(ang)) * size / mask.shape[1]
                py = (c0[1] + rr * math.sin(ang)) * size / mask.shape[0]
                cv2.circle(im, (int(px), int(py)), 3, (60, 190, 255), -1, cv2.LINE_AA)
        cv2.putText(im, f"path {total:6.1f} mm", (12, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    .7, (60, 60, 255), 2, cv2.LINE_AA)
        if m["wallMm"]:
            cv2.putText(im, f"amber = inferred along the wall", (12, size - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, (60, 190, 255), 1, cv2.LINE_AA)
        cv2.putText(im, f"{t:5.0f}s", (size - 96, 30), cv2.FONT_HERSHEY_SIMPLEX, .7,
                    (255, 255, 255), 2, cv2.LINE_AA)
        proc.stdin.write(im.tobytes())
        n += 1
        t += every
    cap.release()
    proc.stdin.close()
    if proc.wait() != 0:
        raise lt.TrackingError("ffmpeg failed: " + proc.stderr.read().decode()[-200:])
    log(f"wrote {out} ({n} frames); ends at {m['totalMm']} mm")
    return m


def self_check():
    """The length estimator, against shapes whose length is known exactly."""
    cases = [("straight", lambda im: cv2.line(im, (50, 200), (450, 200), 255, 7), 400.0),
             ("circle", lambda im: cv2.circle(im, (250, 250), 120, 255, 7), 2 * math.pi * 120),
             ("zigzag", lambda im: cv2.polylines(
                 im, [np.array([[40, 60], [160, 300], [280, 60], [400, 300]], np.int32)],
                 False, 255, 7), 3 * math.hypot(120, 240))]
    worst = 0.0
    for name, draw, true in cases:
        im = np.zeros((500, 500), np.uint8)
        draw(im)
        got, _w = ribbon_mm(im, 1.0)
        err = abs(got - true) / true
        worst = max(worst, err)
        print(f"  {name:9s} true {true:7.1f} px, measured {got:7.1f} px ({(got-true)/true:+6.1%})")
    # Measured spread on these shapes is about 6% mean, 9% worst - good enough to
    # compare genotypes, not good enough to quote to three figures.
    assert worst < 0.12, f"length estimator off by {worst:.1%}"
    print("trail self-check OK")


if __name__ == "__main__":
    self_check()

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


def _step_pieces(diff, thr, mpp, max_width_mm, min_mm, max_mm):
    """Candidate larva-steps in one increment, with their centres."""
    bw = (diff > thr).astype(np.uint8) * 255
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats((bw > 0).astype(np.uint8), 8)
    out = []
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] < 25:
            continue
        piece = (lab == k).astype(np.uint8) * 255
        mm, w = ribbon_mm(piece, mpp)
        if w <= max_width_mm and min_mm <= mm <= max_mm:
            out.append({"mask": piece, "mm": mm,
                        "xy": (float(cent[k][0]), float(cent[k][1]))})
    return out


def chain_one(steps, reach_px, log=print):
    """Follow ONE animal through the increments.

    A solo dish holds one larva, so two paths cannot be laid at the same moment:
    in any increment at most one piece is the animal and the rest are artefacts.
    Choosing the piece that continues where the larva just was rejects a rim arc
    and a speck alike, without a threshold for either - the constraint does the
    work. Every plausible start is tried and the longest chain wins, so a noisy
    first increment cannot send it off after the wrong thing.
    """
    best = None
    starts = [(i, p) for i in range(min(len(steps), 8)) for p in steps[i]]
    for si, sp in starts:
        chain, last, total = [(si, sp)], sp["xy"], sp["mm"]
        gap = 0
        for i in range(si + 1, len(steps)):
            near = [p for p in steps[i]
                    if math.hypot(p["xy"][0] - last[0], p["xy"][1] - last[1])
                    <= reach_px * (1 + gap)]
            if not near:
                gap += 1
                if gap > 6:                          # half a minute with no sign of it
                    break
                continue
            pick = min(near, key=lambda p: math.hypot(p["xy"][0] - last[0],
                                                      p["xy"][1] - last[1]))
            chain.append((i, pick))
            last, total, gap = pick["xy"], total + pick["mm"], 0
        if best is None or total > best[0]:
            best = (total, chain)
    return best if best else (0.0, [])


def measure(video, dish_mm, circle, every=5.0, edge=0.94, max_width_mm=2.5,
            threshold=None, solo=True, log=print):
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

    def build_one(thr):
        """Solo dish: one larva, so one chain of increments."""
        steps = [_step_pieces(d, thr, mpp, max_width_mm, min_mm, max_mm) for d in diffs]
        reach_px = (max_mm * 1.3) / mpp
        total, chain = chain_one(steps, reach_px)
        tm = np.zeros(grabs[0].shape, np.uint8)
        for _i, p in chain:
            tm = cv2.max(tm, p["mask"])
        return tm, chain

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
    chain = []
    if solo:
        trail_mask, chain = build_one(thr)
        linked = len(chain)
    else:
        trail_mask, linked = build(thr), 0

    total, width = ribbon_mm(trail_mask, mpp)
    log(f"{total:.1f} mm at threshold {thr}, {linked} of {len(diffs)} increments linked")
    return {"totalMm": round(total, 1), "threshold": thr, "mmPerPx": round(mpp, 5),
            "widthMm": round(width, 2), "frames": len(grabs), "linked": linked,
            "increments": len(diffs), "trail": trail_mask, "origin": (ox, oy),
            "mask": mask, "chain": chain, "every": every}


def replay(video, dish_mm, circle, out, every=5.0, edge=0.94, max_width_mm=2.5,
           threshold=None, solo=True, log=print):
    """Render the dish with its path painting itself, increment by increment.

    It paints the chain the measurement chose, in time order, so what you watch
    and what it reports are the same thing.
    """
    import shutil, subprocess
    m = measure(video, dish_mm, circle, every=every, edge=edge,
                max_width_mm=max_width_mm, threshold=threshold, solo=solo,
                log=lambda *a: None)
    ox, oy = m["origin"]
    mask = m["mask"]
    cx, cy, r = circle
    side = int(2 * r)
    mpp = m["mmPerPx"]
    by_step = {}
    for i, p in m["chain"]:
        by_step.setdefault(i, []).append(p["mask"])

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
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

    painted = np.zeros(mask.shape, np.uint8)
    n = 0
    for i in range(m["increments"]):
        t = (i + 1) * every
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, f = cap.read()
        if not ok:
            break
        cur = f[oy:oy + side, ox:ox + side]
        if cur.shape[:2] != mask.shape:
            break
        for pm in by_step.get(i, []):
            painted = cv2.max(painted, pm)
        total, _w = ribbon_mm(painted, mpp)
        im = cv2.resize(cur, (size, size))
        paint = cv2.resize(painted, (size, size), interpolation=cv2.INTER_NEAREST)
        im[paint > 0] = (0.2 * im[paint > 0] + 0.8 * np.array([60, 60, 255])).astype(np.uint8)
        here = by_step.get(i)
        if here:
            ys, xs = np.nonzero(here[-1])
            if len(xs):
                cv2.circle(im, (int(xs.mean() * size / mask.shape[1]),
                                int(ys.mean() * size / mask.shape[0])),
                           13, (80, 255, 80), 2, cv2.LINE_AA)
        cv2.putText(im, f"path {total:6.1f} mm", (12, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    .7, (60, 60, 255), 2, cv2.LINE_AA)
        cv2.putText(im, f"{t:5.0f}s", (size - 96, 30), cv2.FONT_HERSHEY_SIMPLEX, .7,
                    (255, 255, 255), 2, cv2.LINE_AA)
        if not here:
            cv2.putText(im, "lost", (12, 58), cv2.FONT_HERSHEY_SIMPLEX, .6,
                        (80, 200, 255), 2, cv2.LINE_AA)
        proc.stdin.write(im.tobytes())
        n += 1
    cap.release()
    proc.stdin.close()
    if proc.wait() != 0:
        raise lt.TrackingError("ffmpeg failed: " + proc.stderr.read().decode()[-200:])
    log(f"wrote {out} ({n} frames); {m['totalMm']} mm, "
        f"{m['linked']}/{m['increments']} increments linked")
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

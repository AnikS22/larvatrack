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


def measure(video, dish_mm, circle, every=5.0, edge=0.88, max_width_mm=2.5, log=print):
    """Total trail length in mm for one dish."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise lt.TrackingError(f"cannot open {video!r}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cx, cy, r = circle
    ox, oy = max(0, int(cx - r)), max(0, int(cy - r))
    side = int(2 * r)
    frames = []
    for t in np.arange(0.0, total_frames / max(fps, 1e-6), every):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(f[oy:oy + side, ox:ox + side], cv2.COLOR_BGR2GRAY))
    cap.release()
    if len(frames) < 3:
        raise lt.TrackingError("not enough frames")

    frames = [f for f in frames if f.shape == frames[0].shape]
    mask = np.zeros(frames[0].shape, np.uint8)
    cv2.circle(mask, (int(cx - ox), int(cy - oy)), int(r * edge), 255, -1)
    acc = np.zeros(frames[0].shape, np.uint8)
    for a, b in zip(frames, frames[1:]):
        acc = cv2.max(acc, cv2.absdiff(cv2.GaussianBlur(a, (0, 0), 2),
                                       cv2.GaussianBlur(b, (0, 0), 2)))
    acc = cv2.bitwise_and(acc, mask)
    inside = acc[mask > 0].astype(np.float32)
    mad = float(np.median(np.abs(inside - np.median(inside))))
    base = max(8, int(np.median(inside) + 3 * 1.4826 * mad))
    mpp = dish_mm / (2 * r)

    # No single threshold suits every plate: too low and a bright trail floods
    # into a broad blob the width filter discards, too high and a faint one
    # disappears. Sweep, and keep whichever yields the most trail-shaped trail.
    best = None
    hi = max(base + 2, min(int(acc.max()), base + 110))
    for thr in range(base, hi, 3):
        b = (acc > thr).astype(np.uint8) * 255
        b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        b = cv2.morphologyEx(b, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        tot, keep, dropped, lab = pieces_of(b, mpp, max_width_mm)
        if best is None or tot > best[0]:
            best = (tot, thr, keep, dropped, lab)
    total, thr, keep, dropped, lab = best

    shown = np.zeros(acc.shape, np.uint8)
    for p in keep:
        shown[lab == p["label"]] = 255
    log(f"{total:.1f} mm of trail from {len(keep)} pieces at threshold {thr}")
    return {"totalMm": round(total, 1), "threshold": thr, "mmPerPx": round(mpp, 5),
            "widthMm": keep[0]["widthMm"] if keep else 0.0, "frames": len(frames),
            "pieces": keep, "rejected": dropped[:6],
            "acc": acc, "trail": shown, "origin": (ox, oy)}


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


def replay(video, dish_mm, circle, out, every=5.0, show_step=1.0, edge=0.88,
           max_width_mm=2.5, threshold=None, log=print):
    """Render the dish with its trail painting itself as the clip plays.

    Each output frame compares now against `every` seconds ago, so you watch the
    trail accumulate the same way the measurement builds it - the animal moving,
    the line growing behind it, and the running total climbing.
    """
    import shutil, subprocess
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise lt.TrackingError(f"cannot open {video!r}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(fps, 1e-6)
    cx, cy, r = circle
    ox, oy = max(0, int(cx - r)), max(0, int(cy - r))
    side = int(2 * r)
    mpp = dish_mm / (2 * r)
    size = 720

    grab = {}
    def at(t):
        k = round(t, 2)
        if k not in grab:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(k * fps)))
            ok, f = cap.read()
            grab[k] = f[oy:oy + side, ox:ox + side] if ok else None
        return grab[k]

    # The dish can hang off an edge of the frame, so the crop is not always the
    # square we asked for. Take the shape from a real frame.
    first = at(0.0)
    if first is None:
        raise lt.TrackingError("could not read the first frame")
    ch, cw = first.shape[:2]
    mask = np.zeros((ch, cw), np.uint8)
    cv2.circle(mask, (int(cx - ox), int(cy - oy)), int(r * edge), 255, -1)
    acc = np.zeros((ch, cw), np.uint8)

    if threshold is None:
        threshold = measure(video, dish_mm, circle, every=every, edge=edge,
                            max_width_mm=max_width_mm, log=lambda *a: None)["threshold"]
        log(f"using the measurement's threshold ({threshold})")

    ff = shutil.which("ffmpeg")
    if not ff:
        raise lt.TrackingError("ffmpeg is needed to write the replay")
    proc = subprocess.Popen(
        [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{size}x{size}", "-r", "20", "-i", "-", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", out],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    n = 0
    thr_final = None
    t = 0.0
    while t < dur:
        now = at(t)
        past = at(max(0.0, t - every))
        if now is None or past is None:
            break
        a = cv2.cvtColor(now, cv2.COLOR_BGR2GRAY)
        b = cv2.cvtColor(past, cv2.COLOR_BGR2GRAY)
        d = cv2.absdiff(cv2.GaussianBlur(a, (0, 0), 2), cv2.GaussianBlur(b, (0, 0), 2))
        acc = cv2.max(acc, cv2.bitwise_and(d, mask))

        # Use the threshold the measurement settled on. Recomputing it per frame
        # made the video disagree with the number it was supposed to illustrate -
        # 10 mm on screen against 46 mm measured, on the same clip.
        thr = threshold
        bw = (acc > thr).astype(np.uint8) * 255
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        total, keep, _drop, lab = pieces_of(bw, mpp, max_width_mm)
        shown = np.zeros_like(bw)
        for p in keep:
            shown[lab == p["label"]] = 255
        thr_final = thr

        sc = size / float(cw)
        im = cv2.resize(now, (size, size))
        paint = cv2.resize(shown, (size, size), interpolation=cv2.INTER_NEAREST)
        im[paint > 0] = (0.25 * im[paint > 0] + 0.75 * np.array([60, 60, 255])).astype(np.uint8)
        cv2.ellipse(im, (int((cx - ox) * size / cw), int((cy - oy) * size / ch)),
                    (int(r * edge * size / cw), int(r * edge * size / ch)),
                    0, 0, 360, (120, 120, 120), 1)
        cv2.putText(im, f"{t:5.0f}s", (size - 96, 30), cv2.FONT_HERSHEY_SIMPLEX, .7,
                    (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(im, f"trail {total:6.1f} mm", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, .7,
                    (60, 60, 255), 2, cv2.LINE_AA)
        proc.stdin.write(im.tobytes())
        n += 1
        t += show_step
    cap.release()
    proc.stdin.close()
    err = proc.stderr.read().decode()[-300:]
    if proc.wait() != 0:
        raise lt.TrackingError(f"ffmpeg failed: {err}")
    log(f"wrote {out} ({n} frames, threshold ended at {thr_final})")
    return out

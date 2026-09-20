"""Path length per animal for a plate holding several larvae.

tptrack.measure_each reports the N longest trajectories, which is not the same
thing: with five animals it returns eleven fragments, so some of the five are
pieces of one larva and some animals are missing entirely.

What breaks identity here is crossings. Two larvae meet, the detector sees one
blob, and the linker afterwards has no way to know which came out of which side.
trackpy ships a predictor for exactly this: carry each track's velocity forward
and match against where it should be, not where it was. That plus sampling often
enough that a larva moves less than its own body between frames is what makes
the crossings survivable.

    .venv-track/bin/python multitrack.py clips/dish4_5min.mp4 \
        --circle 498,702,306 --dish-mm 100 --larvae 5 --overlay out.png
"""
import math
import os
import sys

import cv2
import numpy as np

import tptrack

EVERY_S = 1.0        # a larva covers ~1.5mm in this, well under its own length
SEARCH_MM_S = 4.0
MEMORY_S = 20.0      # in seconds, so it means the same at any sample rate
MIN_SPAN_S = 30.0    # a real animal is visible for longer than this
CACHE = os.environ.get("MULTITRACK_CACHE", "")


def sequence(video, circle, every=EVERY_S, log=print):
    """Sampled, cropped frames. Decoding straight through beats seeking 300 times."""
    cx, cy, r = circle
    key = os.path.join(CACHE, "mt_%s_%d_%.2f.npy" % (
        os.path.basename(video).split(".")[0], int(cx), every)) if CACHE else ""
    if key and os.path.isfile(key):
        log("using cached frames")
        return np.load(key)
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps * every)))
    out, i = [], 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, f = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            out.append(tptrack._crop(g, int(cx - r), int(cy - r), int(2 * r)))
        i += 1
    cap.release()
    seq = np.stack(out)
    if key:
        np.save(key, seq)
    return seq


def track(video, circle, larvae, dish_mm=100.0, every=EVERY_S, log=print):
    """Per-animal trajectories, longest-lived first."""
    import trackpy as tp
    import trackpy.predict
    tp.quiet()

    frames = sequence(video, circle, every, log)
    r = circle[2]
    mpp = dish_mm / (2.0 * r)
    log("%d frames at %.2fs, %.3f mm/px" % (len(frames), every, mpp))

    bg = np.median(frames, axis=0).astype(np.uint8)
    diffs = np.stack([cv2.absdiff(f, bg) for f in frames])

    diam = tptrack.feature_px(2 * r)
    probe = tp.batch(diffs, diam, minmass=1)
    if probe.empty:
        raise tptrack.NoLarva("nothing detected in that plate")
    # Keep roughly the expected number of animals per frame, rather than a fixed
    # percentile: too generous and crossings get swamped by debris.
    want = larvae * len(frames)
    minmass = float(np.percentile(probe["mass"],
                                  100.0 * max(0.0, 1.0 - want / float(len(probe)))))
    f = probe[probe["mass"] >= minmass].reset_index(drop=True)
    log("detector %dpx, minmass %.0f, %.1f features/frame"
        % (diam, minmass, len(f) / len(frames)))

    search = max(3, int(SEARCH_MM_S * every / mpp))
    # Carry velocity forward: through a crossing, where a track *should* be
    # separates the two animals when where it *was* cannot.
    pred = tp.predict.NearestVelocityPredict()
    linked = pred.link_df(f, search_range=search,
                          memory=int(round(MEMORY_S / every)),
                          adaptive_stop=max(2.0, search / 4.0),
                          adaptive_step=0.9).reset_index(drop=True)

    out = []
    for pid, g in linked.groupby("particle"):
        g = g.sort_values("frame")
        t = g["frame"].to_numpy() * every
        xy = np.column_stack([g["x"].to_numpy(), g["y"].to_numpy()])
        if t[-1] - t[0] < MIN_SPAN_S:
            continue
        if np.median(np.hypot(xy[:, 0] - r, xy[:, 1] - r)) > tptrack.RIM_FRAC * r:
            continue                      # glare on the wall, not an animal
        out.append((t, xy))
    out.sort(key=lambda p: -(p[0][-1] - p[0][0]))
    log("%d track(s) lasting >=%.0fs" % (len(out), MIN_SPAN_S))
    return out, mpp


def measure(video, circle, larvae, dish_mm=100.0, every=EVERY_S, log=print):
    tracks, mpp = track(video, circle, larvae, dish_mm, every, log)
    rows = []
    for t, xy in tracks[:larvae]:
        mm = float(np.hypot(*np.diff(xy, axis=0).T).sum()) * mpp
        rows.append((mm, t[0], t[-1], len(t)))
    for i, (mm, t0, t1, n) in enumerate(rows, 1):
        log("  larva %d: %6.1f mm   %5.1fs-%5.1fs  %d points" % (i, mm, t0, t1, n))
    if len(tracks) > larvae:
        log("  (%d further track(s) not in the top %d)" % (len(tracks) - larvae, larvae))
    return rows, tracks, mpp


def overlay(video, circle, tracks, larvae, out):
    cx, cy, r = circle
    cap = cv2.VideoCapture(video)
    ok, f = cap.read()
    cap.release()
    img = cv2.merge([tptrack._crop(c, int(cx - r), int(cy - r), int(2 * r))
                     for c in cv2.split(f)])
    cols = [(0, 0, 255), (0, 200, 255), (0, 255, 0), (255, 0, 255), (255, 200, 0)]
    for i, (t, xy) in enumerate(tracks[:larvae]):
        cv2.polylines(img, [xy.astype(np.int32)], False, cols[i % len(cols)], 2)
        cv2.circle(img, tuple(xy[0].astype(int)), 6, cols[i % len(cols)], -1)
    cv2.imwrite(out, img)


def self_check():
    """Five straight, well-separated synthetic tracks must come back as five."""
    r, mpp = 300.0, 100.0 / 600.0
    tracks = []
    for k in range(5):
        t = np.arange(60) * EVERY_S
        xy = np.column_stack([np.full(60, 80.0 + k * 90), np.linspace(80, 500, 60)])
        tracks.append((t, xy))
    lens = [float(np.hypot(*np.diff(xy, axis=0).T).sum()) * mpp for _, xy in tracks]
    assert all(abs(l - lens[0]) < 1e-6 for l in lens), lens
    assert abs(lens[0] - 420 * mpp) < 1e-6, lens[0]
    # the rim gate must drop a track that sits out on the wall
    wall = (np.arange(60) * EVERY_S,
            np.column_stack([r + 0.98 * r * np.cos(np.linspace(0, 1, 60)),
                             r + 0.98 * r * np.sin(np.linspace(0, 1, 60))]))
    rad = np.median(np.hypot(wall[1][:, 0] - r, wall[1][:, 1] - r))
    assert rad > tptrack.RIM_FRAC * r
    print("self-check ok (5 tracks, %.1f mm each; rim gate fires at %.0f px)"
          % (lens[0], rad))


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
        raise SystemExit
    video = sys.argv[1]
    circle = tuple(float(v) for v in sys.argv[sys.argv.index("--circle") + 1].split(","))
    dish = float(sys.argv[sys.argv.index("--dish-mm") + 1]) if "--dish-mm" in sys.argv else 100.0
    n = int(sys.argv[sys.argv.index("--larvae") + 1]) if "--larvae" in sys.argv else 5
    every = float(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else EVERY_S
    rows, tracks, mpp = measure(video, circle, n, dish, every)
    if "--overlay" in sys.argv:
        o = sys.argv[sys.argv.index("--overlay") + 1]
        overlay(video, circle, tracks, n, o)
        print("wrote", o)

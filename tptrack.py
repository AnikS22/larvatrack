"""Path length of a single larva, using trackpy for detection and linking.

Hand-rolled blob detection kept locking onto the agar specks, which are the same
size and shape as a larva.  trackpy is a mature particle-tracking library that
does the same job properly: band-pass filtering, sub-pixel centroids and a
proper linker.  It finds clean trajectories here - but it breaks one larva into
several of them, because the animal fades out whenever it presses against the
dish wall or crawls over a speck.

A solo dish holds exactly one larva, so every real trajectory in it belongs to
the same animal.  This chains them back together in time order and bridges the
gaps: round the wall when the animal vanished against it, straight otherwise.

    python tptrack.py clips/dish3_5min.mp4 --dish-mm 100 --circle 568,549,297

Needs trackpy, which is not in the main environment - use .venv-track/bin/python.
"""
import math
import sys

import cv2
import numpy as np

import trail

EVERY_S = 2.0        # sampling interval; the linker's search range scales with it
DIAMETER = 13        # odd, and a bit larger than the larva in px at working scale
MASS_PCT = 99.5      # keep only the brightest features - the rest are agar specks
MEMORY = 20          # frames a trajectory may vanish for and still be continued
SEARCH_MM_S = 4.0    # generous vs the ~1.5mm/s crawl, to survive a speck crossing
MIN_DETECTIONS = 10  # shorter trajectories are specks flickering, not an animal
MAX_GAP_S = 30.0     # past this a bridge is a guess, not a measurement
RIM_FRAC = 0.95      # a trajectory living out here is the dish wall, not a larva


def _sample(video, circle, every=EVERY_S):
    """Frames cropped square to the dish, greyscale, one every `every` seconds."""
    cx, cy, r = circle
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit("cannot open %s" % video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ox, oy, side = int(cx - r), int(cy - r), int(2 * r)
    frames, t = [], 0.0
    while True:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(f[oy:oy + side, ox:ox + side], cv2.COLOR_BGR2GRAY))
        t += every
    cap.release()
    return frames, fps


def _moving(frames):
    """Per-pixel median over the clip removes the agar; what is left moved."""
    bg = np.median(np.stack(frames), axis=0).astype(np.uint8)
    return [cv2.absdiff(f, bg) for f in frames]


def trajectories(video, circle, every=EVERY_S, mm_per_px=None, log=print):
    """Linked trajectories, as a list of (times_s, xy_px) arrays, longest first."""
    import trackpy as tp
    tp.quiet()

    frames, _ = _sample(video, circle, every)
    if not frames:
        raise SystemExit("no frames read from %s" % video)
    log("%d frames at %.1fs spacing" % (len(frames), every))

    diffs = _moving(frames)
    # Two passes: the first learns what a bright feature looks like in this dish,
    # so the mass cut adapts to the lighting instead of being a magic number.
    probe = tp.batch(np.stack(diffs), DIAMETER, minmass=1)
    if probe.empty:
        return []
    minmass = float(np.percentile(probe["mass"], MASS_PCT))
    log("minmass %.0f (p%.1f of observed)" % (minmass, MASS_PCT))

    f = probe[probe["mass"] >= minmass].reset_index(drop=True)
    log("%.1f features per frame" % (len(f) / len(frames)))

    mpp = mm_per_px if mm_per_px else 1.0
    search = max(2, int((SEARCH_MM_S * every) / mpp))
    # adaptive_stop lets trackpy shrink the search range where features crowd,
    # instead of giving up with SubnetOversizeException.
    linked = tp.link(f, search_range=search, memory=MEMORY,
                     adaptive_stop=max(2.0, search / 4.0),
                     adaptive_step=0.9).reset_index(drop=True)

    r_px = circle[2]
    out = []
    for pid, g in linked.groupby("particle"):
        if len(g) < MIN_DETECTIONS:
            continue
        g = g.sort_values("frame")
        xy = np.column_stack([g["x"].to_numpy(), g["y"].to_numpy()])
        # Frames are cropped square to the dish, so its centre is (r, r).  Glare
        # and the lid rim throw features that sit out on the wall all clip long;
        # a larva that truly wall-follows still comes back in, so gate on median.
        if np.median(np.hypot(xy[:, 0] - r_px, xy[:, 1] - r_px)) > RIM_FRAC * r_px:
            continue
        out.append((g["frame"].to_numpy() * every, xy))
    out.sort(key=lambda p: -len(p[0]))
    log("%d trajectories of >=%d detections" % (len(out), MIN_DETECTIONS))
    return out


def _drop_overlaps(trs):
    """One larva cannot be in two places, so when two trajectories cover the same
    stretch of time the shorter one is a speck.  Keep the longer."""
    kept = []
    for times, xy in sorted(trs, key=lambda p: -len(p[0])):
        a0, a1 = times[0], times[-1]
        if any(not (a1 < b0 or a0 > b1)
               for b0, b1 in ((t[0], t[-1]) for t, _ in kept)):
            continue
        kept.append((times, xy))
    kept.sort(key=lambda p: p[0][0])
    return kept


def _attribute(kept):
    """The trajectories belonging to the animal: the one we followed longest,
    plus neighbours near enough in time to be the same creature.

    Indices, not the tuples themselves - these hold numpy arrays, so == is
    elementwise and list.index / "in" raise on them.
    """
    i = max(range(len(kept)), key=lambda k: len(kept[k][0]))
    group, lo, hi = [kept[i]], i, i
    for j in range(i - 1, -1, -1):
        if group[0][0][0] - kept[j][0][-1] > MAX_GAP_S:
            break
        group.insert(0, kept[j])
        lo = j
    for j in range(i + 1, len(kept)):
        if kept[j][0][0] - group[-1][0][-1] > MAX_GAP_S:
            break
        group.append(kept[j])
        hi = j
    return group, lo, hi


def chain(trs, circle, mpp):
    """Total mm walked: within each trajectory, plus the gaps between them.

    A gap bridges round the wall when the animal disappeared against it, and in a
    straight line otherwise.  Both are lower bounds - a straight line is the
    shortest route between two points, and an arc the shortest along the rim.
    """
    kept = _drop_overlaps(trs)
    if not kept:
        return 0.0, 0.0, []
    cx, cy, r = circle
    centre = (r, r)          # frames are cropped square to the dish
    seen = bridged = 0.0
    segs = []
    for times, xy in kept:
        seen += float(np.hypot(*np.diff(xy, axis=0).T).sum()) * mpp
    for (t0, a), (t1, b) in zip(kept, kept[1:]):
        gap_s = t1[0] - t0[-1]
        if gap_s <= 0:
            continue
        if gap_s > MAX_GAP_S:
            # Too long to attribute: the next fragment may not even be the same
            # animal.  Counting the seen stretches only is an honest undercount;
            # inventing the join is how a speck gets welded onto a real path.
            segs.append((t0[-1], t1[0], 0.0, "gap-too-long"))
            continue
        arc = trail.arc_bridge(a[-1], b[0], centre, r, mpp)
        straight = math.hypot(*(b[0] - a[-1])) * mpp
        d = arc if arc is not None else straight
        # However it got there, it cannot have crawled further than a larva can.
        d = min(d, trail.WALL_SPEED_MM_S * gap_s)
        bridged += d
        segs.append((t0[-1], t1[0], d, "arc" if arc is not None else "straight"))
    return seen, bridged, segs


def measure(video, dish_mm, circle, every=EVERY_S, log=print):
    """Path length in mm.

    Reports the longest single trajectory as the headline figure, because that
    is the stretch we actually watched one animal walk, and lists the remaining
    fragments separately.  Chaining everything together was tried and is worse:
    a fragment that is really glare on the lid gets welded onto the larva's path
    and inflates the total by a third.  A fragment only joins the headline when
    the gap to it is short enough to attribute (see MAX_GAP_S).
    """
    mpp = dish_mm / (2.0 * circle[2])
    trs = trajectories(video, circle, every, mpp, log)
    if not trs:
        log("no trajectories found")
        return 0.0, 0.0, 0.0
    kept = _drop_overlaps(trs)
    group, lo, hi = _attribute(kept)

    seen, bridged, segs = chain(group, circle, mpp)
    for t0, t1, d, how in segs:
        log("  bridge %5.1fs-%5.1fs  %5.1f mm  %s" % (t0, t1, d, how))
    total = seen + bridged
    span = group[-1][0][-1] - group[0][0][0]
    log("tracked %.0fs of the clip in %d piece(s)" % (span, len(group)))
    log("PATH %.1f mm  (%.1f seen + %.1f bridged)" % (total, seen, bridged))
    others = [p for k, p in enumerate(kept) if not lo <= k <= hi]
    if others:
        log("%d other fragment(s) not attributed to this animal:" % len(others))
        for t, xy in others:
            log("  %5.1fs-%5.1fs  %.1f mm"
                % (t[0], t[-1], float(np.hypot(*np.diff(xy, axis=0).T).sum()) * mpp))
    return total, seen, bridged


def overlay(video, circle, out, every=EVERY_S, mm_per_px=None):
    """First frame with every kept trajectory drawn, so the path can be eyeballed."""
    cx, cy, r = circle
    cap = cv2.VideoCapture(video)
    ok, f = cap.read()
    cap.release()
    if not ok:
        return
    img = f[int(cy - r):int(cy + r), int(cx - r):int(cx + r)].copy()
    kept = _drop_overlaps(trajectories(video, circle, every, mm_per_px,
                                       log=lambda *a: None))
    if not kept:
        cv2.imwrite(out, img)
        return
    _, lo, hi = _attribute(kept)
    for i, (_, xy) in enumerate(kept):
        measured = lo <= i <= hi
        # red is the path that was measured; grey is a fragment left out of it
        col = (0, 0, 255) if measured else (150, 150, 150)
        cv2.polylines(img, [xy.astype(np.int32)], False, col, 2 if measured else 1)
    cv2.imwrite(out, img)


def self_check():
    """A synthetic larva on a known path, broken into fragments the way the real
    detector breaks.  A gap against the wall is bridged round it and should come
    back close to truth; a gap mid-dish falls back to a straight chord, which is
    a lower bound by construction - assert it behaves as one rather than pretend
    it is accurate."""
    r, mpp = 300.0, 100.0 / 600.0
    centre = (r, r, r)

    def arc_at(radius, n=60):
        a = np.linspace(0, math.pi / 2, n)
        return np.column_stack([r + radius * np.cos(a), r + radius * np.sin(a)])

    def length(xy):
        return float(np.hypot(*np.diff(xy, axis=0).T).sum()) * mpp

    # Unbroken: chaining must not add or lose anything.
    xy = arc_at(200)
    whole = [(np.arange(60) * EVERY_S, xy)]
    seen, bridged, _ = chain(whole, centre, mpp)
    assert abs(seen + bridged - length(xy)) < 1e-6, (seen, bridged)
    assert bridged == 0.0

    # Gap against the wall (r=280 is outside the 0.8*r rim band): bridged as an
    # arc, so the curve is followed and the total lands close to truth.
    wall = arc_at(280)
    parts = [(np.arange(0, 25) * EVERY_S, wall[:25]),
             (np.arange(35, 60) * EVERY_S, wall[35:])]
    s_, b_, segs = chain(parts, centre, mpp)
    assert segs and segs[0][3] == "arc", segs
    err = abs((s_ + b_) - length(wall)) / length(wall)
    assert err < 0.05, "wall gap: %.1f vs %.1f (%.0f%%)" % (s_ + b_, length(wall), err * 100)

    # Gap mid-dish: straight chord, a lower bound - under truth but not by half.
    parts = [(np.arange(0, 25) * EVERY_S, xy[:25]),
             (np.arange(35, 60) * EVERY_S, xy[35:])]
    s_, b_, segs = chain(parts, centre, mpp)
    assert segs and segs[0][3] == "straight", segs
    total = s_ + b_
    assert 0.75 * length(xy) < total <= length(xy) + 1e-6, (total, length(xy))

    # An overlapping speck trajectory must be discarded, not added on.
    speck = (np.arange(5, 20) * EVERY_S, xy[5:20] + 50)
    assert abs(sum(chain(whole + [speck], centre, mpp)[:2]) - length(xy)) < 1e-6

    # A gap longer than MAX_GAP_S must not be bridged at all.
    long_gap = [(np.arange(0, 25) * EVERY_S, xy[:25]),
                (np.arange(25) * EVERY_S + 25 * EVERY_S + MAX_GAP_S + 10, xy[35:])]
    s_, b_, segs = chain(long_gap, centre, mpp)
    assert b_ == 0.0 and segs[0][3] == "gap-too-long", (b_, segs)

    # The speed cap must stop a long gap inventing an impossible crawl.
    far = [(np.array([0.0]), np.array([[20.0, 300.0]])),
           (np.array([4.0]), np.array([[580.0, 300.0]]))]
    assert chain(far, centre, mpp)[1] <= trail.WALL_SPEED_MM_S * 4.0 + 1e-9

    print("self-check ok (wall gap within %.1f%%, mid-dish chord is a lower bound)"
          % (err * 100))


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
        raise SystemExit
    video = sys.argv[1]
    dish = float(sys.argv[sys.argv.index("--dish-mm") + 1])
    circle = tuple(float(v) for v in sys.argv[sys.argv.index("--circle") + 1].split(","))
    measure(video, dish, circle)
    if "--overlay" in sys.argv:
        o = sys.argv[sys.argv.index("--overlay") + 1]
        overlay(video, circle, o, mm_per_px=dish / (2.0 * circle[2]))
        print("wrote", o)

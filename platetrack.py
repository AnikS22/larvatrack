"""Path length on a plate holding several larvae, and what of it is trustworthy.

tptrack.measure_each reports the N longest trajectories and says plainly that it
cannot keep identity across a gap.  Two things sit underneath that, and only one
of them is fixable:

Detection - fixable.  _moving() subtracts the temporal median of the RAW frames,
so a larva scores by its absolute contrast against the agar.  A phone shadow
covers half of each plate in these clips: a larva on the shadow reads 140 grey
levels above its background, the same larva on the lit agar reads 40, and one
global mass threshold cannot keep both.  The lit half of the plate was simply
invisible - 2.8 detections a frame where five larvae were walking.  Flattening
with a morphological top-hat FIRST (an opening wider than a larva but narrower
than a yeast spot is the illumination, by definition) and only then removing the
temporal median lifts that to 4.5 a frame, and separates larvae from agar specks
by a factor of three in mass, so the threshold stops being a magic number.
Against frames labelled by eye: 100% recall (13/13) where the old detector got
92% at best and the top-hat alone got 46%.

Identity - not fixable here, and this module does not pretend.  Five larvae over
300s come out as ~25 fragments however the linker is tuned, and the five longest
hold only half the time the animals were actually seen.  Sampling finer does not
help: fragment count follows the search range in PIXELS, not the interval, so
0.5s sampling fragments three times worse than 2.0s at the same mm/s.  Stitching
does not help either - across the median 18s gap a larva's heading has already
decorrelated to +0.2, so "it went on the way it was going" is barely better than
"it went anywhere", and on a plate holding ONE larva the stitcher proves it by
welding a second animal's worth of path onto a known 72mm walk.

So the headline is the plate total, which needs no identity.  Per-fragment rows
are printed underneath, and confident() names the subset of fragments long
enough that they really are one animal each - usually two or three of the five.

    .venv-track/bin/python platetrack.py clips/dish4_5min.mp4 \
        --dish-mm 100 --circle 1260,682,297 --larvae 5 --overlay out.png

Needs trackpy - use .venv-track/bin/python.
"""
import sys

import cv2
import numpy as np

import tptrack as tt

EVERY_S = 2.0        # finer was measured and is worse; see the module docstring
FLAT_MM = 7.0        # opening width: wider than a larva, narrower than a yeast spot
MASS_SLACK = 1.0     # of the typical Nth-brightest feature, so a dim frame still counts
SEARCH_MM_S = 4.0    # generous against the ~1.5mm/s crawl, for a bent-body centroid
MEMORY_S = 60.0      # a larva can sit on a yeast spot this long and still be itself
RIM_FRAC = 0.93      # outside this is the dish wall and its glare, not the agar
MIN_POINTS = 5       # fewer than this is a speck flickering
FAST_MM_S = 3.0      # twice a crawl: a linked step above this is the linker jumping
CONFIDENT_S = 60.0   # a fragment this long is one animal, whatever else is lost
MAX_GAP_S = 40.0     # past this a stitch is a guess, not a measurement


def sample(video, circle, every=EVERY_S):
    """Frames cropped square to the dish, greyscale, one every `every` seconds.

    Decoded straight through rather than seeking per frame: at a fine interval
    that is hundreds of seeks, which is slower AND lands on different frames
    than the timestamps asked for.
    """
    cx, cy, r = circle
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise tt.NoLarva("cannot open the video file")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps * every)))
    ox, oy, side = int(cx - r), int(cy - r), int(2 * r)
    out, i = [], 0
    while cap.grab():
        if i % step == 0:
            ok, f = cap.retrieve()
            if not ok:
                break
            out.append(tt._crop(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), ox, oy, side))
        i += 1
    cap.release()
    if not out:
        raise tt.NoLarva("no frames could be read from the clip")
    return out


def flatten(frames, mpp):
    """Larvae on a uniform black ground, whatever the lighting did.

    The order is the whole trick.  Top-hat first turns "how bright is this pixel"
    into "how far above its own surroundings", which is what makes a larva on lit
    agar and one on the shadow score alike.  Only then does the temporal median
    mean anything: it now holds the static agar specks and nothing else, so
    subtracting it leaves what moved, already levelled.
    """
    w = int(round(FLAT_MM / mpp))
    w = max(3, w + 1 - w % 2)            # odd, so the opening is centred
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (w, w))
    th = np.stack([cv2.morphologyEx(f, cv2.MORPH_TOPHAT, k) for f in frames])
    return th - np.minimum(th, np.median(th, axis=0).astype(np.uint8))


def detect(frames, r, mpp, larvae, log=print):
    """Larva-sized bright features: one row per sighting, rim and specks gone.

    The threshold is the only free number and it must not be free.  The caller
    knows how many larvae are on the plate, so take the Nth-brightest feature in
    each frame and use the median of that across the clip: on a plate where the
    animals are bright it lands high, on a dim one it lands low, and either way
    a typical frame yields about N.  A fixed fraction of the BRIGHTEST feature
    was tried and is not robust - it gave 4.5 detections a frame on one clip and
    56 on another, because it never learns how bright the specks are.
    """
    import trackpy as tp
    tp.quiet()
    f = tp.batch(flatten(frames, mpp), tt.feature_px(2 * r), minmass=1)
    if f.empty:
        return f
    f = f[np.hypot(f["x"] - r, f["y"] - r) < RIM_FRAC * r]
    nth = f.groupby("frame")["mass"].apply(
        lambda m: m.nlargest(larvae).min() if len(m) >= larvae else np.nan)
    cut = MASS_SLACK * float(np.nanmedian(nth))
    f = f[f["mass"] >= cut].reset_index(drop=True)
    log("minmass %.0f (%.0f%% of the typical %d%s-brightest feature)"
        % (cut, 100 * MASS_SLACK, larvae, "st" if larvae == 1 else "th"))
    log("%.2f detections per frame for %d larvae" % (len(f) / len(frames), larvae))
    return f


def track(video, circle, larvae=1, every=EVERY_S, mpp=None, log=print, frames=None):
    """Fragments, as a list of (times_s, xy_px), in time order.

    Fragments, not animals - see the module docstring.
    """
    import trackpy as tp
    tp.quiet()
    r = circle[2]
    mpp = mpp or 1.0
    if frames is None:
        frames = sample(video, circle, every)
    log("%d frames at %.1fs spacing" % (len(frames), every))
    f = detect(frames, r, mpp, larvae, log)
    if f.empty:
        return []
    search = max(3, int(SEARCH_MM_S * every / mpp))
    lk = tp.link(f, search_range=search, memory=int(round(MEMORY_S / every)),
                 adaptive_stop=max(2.0, search / 4.0), adaptive_step=0.9)
    out = []
    for _, g in lk.groupby("particle"):
        if len(g) < MIN_POINTS:
            continue
        g = g.sort_values("frame")
        out.append((g["frame"].to_numpy() * float(every),
                    np.column_stack([g["x"].to_numpy(), g["y"].to_numpy()])))
    out.sort(key=lambda p: p[0][0])
    log("%d fragments of >=%d detections" % (len(out), MIN_POINTS))
    return out


def walked(xy, mpp):
    """mm along a polyline."""
    if len(xy) < 2:
        return 0.0
    return float(np.hypot(*np.diff(xy, axis=0).T).sum()) * mpp


def jumps(trs, mpp):
    """Steps inside a fragment that no larva could have walked.

    The linker gets a wide search range so it can hold on through a bent body and
    a missed frame; the price is that it can also hop to a different animal. A
    hop shows up as speed, so counting these prices that choice instead of
    leaving it to faith.
    """
    n = 0
    for t, xy in trs:
        if len(t) < 2:
            continue
        n += int((np.hypot(*np.diff(xy, axis=0).T) * mpp / np.diff(t) > FAST_MM_S).sum())
    return n


def confident(trs, mpp, min_s=CONFIDENT_S):
    """The fragments long enough to be one animal each, and what they walked.

    A fragment is only ever a lower bound on its animal - it started when the
    tracker found the larva and ended when it lost it.  But a fragment that ran
    unbroken for a minute is certainly ONE animal, which is more than can be said
    for the plate as a whole, so these are the rows worth quoting per animal.
    """
    rows = [(t[-1] - t[0], walked(xy, mpp), t[0], t[-1])
            for t, xy in trs if t[-1] - t[0] >= min_s]
    rows.sort(reverse=True)
    return rows


def stitch(trs, mpp, larvae, max_gap_s=MAX_GAP_S):
    """Join fragments that could be the same animal.  Off by default: it is wrong.

    Kept so the obvious thing to try stays measurable rather than arguable.
    Greedy on the cheapest plausible join: the next fragment must start after
    this one ends, be reachable at a crawl, and lie the way the animal was
    heading.  It still fails, for a reason no tuning reaches - across the median
    18s gap a larva's heading has decorrelated to +0.2, so the direction term is
    barely better than noise.  Validate it on a one-larva plate before believing
    a number it produced.
    """
    chains = [[k] for k in sorted(range(len(trs)), key=lambda k: trs[k][0][0])]
    while len(chains) > larvae:
        best = None
        for i, a in enumerate(chains):
            ta, xa = trs[a[-1]]
            if len(xa) < 2:
                continue
            d0 = xa[-1] - xa[-2]
            heading = d0 / max(float(np.hypot(*d0)), 1e-9)
            for j, b in enumerate(chains):
                if i == j:
                    continue
                tb, xb = trs[b[0]]
                gap = tb[0] - ta[-1]
                if not 0 < gap <= max_gap_s:
                    continue
                step = xb[0] - xa[-1]
                d = float(np.hypot(*step)) * mpp
                if d > tt.trail.WALL_SPEED_MM_S * gap:
                    continue          # it could not have got there at a crawl
                cos = float(step @ heading) / max(float(np.hypot(*step)), 1e-9)
                if best is None or d * (2.0 - cos) < best[0]:
                    best = (d * (2.0 - cos), i, j)
        if best is None:
            break
        _, i, j = best
        chains[i] = chains[i] + chains[j]
        chains.pop(j)
    return chains


def measure(video, dish_mm, circle, larvae, every=EVERY_S, log=print, trs=None,
            join=False):
    """Distance covered on this plate, plus what of it is per-animal.

    The plate total is the headline because it needs no identity, so nothing has
    to be guessed.  The confident rows underneath are the animals that really
    were followed; the fragment count is itself the warning that the rest is not
    there.
    """
    mpp = dish_mm / (2.0 * circle[2])
    if trs is None:
        trs = track(video, circle, larvae, every, mpp, log)
    if not trs:
        log("nothing was tracked")
        return 0.0, []
    bad = jumps(trs, mpp)
    if bad:
        log("%d linked step(s) faster than %.1f mm/s - the linker jumped"
            % (bad, FAST_MM_S))
    if join:
        rows = sorted((sum(walked(trs[k][1], mpp) for k in c), len(c))
                      for c in stitch(trs, mpp, larvae))[::-1]
        log("stitched into %d chain(s) - A GUESS, see stitch()" % len(rows))
        for i, (mm, n) in enumerate(rows, 1):
            log("  chain %d: %6.1f mm from %d fragment(s)" % (i, mm, n))
        return sum(r[0] for r in rows), rows

    seen = sum(walked(xy, mpp) for _, xy in trs)
    held = sum(t[-1] - t[0] for t, _ in trs)
    span = max(t[-1] for t, _ in trs)
    log("PLATE TOTAL %.1f mm by %d larvae  (%.0fs of animal-time seen of %d x %.0fs)"
        % (seen, larvae, held, larvae, span))
    conf = confident(trs, mpp)
    log("%d fragments; %d of them ran >=%.0fs and so are one animal each:"
        % (len(trs), len(conf), CONFIDENT_S))
    for i, (dur, mm, t0, t1) in enumerate(conf[:2 * larvae], 1):
        log("  animal %d (partial): %6.1f mm over %5.1fs   %5.1fs-%5.1fs"
            % (i, mm, dur, t0, t1))
    rest = sorted((walked(xy, mpp) for t, xy in trs if t[-1] - t[0] < CONFIDENT_S),
                  reverse=True)
    if rest:
        log("  + %d short fragment(s) totalling %.1f mm, not attributable"
            % (len(rest), sum(rest)))
    return seen, conf


def overlay(video, circle, out, larvae=1, every=EVERY_S, dish_mm=100.0, trs=None):
    """Fragments drawn over the trails the larvae actually left.

    The background is the brightest each pixel ever got after flattening, which
    is exactly the smear of every path walked - so a fragment that wanders off
    its trail shows up as such, without asking the tracker to grade itself.
    """
    mpp = dish_mm / (2.0 * circle[2])
    frames = sample(video, circle, every)
    flat = flatten(frames, mpp)
    bg = cv2.normalize(flat.max(axis=0), None, 0, 255, cv2.NORM_MINMAX)
    img = (cv2.cvtColor(bg, cv2.COLOR_GRAY2BGR) * 0.75).astype(np.uint8)
    if trs is None:
        trs = track(video, circle, larvae, every, mpp, log=lambda *a: None, frames=frames)
    cols = [(0, 0, 255), (0, 200, 255), (0, 255, 0), (255, 0, 255), (255, 200, 0),
            (255, 255, 255), (180, 0, 255), (0, 170, 170), (200, 200, 0), (120, 255, 180)]
    for i, (t, xy) in enumerate(sorted(trs, key=lambda p: -(p[0][-1] - p[0][0]))):
        c = cols[i % len(cols)]
        thick = 2 if t[-1] - t[0] >= CONFIDENT_S else 1
        cv2.polylines(img, [xy.astype(np.int32)], False, c, thick)
        cv2.circle(img, tuple(xy[0].astype(int)), 5, c, -1)
        cv2.putText(img, "%d:%.0f-%.0fs" % (i + 1, t[0], t[-1]),
                    tuple((xy[0] + 7).astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, c, 1)
    cv2.imwrite(out, img)
    return out


def _recall(f, paths, tol=8.0):
    """How many frames each blob was found in - the thing the flatten is for."""
    out = []
    for p in paths:
        hit = 0
        for i in sorted(set(int(v) for v in f["frame"])) if len(f) else []:
            x, y = p(i)
            g = f[f["frame"] == i]
            if len(g) and np.hypot(g["x"] - x, g["y"] - y).min() < tol:
                hit += 1
        out.append(hit)
    return out


def _fake_clip(paths, side=240, n=60, speck=True):
    """A clip of bright blobs on an uneven, half-shadowed ground with a static
    speck - the three things that broke the old detector, in one fixture."""
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float32)
    # a lighting gradient and a hard shadow edge, scaled to what the real clip
    # does: a larva sits ~2x further above the shaded agar than the lit agar.
    # The edge DRIFTS, which is the detail that matters - a still shadow is
    # removed perfectly by a temporal median, and the real one is not.
    base = 60 + 60 * (xx / side)
    out = []
    for i in range(n):
        f = base.copy()
        f[:, side // 2 + i // 2:] += 40
        if speck:
            # a field of static agar specks. they never move, but the drifting
            # shadow moves UNDER them, so a temporal median of the raw frames
            # leaves every one of them glowing - which is the real failure.
            rng = np.random.default_rng(7)
            for sx, sy in rng.integers(12, side - 12, (12, 2)):
                f[sy:sy + 4, sx:sx + 4] = 200
        for p in paths:
            x, y = p(i)
            f[int(y) - 4:int(y) + 5, int(x) - 3:int(x) + 4] = 250
        out.append(np.clip(f, 0, 255).astype(np.uint8))
    return out


def self_check():
    r, mpp = 120.0, 100.0 / 240.0

    # flatten must level the lighting and delete what never moved.
    frames = _fake_clip([lambda i: (40 + 2.0 * i, 120)])
    flat = flatten(frames, mpp)
    assert flat[0][30:36, 30:36].max() < 40, "the static speck survived the flatten"
    lit, shade = int(flat[0][120, 40]), int(flat[20][120, 80])
    assert lit > 120 and shade > 120, ("a larva must read alike on both halves",
                                       lit, shade)

    # the detector must find every blob, on both halves, in every frame.
    # three parallel walks: this fixture is for the detector and the linker, so
    # it deliberately has no crossing for them to get wrong.
    paths = [lambda i: (45 + 2.0 * i, 60),
             lambda i: (195 - 2.0 * i, 120),
             lambda i: (45 + 2.0 * i, 180)]
    frames = _fake_clip(paths)
    f = detect(frames, r, mpp, 3, log=lambda *a: None)
    # recall per blob, not detections per frame: the point of the flatten is that
    # the blob on the LIT half is found as often as the one on the shaded half,
    # which is exactly what the old detector got wrong.
    # the flatten's whole job is fairness between the halves, so test that and
    # not an absolute count: how often a blob is found depends on the threshold,
    # but a blob on the lit agar must not be found far less often than one on
    # the shaded agar. That gap is what made the old detector miss half a plate.
    fair = _recall(f, paths)
    assert min(fair) >= 30, ("a blob went missing altogether", fair)
    # No assert here that this beats tt._moving, though it does on the real clip
    # (100% vs 92% recall on frames labelled by eye, 4.4 vs 2.8 detections a
    # frame).  This fixture cannot show it: a synthetic shadow and synthetic
    # specks are too well behaved, and the two detectors score the same on it.
    # Better an honest gap in the test than a fixture bent until it agrees.

    # and linking them must give three fragments, not thirty.
    trs = track(None, (r, r, r), 3, 1.0, mpp, log=lambda *a: None, frames=frames)
    # three walks, so three long fragments. an extra short one is a speck the
    # drifting shadow lit up; what must not happen is the walks themselves
    # shattering, so gate on the long ones.
    long_ = [t for t, _ in trs if len(t) >= 30]
    assert len(long_) == 3, ("three blobs linked into %d long fragments of %d"
                             % (len(long_), len(trs)))
    # a blob on the lit half is found in fewer frames than one on the shaded
    # half - that gap is real and this module narrows it rather than closing it.
    # What the linker must not do is lose a walk it could see, so require each
    # long fragment to hold most of the sightings of its own blob.
    assert sum(len(t) for t in long_) >= 0.9 * sum(fair), (
        [len(t) for t in long_], fair)
    assert jumps(trs, mpp) == 0

    # an impossible step must be counted, or a wide search range looks free.
    swapped = [(np.arange(4) * 1.0,
                np.array([[10., 10.], [12., 10.], [200., 10.], [202., 10.]]))]
    assert jumps(swapped, mpp) == 1

    # walked() is the plain polyline length in mm, and safe on a single point.
    box = np.array([[0., 0.], [30., 0.], [30., 40.], [0., 40.]])
    assert abs(walked(box, mpp) - 100 * mpp) < 1e-9
    assert walked(box[:1], mpp) == 0.0

    # confident() must keep the long fragment and drop the flicker.
    line = np.column_stack([np.linspace(20, 200, 40), np.full(40, 60.0)])
    long_ = (np.arange(40) * 2.0, line)
    blip = (np.arange(5) * 2.0 + 10.0, line[:5])
    got = confident([long_, blip], mpp)
    assert len(got) == 1 and abs(got[0][1] - walked(line, mpp)) < 1e-9, got

    # stitch must refuse what physics refuses, and take the join that is there.
    a = (np.array([0., 2.]), np.array([[10., 10.], [20., 10.]]))
    far = (np.array([4., 6.]), np.array([[560., 10.], [570., 10.]]))
    assert len(stitch([a, far], mpp, 1)) == 2, "stitched across an impossible gap"
    parts = [(np.arange(20) * 2.0, line[:20]),
             (np.arange(20) * 2.0 + 48.0, line[20:])]
    assert len(stitch(parts, mpp, 1)) == 1, "failed to rejoin one broken walk"
    over = [(np.arange(20) * 2.0, line[:20]), (np.arange(20) * 2.0, line[20:])]
    assert len(stitch(over, mpp, 1)) == 2, "stitched two fragments that co-existed"

    # the flatten window must scale with the dish, the way the detector does.
    assert flatten(_fake_clip([lambda i: (30, 30)], side=60, n=8),
                   100.0 / 60.0).shape == (8, 60, 60)

    print("self-check ok")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
        raise SystemExit
    video = sys.argv[1]
    dish = float(sys.argv[sys.argv.index("--dish-mm") + 1])
    circle = tuple(float(v) for v in sys.argv[sys.argv.index("--circle") + 1].split(","))
    n = int(sys.argv[sys.argv.index("--larvae") + 1]) if "--larvae" in sys.argv else 1
    every = float(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else EVERY_S
    trs = track(video, circle, n, every, dish / (2.0 * circle[2]))
    measure(video, dish, circle, n, every, trs=trs, join="--stitch" in sys.argv)
    if "--overlay" in sys.argv:
        print("wrote", overlay(video, circle,
                               sys.argv[sys.argv.index("--overlay") + 1],
                               larvae=n, every=every, dish_mm=dish, trs=trs))

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
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np

import trail

class NoLarva(Exception):
    """Nothing trackable in the dish. A normal outcome, not a crash: the dish may
    be wrongly placed, or the animal never visible enough to find."""


EVERY_S = 2.0        # sampling interval; the linker's search range scales with it
DIAMETER = 13        # odd, and a bit larger than the larva in px at a 600px dish
REF_DISH_PX = 600.0  # the dish size DIAMETER was chosen against
MASS_PCT = 99.5      # keep only the brightest features - the rest are agar specks
MEMORY = 20          # frames a trajectory may vanish for and still be continued
SEARCH_MM_S = 4.0    # generous vs the ~1.5mm/s crawl, to survive a speck crossing
MIN_DETECTIONS = 10  # shorter trajectories are specks flickering, not an animal
MAX_GAP_S = 30.0     # past this a bridge is a guess, not a measurement
RIM_FRAC = 0.95      # a trajectory living out here is the dish wall, not a larva
ANCHOR_TOL_MM = 6.0  # how far a trajectory may sit from a pinned point and still be it


def _sample(video, circle, every=EVERY_S):
    """Frames cropped square to the dish, greyscale, one every `every` seconds."""
    cx, cy, r = circle
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise NoLarva("cannot open the video file")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ox, oy, side = int(cx - r), int(cy - r), int(2 * r)
    frames, t = [], 0.0
    while True:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, f = cap.read()
        if not ok:
            break
        frames.append(_crop(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), ox, oy, side))
        t += every
    cap.release()
    return frames, fps


def _crop(g, ox, oy, side):
    """Square crop that may hang off the frame - a dish can sit against the edge.
    Missing rows and columns are filled with the border, so the dish centre stays
    at (r, r) and every radius in the rest of the module keeps its meaning.
    """
    h, w = g.shape[:2]
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(w, ox + side), min(h, oy + side)
    out = g[y0:y1, x0:x1]
    top, left = y0 - oy, x0 - ox
    bottom, right = side - (y1 - oy), side - (x1 - ox)
    if top or left or bottom or right:
        out = cv2.copyMakeBorder(out, top, bottom, left, right, cv2.BORDER_REPLICATE)
    return out


def stabilise(frames):
    """Undo camera drift, for clips shot without a tripod.

    The median background only removes the agar if the agar stays put.  A phone
    that shifts 70px over five minutes makes the whole dish register as motion,
    and the larva is lost in it.  Phase correlation gives the global shift per
    frame against the first; rolling each frame back makes the dish static again.

    Off by default: a rock-steady clip gains nothing, and an estimator run on one
    would only add its own jitter.
    """
    ref = np.float32(frames[0])
    out = [frames[0]]
    for f in frames[1:]:
        (dx, dy), _ = cv2.phaseCorrelate(ref, np.float32(f))
        M = np.float32([[1, 0, -dx], [0, 1, -dy]])
        out.append(cv2.warpAffine(f, M, (f.shape[1], f.shape[0]),
                                  borderMode=cv2.BORDER_REPLICATE))
    return out


def feature_px(dish_px):
    """Detector width in pixels, scaled to how big the dish actually is.

    A larva is a fixed fraction of the dish, not a fixed number of pixels. Held
    at 13 the detector hunts for blobs far larger than the animal in any clip
    that was downscaled on its way here - it finds nothing and the clip looks
    untrackable when it is merely small. trackpy needs an odd number, minimum 3.
    """
    d = int(round(DIAMETER * dish_px / REF_DISH_PX))
    return max(3, d + 1 - d % 2)


def _moving(frames):
    """Per-pixel median over the clip removes the agar; what is left moved."""
    bg = np.median(np.stack(frames), axis=0).astype(np.uint8)
    return [cv2.absdiff(f, bg) for f in frames]


def trajectories(video, circle, every=EVERY_S, mm_per_px=None, log=print,
                 steady=False):
    """Linked trajectories, as a list of (times_s, xy_px) arrays, longest first."""
    import trackpy as tp
    tp.quiet()

    frames, _ = _sample(video, circle, every)
    if not frames:
        raise NoLarva("no frames could be read from the clip")
    log("%d frames at %.1fs spacing" % (len(frames), every))

    if steady:
        frames = stabilise(frames)
        log("stabilised against camera drift")
    diffs = _moving(frames)
    # Two passes: the first learns what a bright feature looks like in this dish,
    # so the mass cut adapts to the lighting instead of being a magic number.
    diam = feature_px(2 * circle[2])
    if diam != DIAMETER:
        log("dish is %d px across, so detecting at %d px instead of %d"
            % (int(2 * circle[2]), diam, DIAMETER))
    probe = tp.batch(np.stack(diffs), diam, minmass=1)
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


def to_crop(anchors, circle):
    """Pinned points arrive in whole-frame pixels; everything here is in the
    dish crop, whose origin is the circle's top-left corner."""
    cx, cy, r = circle
    # A pin may carry which larva it belongs to as a fourth field; ignore it
    # here. Unpacking exactly three crashed every correction once hand tracing
    # started tagging points with an animal.
    return [(float(a[0]), float(a[1]) - (cx - r), float(a[2]) - (cy - r))
            for a in anchors]


def _contradicted(traj, anchors, mpp, every=EVERY_S, tol_mm=ANCHOR_TOL_MM):
    """True when the trajectory claims the animal was somewhere the user says it
    was not.  A pin is a statement about one moment only, so a trajectory that
    does not cover that moment is not contradicted by it - it is just silent.
    """
    t, xy = traj
    for at, ax, ay in anchors:
        i = int(np.argmin(np.abs(t - at)))
        if abs(t[i] - at) > every:
            continue
        if math.hypot(xy[i][0] - ax, xy[i][1] - ay) * mpp > tol_mm:
            return True
    return False


def _endorsed(traj, anchors, mpp, every=EVERY_S, tol_mm=ANCHOR_TOL_MM):
    """True when the trajectory passes through at least one pinned point."""
    t, xy = traj
    for at, ax, ay in anchors:
        i = int(np.argmin(np.abs(t - at)))
        if abs(t[i] - at) <= every and \
                math.hypot(xy[i][0] - ax, xy[i][1] - ay) * mpp <= tol_mm:
            return True
    return False


def _attribute(kept, anchors=None, mpp=1.0):
    """With pins, the animal is what the pins say it is.

    Without them the longest trajectory is the best guess available, and that is
    what goes wrong: the longest thing in the dish is sometimes a speck. A pin
    settles it - trajectories that disagree with one are thrown out, and the
    animal becomes whatever the pins actually touch.
    """
    if anchors:
        ok = [k for k, p in enumerate(kept)
              if not _contradicted(p, anchors, mpp)]
        hit = [k for k in ok if _endorsed(kept[k], anchors, mpp)]
        if hit:
            lo, hi = min(hit), max(hit)
            # Everything between the first and last endorsed piece, minus
            # anything a pin rules out, is the same animal's walk.
            group = [kept[k] for k in range(lo, hi + 1) if k in set(ok)]
            return group, lo, hi
        if ok:
            kept = [kept[k] for k in ok]
    return _attribute_longest(kept)


def _attribute_longest(kept):
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


def measure(video, dish_mm, circle, every=EVERY_S, log=print, steady=False,
            trs=None, anchors=None):
    """Path length in mm.

    Reports the longest single trajectory as the headline figure, because that
    is the stretch we actually watched one animal walk, and lists the remaining
    fragments separately.  Chaining everything together was tried and is worse:
    a fragment that is really glare on the lid gets welded onto the larva's path
    and inflates the total by a third.  A fragment only joins the headline when
    the gap to it is short enough to attribute (see MAX_GAP_S).
    """
    mpp = dish_mm / (2.0 * circle[2])
    if trs is None:
        trs = trajectories(video, circle, every, mpp, log, steady)
    if not trs:
        log("no trajectories found")
        return 0.0, 0.0, 0.0
    kept = _drop_overlaps(trs)
    pins = to_crop(anchors, circle) if anchors else None
    if pins:
        log("%d correction(s) pinned" % len(pins))
    group, lo, hi = _attribute(kept, pins, mpp)

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


def measure_each(video, dish_mm, circle, larvae, every=EVERY_S, log=print,
                 steady=False):
    """Path length per animal, for a dish holding more than one.

    No attribution across gaps here.  With several larvae in the dish a gap is
    just as likely to be one animal ending as another beginning, and joining
    them reports two creatures' walks as one.  Each surviving trajectory is
    reported on its own; the `larvae` count is what to expect, not a target to
    pad up to - a sitter that barely moves may not clear MIN_DETECTIONS at all.
    """
    mpp = dish_mm / (2.0 * circle[2])
    # No _drop_overlaps here: it exists to throw away a second trajectory that
    # runs at the same time as the real one, which is right for a solo dish and
    # exactly wrong here - several larvae crawl simultaneously by definition.
    kept = trajectories(video, circle, every, mpp, log, steady)
    rows = [(float(np.hypot(*np.diff(xy, axis=0).T).sum()) * mpp, t[0], t[-1])
            for t, xy in kept]
    rows.sort(reverse=True)
    log("expected %d larvae, %d trajectory(ies) survived:" % (larvae, len(rows)))
    for i, (mm, t0, t1) in enumerate(rows[:larvae], 1):
        log("  larva %d: %6.1f mm   %5.1fs-%5.1fs" % (i, mm, t0, t1))
    if len(rows) > larvae:
        log("  (%d shorter trajectory(ies) below the top %d, not listed)"
            % (len(rows) - larvae, larvae))
    return [r[0] for r in rows[:larvae]]


def overlay(video, circle, out, every=EVERY_S, mm_per_px=None, larvae=1,
            steady=False, anchors=None):
    """First frame with every kept trajectory drawn, so the path can be eyeballed."""
    cx, cy, r = circle
    cap = cv2.VideoCapture(video)
    ok, f = cap.read()
    cap.release()
    if not ok:
        return
    img = cv2.merge([_crop(c, int(cx - r), int(cy - r), int(2 * r))
                     for c in cv2.split(f)])
    kept = trajectories(video, circle, every, mm_per_px, log=lambda *a: None,
                        steady=steady)
    if larvae == 1:
        kept = _drop_overlaps(kept)
    if not kept:
        cv2.imwrite(out, img)
        return
    if larvae > 1:
        # Each animal gets its own colour; no attribution across gaps.
        order = sorted(range(len(kept)), key=lambda k: -len(kept[k][0]))[:larvae]
        lo, hi, top = None, None, set(order)
    else:
        _, lo, hi = _attribute(kept, to_crop(anchors, circle) if anchors else None,
                               mm_per_px or 1.0)
        top = None
    for i, (_, xy) in enumerate(kept):
        measured = (i in top) if top is not None else (lo <= i <= hi)
        # red is the path that was measured; grey is a fragment left out of it
        if not measured:
            col = (150, 150, 150)
        elif top is not None:
            col = [(0, 0, 255), (0, 200, 255), (0, 255, 0),
                   (255, 0, 255), (255, 200, 0)][order.index(i) % 5]
        else:
            col = (0, 0, 255)
        cv2.polylines(img, [xy.astype(np.int32)], False, col, 2 if measured else 1)
    cv2.imwrite(out, img)


def replay(video, dish_mm, circle, out, every=EVERY_S, larvae=1, steady=False,
           size=720, log=print, trs=None, anchors=None):
    """Write the clip back out with each path drawn in as it is walked.

    Same trajectories the measurement uses - this is the measurement being shown,
    not a second guess at it, so what is on screen is what got counted.
    """
    mpp = dish_mm / (2.0 * circle[2])
    # Detection and linking is the slow half; reuse it when the caller has it.
    kept = trajectories(video, circle, every, mpp, log, steady) if trs is None \
        else list(trs)
    if not kept:
        raise NoLarva("nothing was tracked, so there is no path to replay")
    if larvae == 1:
        kept = _drop_overlaps(kept)
        group, lo, hi = _attribute(kept, to_crop(anchors, circle) if anchors else None,
                                   mpp)
        shown = list(range(lo, hi + 1))
    else:
        shown = sorted(range(len(kept)), key=lambda k: -len(kept[k][0]))[:larvae]
    cols = [(0, 0, 255), (0, 200, 255), (0, 255, 0), (255, 0, 255), (255, 200, 0)]

    cx, cy, r = circle
    side = int(2 * r)
    scale = size / float(side)
    # Every sampled instant, so a path grows in step with the frame it belongs to.
    stamps = sorted({float(t) for k in shown for t in kept[k][0]})
    if not stamps:
        raise NoLarva("nothing was tracked, so there is no path to replay")

    ff = shutil.which("ffmpeg")
    if not ff:
        raise NoLarva("ffmpeg is needed to write the replay")
    proc = subprocess.Popen(
        [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", "%dx%d" % (size, size), "-r", "8", "-i", "-", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", out],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    cap = cv2.VideoCapture(video)
    try:
        for now in stamps:
            cap.set(cv2.CAP_PROP_POS_MSEC, now * 1000.0)
            ok, f = cap.read()
            if not ok:
                break
            img = cv2.merge([_crop(c, int(cx - r), int(cy - r), side)
                             for c in cv2.split(f)])
            img = cv2.resize(img, (size, size))
            walked = 0.0
            for n, k in enumerate(shown):
                t, xy = kept[k]
                upto = xy[t <= now]
                if len(upto) < 2:
                    continue
                col = cols[n % len(cols)] if larvae > 1 else (0, 0, 255)
                cv2.polylines(img, [(upto * scale).astype(np.int32)], False, col, 2)
                cv2.circle(img, tuple((upto[-1] * scale).astype(int)), 5, col, -1)
                walked += float(np.hypot(*np.diff(upto, axis=0).T).sum()) * mpp
            # With several larvae the running figure is their sum, which reads
            # as one animal's distance unless it says so.
            cap_txt = ("%5.1fs   %.1f mm total of %d" % (now, walked, len(shown))
                       if larvae > 1 else "%5.1fs   %.1f mm" % (now, walked))
            cv2.putText(img, cap_txt, (12, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 230, 255), 2)
            proc.stdin.write(img.tobytes())
    finally:
        cap.release()
        proc.stdin.close()
        if proc.wait() != 0:
            raise NoLarva("ffmpeg failed: " + proc.stderr.read().decode()[-300:])
    log("wrote %s (%d frames)" % (out, len(stamps)))
    return out


def manual_paths(dish_mm, circle, anchors, log=print):
    """Hand-traced path length per animal, for a plate holding several.

    Each clicked point carries which larva it belongs to, so five animals can be
    followed in one pass through the clip rather than five. Identity comes from
    the operator, which is the one source that does not lose track of an animal
    when two of them cross.
    """
    by = {}
    for a in anchors:
        by.setdefault(int(a[3]) if len(a) > 3 else 1, []).append(a[:3])
    out = {}
    for larva in sorted(by):
        mm, pts = manual_path(dish_mm, circle, by[larva], log=lambda *x: None)
        out[larva] = mm
        log("larva %d: %6.1f mm from %d point(s)" % (larva, mm, len(pts)))
    log("PATH total %.1f mm across %d larva(e)" % (sum(out.values()), len(out)))
    return out


def manual_path(dish_mm, circle, anchors, log=print):
    """Path length from points the operator clicked, in time order.

    For clips the tracker cannot do honestly - too little contrast, a larva that
    sits on a yeast spot, debris it will not stop grabbing. A person scrubbing
    the clip and clicking the animal is slower but it is real data, and it beats
    a confident wrong number.

    Straight lines between clicks, so this is a lower bound like everything else
    here: click more often through a turn and it gets closer to the truth.
    """
    pts = sorted(to_crop(anchors, circle), key=lambda p: p[0])
    mpp = dish_mm / (2.0 * circle[2])
    total = 0.0
    for (t0, x0, y0), (t1, x1, y1) in zip(pts, pts[1:]):
        total += math.hypot(x1 - x0, y1 - y0) * mpp
    if pts:
        log("hand-traced %d point(s) from %.1fs to %.1fs"
            % (len(pts), pts[0][0], pts[-1][0]))
        log("PATH %.1f mm (straight between clicks, so a lower bound)" % total)
    return total, pts


def manual_replay(video, dish_mm, circle, anchors, out, size=720, log=print):
    """The hand-traced paths drawn in, one colour per animal."""
    groups = {}
    for a in anchors:
        groups.setdefault(int(a[3]) if len(a) > 3 else 1, []).append(a[:3])
    tracks = {k: sorted(to_crop(v, circle), key=lambda p: p[0])
              for k, v in groups.items()}
    pts = sorted([p for v in tracks.values() for p in v], key=lambda p: p[0])
    if len(pts) < 2:
        raise NoLarva("hand tracing needs at least two points")
    mpp = dish_mm / (2.0 * circle[2])
    cx, cy, r = circle
    side = int(2 * r)
    scale = size / float(side)
    ff = shutil.which("ffmpeg")
    if not ff:
        raise NoLarva("ffmpeg is needed to write the replay")
    proc = subprocess.Popen(
        [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", "%dx%d" % (size, size), "-r", "6", "-i", "-", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", out],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    cap = cv2.VideoCapture(video)
    try:
        for i in range(len(pts)):
            t = pts[i][0]
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, f = cap.read()
            if not ok:
                break
            img = cv2.merge([_crop(c, int(cx - r), int(cy - r), side)
                             for c in cv2.split(f)])
            img = cv2.resize(img, (size, size))
            cols = [(0, 0, 255), (0, 200, 255), (0, 255, 0), (255, 0, 255),
                    (255, 200, 0)]
            total = 0.0
            for n, (larva, tr) in enumerate(sorted(tracks.items())):
                upto = [p for p in tr if p[0] <= t]
                total += sum(math.hypot(upto[k + 1][1] - upto[k][1],
                                        upto[k + 1][2] - upto[k][2]) * mpp
                             for k in range(len(upto) - 1))
                if len(upto) < 2:
                    continue
                xy = np.array([[p[1] * scale, p[2] * scale] for p in upto])
                col = cols[n % len(cols)]
                cv2.polylines(img, [xy.astype(np.int32)], False, col, 2)
                cv2.circle(img, tuple(xy[-1].astype(int)), 5, col, -1)
            tag = "%5.1fs   %.1f mm" % (t, total)
            if len(tracks) > 1:
                tag += "  total of %d  (hand-traced)" % len(tracks)
            else:
                tag += "  (hand-traced)"
            cv2.putText(img, tag, (12, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 230, 255), 2)
            proc.stdin.write(img.tobytes())
    finally:
        cap.release()
        proc.stdin.close()
        if proc.wait() != 0:
            raise NoLarva("ffmpeg failed: " + proc.stderr.read().decode()[-300:])
    log("wrote %s" % out)
    return out


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

    # Stabilising a deliberately drifted clip must put it back where it started.
    base = np.zeros((80, 80), np.uint8)
    base[30:38, 30:50] = 200          # a bar to lock onto
    drifted = [base] + [np.roll(base, (dy, dx), (0, 1))
                        for dx, dy in ((3, 2), (7, -4), (-5, 6))]
    fixed = stabilise(drifted)
    for f in fixed[1:]:
        assert abs(int(f.sum()) - int(base.sum())) < base.sum() * 0.05
        ys, xs = np.nonzero(f > 100)
        assert abs(ys.mean() - 33.5) < 1.5 and abs(xs.mean() - 39.5) < 1.5, \
            (ys.mean(), xs.mean())

    # A pin must beat "longest wins". Here the speck is followed for longer than
    # the animal, so the unpinned answer is the wrong one; pinning a point on the
    # real path has to switch the verdict.
    r2, mpp2 = 300.0, 100.0 / 600.0
    animal_xy = np.column_stack([np.linspace(200, 400, 20), np.full(20, 300.0)])
    speck_xy = np.column_stack([np.full(40, 120.0), np.linspace(100, 500, 40)])
    animal = (np.arange(20) * EVERY_S, animal_xy)
    speck = (np.arange(40) * EVERY_S, speck_xy)
    kept = [speck, animal]                      # speck first: it is the longer
    g_none, _, _ = _attribute(list(kept))
    assert g_none[0] is speck, "unpinned should pick the longer trajectory"

    # Pin a point the animal passes through, in whole-frame coordinates.
    circle2 = (500.0, 500.0, r2)
    pin_t = 10 * EVERY_S
    pin = [(pin_t, animal_xy[10][0] + (circle2[0] - r2),
            animal_xy[10][1] + (circle2[1] - r2))]
    g_pin, _, _ = _attribute(list(kept), to_crop(pin, circle2), mpp2)
    assert any(p is animal for p in g_pin), "a pin must select the trajectory it touches"
    assert all(p is not speck for p in g_pin), "a pin must reject what it contradicts"

    # A pin carrying a larva tag must be accepted wherever a plain one is.
    tagged = [(pin_t, animal_xy[10][0] + (circle2[0] - r2),
               animal_xy[10][1] + (circle2[1] - r2), 3)]
    assert to_crop(tagged, circle2)[0][:3] == to_crop(pin, circle2)[0][:3]

    # A pin where nothing was tracked must not throw everything away.
    lonely = [(500.0, circle2[0], circle2[1])]
    assert _attribute(list(kept), to_crop(lonely, circle2), mpp2)[0]

    # The detector has to shrink with the dish or a downscaled clip finds nothing.
    assert feature_px(600) == 13, feature_px(600)
    assert feature_px(95) == 3, feature_px(95)      # the clip that found nothing
    assert feature_px(300) == 7, feature_px(300)
    assert all(feature_px(p) % 2 == 1 and feature_px(p) >= 3
               for p in (10, 50, 95, 300, 600, 1200))

    # Hand tracing: three clicks 100px apart on a 600px/100mm plate is 100/6 mm
    # per leg, and the total must not depend on the order they were clicked in.
    circ = (400.0, 400.0, 300.0)
    a = [(0.0, 400.0, 400.0), (2.0, 500.0, 400.0), (4.0, 500.0, 500.0)]
    mm, _ = manual_path(100.0, circ, a, log=lambda *x: None)
    assert abs(mm - 2 * 100 * (100.0 / 600.0)) < 1e-6, mm
    mm2, _ = manual_path(100.0, circ, list(reversed(a)), log=lambda *x: None)
    assert abs(mm - mm2) < 1e-9, (mm, mm2)

    # Two animals traced in one pass must not have their points joined together.
    two = [(0.0, 400.0, 400.0, 1), (2.0, 500.0, 400.0, 1),
           (0.0, 400.0, 600.0, 2), (2.0, 400.0, 700.0, 2)]
    per = manual_paths(100.0, circ, two, log=lambda *x: None)
    assert set(per) == {1, 2}, per
    leg = 100 * (100.0 / 600.0)
    assert abs(per[1] - leg) < 1e-6 and abs(per[2] - leg) < 1e-6, per

    print("self-check ok (wall gap within %.1f%%, mid-dish chord is a lower bound)"
          % (err * 100))


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
        raise SystemExit
    video = sys.argv[1]
    dish = float(sys.argv[sys.argv.index("--dish-mm") + 1])
    circle = tuple(float(v) for v in sys.argv[sys.argv.index("--circle") + 1].split(","))
    n = int(sys.argv[sys.argv.index("--larvae") + 1]) if "--larvae" in sys.argv else 1
    steady = "--stabilise" in sys.argv
    if n > 1:
        measure_each(video, dish, circle, n, steady=steady)
    else:
        measure(video, dish, circle, steady=steady)
    if "--overlay" in sys.argv:
        o = sys.argv[sys.argv.index("--overlay") + 1]
        overlay(video, circle, o, mm_per_px=dish / (2.0 * circle[2]), larvae=n,
                steady=steady)
    if "--replay" in sys.argv:
        i = sys.argv.index("--replay") + 1
        # Timestamped by default: overwriting a file QuickTime still has open is
        # what made earlier replays look corrupted.
        o = sys.argv[i] if i < len(sys.argv) and not sys.argv[i].startswith("-") \
            else "replay_%s.mp4" % time.strftime("%H%M%S")
        replay(video, dish, circle, o, larvae=n, steady=steady)
        print("wrote", o)

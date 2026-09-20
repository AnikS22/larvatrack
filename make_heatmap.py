"""Every 2-second motion sample painted onto the plate.

The path figures show one reconstructed trajectory. This shows the raw evidence
underneath it: everything that moved between consecutive samples, accumulated
over the whole recording. Red is a plain overlay; the time-coloured version maps
each sample to when it happened, so the direction of travel is readable.
"""
import sys
import cv2
import numpy as np
import tptrack

F = cv2.FONT_HERSHEY_SIMPLEX


def motion_samples(video, circle, steady=False):
    """Binary mask per sampled interval: what moved since the frame before."""
    frames, _ = tptrack._sample(video, circle)
    if steady:
        frames = tptrack.stabilise(frames)
    bg = np.median(np.stack(frames), axis=0).astype(np.uint8)
    r = int(circle[2])
    dish = np.zeros(frames[0].shape[:2], np.uint8)
    cv2.circle(dish, (r, r), int(r * 0.94), 255, -1)
    out = []
    for f in frames:
        d = cv2.absdiff(f, bg)
        # Same 99.8th-percentile cut the tracker uses, so this shows what it saw.
        thr = max(8, int(np.percentile(d[dish > 0], 99.8)))
        m = cv2.bitwise_and((d >= thr).astype(np.uint8) * 255, dish)
        out.append(m)
    return frames, out


def render(video, circle, out_png, label, steady=False, side=760):
    frames, masks = motion_samples(video, circle, steady)
    cx, cy, r = circle
    cap = cv2.VideoCapture(video)
    ok, raw = cap.read()
    cap.release()
    base = cv2.merge([tptrack._crop(c, int(cx - r), int(cy - r), int(2 * r))
                      for c in cv2.split(raw)])

    flat, timed = base.copy(), base.copy()
    n = max(1, len(masks) - 1)
    for i, m in enumerate(masks):
        sel = m > 0
        if not sel.any():
            continue
        flat[sel] = (0, 0, 255)
        # Hue walks blue -> red across the recording, so early and late differ.
        col = cv2.applyColorMap(np.uint8([[255 - int(255 * i / n)]]),
                                cv2.COLORMAP_JET)[0][0]
        timed[sel] = col

    panels = []
    for img, ttl, sub in ((flat, label + " - all motion samples",
                           "every 2 s interval, %d in total" % len(masks)),
                          (timed, label + " - coloured by time",
                           "blue = start of recording, red = end")):
        img = cv2.resize(img, (side, side), interpolation=cv2.INTER_AREA)
        s = side / (2 * r)
        bar = int(round(10.0 / (100.0 / (2 * r)) * s))
        x0, y0 = int(side * .06), int(side * .94)
        box = img[y0 - 46:y0 + 12, x0 - 12:x0 + bar + 12].copy()
        img[y0 - 46:y0 + 12, x0 - 12:x0 + bar + 12] = cv2.addWeighted(
            box, .35, np.zeros_like(box), .65, 0)
        cv2.line(img, (x0, y0 - 6), (x0 + bar, y0 - 6), (255, 255, 255), 5)
        cv2.putText(img, "10 mm", (x0, y0 - 18), F, .58, (255, 255, 255), 2)
        strip = np.full((78, side, 3), 255, np.uint8)
        cv2.putText(strip, ttl, (14, 32), F, .62, (0, 0, 0), 2)
        cv2.putText(strip, sub, (14, 58), F, .5, (90, 90, 90), 1)
        panels.append(np.vstack([img, strip]))
    cv2.imwrite(out_png, np.hstack(panels))
    print("wrote", out_png)


if __name__ == "__main__":
    render('clips/dish3_5min.mp4', (568., 549., 297.),
           'docs/fig3_motion_heatmap.png', 'Plate 3, left')

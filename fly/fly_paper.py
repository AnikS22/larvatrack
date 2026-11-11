"""Count real flies stuck on fly paper, per zone between the red lines.

  python fly_paper.py PHOTO [PHOTO...]  -> fly_paper.csv + PHOTO.check.jpg (circled flies, numbered zones)

Real flies = small brown specks. The big black flies are PRINTED on the paper (bluish-black) and are ignored,
as are red lines/dots and ink. Zone 1 = top of the photo as taken (or left, if the lines run vertically).
"""
import csv, json, os, sys
import cv2
import numpy as np

SCALE = 0.5      # work at half resolution (12 MP -> 3 MP); a fly is then ~15-25 px
DARK = 35        # fly must be this much darker than the surrounding paper
AREA = (150, 1050)  # px at SCALE: one fly ~400, two touching ~900; printed flies are 1100+, speckle < 150
ONE_FLY = 450       # clumps count as round(area / ONE_FLY) flies
PEAK = 60        # a real fly has a dark core; faint smudges on dirty sheets don't
# glass tube lying on the sheet: flies/ink inside it are not stuck to the paper. Boxes read off the photos
# by eye, [x, y, w, h] at SCALE. ponytail: hand-marked per photo; a new photo with a tube needs its box added.
TUBES = {"IMG_6491": [1290, 130, 190, 910], "IMG_6492": [1260, 300, 180, 790], "IMG_6493": [1090, 1050, 190, 810],
         "IMG_6494": [1040, 970, 200, 760], "IMG_6495": [470, 330, 610, 230], "IMG_6496": [1260, 510, 170, 840],
         "IMG_6497": [1260, 530, 170, 820], "IMG_6498": [1830, 980, 200, 840], "IMG_6500": [1090, 670, 180, 740],
         "IMG_6501": [1120, 990, 200, 800], "IMG_6502": [990, 840, 180, 760], "IMG_6503": [1110, 550, 190, 790],
         "IMG_6504": [1290, 510, 170, 790]}


def count(path):
    im = cv2.resize(cv2.imread(path), None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    b, g, r = [c.astype(np.int16) for c in cv2.split(im)]
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)

    # paper = yellow-green, holes (flies, lines, print) filled by closing
    red = (cv2.inRange(hsv, (0, 90, 70), (10, 255, 255)) | cv2.inRange(hsv, (165, 90, 70), (180, 255, 255)))
    paper = cv2.inRange(hsv, (25, 60, 110), (55, 255, 255)) | red
    paper = cv2.morphologyEx(paper, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    paper = cv2.erode(paper, np.ones((31, 31), np.uint8))          # drop the ragged edge
    n, lab, st, _ = cv2.connectedComponentsWithStats(paper, 8)     # only the main sheet, not neighbours at the edge
    if n > 1:
        paper = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8) * 255

    # zone lines: rows (or columns) where a big share of the sheet's width is red. Robust to a line being
    # broken by the tube, a tear or glare. ponytail: assumes lines run roughly straight across the sheet.
    red &= cv2.dilate(paper, np.ones((61, 61), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(red, 8)
    big_red = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > AREA[1]]).astype(np.uint8)
    redf, pap = red > 0, paper > 0
    W = np.median(pap.sum(1)[pap.sum(1) > 0]); H = np.median(pap.sum(0)[pap.sum(0) > 0])  # typical sheet width / height
    rows = redf.sum(1) / W
    cols = redf.sum(0) / H
    horiz = rows.max() >= cols.max()
    prof = rows if horiz else cols
    hits = np.where(prof > 0.25)[0]
    lines = [int(np.mean(g)) for g in np.split(hits, np.where(np.diff(hits) > 40)[0] + 1) if len(g)] if len(hits) else []
    t = TUBES.get(os.path.splitext(os.path.basename(path))[0])
    if t:  # glass tube: nothing under it counts
        paper[t[1]:t[1] + t[3], t[0]:t[0] + t[2]] = 0

    d = cv2.medianBlur(gray, 51).astype(np.int16) - gray
    # printed flies: their solid black body is far bigger than any real fly. Blank a wide square around each
    # body so the legs and stippled wings (which look brownish against the yellow) are never counted.
    n, lab, st, _ = cv2.connectedComponentsWithStats((d > DARK).astype(np.uint8), 8)
    printed = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > AREA[1]]).astype(np.uint8)
    printed = cv2.dilate(printed, np.ones((71, 71), np.uint8))
    cand = ((d > DARK) & (paper > 0) & (printed == 0) & (cv2.dilate(big_red, np.ones((21, 21), np.uint8)) == 0)).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(cand, 8)
    sat = cv2.blur(hsv[..., 1].astype(np.float32), (61, 61))      # glare = washed-out, low-saturation patch
    sat_ok = np.median(hsv[..., 1][paper > 0]) * 0.7
    flies = []
    for i in range(1, n):
        if not AREA[0] <= st[i, cv2.CC_STAT_AREA] <= AREA[1]:
            continue
        m = lab == i
        if (r[m] - b[m]).mean() < 8:      # brown flies only; gray speckle / black ink fail this
            continue
        if d[m].max() < PEAK or sat[int(cen[i][1]), int(cen[i][0])] < sat_ok:
            continue
        k = max(1, round(st[i, cv2.CC_STAT_AREA] / ONE_FLY))
        # fan clump flies out sideways so each is its own clickable circle in the review page
        flies += [(cen[i][0] + 12 * (j - (k - 1) / 2), cen[i][1]) for j in range(k)]

    # zone = how many red lines the fly is past, counting from the top (or left)
    zones = [1 + sum((p[1] if horiz else p[0]) > ln for ln in lines) for p in flies]

    out = im.copy()
    for (x, y), z in zip(flies, zones):
        cv2.circle(out, (int(x), int(y)), 14, (255, 0, 255), 3)
        cv2.putText(out, str(z), (int(x) + 14, int(y) - 10), 0, 0.9, (255, 0, 255), 2)
    cv2.imwrite(os.path.splitext(path)[0] + ".check.jpg", cv2.resize(out, None, fx=0.6, fy=0.6))
    pts = [[round(float(x), 1), round(float(y), 1)] for x, y in flies]
    return len(lines), "horizontal" if horiz else "vertical", [zones.count(z) for z in (1, 2, 3)], \
        {"lines": [int(v) for v in lines], "horiz": bool(horiz), "pts": pts, "scale": SCALE}


if __name__ == "__main__":
    rows = [["photo", "red_lines_found", "line_direction", "zone1", "zone2", "zone3", "total"]]
    points = {}   # per photo: red line positions + fly points, for review.html
    for p in sys.argv[1:]:
        nl, dirn, z, points[os.path.basename(p)] = count(p)
        rows.append([os.path.basename(p), nl, dirn, *z, sum(z)])
        print(*rows[-1])
    csv.writer(open("fly_paper.csv", "w", newline="")).writerows(rows)
    json.dump(points, open("fly_paper_points.json", "w"))

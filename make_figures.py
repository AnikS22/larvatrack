import sys; sys.path.insert(0,'/Users/aniksahai/Desktop/PCB4054C-01H')
import cv2, numpy as np, tptrack

DOCS='/Users/aniksahai/Desktop/PCB4054C-01H/docs'
F=cv2.FONT_HERSHEY_SIMPLEX

def panel(video, circle, larvae, letter, title, sub, side=760):
    """One dish, its tracks, a 10mm scale bar and a caption strip."""
    mpp = 100.0/(2*circle[2])
    tmp = '/tmp/_p.png'
    tptrack.overlay(video, circle, tmp, mm_per_px=mpp, larvae=larvae)
    im = cv2.resize(cv2.imread(tmp), (side, side), interpolation=cv2.INTER_AREA)
    s = side/(2*circle[2])                      # px in panel per px in source
    # 10 mm scale bar, bottom-left
    bar = int(round(10.0/mpp*s))
    x0, y0 = int(side*0.06), int(side*0.94)
    # Dark plate on a dark bench, pale agar in between - the bar needs its own
    # backing or it vanishes into whichever it happens to land on.
    pad = 12
    box = im[y0-46:y0+pad, x0-pad:x0+bar+pad].copy()
    im[y0-46:y0+pad, x0-pad:x0+bar+pad] = cv2.addWeighted(
        box, 0.35, np.zeros_like(box), 0.65, 0)
    cv2.line(im,(x0,y0-6),(x0+bar,y0-6),(255,255,255),5)
    cv2.putText(im,"10 mm",(x0,y0-18),F,0.58,(255,255,255),2)
    # caption strip under the image
    strip = np.full((96, side, 3), 255, np.uint8)
    cv2.putText(strip,letter,(14,40),F,1.0,(0,0,0),3)
    cv2.putText(strip,title,(58,38),F,0.72,(0,0,0),2)
    for i,l in enumerate(sub):
        cv2.putText(strip,l,(58,64+i*24),F,0.52,(90,90,90),1)
    return np.vstack([im, strip])

def main():
    C='/Users/aniksahai/Desktop/PCB4054C-01H/clips'
    # Figure 1 - one larva per plate
    p=[panel(f'{C}/dish3_5min.mp4',(568.,549.,297.),1,'A','Plate 3, left  -  72.1 mm',
             ['single larva, tracked 116 s of 300 s']),
       panel(f'{C}/dish3_5min.mp4',(1182.,543.,288.),1,'B','Plate 3, right  -  62.2 mm',
             ['single larva, tracked 226 s of 300 s']),
       panel(f'{C}/dish2_5min.mp4',(1005.,790.,306.),1,'C','Plate 2  -  44.3 mm',
             ['single larva, tracked 126 s of 300 s'])]
    cv2.imwrite(f'{DOCS}/fig1_single_larva_paths.png', np.hstack(p))
    print('fig1', np.hstack(p).shape)

    # Figure 2 - five larvae per plate, one colour each
    q=[panel(f'{C}/dish4_5min.mp4',(498.,702.,306.),5,'A','Plate 4, left  -  5 larvae',
             ['62.9 / 57.6 / 35.3 / 32.6 mm','per-trajectory, not per-animal identity']),
       panel(f'{C}/dish4_5min.mp4',(1260.,682.,297.),5,'B','Plate 4, right  -  5 larvae',
             ['99.3 / 72.9 / 44.1 / 30.8 / 30.0 mm','per-trajectory, not per-animal identity'])]
    cv2.imwrite(f'{DOCS}/fig2_multiple_larvae_paths.png', np.hstack(q))
    print('fig2', np.hstack(q).shape)

if __name__=='__main__': main()

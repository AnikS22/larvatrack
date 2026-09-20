<div align="center">

# larvatrack

**Measures how far a *Drosophila* larva crawls in a petri dish, from a phone video.**

Built for a `for` gene foraging assay — rovers cover more ground than sitters,
and what you need out of a clip is one number: path length in millimetres.

<img src="docs/demo.gif" width="420" alt="a larva's path drawn in as it is walked">

*dish 3, left — 72.1 mm. The path is drawn in as it was walked, with the clock
and running distance burned in.
<a href="docs/demo_dish3L.mp4">Full-quality MP4</a>.*

</div>

---

> ### One larva at a time
> This measures **a single animal per run**. Point it at a dish with five larvae
> and it reports whichever one it followed longest — not all five, and not their
> total. The solo-larva dishes (all-yeast, all-agar) are what it is for.

---

## What you give it

| | |
|---|---|
| **A clip** | MP4 or MOV, straight off the phone. Keep the camera still. |
| **Which dish** | Click a circle the detector found, or drag across the dish by hand. |
| **How wide it is** | In mm. Everything is scaled from this, so a wrong diameter gives a wrong answer with no other symptom. Standard dishes here are 100 mm. |

You get back the path length and the replay above, so you can see whether it
followed the larva or a speck of agar.

## Running it

The measurement needs `trackpy`, hence a separate environment:

```bash
python3 -m venv .venv-track
.venv-track/bin/pip install trackpy opencv-python numpy pandas
.venv-track/bin/python app.py          # http://localhost:8020
```

`ffmpeg` must be on `PATH` for the replay video.

### From the command line

```bash
.venv-track/bin/python tptrack.py clip.mp4 \
    --dish-mm 100 --circle 568,549,297 \
    --replay out.mp4 --overlay out.png
```

| flag | |
|---|---|
| `--circle cx,cy,r` | the dish, in pixels |
| `--dish-mm` | its real diameter |
| `--larvae N` | crowded dish: report each trajectory separately |
| `--stabilise` | the camera moved during filming |
| `--replay` / `--overlay` | write the video / a still |

## Letting other people upload

```bash
./deploy.sh
```

Publishes the page to Vercel pointed at this machine through an ngrok tunnel.
The page is public; the measuring stays here, because the tracker needs OpenCV,
trackpy and minutes of CPU per clip — none of which fits in a serverless function.

- Clips are measured **one at a time**. Others queue and are told their position.
- Uploads go **in 4 MB chunks** with retries. Sent whole, a 120 MB clip is a
  72-second request that one network hiccup kills outright.
- This machine must be **awake and running `app.py`**.
- A free ngrok URL rotates on restart — re-run `./deploy.sh` and nothing else.

## How it measures

[`trackpy`](https://soft-matter.github.io/trackpy/) does detection and linking.
Rolling your own blob detector does not work here: the agar is covered in specks
the same size and shape as a larva, and a hand-written detector locks onto them.

trackpy still breaks one larva into several trajectories, because the animal
fades out against the dish wall. So:

- trajectories living out on the wall are dropped — that is glare, not an animal
- fragments join only across gaps short enough to be the same creature
- a gap against the wall is bridged **round** it, since that is where the larva
  went; mid-dish it is bridged straight, a lower bound by construction
- anything left over is reported separately rather than added in

> **The numbers are undercounts.** A five-minute clip typically yields two to
> four minutes of tracked path. Time the larva was invisible is not counted
> rather than guessed at.

Chaining every fragment together was tried and is worse — on one dish it welded
a glare fragment on the lid onto the real path, turning 72 mm into 153 mm.

## Checks

```bash
.venv-track/bin/python tptrack.py --self-check
```

Covers the bridging arithmetic, the wall arc, the speed cap, rejection of
over-long gaps, and the drift correction.

## Layout

| | |
|---|---|
| `tptrack.py` | the measurement, and the CLI |
| `app.py` | local server: upload, pick dish, measure, replay |
| `app.html` | the page |
| `deploy.sh` | publish the page, pointed at this machine |
| `trail.py` | older trail-area method, kept as a cross-check |
| `larvatrack.py` | earlier hand-rolled tracker; still used for dish auto-detection |

## Resolution matters more than you would think

The dish must be about **440 px across** in the clip. This is measured, not a
guess — the same recording downscaled, against its full-resolution answer of
72.1 mm:

| dish in frame | measured | error |
|---|---|---|
| 534 px | 71.4 mm | −1% |
| 445 px | 72.3 mm | +0% |
| 392 px | 112.4 mm | **+56%** |
| 297 px | 174.0 mm | **+141%** |
| 148 px | nothing found | — |

It does not degrade gracefully. Past the cliff it returns a confident wrong
number rather than a rough one, so clips below the threshold are refused instead
of measured. The detector width scales with the dish, which is what makes the
445 px case work at all.

**AirDrop, iMessage and iCloud Photos all shrink video.** Send the original file
off the phone, not a copy that has been through any of them.

## Known limits

- Needs a still camera and visible contrast between larva and agar. One test clip
  (white larvae on washed-out agar, handheld) fails, and `--stabilise` does not
  rescue it — that one needs reshooting.
- Dish diameter is trusted, not verified.
- Multi-larva mode gives per-trajectory lengths, not per-animal identities.

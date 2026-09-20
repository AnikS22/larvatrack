# larvatrack

Measures how far a *Drosophila* larva crawls in a petri dish, from a phone video.

Built for a `for` gene foraging assay — rovers cover more ground than sitters, and
the thing you need out of a clip is one number: path length in millimetres.

[**Watch a measured path**](docs/demo_dish3L.mp4) — dish3 left, 72.1 mm. The path is
drawn in as it is walked, with the clock and running distance burned in.

## One larva at a time

**This measures a single animal per run.** Point it at a dish with five larvae in
it and it will report whichever one it followed longest — not all five, and not
their total. The solo-larva dishes (all-yeast, all-agar) are what it is for.

There is a multi-larva mode for looking at a crowded dish, but it reports each
trajectory separately and cannot tell you which animal is which across a gap:

```bash
.venv-track/bin/python tptrack.py clip.mp4 --dish-mm 100 --circle 1260,682,297 --larvae 5
```

## What you give it

1. **A clip.** MP4 or MOV, straight off the phone. Keep the camera still.
2. **Which dish.** Click an auto-detected circle, or drag across the dish by hand.
3. **How wide that dish is,** in mm. Everything downstream is scaled from this, so
   a wrong diameter gives a wrong answer with no other symptom. Standard dishes
   here are 100mm.

You get back the path length, and a replay video with the path drawn in as it was
walked — so you can see whether it followed the larva or a speck of agar.

## Running it

The measurement needs `trackpy`, which is why there is a separate environment:

```bash
python3 -m venv .venv-track
.venv-track/bin/pip install trackpy opencv-python numpy pandas
.venv-track/bin/python app.py        # http://localhost:8020
```

`ffmpeg` needs to be on PATH for the replay video.

Command line, without the web page:

```bash
.venv-track/bin/python tptrack.py clip.mp4 --dish-mm 100 --circle 568,549,297 \
    --replay out.mp4 --overlay out.png
```

Add `--stabilise` if the camera moved during filming.

## Letting other people upload

`./deploy.sh` publishes the page to Vercel and points it at this machine through
an ngrok tunnel. The page is public; the measuring still happens here, because the
tracker needs OpenCV, trackpy and minutes of CPU per clip — none of which fits in a
serverless function.

Clips are processed **one at a time**. If several people upload at once the rest
queue up and are told where they are in the line.

This machine has to be awake and running `app.py` for any of it to work. A free
ngrok URL changes every restart, so re-run `./deploy.sh` when it does — nothing
else needs touching.

## How it measures

`trackpy` does detection and linking. Rolling your own blob detector does not work
here: the agar is covered in specks that are the same size and shape as a larva,
and a hand-written detector locks onto them.

trackpy still breaks one larva into several trajectories, because the animal fades
out when it presses against the dish wall. So:

- trajectories that live out on the wall are dropped — that is glare, not an animal
- fragments are joined only across gaps short enough to be the same creature
- a gap against the wall is bridged **round** it, since that is where the larva went;
  mid-dish it is bridged straight, which is a lower bound by construction
- anything left over is reported separately rather than added in

**The numbers are undercounts.** A five-minute clip typically yields 2–4 minutes of
tracked path; time the larva was invisible is not counted rather than guessed at.

Chaining every fragment together was tried and is worse — on one dish it welded a
glare fragment on the lid onto the real path and turned 72mm into 153mm.

## Checks

```bash
.venv-track/bin/python tptrack.py --self-check
```

Covers the bridging arithmetic, the wall arc, the speed cap, rejection of
over-long gaps, and the drift correction.

## Files

| | |
|---|---|
| `tptrack.py` | the measurement, and the CLI |
| `app.py` | local server: upload, pick dish, measure, replay |
| `app.html` | the page |
| `deploy.sh` | publish the page to Vercel, pointed here |
| `trail.py` | older trail-area method, kept as a cross-check |
| `larvatrack.py` | earlier hand-rolled tracker; still used for dish auto-detection |

## Known limits

- Needs a still camera and visible contrast between larva and agar. One test clip
  (white larvae on washed-out agar, handheld) fails and `--stabilise` does not
  rescue it — that one needs reshooting.
- Dish diameter is trusted, not verified.
- Multi-larva mode gives per-trajectory lengths, not per-animal identities.

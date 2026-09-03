# larvatrack

Live path length of *Drosophila* larvae from your phone, several per dish.
`for` rover/sitter assay. Nothing is recorded — you save the numbers at the end.

```bash
python3 larvatrack.py --port 8777    # then open http://localhost:8777
python3 larvatrack.py --demo         # self-check, no camera needed
```

The browser owns the camera; Python does the vision. That split is deliberate:
browsers list real device names and hold a Continuity Camera connection properly,
which OpenCV on macOS does not — probing camera indices from Python is what kept
grabbing the MacBook cam and dropping the iPhone.

## Workflow
1. Allow camera access. The dropdown auto-selects anything matching iPhone/Continuity.
2. Type the **dish diameter** (mm) and press **Find dish**. It finds the rim, masks
   everything outside it, and derives mm/px and the plausible larva size from it.
3. **Drag a box round each larva.** It locks onto the animal inside your box and
   adds it to the list, where you can rename it and pick its colour.
4. **Start.** Each larva gets its own coloured path, outline and running total.
5. **Save** → `run_<timestamp>_tracks.csv` (larva, name, t, x, y, cumulative mm),
   `_summary.csv` (one row per larva) and `_overlay.png`.

**Reset paths** clears the tracks but keeps the locks. **×** removes a larva.

## Why boxes, not full auto
Foraging plates are covered in **yeast smears that are pale, elongated and
larva-sized**. Brightness, shape and size genuinely cannot tell them from an
animal — every fully-automatic version of this locked onto a smear. Your box is
the disambiguation, and it takes a second. The self-check builds smears into the
synthetic dish and asserts the tracker doesn't fall for them.

## If it grabs the wrong thing
| symptom | fix |
|---|---|
| box-add finds nothing | draw the box tighter round the animal |
| it grabs a smear next to the larva | tighter box; the best blob *in the box* wins |
| LOST (dashed outline) | raise **max jump**, or the larva is under **min area** |
| larva darker than the dish | untick **larva is brighter** before adding |
| parked larva shows nonzero path | raise **noise floor** |

Each larva keeps the polarity and threshold found when you added it, so a dark
larva and a pale one can be tracked on the same dish.

## Filming
- Phone locked in the stand, **no zoom or reframing mid-trial** — camera motion is
  scored as larval movement. Turn off auto-rotate.
- Diffuse even light, no shadow of you crossing the plate.
- Keep the whole dish in frame so the rim can be found.
- **sample Hz** (default 2): path length is scale-dependent, so keep it identical
  across every animal you compare.
- 5 min is the standard rover/sitter foraging window.

## Known limits
- **A larva pressed against the wall is not seen.** The dish mask stops at 90% of
  the radius, because the bright rim highlight otherwise out-contrasts the animal.
- Two larvae that touch can swap identities. They can't claim the same blob in one
  frame, but nothing recovers a swap once they separate — watch the colours.
- Lost samples are skipped, not interpolated, so a long LOST stretch understates
  path length. Compare `samples` in `_summary.csv` against `minutes × 60 × sample_hz`.
- mm/px assumes a **top-down** view. A tilted phone makes the dish an ellipse that
  Hough fits as a circle, and the scale is off by roughly the cosine of the tilt.
- Centroid only — no body angle, head/tail, or bending metrics.
- The yeast trail isn't read. Worth photographing at the end as an independent check.
- No auth, binds 127.0.0.1 only. It's a lab tool on your own machine.
- `--video FILE` tracks a file offline (one larva, auto-locked) for tuning knobs.

## Existing tools, if this outgrows itself
- **FIMTrack** (github.com/kostasl/FIMTrack) — the standard larval tracker: body
  posture, bending, head/tail. Built for FIM rigs but takes ordinary video.
- **Tierpsy Tracker** (github.com/Tierpsy/tierpsy-tracker) — multi-worm, maintained, GUI.
- **idtracker.ai** — keeps identities through crossings, which this does not.
- **Multi-Worm Tracker (MWT)**, **Ctrax** — older, worm/adult-fly oriented.

Terminology: the `for` alleles are **rover** (`for^R`) and **sitter** (`for^s`).
Classic Sokolowski numbers on yeast are roughly >7–8 cm (rover) vs <3–4 cm (sitter)
over 5 min — derive your own cutoff from your controls, not from a paper's rig.

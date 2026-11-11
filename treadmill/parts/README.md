# Fly treadmill — every component, separate

All files in **assembly position**: import the folder and the machine is together.
`00_ASSEMBLED.stl` is a quick look. `.stl` and `.obj` of each. Millimetres.
Source: `../fly/treadmill_mini.scad`.

`alt_MR105_lighter/` is the same machine built around small bearings — see below.

| # | part | qty | source |
|---|---|---|---|
| 01 | frame | 1 | **print** floor-down, no supports |
| 02 | pulley_drive | 1 | **print** — double-D, onto the motor shaft |
| 03 | pulley_idler | 1 | **print** — plain bore, onto the shaft |
| 04 | belt GT2 100 mm × 6 mm | 1 | buy |
| 05 | shaft | 1 | buy — 8 mm rod, 31.5 long (MR105 build: 5 mm, 25.5) |
| 06–07 | bearing | 2 | have |
| 08 | motor 28BYJ-48 | 1 | have |
| 09 | fit_gauge | 1 | **print this first**, 3 g, ~10 min |

Pulleys are lying on their side in these files — rotate them bore-up before slicing,
or they print oval. The frame and gauge are already in print orientation.

## Mounting

Four **M3 holes on a 53 × 39.5 mm rectangle**, through ears at the corners of the floor:

    (-27, -19.75)   (-27, +19.75)
    (+26, -19.75)   (+26, +19.75)

Holes are Ø3.45, so M3 passes freely and you bolt down from underneath. That pattern
straddles a 20×20 extrusion, drops onto a breadboard with M3 adapters, or takes four
screws into a plate. The belt's top surface sits **22.63 mm** above whatever you bolt
it to (15.36 mm on the MR105 build) — that is the number the camera has to be levelled
against.

## Bearing choice — this is what makes it heavy

| | plastic | frame | shaft axis |
|---|---|---|---|
| **608RS**, 22T (what you own) | 17.9 cm³ · 22 g · 7.4 m | 69 × 46 × 28.5 | 15.0 |
| **MR105ZZ**, 18T (~$1 for ten) | ~10 cm³ · 12 g · 4.1 m | 67 × 40 × 16.5 | 9.0 |

A 608 is Ø22 and 7 wide. Nothing else in this machine is big: the belt is 6 mm and the
pulleys are 14. That one bearing sets the shaft height and the wall thickness, and it
roughly doubles the print. Switching is one line — `bearing = "MR105"` at the top of
the .scad — and `alt_MR105_lighter/` is already exported if you want to compare.

## Tolerance — what I am and am not confident about

**Confident:** the clearance holes. Shaft through a wall is 0.60 over nominal, screw
holes 0.30 over. Those have enough slack to absorb any sane printer error.

**Not confident without a test print, and this is the honest answer:** the 608 pocket.
It is modelled at **22.45** — 22.00 bearing, +0.30 to let it slide for tensioning,
+0.15 for a printer's typical undersize. If your printer is off, too tight means the
bearing will not slide and you cannot tension the belt; too loose means it rattles.

**Do not force:** the drive pulley onto the motor's shaft. That load goes into a plastic
gear train. It should go on by hand.

That is what `09_fit_gauge` is for — four bores, 3 g, ten minutes:

    A  22.45       608 pushes in by thumb and still slides
    B   8.25       the rod goes in by hand, does not drop out
    C   5.25/3.25  motor shaft enters without forcing
    D   4.65       M4 passes freely

Measure them, set `xy_comp = nominal − measured` in the .scad, re-export. Shipped guess
is 0.15. Everything derives from that one number.

## What has been checked, and how

- The motor's placement was **measured** off the vendor mesh, not assumed: shaft axis
  (20.555, 31.822), tip at z=0, face at z=10, tab holes 8.02 below the axis at 35.11
  pitch — matching the datasheet's 8 and 35.
- After export, motor tab holes land at (−31.550, 23.000) and (3.550, 23.000); frame
  plate holes at (−31.46, 22.98) and (3.44, 22.93). Worst offset **0.12 mm** against
  0.225 mm of radial clearance.
- `part="clash"` intersects the frame with motor, belt, both pulleys and the shaft.
  **Empty** for both bearing variants. It was validated against two deliberate failures
  first, so the pass is not vacuous.
- Nine `assert()`s fail the render if the dimensions stop agreeing.

## Still not done

- **No chamber.** The belt top is 22.63; the pulley flanges reach 23.25, so a chamber
  cannot simply sit across them.
- **The camera can only see from +y.** The motor plate closes the −y side over the drive half.
- **The bearing block from your photo** — not built yet.

## Vendor originals

`../vendor/` — `28BYJ-48.stl/.obj` converted from the supplier 3MF, and `608RS.stl/.obj`
built from nominal 8×22×7 (the SLDPRT is proprietary binary, no mesh inside).

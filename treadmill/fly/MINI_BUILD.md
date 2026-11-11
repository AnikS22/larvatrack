# Fly treadmill — 28BYJ-48 direct drive, 608RS idler

`treadmill_mini.scad`. Parts: `mini_frame.stl`, `mini_pulley_drive.stl`,
`mini_pulley_idler.stl`, `mini_gauge.stl`. `mini_plate.stl` is all of them on one bed.

**Print `mini_gauge.stl` first.** It is a 10-minute coupon carrying the four critical
bores. Measure them, set `xy_comp`, then print the rest. Everything below assumes you did.

## Two numbers set the whole layout, and neither was a choice

    608 bore is 8 mm   -> the idler pulley needs >=22 teeth to leave any wall
                          (16T leaves 0.04 mm; 22T leaves 1.95 mm)
    motor shaft is 10 mm, 1.5 of it boss
                       -> only 8.5 mm of usable shaft, the pulley is 8.0 mm,
                          so the motor's FACE sits 5.75 mm from the belt centreline.
                          Nothing thicker than 2 mm fits between motor and belt.
                          That is why the motor plate is 2 mm and not 4.

Everything else follows:

    pulley pitch dia    14.006   (22T x 2 mm / pi)
    span                28.00    = (100 - 22x2) / 2, taut at zero stretch
    idler travel        +3.00    outward, on the two tension screws
    shaft axis          15.00    forced by the 608's 11 mm radius + floor
    belt top surface    22.63    <- the fly walks here
    frame               69 x 31.5 x 28.5
    motor face          y = -5.75 ; tab holes at z = 23, 35 mm apart
    idler shaft         8 mm rod, cut to 31.5 mm

## Bearings: two, and only at the idler

The drive pulley goes **straight onto the motor's shaft** — no bearing, no coupler,
no second shaft. That is what Pratt does too. The 28BYJ-48's own gearbox output
carries it, and the load is a 6 mm belt pushing a 1 mg fly.

The idler is the only thing that has to spin freely, so it gets both 608s: one in
each wall, on a shared 8 mm shaft, with the pulley keyed to the shaft. Your two
bearings is exactly the right number.

Two consequences of driving off a plastic gearbox, worth knowing up front:

- **Run it one direction only.** The gear train has 1–3° of backlash. Unidirectional,
  it takes up once and stays taken up. Reverse it mid-experiment and you lose steps
  worth of belt position.
- **Radial play is ~0.1–0.2 mm.** That wobbles the pulley but not the belt *speed* —
  the belt still advances exactly 2 mm per tooth. Calibrate the mean and ignore it.

## Fits — one number to tune, then everything derives

A printed hole always comes out undersize; how much is a property of your printer, not
of this design. So it lives in one variable and `bore()` applies it everywhere:

| what | nominal | fit | modelled | why |
|---|---|---|---|---|
| 608 OD in its pocket | 22.00 | +0.30 slide | 22.45 | **must slide** to tension the belt |
| idler pulley on shaft | 8.00 | +0.10 key | 8.25 | hand push, retain with CA |
| drive pulley on motor | 5.00 / 3.00 flats | +0.10 key | 5.25 / 3.25 | double-D; **never press hard**, the load goes into a plastic gear train |
| shaft through a wall | 8.00 | +0.60 free | 8.75 | touches nothing |
| motor screws | 4.20 | +0.30 | 4.65 | M4 clearance |
| tension screws | 2.50 | 0 | 2.65 | self-tap, meant to be tight |

`xy_comp = 0.15` is the shipped guess. Pocket mouths get a 0.6 mm lead-in chamfer so
the bearing starts square instead of cocking.

## Speed — the one place this motor costs you

4096 steps/rev through 44 mm of belt = **10.7 µm per step**, open loop, no PID.
That is far better resolution than Pratt's encoder-and-PID stack.

| step rate | rpm | belt |
|---|---|---|
| 100 Hz (rated) | 1.46 | 1.07 mm/s |
| 600 Hz (in-traction — can start/stop) | 8.79 | 6.45 mm/s |
| 1000 Hz (out-traction — running only) | 14.65 | 10.74 mm/s |

Pratt's five speeds are 3.9, 7.4, 10.9, 14.4, 17.9 mm/s. **You reach the first three.
14.4 and 17.9 are out of reach** on a 28BYJ-48 at 5 V — it would need ~20 and ~25 rpm.
Going to 22T from 16T already bought you the third one. If you need the top two later:
a bigger drive pulley trades away resolution, or 12 V gets maybe 1.5x at the cost of
heat and torque margin. Not a thing to fix now.

## Bought parts — about $10

| qty | part |
|---|---|
| 1 | GT2 closed-loop belt, 100 mm (50T), **6 mm** wide |
| 2 | 608RS bearing, 8 x 22 x 7 *(have)* |
| 1 | 28BYJ-48 5 V + ULN2003 board *(have)* |
| 1 | 8 mm rod, cut to 31.5 mm |
| 2 | M4 x 10 (motor) |
| 2 | M3 x 16 (tension) |

## Build

1. Gauge coupon, measure, set `xy_comp`. Then print the frame floor-down, no supports.
2. Drop a 608 into each idler pocket. They should slide, not rattle.
3. Belt over both pulleys **first** — you cannot thread it in afterwards.
4. Idler pulley onto the 8 mm rod, drop of CA. Rod through bearing → pulley → bearing.
   The two pocket shoulders face each other; that is what traps the assembly.
5. Drive pulley onto the motor's flatted shaft — it should go on by hand. Drop of CA.
   If it needs force, `xy_comp` is wrong; do not push, you will damage the gearbox.
6. Motor onto the plate, 2x M4. Its body hangs past the frame in free air.
7. Two M3 in through the end face until they touch the idler bearings, then evenly until
   the belt stops being floppy. Belt tension holds the bearings back — nothing clamps.
8. **Calibrate.** Mark the belt, film it, fit measured mm/s against commanded step rate.
   The theoretical 10.7 µm/step is the ceiling, not the answer.

## Verification that actually ran

`part="clash"` intersects the frame with the motor, belt, both pulleys and the shaft.
It renders **empty**. Checked against two deliberate failures (relief removed; idler
driven 12 mm past its slot) — both detected, so the check is not vacuous. Nine
`assert()`s in the .scad fail the render if the dimensions stop agreeing.

## Still open, deliberately

- **No chamber.** Belt top is at z = 22.63. Pulley flanges reach 23.25, so the chamber
  cannot simply sit across them — it bridges between the pulleys or sits inside the
  flange gap. That is the next problem.
- **The camera can only see from +y.** The motor plate closes the −y side over the
  drive half. The low window is the +y wall, x = −35 to +1.

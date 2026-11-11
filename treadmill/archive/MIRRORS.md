# Mirror geometry — the math, and what it rules out

Sensor: Basler acA800-510um, 800 x 600 px, 4.8 um pixels = **3.84 x 2.88 mm**.
Field needed for one view: 9.5 mm walking region + margin = **12 mm**.

## 1. One view filling the sensor
    magnification m = 3.84 / 12 = 0.32x
    sampling        = 15.0 um/px
    fly (2.04 mm)   = 136 px across

Depth of field at m = 0.32, circle of confusion = 2 px:

| aperture | total DOF |
|---|---|
| f/5.6 | 1.39 mm |
| f/8   | 1.98 mm |
| f/11  | 2.72 mm |
| f/16  | 3.96 mm |

## 2. The rule a 45 deg mirror imposes
A mirror at lateral distance **L** from the subject adds **exactly L** to the optical
path. So for a camera to hold both a direct view and its mirrored view in focus:

    L < DOF

At m = 0.32 that means L would have to be under ~2 mm — physically impossible, the
chamber alone is 10 mm wide. Therefore:

> **Never put a direct view and a mirrored view on the same camera.**
> **Two mirrors at equal L are always co-focal with each other** — that pairing is free.

This is why `mirror_L` is one parameter used for both mirrors in the CAD. If you nudge
one mirror in and the other out, you have silently defocused one of your two views.

## 3. What tiling costs you
Putting n views on one sensor multiplies the field by n:

| views | camera | sampling | fly width |
|---|---|---|---|
| 2 | acA800 (800 px)  | 30.0 um/px | 68 px |
| 2 | OV9281 (1280 px) | 18.8 um/px | 109 px |
| 3 | acA800 (800 px)  | 45.0 um/px | 45 px |
| 3 | OV9281 (1280 px) | 28.1 um/px | 73 px |

The paper's tracking worked at 15 um/px. Two views on an OV9281 (18.8) is the only
tiling option that stays close. Three views on an 800 px sensor is not usable for legs.

## 4. So what do mirrors actually buy?
**Packaging, not camera count.** At this magnification each view wants a whole sensor,
so mirrors do not let you delete cameras — they let you put the cameras somewhere
sensible (all above the rig, out of the belt plane) instead of crowding five lenses
around a 10 mm chamber. That crowding is visible in Fig. S3B of the paper.

Use them when: bench space or working distance is the constraint.
Skip them when: you can simply aim another camera at the chamber.

## 5. Numbers the CAD uses
    fly_z        = floor_z + 0.75      // middle of the 1.5 mm channel = 32.90 mm
    mirror_L     = 22 mm               // both mirrors, identical
    mirror tilt  = 45 deg about X      // folds the across-belt view upward
    mirror size  = 25 mm               // half-extent along the fold = 25/sqrt(2) = 17.7 mm
    post height  = fly_z - 17.7/2 - 2  // puts the mirror centre level with the fly

Change `mirror_L` in treadmill_frame.scad and both mirrors move together, which is the
only way they are allowed to move.

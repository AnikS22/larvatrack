# MINI treadmill — complete, one plate

`mini_treadmill_COMPLETE.stl` — every part on one 250 x 210 bed. One print, working machine.

    about 18 g at 15% infill
    no supports
    bed usage  X 8..245   Y 8..178   of 250 x 210
    0 overlaps, tightest gap 2.20 mm

Slicer: 0.4 nozzle, 0.2 mm layers, PLA, 15% infill, 2 perimeters — the config from your
last fly_treadmill print. It lives on the USB at `fly_treadmill/slicer_config_MK4_PLA.ini`
(the drive unmounted before I could copy it across).

## This is built on the MINI, not the big conveyor

Earlier I used `New_Conveyor_Belt.3mf` (Jan 30). Wrong file —
`Mini_Conveyor_Belt_New.3mf` (Apr 9) is newer and is a much smaller machine:

| | New (what I used first) | **Mini (this)** |
|---|---|---|
| rail | 150 x 42 x 32.5 | **150 x 34 x 20.5** |
| roller | 19.2 x 60 | **19.2 x 36** -> 36 mm belt, not 60 |
| drive wheel | 46 | **34** |
| chain link | 60 x 11 x 4 | **36 x 10.6 x 4** |
| whole print | ~34 g | **~18 g** |

## What's on the plate

| part | qty | note |
|---|---|---|
| rail_short80 | 2 | Mini rail with 70 mm cut out of its middle |
| chain link | 20 | 18 needed + 2 spare |
| hinge pin | 24 | laid flat, not standing |
| roller | 2 | 36 long, prints standing so journals stay round |
| drive wheel | 1 | |
| shaft collar | 2 + 1 wide | |
| rail connector | 2 | |

Individual `part_*.stl` files are the same parts alone. `_xN` is the quantity.

## The only modified part

The Mini rail is 150 long with end tabs in x 0..33 and x 117..150, and featureless
extrusion between. 70 mm was cut out of that middle and the ends butted back together:
**150 -> 80 mm**. That is what brings the rollers together.

Verified: 80.0 mm, watertight, 0 non-manifold edges, normals correct, 8.0 g.

`rail_cut = 70` in `../mini/plate.scad`. Cut boundaries must stay inside the featureless
zones (x 33..75 and 78..117), so keep `rail_keep_lo` at 40 and `rail_cut` under ~77.

## Why 20 links

    80 mm rail -> roller centres ~64 mm apart
    loop = 2 x 64 + pi x 19.2 = 188 mm
    188 / 10.6 mm link pitch = 17.8  ->  18 links, 20 printed

Estimated from rail geometry, not a measured wrap. A chain doesn't care — assemble until
the loop closes, add or drop one. Spare pins are on the plate for that.

## No bearings

The kit uses none and is right not to: rollers journal straight into printed holes in the
end tabs, and the load is a 1 mg fly.

## Not done

**28BYJ-48 mount.** The kit's `USB-TT-Motor-Upgrade` and `New_Gear_Motor_Upgrade` show the
pattern — they change only the drive-side rail and the 8 x 8 shaft collar. Both plate rails
here are plain, so as printed there is no way to drive it.

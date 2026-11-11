# Fly treadmill — complete build spec
Everything below is measured or derived from the model. Build it in Fusion 360 from these
numbers; nothing else is needed.

## The machine, in one paragraph
A motor turns a 20-tooth GT2 pulley mounted straight on its output shaft. A 200 mm GT2 belt
runs from that pulley to a second, identical pulley at the far end, which spins freely on a
5 mm shaft in two bearings. Pratt's 3D-printed chamber sits over the top run of the belt,
with its own floor removed — the moving belt IS the floor. A fly placed inside is carried
backwards and has to walk forwards to stay put.

## Bought parts
| part | spec | qty |
|---|---|---|
| Belt | GT2 / 2GT closed loop, 200 mm (100 teeth), 6 mm wide | 1 |
| Pulley | GT2 20-tooth, 6 mm bore, 6 mm belt, flanged (drive) | 1 |
| Pulley | GT2 20-tooth, 5 mm bore, 6 mm belt, flanged (idler) | 1 |
| Bearing | MR105ZZ, 5 x 10 x 4 mm | 2 |
| Shaft | 5.0 mm ground rod, cut to 48 mm | 1 |
| Motor | any gearmotor with a 6 mm output shaft (Phidgets 3263E_1 = 12 V, 51:1, 78 rpm, encoder) | 1 |
| Screws | M3 x 16 + M3 nut (holders) | 4 + 4 |
| Screws | M3 x 10 (motor face — its threads are only 6 mm deep) | 4 |
| Coverslips | 22 x 22 mm, #1 | 1 box |
| Chamber | Treadmill_Chamber.stl, SLA in black resin | 1 |

## The one number everything hangs off
    shaft axis height  = 16.00 mm above the frame floor
Then:
    pulley pitch diameter  12.73      (20 teeth x 2 mm / pi)
    pulley tip diameter    12.22
    belt top surface       16.00 + 12.73/2 + 0.63 = 22.996  -> 23.00 mm
    chamber floor          23.00 + 0.15 clearance           = 23.15 mm
Change the shaft height and everything else follows. Do not set these independently.

## Belt sets the span, not the other way round
    belt length L = 2 x span + teeth x pitch
    20T GT2 -> the tail term is exactly 40 mm
    L = 200  ->  span = 80.0 nominal
    BUILD AT 78.0 and slide the idler out ~2 mm to tension it.
    (158 -> 59   |   200 -> 80   |   280 -> 120   |   300 -> 130)

## Frame — one piece
    overall            116.2 long x 35 wide x 29 tall
    two side walls     4 mm thick, inner faces at +/-12.0 (24.0 mm gap)
    floor              3 mm thick
    wall height        29 at each end (bearing/motor region), 11 in the middle
                       -- the low middle is so the camera can see the chamber
    drive wall         thickened to 5 mm locally, with two buttresses (the motor is 193 g)

### Holes in the frame
    drive end,  x = -39.0, z = 16.0
        motor pilot recess   17.0 dia x 2.6 deep, on the OUTER face
        motor bolts          4 x 3.4 dia on a 22.0 mm bolt circle, 90 deg apart
        shaft clearance      8.0 dia through
    idler end,  x = +42.5, z = 16.0
        shaft slot           5.8 dia, 7 mm of travel along x
        holder bolt slots    2 x 3.3 dia, 7 mm travel, at x = +32.5 and +52.5

## Bearing holder — print 4... no, print 2
    26 x 20 x 6.5 mm
    bore pocket   9.90 dia x 4.2 deep from one face   (bearing is 10.00 -> 0.10 press fit)
    shoulder      2.3 mm behind it, with a 5.6 dia shaft hole
    bolts         2 x 3.3 dia at +/-10.0 from the bore centre, with M3 nut pockets
    Print it bore-UP so the pocket comes out round.

## Every fit, along the shaft axis (mm from the belt centreline)
    belt                   -3.18 .. +3.18
    pulley belt channel    -3.50 .. +3.50      0.16 mm each side
    frame wall             12.0 .. 16.0
    bearing holder         16.0 .. 22.5
    bearing in its pocket  18.3 .. 22.5
    idler shaft            spans +/-22.5, so cut it 48 mm (1.5 proud each end)

## Drive: no coupler, no second shaft
The motor's own 6 mm output shaft carries the drive pulley directly, exactly like a 3D
printer drives its belts off a stepper. With the motor face 17.0 mm out from the belt
centreline and a 16.7 mm shaft, 10.2 mm of shaft sits inside the pulley hub. The grub
screw clamps there.

## Speed
    belt speed = pulley circumference x rpm / 60 = 40 mm x rpm / 60
    Pratt's five speeds: 3.9, 7.4, 10.9, 14.4, 17.9 mm/s
      -> 5.9, 11.1, 16.4, 21.6, 26.9 rpm at the pulley
    CALIBRATE THIS. Mark the belt, film it, measure mm/s against commanded rpm, and fit
    the line. Pratt's own code uses empirical constants, not theoretical ones, for exactly
    this reason.

## Camera
Chronos 2.1-HD, 19.2 x 10.8 mm sensor, 10 um pixels, 1920x1080 at 1000 fps.
    side view, 12 mm field  ->  1.6x magnification, 6.25 um/px  (the paper managed 15)
    optical axis sits 33.5 mm above the camera's base
    fly sits 23.9 mm above the frame floor
    -> put the treadmill on a 9.6 mm riser if both sit on one flat surface
    stop down to f/22 — the channel is 1.5 mm deep and f/16 only holds 1.28 mm
    back-light through the far coverslip; at 1000 fps you have under 1 ms of exposure

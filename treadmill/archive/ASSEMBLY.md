# Hole schedule and assembly order
Desk-mounted build. No extrusion, no rails — a printed **baseplate** holds the geometry.

Fasteners: **M3 only.** Nothing threads into bare plastic; every screw meets a steel nut
or a tapped hole in the motor.

## Hole schedule

| # | Joint | Fastener | Clearance side | Thread side |
|---|---|---|---|---|
| 1 | bracket -> baseplate (x2) | M3x12, 2 each | foot slot 3.3 + 6.4 cbore, 10 mm travel | **M3 nut in the baseplate's underside pocket** |
| 2 | motor plate -> baseplate | M3x12 x2 | foot slot, 8 mm travel | M3 nut, underside pocket |
| 3 | motor cradle -> baseplate | M3x12 x2 | foot slot, 8 mm travel | M3 nut, underside pocket |
| 4 | pillar -> baseplate | M3x12 x2 | foot slot, 14 mm travel | M3 nut, underside pocket |
| 5 | **motor -> motor plate** | **M3x10 x4** | plate 3.4 on a **22.0 mm bolt circle, 90 deg apart** | **the motor's own M3 holes, 6.0 mm deep** |
| 6 | jaw -> pillar | M3x16 x2 | jaw 3.3 + 6.4 cbore | M3 nut in the pillar T-slot |
| 7 | height jack | M3x20 x1 | — | M3 nut captive in the jaw tab, tip in the shelf dimple |
| 8 | chamber clamp | M3x12 x1 | — | M3 nut captive in the pocket boss |
| 9 | bearings -> bracket | press fit | 11.9 pocket, 4.2 deep | 1.8 mm shoulder |
| 10 | pulleys -> shafts | grub screws | supplied | — |
| 11 | coupler -> both shafts | grub screws | supplied | — |

**Totals:** 8x M3x12, 4x M3x10, 2x M3x16, 1x M3x20, 1x M3x12 (chamber), **14x M3 hex nuts**,
4x SMF126ZZ bearings, 6 mm rod cut to **45 mm** (idler) and **53 mm** (drive).

`M3x10` for the motor matters: its threads are only 6.0 mm deep and the plate is 6 mm, so
anything longer bottoms out before it clamps.

## Why a baseplate

Without extrusion, the baseplate is the only thing making the two pulley shafts parallel and
the motor coaxial with the drive shaft. Its ten mounting holes are generated from the same
variables as the parts, so they cannot drift apart. Nut pockets are on the **underside**, which
prints face-down on the bed: no bridging, no captive-nut pause.

## Motor, from the Phidgets mechanical drawing

    4 x M3 threaded, 6.0 mm deep, on a 22.0 mm bolt circle, 90 deg apart
    pilot boss ~16 dia, 2.0 mm proud   (the plate's recess is 17.0 x 2.6 — deliberately loose,
                                        so it cannot fight the four screws for location)
    shaft 6 mm with a flat, 16.7 mm from the face
    body 28.0 dia; gearbox 48.5 + can 37.5 + tail 9.0 + encoder
    ~100 mm of motor and 193 g hanging off the face -> hence the cradle under the gearbox

## Assembly order

1. Print everything. Drop **14 M3 nuts** into the baseplate's underside pockets and the
   captive pockets in the jaw, then set the plate down — the desk holds the nuts in.
2. Press a **bearing** into each bracket plate from the OUTER face until it stops on the
   shoulder. Four total.
3. Drop a **pulley** into each bracket's open top, then slide the shaft through
   bearing -> pulley -> bearing. 45 mm idler, 53 mm drive. Leave the grub screws loose.
4. Bolt both brackets down loosely, roughly at span.
5. Slip the **belt loop** over both pulleys — it passes under them through the gap above
   the feet, so nothing has to come apart.
6. Drop the **span gauge** over both protruding shaft ends. Push the brackets until it
   seats: parallel and exactly `span` apart. Tighten the idler, remove the gauge.
7. Slide the drive bracket out ~2 mm to tension the belt, tighten it, then tighten the
   pulley grub screws.
8. Bolt the **motor** to the motor plate with 4x M3x10. Bolt the plate and the **cradle**
   to the baseplate. Fit the **coupler** over both 6 mm shafts, align, tighten its grubs.
9. Bolt the **pillar** down. Drop 2 M3 nuts into the top of its T-slot.
10. Slide the **jaw** down over the pillar plate until the clamp holes meet the nuts.
    Fit M3x16 loosely. Fit the jack nut and run the M3x20 down onto the shelf dimple.
11. Slide the **chamber** into the jaw pocket from either end; the chamfers guide it past
    the grip ribs. Nip the M3x12 clamp screw.
12. Set height with the jack screw until the chamber floor clears the belt by 0.15 mm,
    then tighten the two clamp screws.

## Print orientation

| Part | Orientation | Note |
|---|---|---|
| baseplate | flat, **nut pockets down** | biggest part; pockets print on the bed |
| bracket x2 | foot on the bed | bearing bore is horizontal; its crown sags ~0.2 mm and self-broaches |
| motor plate | foot on the bed | gussets support it |
| motor cradle | foot on the bed | the 28 mm saddle is a bridge at its crown |
| pillar | foot on the bed | T-slot prints as a vertical channel |
| jaw | **pocket opening UP** | roof on the bed, ribs as vertical walls |
| gauge | flat on its face | zero overhang |

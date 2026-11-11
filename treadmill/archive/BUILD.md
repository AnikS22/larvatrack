# Fly treadmill build — cheap everything, real cameras
Based on Pratt et al. 2024, Current Biology (PDF + Fig. S3 blueprint in this folder).
Code: github.com/Prattbuw/Treadmill_Paper

Cameras stay machine-vision grade. Everything around them gets the cheap swap.
Prices are estimates — get quotes before budgeting.

## Imaging — the part we are NOT cutting
| Qty | Item | Part | ~$ ea |
|---|---|---|---|
| 2–5 | USB3 mono global-shutter camera | Basler **acA800-510um** (active; successor to the paper's acA800-600um; 800x600, 511 fps max, you run 180) | 400–500 |
| 2–5 | Macro lens | Computar MLM3X-MP | 400 |
| 2–5 | 850 nm bandpass filter | Midopt BP850 / FS03-BP850-34 | 100 |
| 2–5 | Locking USB3 cable, 3 m | Basler / Newnex | 30 |

Cut camera COUNT, not camera quality: 2 cameras + 2 first-surface mirrors at 45° give 4 views
for 3D triangulation (calibrate each virtual view as its own camera in Anipose).
~$1,900 of imaging instead of ~$4,750, losing pixels per view, not sensor quality.
Optional fallback if budget bites: C-mount 25 mm + extension tubes (~$60) instead of the
Computar — costs you working distance and flatness, not frame rate.

## Everything else (~$230)
| Item | Part | ~$ |
|---|---|---|
| **Motor** | **NEMA 17 stepper, 42 mm face, 5 mm shaft** (any 34–48 mm body; 1.5–2 A) + **TMC2209** driver + 12 V 2 A supply. Run at 1/16 microstep = 12.5 um of belt per step | 35 |
| Coupler | 5 mm to 5 mm rigid shaft coupler, 25 mm long | 5 |
| Motor control | Arduino/Teensy (also emits the camera TTL) | 0–25 |
| **Belt** | **GT2 / 2GT closed loop, 200 mm (100 teeth), 6 mm wide** — e.g. BTRKT 200-2GT-6, 5-pack. Verified: 100 x 2 mm = 200 mm, sets span to 80 (file uses 78 for take-up) | 7 |
| **Pulleys** | **2x GT2 20-tooth, 5 mm bore, 6 mm belt width, flanged, with grub screws** — must say 6 mm, a 10 mm pulley will not hold a 6 mm belt straight | 8 |
| Bearings + shafts | 686ZZ or MF126ZZ + 6 mm rod | 15 |
| Chamber | Treadmill_Chamber.stl → SLA print service, black resin | 40 |
| Chamber walls | #1 coverslips 22x22 mm (EMS 72200-10) + Rain-X on inner faces | 38 |
| Brackets | 3D printed, or aluminum angle from a hardware store | 20 |
| Light | 850 nm IR LED illuminator board + baking-paper diffuser | 15 |
| Base | 20x20 extrusion or MDF slab + printed camera cradles | 60 |
| Sync | Arduino square wave at 180 Hz → all camera trigger lines | 0 |

Why the stepper: the paper's Phidget gearmotor + encoder + PID stack ($160) exists to hold belt
speed against load. The load is a 1 mg fly. A microstepped stepper holds commanded speed
open-loop. 18 mm/s on a 20T GT2 pulley is ~27 rpm — far below any stepper limit.

## Totals
| Build | Imaging | Rest | Total |
|---|---|---|---|
| 2 cameras + mirrors | ~$1,900 | ~$230 | **~$2,100** |
| 3 cameras + mirrors | ~$2,800 | ~$230 | ~$3,000 |
| 5 cameras (as published) | ~$4,750 | ~$230 | ~$5,000 |
| Paper's full parts list | — | — | $7,000–9,000 |

## Build order
1. Print chamber; Rain-X the inner coverslip faces; glue coverslips into the slots.
2. Pulleys on shafts in bearings, two brackets, belt between them; chamber sits over the belt so
   the belt IS its floor. Bracket spacing = belt tension.
3. Stepper drives one pulley directly (skip the paper's spur-gear pair).
4. Wire stepper → TMC2209 → Arduino; same Arduino outputs the 5 V frame-sync square wave.
5. CALIBRATE before trusting any number: belt speed = (step_rate / steps_per_rev) x teeth x pitch.
   GT2 = 2 mm pitch, so a 20T pulley = 40 mm/rev. Then mark the belt, film it, and fit measured
   mm/s vs commanded step rate. This is the one knob that makes the data real.
6. Mount cameras + mirrors, focus on the chamber, IR light + filters, check sync, record.

## Code changes to the repo scripts
- Delete the Phidget22 PID block; send step-rate commands over serial instead.
- Keep the pypylon camera setup as written — it is Basler-specific and you kept Basler.
- Replace subprocess_daq_trigger.py (nidaqmx) with a serial write to the Arduino.
- Scripts are Windows-only as published (they import msvcrt); swap that for input polling on
  macOS/Linux.

## Reference — the paper's original parts (for ordering identical spares)
Chamber: Formlabs Form 2, black resin RS-F2-GPBK-04. Walking region 8.929 x 8 x 1.5 mm, outer
40 x 16 x 10 mm. Pulleys B&B 28MP025M6FA6, belt B&B 100MXL025UK, bearings AST SMF126ZZ.
Motor Phidgets 3256E_0 (12V, 0.8 kg-cm, 46 RPM, 50:1, encoder); controller Phidgets 1065_1B
(now NRND → DCC1000_0 + HUB0000 VINT hub). Light Smart Vision Lights R130-850. Cameras 5x
Basler acA800-600um @ 180 fps, Computar MLM3X-MP, FS03-BP850-34 filters. Sync NI BNC-2110.
PID: Kp 0.75, Ki 1, Kd 0.2; r 13.5001 mm, GR 50, duty-cycle slope 70.
Split-belt: belts 100MXL012UK, pulleys 28MP012M6FA6, 2x motors Phidgets 3263E_1, 200 fps.
Contact for anything unpublished (brackets, gear pair): tuthill@uw.edu

---

## Printable frame — treadmill_frame.scad
Parametric OpenSCAD source for the parts the paper never published. Edit the numbers at the
top to match the pulley/bearing/motor you actually buy, then re-render:

    openscad --export-format binstl -D 'part="bracket"' -o part_bracket.stl treadmill_frame.scad

Parts (STLs already rendered in this folder):
- part_bracket.stl (print 2) — holds an MR105ZZ bearing each side of a 5 mm shaft carrying the
  GT2 pulley. Feet are slotted: sliding one bracket away from the other IS the belt tensioner.
- part_motor_mount.stl — NEMA 11 face mount, shaft coaxial with the pulley shaft, join with a
  5–5 mm rigid coupler. No gear pair needed.
- part_chamber_holder.stl — post with a vertical slot + a jaw that grips the chamber's
  40 x 10 x 3.25 mm top flange. The slot is how you set chamber-floor-to-belt clearance.
- part_mirror_mount.stl — 45 deg cradle for a 25 mm first-surface mirror.

Key derived number, echoed on every render: with shaft_h = 20 and a 20T GT2 pulley the belt
top surface lands **27.0 mm** above the base plate, and the chamber floor sits at 27.17
(ch_gap = 0.15 mm). Change shaft_h and everything else follows.

Chamber geometry, measured from Treadmill_Chamber.stl rather than the figure:
outer 40 (along belt) x 10 (across) x 16 (tall); top flange y 12.75–16; the fly walks in the
1.5 mm slot at the very bottom, so the chamber hangs down onto the belt.

Print notes: PETG or PLA, 0.2 mm, 4 perimeters, 40% infill. Print brackets on their feet so
the bearing bore is vertical. brg_fit = -0.1 is a press fit; loosen to +0.1 if your printer
runs tight. Test-print one bracket before committing to the set.

## Open-source alternative, if you want something already validated
There is no open-source LINEAR insect treadmill — Pratt's is the only published one and only
the chamber was released. The closest open design is a SPHERICAL (ball) treadmill:
"An Inexpensive, High-Precision, Modular Spherical Treadmill Setup Optimized for Drosophila
Experiments", Front. Behav. Neurosci. 2021 — 3D-printable, off-the-shelf parts, ~180 Hz.
Different experiment: the fly is tethered and walks in place, so you measure fictive path
rather than compelling real locomotion. Pratt built the linear rig precisely because tethered
kinematics differ from free walking.

// =====================================================================
// Linear fly treadmill — printable frame for the Pratt et al. 2024 chamber
// Base: 20x20 T-slot extrusion. Motor: NEMA 17. Direct drive, no gear pair.
//
// Everything is referenced to ONE datum: the TOP FACE of the main rail (z=0).
// shaft_h sets the belt line; every other height is derived from it, so the
// two pulleys, the motor shaft and the chamber floor cannot drift out of line.
//
// Render:  openscad --export-format binstl -D 'part="bracket"' -o part_bracket.stl treadmill_frame.scad
// View:    part="assembly" (default) or "section"
// =====================================================================

part = "assembly";
// "assembly" | "section" | "parts"
// "bracket" | "motor_mount" | "pillar" | "jaw" | "mirror_mount"

/* ============ 1. WHAT YOU BOUGHT ============
   These are OpenSCAD Customizer parameters: open Window > Customizer in the GUI
   and edit them with sliders/boxes instead of typing in the file.
   Measure with calipers. Every other dimension in this file is derived. */

/* [Motor - Phidgets 3263E_1, from the official mechanical drawing] */
// bolt circle diameter, mm — 4 x M3 at 90 deg (drawing: "22.0", "M3 Depth 6.0")
motor_bolt    = 22.0;
// mounting screw clearance, mm
motor_screw   = 3.4;
// pilot boss recess diameter, mm — generous, the 4 screws do the locating
motor_boss_d  = 17.0;
// pilot boss recess depth, mm — the boss stands 2.0 proud of the face
motor_boss_h  = 2.6;
// motor body diameter, mm
motor_body    = 28.0;
// motor shaft diameter, mm
motor_shaft   = 6.0;
// shaft length from the mounting face, mm
motor_shaft_l = 16.7;
// gearbox length, mm (3263 row of the drawing's table)
motor_gearbox = 48.5;
// motor can length, mm
motor_can     = 37.5;
// terminals + E4P encoder behind the can, mm (estimate — measure yours)
motor_tail    = 22;
// rigid coupler, 6 mm to 6 mm
coupler_len   = 25;
coupler_od    = 16;

/* [Belt and pulleys] */
// teeth on the drive pulley
teeth       = 28;          // B&B 28MP025M6FA6, Pratt's exact pulley
// belt tooth pitch, mm (GT2 = 2.0, MXL = 2.032)
belt_pitch  = 2.032;       // MXL, 0.080 in — NOT GT2
// pulley overall length including hub, mm
pulley_len  = 16;
// width of the belt channel between the flanges, mm
pulley_belt_w = 7.2;
// pulley flange diameter, mm
pulley_fl   = 22;
// pulley hub diameter, mm
pulley_hub  = 16;
// belt width, mm
belt_w      = 6.35;        // 1/4 in, B&B 100MXL025UK
// total belt thickness, mm
belt_th     = 1.38;
// belt thickness above the pitch line, mm
belt_back   = 0.63;
// pulley centre to pulley centre, mm.
// DO NOT pick this freely - a closed-loop belt sets it:
//     belt length L = 2*span + teeth*belt_pitch     (both pulleys the same size)
// With a 20T GT2 pulley that tail term is exactly 40 mm, so:
//     L=158 -> span 59    L=200 -> span 80    L=280 -> span 120    L=300 -> span 130
// Set span ~2 mm SHORT of nominal and slide the idler bracket out to tension.
span        = 71;          // 100MXL belt gives 73.15 nominal; 2 mm short for take-up

/* [Bearings and shaft] */
// bearing outside diameter, mm (MR105ZZ = 10)
brg_od      = 12;          // AST SMF126ZZ, Pratt's exact bearing
// bearing bore, mm
brg_id      = 6;
// bearing width, mm
brg_w       = 4;
// bearing seat fit: negative = press fit. Loosen toward +0.1 if your printer runs tight
brg_fit     = -0.10;
// shaft diameter, mm
shaft_d     = 6;           // 6 mm, matches the 3263E_1 motor shaft
// height of the shaft axis above the rail top, mm - THIS SETS THE WHOLE BELT LINE
shaft_h     = 25;

/* [Base plate - it just sits on a desk] */
// baseplate thickness, mm
base_t      = 5;
// main rail to chamber-pillar centreline, mm
side_offset = 55;
// M3 clearance in the parts' feet, mm
foot_screw  = 3.3;
// screw head counterbore, mm
foot_cbore  = 6.4;

/* [Chamber - measured from Treadmill_Chamber.stl, do not change] */
// chamber length along the belt, mm
ch_len      = 40;
// chamber width across the belt, mm
ch_w        = 10;
// chamber floor to top of flange, mm
ch_h        = 16;
// top flange thickness, mm
ch_flange_h = 3.25;
// chamber floor to belt clearance, mm - set this under a scope, not by eye
ch_gap      = 0.15;

/* [Print settings] */
// nominal wall thickness, mm
wall        = 3;
// M3 clearance, mm
m3          = 3.3;
// M3 nut across flats, mm
m3_nut      = 5.6;
// sliding fit clearance, total across a dimension, mm. Raise if the sleeve binds.
slide_fit   = 0.7;
// chamber pocket width clearance before ribs, mm
grip_gap    = 0.5;
// how far each grip rib stands proud of the pocket wall, mm
grip_rib    = 0.35;
// roof thickness above the chamber flange, mm
roof        = 3;

/* [Hidden] */
eps         = 0.01;
key_h       = 1.6;

/* ============ 2. DERIVED - do not edit ============ */
fly_z_marker = 0;   // kept for reference; the fly walks at floor_z + 0.75
pulley_pd = teeth * belt_pitch / PI;             // pitch diameter
pulley_od = pulley_pd - 0.508;                   // tooth-tip diameter (GT2)
belt_top  = shaft_h + pulley_pd/2 + belt_back;   // top surface of the belt
floor_z   = belt_top + ch_gap;                   // where the chamber floor lands
flange_z  = floor_z + ch_h - ch_flange_h;        // underside of the chamber flange
brk_inner = 2*(pulley_len - pulley_belt_w/2) + 3;
brk_w     = brk_inner + 2*wall;

/* ============ 3. HARDWARE (reference only, not printed) ============ */

module pulley() {
    color("gold") difference() {
        union() {
            cylinder(d=pulley_od, h=pulley_belt_w, $fn=64);
            for (z=[0, pulley_belt_w-1.2]) translate([0,0,z]) cylinder(d=pulley_fl, h=1.2, $fn=64);
            translate([0,0,-(pulley_len-pulley_belt_w)]) cylinder(d=pulley_hub, h=pulley_len-pulley_belt_w, $fn=48);
        }
        translate([0,0,-pulley_len]) cylinder(d=shaft_d, h=pulley_len*3, $fn=32);
        // GT2 teeth: 20 rounded grooves on the pitch circle
        for (a=[0:360/teeth:359]) rotate([0,0,a]) translate([pulley_od/2, 0, -1])
            cylinder(d=1.1, h=pulley_belt_w+2, $fn=16);
    }
}

module belt() {
    color("#222222") rotate([90,0,0]) linear_extrude(belt_w, center=true)
        difference() {
            hull() for (x=[-span/2, span/2]) translate([x, shaft_h]) circle(d=pulley_pd+2*belt_back, $fn=72);
            hull() for (x=[-span/2, span/2]) translate([x, shaft_h]) circle(d=pulley_pd-2*(belt_th-belt_back), $fn=72);
        }
}

motor_y      = brk_w/2 + coupler_len + 10;   // mounting-face plane
cradle_y     = motor_y + 40;                 // body support, on the gearbox

module phidget_motor() {
    color("#3a3a3a") translate([0, 0, shaft_h]) rotate([-90,0,0]) {
        translate([0,0,motor_y]) cylinder(d=motor_body, h=motor_gearbox, $fn=64);
        translate([0,0,motor_y + motor_gearbox]) cylinder(d=motor_body - 3, h=motor_can, $fn=64);
        translate([0,0,motor_y + motor_gearbox + motor_can]) cylinder(d=motor_body - 8, h=motor_tail, $fn=48);
        translate([0,0,motor_y - 2]) cylinder(d=16, h=2, $fn=48);                 // pilot boss
        translate([0,0,motor_y - motor_shaft_l]) cylinder(d=motor_shaft, h=motor_shaft_l, $fn=32);
    }
}

module coupler() {
    color("#9a9a9a") translate([0, brk_w/2 + 4, shaft_h]) rotate([-90,0,0])
        difference() {
            cylinder(d=coupler_od, h=coupler_len, $fn=48);
            translate([0,0,-1]) cylinder(d=shaft_d, h=coupler_len+2, $fn=32);
        }
}

module shaft(len) {
    // along Y — same axis as the bearings. This was the 90 deg error.
    color("#b8b8b8") rotate([-90,0,0]) cylinder(d=shaft_d, h=len, center=true, $fn=32);
}

/* ============ 4. PRINTED PARTS ============ */

// ---- foot that bolts to the baseplate ----
// No rails: the baseplate is what holds alignment. Each foot has two slots so the part
// can still be positioned, and an M3 drops through into a captive nut under the plate.
module rail_foot(len, w, t, travel) {
    difference() {
        translate([0,0,t/2]) cube([len, w, t], center=true);
        for (x=[-1,1]) translate([x*(len/2 - 8), 0, -1]) {
            hull() for (q=[-travel/2, travel/2]) translate([q,0,0]) cylinder(d=foot_screw, h=t+2, $fn=24);
            translate([0,0,t-1.5]) hull() for (q=[-travel/2, travel/2])
                translate([q,0,0]) cylinder(d=foot_cbore, h=4, $fn=24);
        }
    }
}

// ---- pulley bracket (print 2) : slots = belt tensioner ----
// The bearing needs a SEAT, not a hole. A boss on the outer face gives a 4.2 mm deep
// pocket and leaves a 1.8 mm shoulder, so the bearing presses in from outside and
// stops against the shoulder instead of wandering through the plate.
boss_extra = 3;                       // extra thickness at the bearing, outer face
brg_seat   = brg_w + 0.2;             // pocket depth
shoulder   = wall + boss_extra - brg_seat;

module bracket_plate(dir) {
    difference() {
        union() {
            hull() {
                translate([0, 0, 2]) cube([34, wall, 4], center=true);
                translate([0, 0, shaft_h]) rotate([90,0,0])
                    cylinder(d=brg_od + 2*wall, h=wall, center=true, $fn=64);
            }
            translate([0, dir*(wall + boss_extra)/2, shaft_h]) rotate([90,0,0])
                cylinder(d=brg_od + 2*wall, h=boss_extra, center=true, $fn=64);
        }
        // bearing pocket, open at the OUTER face only
        translate([0, dir*(wall/2 + boss_extra - brg_seat/2 + eps), shaft_h]) rotate([90,0,0])
            cylinder(d=brg_od + brg_fit, h=brg_seat, center=true, $fn=64);
        // shaft clearance through the shoulder
        translate([0, 0, shaft_h]) rotate([90,0,0])
            cylinder(d=shaft_d + 0.6, h=40, center=true, $fn=32);
    }
}

module bracket() {
    union() {
        for (y=[-1,1]) translate([0, y*(brk_inner + wall)/2, 0]) bracket_plate(y);
        rail_foot(34, brk_w, 5, 10);
    }
}

module bearings() {
    for (y=[-1,1]) translate([0, y*((brk_inner + wall)/2 + wall/2 + boss_extra - brg_seat/2), shaft_h])
        rotate([90,0,0]) color("#c8c8c8") difference() {
            cylinder(d=brg_od, h=brg_w, center=true, $fn=48);
            cylinder(d=brg_id, h=brg_w + 1, center=true, $fn=32);
        }
}

// ---- motor mount: face plate + body cradle ----
// Drawn to the Phidgets mechanical drawing: 4 x M3 on a 22.0 mm bolt circle, 90 deg
// apart, with a pilot boss 2.0 proud of the face. The 4 screws locate the motor; the
// boss recess is deliberately loose so it cannot fight them.
// The motor is ~100 mm long and 193 g, so it gets a second support under the gearbox
// rather than hanging off four M3 screws.
plate_t = 6;

module motor_plate() {
    // Just enough material to carry the 22 mm bolt circle, on a blade down to the foot.
    // The old version was a 40 x 46 slab standing beside the drive pulley — more plastic
    // than the job needs and an obstruction when you are working the belt on.
    disc = motor_bolt + 12;                 // 34: bolt circle + edge for the screw heads
    difference() {
        union() {
            hull() {
                translate([0, motor_y - plate_t/2, shaft_h]) rotate([90,0,0])
                    cylinder(d=disc, h=plate_t, center=true, $fn=64);
                translate([0, motor_y - plate_t/2, 4]) cube([16, plate_t, 8], center=true);
            }
            translate([0, motor_y - plate_t/2 - 9, 0]) rail_foot(40, 24, 6, 8);
            hull() {   // gusset back to the foot
                translate([0, motor_y - plate_t/2, 7]) cube([14, plate_t, 4], center=true);
                translate([0, motor_y - plate_t/2 - 15, 3]) cube([14, 4, 6], center=true);
            }
        }
        translate([0, 0, shaft_h]) rotate([90,0,0])
            cylinder(d=motor_shaft + 1.5, h=plate_t*4, center=true, $fn=32);
        translate([0, motor_y - motor_boss_h/2 + eps, shaft_h]) rotate([90,0,0])
            cylinder(d=motor_boss_d, h=motor_boss_h, center=true, $fn=48);
        for (a=[0:90:359]) translate([motor_bolt/2*cos(a), 0, shaft_h + motor_bolt/2*sin(a)])
            rotate([90,0,0]) cylinder(d=motor_screw, h=plate_t*4, center=true, $fn=24);
    }
}

module motor_cradle() {
    h = shaft_h;
    difference() {
        union() {
            translate([0, 0, h/2]) cube([motor_body + 4*wall, 12, h], center=true);
            translate([0, -15, 0]) rail_foot(40, 22, 6, 8);
        }
        translate([0, 0, shaft_h]) rotate([90,0,0]) cylinder(d=motor_body + 0.6, h=40, center=true, $fn=64);
        translate([0, 0, shaft_h + motor_body/2 + 10]) cube([motor_body - 6, 40, 20], center=true);
    }
}

module motor_mount() { motor_plate(); }

// ================= adjustable chamber pillar =================
// The pillar is a plate carrying a vertical T-SLOT, exactly like the extrusion.
// Standard M3 hex nuts drop into the top of it and slide. The jaw straddles the plate
// with two side ribs (no rotation, no racking) and clamps onto those nuts. A jack screw
// in the jaw stands on a shelf on the pillar and sets the height.
//
// Why not a sleeve on a square post: the post needs a cap to retain the lead screw, and
// any cap wide enough to retain it is too wide for the sleeve to pass over. That part
// could be drawn but never assembled.
arm_len    = side_offset;
flange_top = floor_z + ch_h;
jaw_x      = -20;

pil_w    = 26;
pil_t    = 10;
pil_h    = flange_top + 14;
ts_mouth = 3.8;      // T-slot mouth: the screw passes, the nut cannot
ts_w     = 6.3;      // channel width : M3 nut 5.5 across flats + clearance
ts_d     = 3.2;      // channel depth : M3 nut 2.4 thick
ts_lip   = 1.6;      // lip the screw head pulls the nut against
shelf_z  = 14;
sad_h    = 20;
rib_t    = 3;

module pillar() {
    difference() {
        union() {
            rail_foot(46, 26, 6, 14);
            translate([0, 0, pil_h/2]) cube([pil_w, pil_t, pil_h], center=true);
            translate([0, pil_t/2 + 6, shelf_z - 2.5]) cube([14, 12, 5], center=true);
        }
        translate([0, pil_t/2 - ts_lip/2 + eps, pil_h/2 + 10]) cube([ts_mouth, ts_lip + 0.1, pil_h], center=true);
        translate([0, pil_t/2 - ts_lip - ts_d/2, pil_h/2 + 10]) cube([ts_w, ts_d, pil_h], center=true);
        translate([0, pil_t/2 + 6, shelf_z - 1.2]) cylinder(d1=4, d2=0, h=2, $fn=24);
    }
}

// ---- jaw : straddles the plate and slides on from the top ----
// local z = 0 is the TOP face of the chamber flange.
module jaw() {
    sad_top  = -2;
    back_y   = -arm_len + pil_t/2;
    head_y   = back_y + 8;
    rib_x    = (pil_w + slide_fit)/2 + rib_t/2;
    difference() {
        union() {
            translate([0, back_y + 4, sad_top - sad_h/2]) cube([pil_w + 2*rib_t, 8, sad_h], center=true);
            for (x=[-1,1]) translate([x*rib_x, -arm_len, sad_top - sad_h/2])
                cube([rib_t, pil_t + slide_fit + rib_t, sad_h], center=true);
            translate([0, head_y/2, -7]) cube([14, -head_y, 12], center=true);
            hull() {
                translate([0, head_y, -7]) cube([14, 1, 12], center=true);
                translate([0, head_y + 16, -13]) cube([14, 1, 2], center=true);
            }
            translate([0, head_y + 2, sad_top - sad_h + 4]) cube([14, 12, 8], center=true);
            translate([0, 0, (roof - (ch_flange_h + 8))/2]) cube([18, ch_w + 2*wall, ch_flange_h + 8], center=true);
            translate([0, ch_w/2 + wall + 2, -ch_flange_h/2]) cube([12, 4, 7], center=true);
        }
        // two clamp screws -> M3 nuts sitting in the pillar T-slot
        for (z=[-6, -18]) translate([0, head_y, sad_top + z]) rotate([90,0,0]) {
            cylinder(d=m3, h=30, $fn=24);
            cylinder(d=6.4, h=4.5, $fn=24);
        }
        // jack screw + captive nut in the tab
        translate([0, head_y + 2, sad_top - sad_h - 6]) cylinder(d=m3, h=26, $fn=24);
        translate([0, head_y + 2, sad_top - sad_h + 2.4]) rotate([0,0,30]) cylinder(d=m3_nut/cos(30), h=2.6, $fn=6);
        translate([0, head_y + 10, sad_top - sad_h + 2.4]) cube([m3_nut - 0.7, 16, 2.6], center=true);
        // chamber pocket: roof above, open through the bottom, open both ends
        translate([0, 0, -10]) cube([28, ch_w + grip_gap, 20], center=true);
        for (x=[-1,1]) translate([x*9.5, 0, -ch_flange_h/2]) rotate([0,0,45*x])
            translate([0,0,-ch_flange_h]) linear_extrude(ch_flange_h*2)
                polygon([[0,-(ch_w+grip_gap)/2 - 2],[0,(ch_w+grip_gap)/2 + 2],[x*2.5,0]]);
        // chamber clamp screw: through a captive nut in the boss, tip onto the flange
        translate([0, ch_w/2 + wall + 4, -ch_flange_h/2]) rotate([90,0,0]) cylinder(d=m3, h=14, $fn=24);
        translate([0, ch_w/2 + wall + 1.4, -ch_flange_h/2]) rotate([-90,0,0]) rotate([0,0,30])
            cylinder(d=m3_nut/cos(30), h=2.6, $fn=6);
        translate([0, ch_w/2 + wall + 2.7, -ch_flange_h/2 + 8]) cube([m3_nut - 0.7, 2.6, 16], center=true);
    }
    for (y=[-1,1], i=[-3,-2,-1,1,2,3])
        translate([i*2.2, y*(ch_w + grip_gap)/2, -ch_flange_h/2])
            cube([0.9, grip_rib*2, ch_flange_h - 0.4], center=true);
}

// ---- baseplate: it just sits on a desk ----
// With no extrusion, THIS is what holds the geometry: the two pulley shafts parallel and
// the motor coaxial with the drive shaft. Every mounting hole is generated from the same
// variables the parts are, so they cannot drift apart.
// M3 drops through a part's slot, through the plate, into a hex nut in a pocket on the
// UNDERSIDE — which prints open-side-down on the bed, so no bridging and no captive-nut pause.
base_holes = [ [-span/2 - 9, 0], [-span/2 + 9, 0], [span/2 - 9, 0], [span/2 + 9, 0],
               [jaw_x - 15, -side_offset], [jaw_x + 15, -side_offset],
               [span/2 - 13, motor_y - 9], [span/2 + 13, motor_y - 9],
               [span/2 - 13, cradle_y],    [span/2 + 13, cradle_y] ];

module base_pad(x0, x1, y0, y1) {
    hull() for (x=[x0,x1], y=[y0,y1]) translate([x, y, -base_t/2]) cylinder(d=10, h=base_t, center=true, $fn=24);
}

module baseplate(pillar_arm = true) {
    difference() {
        union() {
            base_pad(-span/2 - 20, span/2 + 20, -20, 20);        // spine, both brackets
            base_pad(span/2 - 20, span/2 + 20, 14, cradle_y + 14); // motor arm
            if (pillar_arm) base_pad(jaw_x - 26, jaw_x + 26, -side_offset - 16, -14);
        }
        for (h = (pillar_arm ? base_holes : [for (q = base_holes) if (q[1] > -40) q])) translate([h[0], h[1], -base_t - 1]) {
            cylinder(d=foot_screw, h=base_t + 2, $fn=24);
            rotate([0,0,30]) cylinder(d=m3_nut/cos(30), h=3.0, $fn=6);   // nut pocket, underside
        }
    }
}

// ---- span gauge: drops over both protruding shaft ends on the -y side ----
// Sets pulley spacing AND parallelism in one move, then comes off. The previous version
// had its holes drilled vertically through a flat bar, so it could not fit over anything.
module gauge() {
    difference() {
        union() {
            translate([0, 0, shaft_h]) cube([span + 34, 4, 20], center=true);
            for (x=[-1,1]) translate([x*span/2, 0, shaft_h]) rotate([90,0,0])
                cylinder(d=16, h=4, center=true, $fn=48);
        }
        for (x=[-1,1]) translate([x*span/2, 0, shaft_h]) rotate([90,0,0])
            cylinder(d=shaft_d + 0.3, h=10, center=true, $fn=32);
    }
}

module assembly() {
    baseplate();

    for (x=[-span/2, span/2]) {
        translate([x,0,0]) bracket();
        translate([x,0,0]) bearings();
        translate([x, x>0 ? 5 : 0, shaft_h]) shaft(x>0 ? 56 : brk_w + 8);
        translate([x, -pulley_belt_w/2, shaft_h]) rotate([-90,0,0]) pulley();
    }
    belt();

    translate([span/2, 0, 0]) motor_plate();
    translate([span/2, cradle_y, 0]) motor_cradle();
    translate([span/2, 0, 0]) phidget_motor();
    translate([span/2, 0, 0]) coupler();

    color("#3c3c3c", 0.92) translate([0, ch_w/2, floor_z]) rotate([90,0,0]) import("Treadmill_Chamber.stl");
    translate([jaw_x, -side_offset, 0]) pillar();
    translate([jaw_x, 0, flange_top]) jaw();
    hardware();
}

module cap_screw(len, d=3) {
    color("#8a8a8a") { cylinder(d=d, h=len, $fn=24); translate([0,0,len]) cylinder(d=d*1.85, h=d*0.9, $fn=24); }
}
module hex_nut() { color("#6e6e6e") rotate([0,0,30]) cylinder(d=m3_nut/cos(30), h=2.4, $fn=6); }

module hardware() {
    sad_top = flange_top - 2;
    face_y  = -side_offset + pil_t/2;
    for (z=[-6,-18]) {
        translate([jaw_x, face_y + 8, sad_top + z]) rotate([-90,0,0]) cap_screw(16);
        translate([jaw_x, face_y - ts_lip - ts_d/2 - 1.2, sad_top + z]) rotate([-90,0,0]) hex_nut();
    }
    translate([jaw_x, face_y + 10, shelf_z]) cap_screw(20);
    translate([jaw_x, ch_w/2 + wall + 6, flange_top - ch_flange_h/2]) rotate([90,0,0]) cap_screw(12);
}

// ---- the drivetrain on its own: no chamber, no pillar, no jaw ----
module treadmill() {
    baseplate(false);
    for (x=[-span/2, span/2]) {
        translate([x,0,0]) bracket();
        translate([x,0,0]) bearings();
        translate([x, x>0 ? 5 : 0, shaft_h]) shaft(x>0 ? 56 : brk_w + 8);
        translate([x, -pulley_belt_w/2, shaft_h]) rotate([-90, 0, spin]) pulley();
    }
    belt();
    belt_marker();
    translate([span/2, 0, 0]) motor_plate();
    translate([span/2, cradle_y, 0]) motor_cradle();
    translate([span/2, 0, 0]) phidget_motor();
    translate([span/2, 0, 0]) coupler();
}

// a tab riding on the belt. Direction matters: rotate([-90,0,spin]) carries a point at
// the top of the pulley toward +x, so the TOP RUN travels +x. The marker follows that.
module belt_marker() {
    r   = pulley_pd/2 + belt_back;
    arc = PI*r;
    L   = 2*span + 2*arc;
    u   = ((spin/360)*PI*pulley_pd % L + L) % L;
    color("red")
    if      (u < span)         translate([-span/2 + u, 0, shaft_h + r]) marker_block();
    else if (u < span + arc)   let(a = 90 - (u - span)/arc*180)
                               translate([ span/2 + r*cos(a), 0, shaft_h + r*sin(a)]) marker_block();
    else if (u < 2*span + arc) translate([ span/2 - (u - span - arc), 0, shaft_h - r]) marker_block();
    else                       let(a = -90 - (u - 2*span - arc)/arc*180)
                               translate([-span/2 + r*cos(a), 0, shaft_h + r*sin(a)]) marker_block();
}
module marker_block() { cube([3, belt_w + 1.5, 1.6], center=true); }

module section() {
    difference() {
        union() {
            belt();
            color("#3c3c3c") translate([0, ch_w/2, floor_z]) rotate([90,0,0]) import("Treadmill_Chamber.stl");
        }
        translate([-60, -40, -20]) cube([120, 40, 120]);   // cut away the near half
    }
    // fly to scale: 2.04 mm mean body length
    color("orangered") translate([0, 2.5, floor_z + 0.45]) scale([1.7,1,0.75]) sphere(d=1.2, $fn=24);
}

// ---- named, placed instances: the assembly and the interference check use the SAME ones ----
module placed(which) {
    if      (which == "bracketL")  translate([-span/2, 0, 0]) bracket();
    else if (which == "bracketR")  translate([ span/2, 0, 0]) bracket();
    else if (which == "motor")     translate([ span/2, 0, 0]) motor_plate();
    else if (which == "cradle")    translate([ span/2, cradle_y, 0]) motor_cradle();
    else if (which == "motorbody") translate([ span/2, 0, 0]) phidget_motor();
    else if (which == "base")      baseplate();
    else if (which == "pillar")    translate([jaw_x, -side_offset, 0]) pillar();
    else if (which == "jaw")       translate([jaw_x, 0, flange_top]) jaw();
    else if (which == "chamber")   translate([0, ch_w/2, floor_z]) rotate([90,0,0]) import("Treadmill_Chamber.stl");
    else if (which == "belt")      belt();
}

a = "none"; b = "none";

// ---- print plate: every part in its printing orientation on a 220x220 bed ----
module plate() {
    %color("#dddddd") translate([0,0,-1]) cube([220, 220, 1], center=true);
    translate([-78, -85, 0]) bracket();
    translate([-78, -35, 0]) bracket();
    translate([  8,  62, 0]) rotate([0,0,90]) motor_mount();
    translate([-74,  30, 0]) pillar();
    translate([ 62, -40, 0]) rotate([180,0,0]) translate([0,0,-24]) jaw();
    translate([ 20, -95, 0]) rotate([0,0,90]) motor_cradle();
    translate([  0,  95, 0]) rotate([-90,0,0]) translate([0,0,-2]) gauge();
}

/* ============ 6. OUTPUT ============ */
spin = $t * 360;   // pulley rotation; $t drives it when --animate is used

if      (part == "treadmill")    treadmill();
else if (part == "plate")        plate();
else if (part == "pair")         intersection() { placed(a); placed(b); }
else if (part == "assembly")     assembly();
else if (part == "section")      section();
else if (part == "bracket")      bracket();
else if (part == "motor_mount")  motor_mount();
else if (part == "pillar")       pillar();
else if (part == "jaw")          jaw();
else if (part == "gauge")        gauge();
else if (part == "baseplate")    baseplate();
else if (part == "motor_cradle") motor_cradle();
else if (part == "parts") {
    bracket();
    translate([0, 70, 0]) motor_mount();
    translate([70, 0, 0]) pillar();
    translate([70, 70, 0]) jaw();
}

echo(str("shaft axis ", shaft_h, "   belt top ", belt_top, "   chamber floor ", floor_z,
         "   flange underside ", flange_z, "   flange top ", flange_top, "   motor face y ", motor_y));

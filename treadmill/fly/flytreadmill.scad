// =====================================================================
// Fly treadmill — a conveyor, shrunk to fit Pratt's chamber
// Architecture borrowed from the 3d-printed-belt-conveyor model:
//   one U-frame, bearing pockets at both ends, one end slotted for tension.
// Sized around a GT2 200 mm x 6 mm belt and Pratt's Treadmill_Chamber.stl.
//
// Why not just scale that model: its belt is 90 mm wide and ours is 6, a factor
// of 0.07 — but its 608 bearings only scale to MR105 at 0.45. Bearings do not
// shrink, so the frame is redrawn, not scaled.
// =====================================================================

part = "assembly";
// "assembly" | "pulley" | "frame" | "parts"

/* [Belt - GT2 200 mm, 6 mm wide] */
// tooth pitch, mm
pitch      = 2.0;
// teeth on the pulley
teeth      = 20;
// belt teeth (200 mm / 2 mm)
belt_teeth = 100;
// belt width, mm
belt_w     = 6.0;
// belt thickness above the pitch line, mm
belt_back  = 0.63;
// total belt thickness, mm
belt_th    = 1.38;

/* [Printed pulley teeth - TUNE THESE AFTER A TEST PRINT] */
// groove depth, mm (GT2 nominal 0.75)
gt_depth   = 0.75;
// groove radius, mm. 0.778 makes the groove 1.49 wide at the pitch line, which is the
// GT2 belt tooth width. 0.62 (my earlier value) was far too narrow - the belt rode the tips.
gt_r       = 0.778;
// flange diameter over the tooth tips, mm
fl_extra   = 4.0;
// flange thickness, mm
fl_t       = 1.2;
// hub diameter for the grub screw, mm
hub_d      = 10;
// hub length, mm
hub_l      = 6;

/* [Bearings and shaft] */
// MR105ZZ: 5 x 10 x 4
brg_od     = 10;
brg_w      = 4;
shaft_d    = 5;
// negative = press fit
brg_fit    = -0.10;
// boss added on the OUTER face so the bearing has a seat, not a through hole, mm
brg_boss   = 2.5;

/* [Frame] */
// inside width between the frame walls, mm
frame_gap  = 24;
// wall thickness, mm
wall       = 4;
// floor thickness, mm
floor_t    = 3;
// shaft axis above the frame floor, mm
axis_h     = 16;
// wall height in the middle, kept low so cameras can see the chamber, mm
mid_h      = 11;
// belt tension travel at the idler end, mm
tension    = 7;

/* [Chamber - measured from Treadmill_Chamber.stl] */
ch_len      = 40;
ch_w        = 10;
ch_h        = 16;
ch_flange_h = 3.25;
ch_gap      = 0.15;

/* [Split build] */
// foot flange width where the wall bolts to the base, mm
flange_w   = 9;
// base plate thickness, mm
base_t     = 4;

/* [Motor - Phidgets 3263E_1, drives the pulley DIRECTLY] */
// bolt circle on the motor face, mm
motor_bolt   = 22.0;
// M3 clearance, mm
motor_screw  = 3.4;
// pilot boss recess, mm
motor_boss_d = 17.0;
motor_boss_h = 2.6;
// motor shaft, mm
motor_shaft  = 6.0;
motor_shaft_l = 16.7;
motor_body   = 28.0;
// extra wall thickness at the motor, mm — it is 193 g on a cantilever
motor_wall   = 5;

/* [Camera - Chronos 2.1-HD] */
// optical axis above the camera's mounting face, mm (from the Kron mechanical drawing)
cam_axis_h  = 33.5;
// riser height so the fly lands on that axis when both sit on one flat surface, mm
riser_h     = 9.6;
// 1/4-20 clearance, mm
cam_quarter = 6.8;
// M4 clearance, mm
cam_m4      = 4.5;
// the two M4 holes sit this far either side of the 1/4-20, mm
cam_m4_pitch = 12.5;

/* [Hidden] */
eps = 0.01;
m3  = 3.3;

/* ===== derived ===== */
pd        = teeth * pitch / PI;          // 12.732 pitch diameter
od        = pd - 0.508;                  // 12.224 over the tooth tips
belt_len  = belt_teeth * pitch;          // 200
span_nom  = (belt_len - teeth*pitch)/2;  // 80.0
span      = span_nom - 2;                // build short, tension outward
pulley_l  = 2*fl_t + belt_w + 1 + hub_l;
belt_top  = axis_h + pd/2 + belt_back;
floor_z   = belt_top + ch_gap;
frame_len = span + od + 26;

/* ===== the printed GT2 pulley ===== */
// The pulley is NOT generated any more. GT2's tooth form is a multi-arc curvilinear
// profile; a single-circle groove fits it only to 0.38 mm RMS. pulley_20T.stl is
// GT2_Pulley_20T_5_R_SS from the big-collection library: tip 6.113, root 5.362,
// depth 0.751, 7.0 mm belt channel, 5.1 bore, 13.42 max dia, 15.0 tall.
// Its hub acts as the second flange.
module pulley() { translate([0, 0, -3.5]) import("pulley_20T.stl"); }

module pulley_generated() {
    gc = od/2 - gt_depth + gt_r;         // groove centre radius
    difference() {
        union() {
            translate([0,0,fl_t]) cylinder(d=od, h=belt_w + 1, $fn=96);
            cylinder(d=od + fl_extra, h=fl_t, $fn=96);
            translate([0,0,fl_t + belt_w + 1]) cylinder(d=od + fl_extra, h=fl_t, $fn=96);
            translate([0,0,fl_t + belt_w + 1 + fl_t]) cylinder(d=hub_d, h=hub_l, $fn=48);
        }
        // the teeth: one groove per tooth, cut the full belt channel
        for (a=[0:360/teeth:359.9]) rotate([0,0,a]) translate([gc, 0, fl_t - 0.5])
            cylinder(r=gt_r, h=belt_w + 2, $fn=24);
        translate([0,0,-1]) cylinder(d=shaft_d + 0.2, h=pulley_l + 2, $fn=48);
        // grub screw
        translate([0, 0, fl_t + belt_w + 1 + fl_t + hub_l/2]) rotate([0,90,0])
            cylinder(d=2.5, h=hub_d, $fn=24);
    }
}

/* ===== the frame ===== */
// ============ one-piece U frame + separate bearing holders ============
// The bore lives in the HOLDER, printed bore-up so it comes out round. That leaves the
// frame with no round critical feature, so it does not need splitting at all: print the
// two walls and the floor as ONE part. No flange, no base plate, no base bolts, no
// mirrored second wall, no tension screw reaching across planes -- all of those were
// bugs waiting to happen, and none of them exist now.
// Tension: slide the idler holder along its slots and nip its two bolts. Belt tension on
// a 6 mm belt driving a fly is small enough that a jack screw is not worth a part.

hold_w    = 26;                       // holder width, along the belt
hold_h    = 20;
hold_t    = brg_w + 0.2 + 2.3;        // pocket + shoulder = 6.5
hold_bolt = 10;                       // bolt spacing either side of the bore
drive_x   = -span/2;
idler_x   = span/2 + tension/2;

module bearing_holder() {
    seat = brg_w + 0.2;
    difference() {
        translate([0, 0, hold_t/2]) cube([hold_w, hold_h, hold_t], center=true);
        translate([0, 0, hold_t - seat + eps]) cylinder(d=brg_od + brg_fit, h=seat + 1, $fn=64);
        translate([0, 0, -1]) cylinder(d=shaft_d + 0.6, h=hold_t + 2, $fn=32);
        for (x=[-1,1]) translate([x*hold_bolt, 0, -1]) {
            cylinder(d=m3, h=hold_t + 2, $fn=24);
            translate([0,0,2.4]) rotate([0,0,30]) cylinder(d=5.6/cos(30), h=2.6, $fn=6);
            translate([0, -hold_h, 2.4]) cube([5.6 - 0.7, hold_h, 2.6]);   // side entry for the nut
        }
    }
}

module frame() {
    end_h = axis_h + hold_h/2 + 3;
    difference() {
        union() {
            for (y=[-1,1]) translate([0, y*(frame_gap + wall)/2, 0]) {
                translate([0, 0, mid_h/2]) cube([frame_len, wall, mid_h], center=true);
                for (e = [[drive_x, -1], [idler_x, 1]]) let(
                        inner = e[0] - e[1]*(hold_w/2 + 4),
                        outer = e[1]*frame_len/2)
                    translate([(inner + outer)/2, 0, end_h/2])
                        cube([abs(outer - inner), wall, end_h], center=true);
            }
            translate([0, 0, floor_t/2]) cube([frame_len, frame_gap + 2*wall, floor_t], center=true);
        }
        // shaft through: hole at the drive end, slot at the idler end
        translate([drive_x, 0, axis_h]) rotate([90,0,0])
            cylinder(d=shaft_d + 0.8, h=frame_gap + 4*wall, center=true, $fn=32);
        translate([idler_x, 0, axis_h]) rotate([90,0,0])
            hull() for (t=[-tension/2, tension/2]) translate([t,0,0])
                cylinder(d=shaft_d + 0.8, h=frame_gap + 4*wall, center=true, $fn=32);
        // holder bolts: fixed at the drive end, slotted at the idler end
        for (b=[-1,1]) {
            translate([drive_x + b*hold_bolt, 0, axis_h]) rotate([90,0,0])
                cylinder(d=m3, h=frame_gap + 4*wall, center=true, $fn=24);
            translate([idler_x + b*hold_bolt, 0, axis_h]) rotate([90,0,0])
                hull() for (t=[-tension/2, tension/2]) translate([t,0,0])
                    cylinder(d=m3, h=frame_gap + 4*wall, center=true, $fn=24);
        }
    }
    // holders, outboard of each wall
    for (y=[-1,1])
        translate([idler_x, y*((frame_gap + 2*wall)/2 + hold_t), axis_h]) rotate([y>0 ? -90 : 90, 0, 0])
            rotate([0,0,y>0 ? 0 : 180]) bearing_holder();
}

module frame_only() {
    end_h = axis_h + hold_h/2 + 3;
    difference() {
        union() {
            for (y=[-1,1]) translate([0, y*(frame_gap + wall)/2, 0]) {
                translate([0, 0, mid_h/2]) cube([frame_len, wall, mid_h], center=true);
                for (e = [[drive_x, -1], [idler_x, 1]]) let(
                        inner = e[0] - e[1]*(hold_w/2 + 4),
                        outer = e[1]*frame_len/2)
                    translate([(inner + outer)/2, 0, end_h/2])
                        cube([abs(outer - inner), wall, end_h], center=true);
            }
            translate([0, 0, floor_t/2]) cube([frame_len, frame_gap + 2*wall, floor_t], center=true);
            // the motor bolts to THIS wall, so thicken it locally and buttress it
            translate([drive_x, (frame_gap + wall)/2 + (motor_wall - wall)/2 + wall/2, end_h/2])
                cube([34, motor_wall, end_h], center=true);
            for (b=[-1,1]) translate([drive_x + b*17, (frame_gap+wall)/2, floor_t]) hull() {
                translate([0,0,0]) cube([4, motor_wall + wall, 2], center=true);
                translate([0, 0, end_h - 8]) cube([4, wall, 2], center=true);
            }
        }
        // ---- DRIVE END: the motor's own shaft carries the pulley. No shaft, no bearing. ----
        translate([drive_x, 0, axis_h]) rotate([-90,0,0])
            cylinder(d=motor_shaft + 2, h=frame_gap, center=true, $fn=32);
        translate([drive_x, (frame_gap + 2*wall)/2 + motor_wall - wall - motor_boss_h/2 + eps, axis_h])
            rotate([-90,0,0]) cylinder(d=motor_boss_d, h=motor_boss_h, center=true, $fn=48);
        for (a=[0:90:359]) translate([drive_x + motor_bolt/2*cos(a), 0, axis_h + motor_bolt/2*sin(a)])
            rotate([-90,0,0]) cylinder(d=motor_screw, h=frame_gap + 4*wall, center=true, $fn=24);
        // ---- IDLER END: 5 mm shaft in two bearings, holders bolt through slots ----
        translate([idler_x, 0, axis_h]) rotate([90,0,0])
            hull() for (t=[-tension/2, tension/2]) translate([t,0,0])
                cylinder(d=shaft_d + 0.8, h=frame_gap + 4*wall, center=true, $fn=32);
        for (b=[-1,1]) translate([idler_x + b*hold_bolt, 0, axis_h]) rotate([90,0,0])
            hull() for (t=[-tension/2, tension/2]) translate([t,0,0])
                cylinder(d=m3, h=frame_gap + 4*wall, center=true, $fn=24);
    }
}

/* ===== reference geometry ===== */
module belt() {
    color("#222") rotate([90,0,0]) linear_extrude(belt_w, center=true)
        difference() {
            hull() for (x=[-span/2, span/2]) translate([x, axis_h]) circle(d=pd + 2*belt_back, $fn=72);
            hull() for (x=[-span/2, span/2]) translate([x, axis_h]) circle(d=pd - 2*(belt_th-belt_back), $fn=72);
        }
}
module bearings(x) {
    seat = brg_w + 0.2;
    for (y=[-1,1]) translate([x, y*((frame_gap + wall)/2 + wall/2 + brg_boss - seat/2), axis_h])
        rotate([90,0,0]) color("#c0c0c0") difference() {
            cylinder(d=brg_od, h=brg_w, center=true, $fn=48);
            cylinder(d=shaft_d, h=brg_w + 1, center=true, $fn=32);
        }
}

module shaft(len) { color("#b8b8b8") rotate([-90,0,0]) cylinder(d=shaft_d, h=len, center=true, $fn=32); }

module assembly() {
    frame();
    belt();
    // DRIVE: the motor's own 6 mm shaft carries the pulley. Hub toward the motor.
    translate([drive_x, 3.5, axis_h]) rotate([90,0,0]) import("pulley_20T_6mm.stl");
    translate([drive_x, (frame_gap + 2*wall)/2 + motor_wall - wall, axis_h]) rotate([-90,0,0]) {
        color("#b8b8b8") translate([0,0,-motor_shaft_l]) cylinder(d=motor_shaft, h=motor_shaft_l, $fn=32);
        color("#3a3a3a") {
            cylinder(d=16, h=2, $fn=48);
            translate([0,0,2]) cylinder(d=motor_body, h=48.5, $fn=64);
            translate([0,0,50.5]) cylinder(d=motor_body - 3, h=37.5, $fn=64);
            translate([0,0,88]) cylinder(d=motor_body - 8, h=22, $fn=48);
        }
    }
    // IDLER: 5 mm shaft in two bearings
    translate([idler_x, 3.5, axis_h]) rotate([90,0,0]) import("pulley_20T.stl");
    translate([idler_x, 0, axis_h]) rotate([-90,0,0])
        color("#b8b8b8") cylinder(d=shaft_d, h=frame_gap + 2*wall + 2*hold_t + 6, center=true, $fn=32);
    color("#3c3c3c", 0.9) translate([0, ch_w/2, floor_z]) rotate([90,0,0]) import("Treadmill_Chamber.stl");
}

module plate_master() {
    frame_only();                                                  // floor down, walls up
    for (i=[0,1]) translate([-24 + i*32, 36, 0]) bearing_holder(); // bore up, prints round
    translate([-24, 62, 7]) import("pulley_20T.stl");              // idler, 5 mm bore
    translate([  8, 62, 7]) import("pulley_20T_6mm.stl");          // drive, 6 mm bore
    translate([0, -34, 0]) treadmill_riser();                      // two height blocks
}

if      (part == "riser")    treadmill_riser();
else if (part == "camplate") camera_plate();
else if (part == "master")   plate_master();
else if (part == "plate04")  plate_04();
else if (part == "plate025") plate_025();
else if (part == "assembly") assembly();
else if (part == "section")  section();
else if (part == "pulley")   pulley();
else if (part == "frame")    frame();
else if (part == "frame1")   frame_only();

else if (part == "holder")   bearing_holder();
else if (part == "pulley_gen") pulley_generated();
else if (part == "parts")  { pulley(); translate([30,0,0]) frame(); }

echo(str("pitch dia ", pd, "  tip dia ", od, "  span ", span, " (nominal ", span_nom,
         ")  belt top ", belt_top, "  chamber floor ", floor_z, "  frame ", frame_len));

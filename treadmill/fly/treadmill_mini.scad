// =====================================================================
// Fly treadmill — 28BYJ-48 direct drive, 608RS idler.
//
// Motor:    28BYJ-48 5V, from the Kiatronics drawing in Downloads.
//           Body 28 x 19, boss 9 x 1.5, shaft 5 mm with 3 mm flats, 10 long.
//           2 x 4.2 holes, 35 apart, shaft 8 mm off the hole line.
// Bearings: 2 x 608RS, 8 x 22 x 7. Idler only. The motor's own gearbox
//           carries the drive pulley, exactly as Pratt's build does.
// Belt:     GT2 closed loop, 100 mm (50T), 6 mm wide.
//
// Two numbers drive the whole layout and neither was a choice:
//   * the 8 mm bore of a 608 needs a >=22T pulley to leave any wall, and
//   * the motor's shaft is only 10 mm long, 1.5 of which is boss, so the
//     motor's face must sit 5.75 mm from the belt centreline. Nothing
//     thicker than that fits between the motor and the pulley.
//
// Reference: Pratt et al. 2024 Curr Biol, github.com/Prattbuw/Treadmill_Paper.
// =====================================================================

part = "assembly";   // assembly | frame | pulley_drive | pulley_idler | plate | gauge

/* [Bearing choice — this ONE line sets how big and how heavy the machine is]
   "608"   : 8 x 22 x 7. What you already own. Its 11 mm radius forces the shaft
             axis to 15 mm and the walls to 10 mm. Frame 69x32x28, 23 g of PLA.
   "MR105" : 5 x 10 x 4, about $1 for ten. Frame 67x24x21, 12 g. Half the plastic
             and 7 mm shorter, because nothing else in here is big. */
bearing = "608";     // "608" | "MR105"

/* [Belt — GT2 closed loop, 100 mm, 6 mm wide] */
pitch      = 2.0;
// tooth count is the minimum that leaves >=1.8 mm of wall around the bore
teeth      = bearing=="MR105" ? 18 : 22;
belt_teeth = 50;
belt_w     = 6.0;
belt_back  = 0.63;
belt_th    = 1.38;

/* [Printed pulleys] */
gt_depth = 0.75;
gt_r     = 0.778;    // 1.49 mm groove at the pitch line
fl_extra = 3.0;      // flange dia over the tooth tips
fl_t     = 0.7;
ch_clr   = 0.6;      // belt channel wider than the belt

/* [Bearings] */
// Nominal metal sizes only. Every fit is applied by bore() below, never here.
brg_od   = bearing=="MR105" ? 10 : 22;   // as bought, 22.000 / -0.009
brg_w    = bearing=="MR105" ?  4 :  7;
shaft_d  = bearing=="MR105" ?  5 :  8;   // ground rod, h7
shoulder = 3.0;      // material behind the pocket (was 2.0 — see tab_relief)

/* [Fits — set xy_comp ONCE from the test coupon, everything follows]
   A printed hole always comes out smaller than modelled: the nozzle rounds
   inside corners and the first layer squashes outward. The error is a property
   of YOUR printer and filament, not of this design, so it lives in one number.
   Print part="gauge" (about 10 min), measure the three bores, and set
   xy_comp = nominal - measured. Typical: 0.10-0.25 on a bed-slinger, ~0 resin. */
xy_comp   = 0.15;    // holes print this much UNDERSIZE; added back to every bore
fit_slide = 0.30;    // 608 OD in its pocket - MUST slide to tension the belt
fit_key   = 0.10;    // printed bore onto steel: slip on by hand, retain with CA
fit_free  = 0.60;    // shaft passing through a wall, touching nothing
fit_screw = 0.30;    // screw shank clearance
lead_in   = 0.6;     // chamfer at the mouth of every pocket, so it starts square
fit_tab   = 0.6;     // relief behind the motor's tabs, on top of mot_tab_t

// The only place a diameter is ever written. Nominal + fit + printer error.
function bore(nominal, fit=0) = nominal + fit + xy_comp;

/* [Motor — 28BYJ-48] */
mot_body_d   = 28;
mot_body_l   = 19;
mot_boss_d   = 9;
mot_boss_h   = 1.5;
mot_shaft_d  = 5.0;
mot_flat     = 3.0;  // across the flats
mot_shaft_l  = 10;   // from the motor face, boss included
mot_hole_d   = 4.2;  // nominal; fit_screw applied by bore()
mot_hole_pitch = 35;
mot_hole_off = 8;    // shaft axis to the hole line
mot_tab_t    = 1.0;  // the stamped tabs stand this proud of the motor's face
plate_t      = 2.0;  // all that fits between the motor face and the belt

/* [Frame] */
floor_t = 2.5;
mid_wall = 4;        // the low middle wall holds no bearing, so it needn't be `wall` thick
ear_out  = 7.5;      // how far each mounting ear sticks past the wall
ear_w    = 12;       // ear width along the frame
ear_hole = 3.0;      // M3 nominal; fit_screw applied by bore()
mid_h   = 10;        // low wall in the middle — the camera looks through here
tension = 3;         // idler travel
end_pad = 6;         // thread length for the tension screws

/* [Hidden] */
eps = 0.01;
m3_tap = 2.5;        // self-tap pilot in PLA; fit 0, it is meant to be tight
$fn = 64;

/* ===== derived ===== */
pd        = teeth * pitch / PI;             // 14.006
od        = pd - 0.508;                     // 13.498 over the tooth tips
root_d    = od - 2*gt_depth;                // 11.998
belt_len  = belt_teeth * pitch;             // 100
span      = (belt_len - teeth*pitch) / 2;   //  28.0, taut at zero stretch
pulley_l  = 2*fl_t + belt_w + ch_clr;       //   8.0
shaft_free = mot_shaft_l - mot_boss_h;      //   8.5 of usable round shaft
half_gap  = pulley_l/2 + mot_boss_h + (shaft_free - pulley_l)/2;   // 5.75
wall      = brg_w + shoulder;               //   9
axis_h    = brg_od/2 + floor_t + 1.5;       //  15, set by the 608's radius
belt_top  = axis_h + pd/2 + belt_back;      //  22.63 — the fly walks here
frame_gap = 2*half_gap;                     //  11.5
frame_w   = frame_gap + 2*wall;             //  29.5
end_h     = axis_h + brg_od/2 + 2.5;        //  28.5
drive_x   = -span/2;
idler_x   =  span/2;                        // slot runs from here OUTWARD
x_max     = idler_x + tension + brg_od/2 + end_pad;
x_min     = drive_x - mot_hole_pitch/2 - 3.5;
mot_face_y = -half_gap;
mot_tab_z  = axis_h + mot_hole_off;         //  23
plate_top  = mot_tab_z + 4;
shaft_len  = frame_w;                       // flush with both outer faces
tall_in    = idler_x - brg_od/2 - 2;
belt_stretch = 1.5;                         // idler wound out this far
tab_relief = mot_tab_t + fit_tab;           // the -y wall is stepped back by this
ear_x      = [x_min + 8, x_max - 8];        // -27 and +26
ear_y      = frame_w/2 + ear_out - 3.5;     // hole centre, 3.5 in from the ear's edge

// ---- checks. If any trip, the numbers above are wrong. ----
assert((root_d - bore(shaft_d, fit_key))/2 >= 1.8, "pulley too few teeth for an 8 mm bore");
assert(shaft_free >= pulley_l,              "motor shaft too short for the pulley");
assert(axis_h - brg_od/2 > floor_t,         "608 cuts into the floor");
assert(axis_h - pd/2 - belt_back > floor_t, "bottom belt run drags on the floor");
assert(frame_gap >= pulley_l + 2,           "pulley does not fit between the walls");
assert(half_gap - plate_t > belt_w/2 + 0.5, "motor plate fouls the belt");
assert(mot_tab_z - mot_body_d/2 > 0,        "motor body hits the table");
assert(span > od + 2,                       "pulleys collide");
assert(x_max - (idler_x + tension + brg_od/2) >= 5, "no thread for the tension screw");

/* ===== pulleys =====
   One circular groove per tooth: fits real GT2 to ~0.4 mm RMS. Fine for a 1 mg
   load. ponytail: swap in bought 22T pulleys when you need absolute belt
   position rather than "it turns".
   Drive pulley gets a double-D bore for the motor's flatted shaft — a round
   bore would only touch two arcs and slip. Idler gets a plain 8 mm bore. */
module pulley(bore_d, flat=0) {
    gc = od/2 - gt_depth + gt_r;
    difference() {
        union() {
            translate([0,0,fl_t]) cylinder(d=od, h=belt_w + ch_clr);
            cylinder(d=od + fl_extra, h=fl_t);
            translate([0,0,fl_t + belt_w + ch_clr]) cylinder(d=od + fl_extra, h=fl_t);
        }
        for (a=[0:360/teeth:359.9]) rotate([0,0,a])
            translate([gc, 0, fl_t - 0.5]) cylinder(r=gt_r, h=belt_w + ch_clr + 1, $fn=24);
        translate([0,0,-1]) intersection() {
            cylinder(d=bore_d, h=pulley_l + 2, $fn=48);
            if (flat > 0) cube([bore_d + 1, flat, 2*(pulley_l + 2)], center=true);
            else cylinder(d=bore_d, h=pulley_l + 2, $fn=48);
        }
    }
}
// Drive: double-D onto the motor's flatted shaft. The flats carry the torque, the
// CA stops it walking off. Never press hard onto this shaft - the load goes
// straight into a plastic gear train.
module pulley_drive() { pulley(bore(mot_shaft_d, fit_key), bore(mot_flat, fit_key)); }
module pulley_idler() { pulley(bore(shaft_d, fit_key)); }

/* ===== frame — one printed part, floor-down, no supports =====
   Drive end has no bearing: the motor bolts to a 2 mm plate whose outer face IS
   the motor's mounting plane, and its body hangs past the frame in free air.
   Idler end has the two 608s in slotted pockets, pushed outward by one M3 each.
   Belt tension pulls them back onto the screws, so nothing clamps. The two
   pocket shoulders face each other, which is what traps the shaft assembly. */
module bearing_slot(travel) {
    for (y=[-1,1]) hull() for (t=[0, travel])
        translate([idler_x + t, y*(frame_w/2 - brg_w/2 + eps), axis_h])
            rotate([90,0,0]) {
                cylinder(d=bore(brg_od, fit_slide), h=brg_w + 2*eps, center=true);
                // lead-in chamfer at the mouth, so the bearing starts square
                translate([0,0,y*(brg_w/2 - lead_in)]) cylinder(
                    d1 = y>0 ? bore(brg_od, fit_slide) : bore(brg_od, fit_slide) + 2*lead_in,
                    d2 = y>0 ? bore(brg_od, fit_slide) + 2*lead_in : bore(brg_od, fit_slide),
                    h = lead_in + eps, center=true);
            }
    hull() for (t=[0, travel])
        translate([idler_x + t, 0, axis_h])
            rotate([90,0,0]) cylinder(d=bore(shaft_d, fit_free), h=frame_w + 2, center=true, $fn=32);
}

module motor_plate() {
    difference() {
        translate([x_min, mot_face_y, floor_t])
            cube([drive_x + mot_hole_pitch/2 + 3.5 - x_min, plate_t, plate_top - floor_t]);
        for (b=[-1,1]) translate([drive_x + b*mot_hole_pitch/2, mot_face_y - 1, mot_tab_z])
            rotate([-90,0,0]) cylinder(d=bore(mot_hole_d, fit_screw), h=plate_t + 2, $fn=32);
        // let both pulley flanges through — they reach past the plate's inner face
        for (e=[[drive_x,0],[idler_x,tension]]) hull() for (t=[0,e[1]])
            translate([e[0] + t, mot_face_y - 1, axis_h])
                rotate([-90,0,0]) cylinder(d=od + fl_extra + 1, h=plate_t + 2);
    }
}

module frame() {
    difference() {
        union() {
            // +y wall: full length, tall over the bearing, low in the middle
            translate([x_min, half_gap, 0]) cube([x_max - x_min, mid_wall, mid_h]);
            translate([tall_in, half_gap, 0]) cube([x_max - tall_in, wall, end_h]);
            // -y wall: only past the motor body, which occupies x_min..1
            translate([1, -half_gap - wall, 0]) cube([x_max - 1, wall, end_h]);
            translate([x_min, -half_gap - wall, 0]) cube([x_max - x_min, frame_w, floor_t]);
            // four mounting ears: this is how the treadmill bolts to anything.
            for (x = ear_x, y = [-1,1])
                translate([x - ear_w/2, y>0 ? frame_w/2 : -frame_w/2 - ear_out, 0])
                    cube([ear_w, ear_out, floor_t]);
            motor_plate();
        }
        bearing_slot(tension);
        // The motor's right-hand tab (x = drive_x + 17.5) lands ON the idler wall.
        // Step that wall's inner face back by a tab's thickness over the motor's
        // whole footprint, rather than notching around one lug. Costs 1.6 mm of
        // shoulder where the bearing barely bears anyway; shoulder was raised to
        // 3.0 to pay for it.
        translate([x_min, -half_gap - tab_relief, floor_t])
            cube([drive_x + mot_hole_pitch/2 + 6 - x_min, tab_relief + eps, end_h]);
        // M3 through each ear
        for (x = ear_x, y = [-1,1])
            translate([x, y*ear_y, -1]) cylinder(d=bore(ear_hole, fit_screw), h=floor_t + 2, $fn=32);
        // window in the floor under the belt — carries nothing, the belt clears it by 4.9
        translate([drive_x + 6, -half_gap + 2, -1])
            cube([idler_x - drive_x - 12, frame_gap - 4, floor_t + 2]);
        // one tension screw per wall, pushing its bearing outward
        for (y=[-1,1]) translate([idler_x, y*(half_gap + wall/2), axis_h])
            rotate([0,90,0]) cylinder(d=bore(m3_tap), h=x_max - idler_x + 1, $fn=24);
    }
}

/* ===== animation: $t drives one lap of the belt ===== */
belt_r  = pd/2 + belt_back + 1.1;
arc_len = PI * belt_r;
loop_len = 2*(idler_x + belt_stretch - drive_x) + 2*arc_len;

function belt_pos(u) =
    let(run = idler_x + belt_stretch - drive_x, s = (u - floor(u)) * loop_len)
    s < run             ? [drive_x + s, axis_h + belt_r]
  : s < run + arc_len   ? let(a = (s - run)/arc_len*180)
                          [idler_x + belt_stretch + belt_r*sin(a), axis_h + belt_r*cos(a)]
  : s < 2*run + arc_len ? [idler_x + belt_stretch - (s - run - arc_len), axis_h - belt_r]
  :                       let(a = (s - 2*run - arc_len)/arc_len*180)
                          [drive_x - belt_r*sin(a), axis_h - belt_r*cos(a)];

module belt_marker(u) {
    p = belt_pos(u);
    color("#e8552d") translate([p[0], 0, p[1]]) sphere(d=2.6, $fn=24);
}

/* ===== reference geometry, assembly view only ===== */
module belt() {
    color("#222") rotate([90,0,0]) linear_extrude(belt_w, center=true)
        difference() {
            hull() for (x=[drive_x, idler_x + belt_stretch]) translate([x, axis_h])
                circle(d=pd + 2*belt_back);
            hull() for (x=[drive_x, idler_x + belt_stretch]) translate([x, axis_h])
                circle(d=pd - 2*(belt_th - belt_back));
        }
}

module motor() {
    translate([drive_x, mot_face_y, axis_h]) rotate([90,0,0]) {
        color("#b0b4b8") { cylinder(d=mot_boss_d, h=mot_boss_h);
                           cylinder(d=mot_shaft_d, h=mot_shaft_l); }
        color("#8f9296") translate([0, mot_hole_off, 0]) {
            cylinder(d=mot_body_d, h=mot_body_l);
            for (b=[-1,1]) translate([b*mot_hole_pitch/2, 0, 0]) difference() {
                cylinder(d=7, h=1);
                translate([0,0,-1]) cylinder(d=mot_hole_d, h=3, $fn=32);
            }
        }
    }
}

module assembly() {
    frame();
    belt();
    motor();
    translate([drive_x, -pulley_l/2, axis_h]) rotate([-90,0,0])
        rotate([0,0,$t*loop_len/(PI*pd)*360]) pulley_drive();
    translate([idler_x + belt_stretch, -pulley_l/2, axis_h]) rotate([-90,0,0])
        rotate([0,0,$t*loop_len/(PI*pd)*360]) pulley_idler();
    translate([idler_x + belt_stretch, 0, axis_h]) rotate([-90,0,0])
        color("#b8b8b8") cylinder(d=shaft_d, h=shaft_len, center=true, $fn=32);
    for (y=[-1,1]) translate([idler_x + belt_stretch, y*(frame_w/2 - brg_w/2), axis_h])
        rotate([90,0,0]) color("#c0c0c0") difference() {
            cylinder(d=brg_od, h=brg_w, center=true, $fn=64);
            cylinder(d=shaft_d, h=brg_w + 1, center=true, $fn=32);
        }
    for (k=[0:5]) belt_marker($t + k/6);
}

/* ===== test coupon — print this FIRST =====
   Four bores at the sizes the real parts use. Check them before committing an
   hour to the frame:
     A  22 slide  -> a 608 pushes in with thumb pressure and slides, no rattle
     B   8 key    -> the 8 mm rod goes in by hand and does not fall out
     C   5/3 D    -> the motor shaft enters without forcing; no wobble
     D   4.2      -> an M4 screw passes freely
   Any of them wrong: change xy_comp by (nominal - measured) and reprint. */
module gauge() {
    t = 5;
    difference() {
        union() {
            translate([14, 13, 0]) cylinder(d=28, h=t);
            translate([26, 7, 0]) cube([26, 12, t]);
        }
        // A: the 608 pocket. Only 4 deep — that tests the DIAMETER, which is the
        // fit you care about. It does not test full seating depth.
        translate([14, 13, t-4]) cylinder(d=bore(brg_od, fit_slide), h=5);
        translate([14, 13, -1])  cylinder(d=bore(shaft_d, fit_free), h=t+2);
        // B: idler pulley bore   C: motor's double-D   D: M4 clearance
        translate([32, 13, -1]) cylinder(d=bore(shaft_d, fit_key), h=t+2);
        translate([42, 13, -1]) intersection() {
            cylinder(d=bore(mot_shaft_d, fit_key), h=t+2, $fn=48);
            cube([10, bore(mot_flat, fit_key), 40], center=true);
        }
        translate([49, 13, -1]) cylinder(d=bore(mot_hole_d, fit_screw), h=t+2, $fn=32);
    }
}

module plate() {
    frame();
    translate([-20, frame_w/2 + 14, 0]) pulley_drive();
    translate([  2, frame_w/2 + 14, 0]) pulley_idler();
}

/* ===== assembly-position exports — one file per component =====
   Every module below places its part where it actually sits in the machine, so
   importing the whole cad/parts/ folder gives the assembled treadmill.
   The motor transform was measured off the vendor mesh, not guessed:
     shaft axis (20.555, 31.822) along z, tip at z=0, mounting face at z=10,
     tab holes at y=23.800 -> 8.02 below the axis, pitch 35.11.
   That matches the datasheet's 8 and 35, which is why the frame's holes line up. */
vendor_dir = "../vendor/";
module asm_motor() {
    translate([drive_x, mot_face_y, axis_h]) rotate([0,0,180]) rotate([-90,0,0])
        translate([-20.555, -31.822, -10]) import(str(vendor_dir, "28BYJ-48.stl"));
}
module asm_bearing(side) {
    translate([idler_x + belt_stretch, side*(frame_w/2 - brg_w), axis_h])
        rotate([side>0 ? -90 : 90, 0, 0])
            if (bearing == "608") import(str(vendor_dir, "608RS.stl"));
            else difference() {                       // generic, from the preset
                cylinder(d=brg_od, h=brg_w, $fn=96);
                translate([0,0,-1]) cylinder(d=shaft_d, h=brg_w+2, $fn=64);
            }
}
module asm_shaft() {
    translate([idler_x + belt_stretch, 0, axis_h]) rotate([-90,0,0])
        cylinder(d=shaft_d, h=shaft_len, center=true, $fn=64);
}
module asm_pulley_drive() {
    translate([drive_x, -pulley_l/2, axis_h]) rotate([-90,0,0]) pulley_drive(); }
module asm_pulley_idler() {
    translate([idler_x + belt_stretch, -pulley_l/2, axis_h]) rotate([-90,0,0]) pulley_idler(); }
module asm_all() {
    frame(); asm_motor(); asm_shaft(); asm_pulley_drive(); asm_pulley_idler();
    belt(); asm_bearing(1); asm_bearing(-1);
}

if      (part == "assembly")      assembly();
else if (part == "frame")         frame();
else if (part == "pulley_drive")  pulley_drive();
else if (part == "pulley_idler")  pulley_idler();
else if (part == "plate")         plate();
else if (part == "gauge")        gauge();
else if (part == "clash")        clash();
else if (part == "asm_motor")     asm_motor();
else if (part == "asm_bearing_a") asm_bearing(1);
else if (part == "asm_bearing_b") asm_bearing(-1);
else if (part == "asm_shaft")     asm_shaft();
else if (part == "asm_pulley_drive") asm_pulley_drive();
else if (part == "asm_pulley_idler") asm_pulley_idler();
else if (part == "asm_belt")      belt();
else if (part == "asm_all")       asm_all();

echo(str("bores as modelled: 608 pocket ", bore(brg_od, fit_slide),
         "  idler ", bore(shaft_d, fit_key), "  drive D ", bore(mot_shaft_d, fit_key),
         "/", bore(mot_flat, fit_key), "  motor screw ", bore(mot_hole_d, fit_screw)));
echo(str("22T pd ", pd, "  span ", span, " +", tension,
         "  belt top ", belt_top,
         "  frame ", x_max - x_min, " x ", frame_w, " x ", end_h,
         "  motor face y ", mot_face_y, "  tab z ", mot_tab_z,
         "  shaft ", shaft_len, "  bore wall ", (root_d - shaft_d)/2));

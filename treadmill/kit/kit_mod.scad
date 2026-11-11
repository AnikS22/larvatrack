// =====================================================================
// Conveyor kit, adapted — NOT redrawn.
//
// The kit's own architecture is kept exactly: flat side rail with two guide
// ribs, an upright tab at each end carrying a journal hole, printed rollers
// running straight in those holes. No bearings anywhere, which is correct —
// the load is a 1 mg fly.
//
// Measured from the real meshes:
//   rail    obj71  150.0 x 42.0 x 32.5 ; ends/tabs live in x 0..40 and
//                  x 142..150, and x 40..142 is a featureless extrusion.
//                  So length can be CUT out of the middle and the ribs
//                  butt back together. That is the "distance between".
//   roller  obj1   60 long: Ø14 flange 0..2, Ø8 journal 2..16,
//                  Ø19.2 toothed body 16..56, mirrored to 60.
//                  The body is uniform, so belt width cuts the same way.
// =====================================================================

part = "rail_short";   // rail_short | roller_narrow | rail_compare | dsc

/* [How much to remove] */
rail_cut   = 60;   // mm out of the rail's middle -> rail is 150 - this
roller_cut = 0;    // mm out of the roller's toothed body -> belt narrows by this

/* [Where it is safe to cut — from the scan above, do not exceed these] */
rail_keep_lo  = 45;    // everything below this is the end tab + ribs
rail_keep_hi  = 140;   // everything above this is the far tab
body_lo = 20;          // roller toothed body starts at 16
body_hi = 52;          // and ends at 56

big = 400;

module rail_short(cut = rail_cut) {
    // keep the near end as-is
    intersection() {
        import("obj71.stl");
        translate([-1, -1, -1]) cube([rail_keep_lo + 1.02, big, big]);   // +0.02 overlap
    }
    // slide the far end back by `cut`
    translate([-cut, 0, 0]) intersection() {
        import("obj71.stl");
        translate([rail_keep_lo + cut, -1, -1]) cube([big, big, big]);
    }
}

module roller_narrow(cut = roller_cut) {
    intersection() { import("obj1.stl"); translate([-big/2,-big/2,-1]) cube([big,big,body_lo+1]); }
    translate([0, 0, -cut]) intersection() {
        import("obj1.stl");
        translate([-big/2,-big/2, body_lo + cut]) cube([big, big, big]);
    }
}

// the kit's drive collar, re-bored for the 28BYJ-48's flatted shaft
module dsc() {
    difference() {
        import("obj17.stl");                       // 8 x 8 x 6.4 collar, as printed
        translate([4, 4, -1]) intersection() {     // its bore, replaced
            cylinder(d=5.25, h=20, $fn=48);
            cube([10, 3.25, 40], center=true);
        }
    }
}

if      (part == "rail_short")   rail_short();
else if (part == "roller_narrow") roller_narrow();
else if (part == "dsc")          dsc();
else if (part == "rail_compare") { import("obj71.stl"); translate([0,50,0]) rail_short(); }

echo(str("rail ", 150 - rail_cut, " long (was 150, cut ", rail_cut, ")   ",
         "roller ", 60 - roller_cut, " long (was 60)"));

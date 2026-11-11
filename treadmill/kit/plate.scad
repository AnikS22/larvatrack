// =====================================================================
// COMPLETE treadmill — every part on one MK4 plate (250 x 210).
// One print gives a working machine: rails, rollers, wheel, collars,
// connectors, pins AND the chain links.
//
// Every part is the conveyor kit's own geometry, untouched, except the
// rail: 60 mm is cut out of its featureless middle (x 40..142) so the
// two rollers sit closer. The guide ribs run straight through the joint.
// =====================================================================
part = "plate";     // plate | rail | roller | wheel | link

rail_cut     = 60;   // rail becomes 150 - this
rail_keep_lo = 45;
n_links      = 21;   // loop = 2 x 74 + pi x 19.2 = 208 mm, /11 = 18.9, +2 spare
n_pins       = 24;
big = 400;

module rail_short(cut = rail_cut) {
    intersection() { import("obj71.stl"); translate([-1,-1,-1]) cube([rail_keep_lo+1.02, big, big]); }
    translate([-cut,0,0]) intersection() {
        import("obj71.stl"); translate([rail_keep_lo+cut,-1,-1]) cube([big,big,big]); }
}

module plate() {
    // --- rails, 90 x 42, bottom-left
    translate([  8,   8, 0]) rail_short();
    translate([  8,  55, 0]) rail_short();
    // --- drive wheel, 46 sq
    translate([105,   8, 0]) import("obj5.stl");
    // --- rollers, 19.2 sq x 60 tall, printed standing so journals stay round
    translate([160,   8, 0]) import("obj1.stl");
    translate([185,   8, 0]) import("obj1.stl");
    // --- shaft collars
    translate([160,  38, 0]) import("obj17.stl");
    translate([172,  38, 0]) import("obj17.stl");
    translate([186,  38, 0]) import("obj19.stl");
    // --- rail connectors: 4 x 3 mm, 2 x 5 mm
    for (i=[0:2]) translate([105, 60 + i*9, 0]) import("obj7.stl");
    translate([128, 60, 0]) import("obj7.stl");
    for (i=[0:1]) translate([128, 69 + i*9, 0]) import("obj9.stl");
    // --- hinge pins, one per link plus spares
    for (i=[0:n_pins-1])
        translate([208 + floor(i/12)*19, 8 + (i%12)*5, 0]) import("obj33.stl");
    // --- chain links, 60 x 11 each, 3 columns x 7 rows
    for (i=[0:n_links-1])
        translate([8 + floor(i/7)*63, 110 + (i%7)*13, 0]) import("one_link.stl");
}

if      (part == "plate")  plate();
else if (part == "rail")   rail_short();
else if (part == "roller") import("obj1.stl");
else if (part == "wheel")  import("obj5.stl");
else if (part == "link")   import("one_link.stl");

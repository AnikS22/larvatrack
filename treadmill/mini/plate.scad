// =====================================================================
// MINI conveyor treadmill — complete, one MK4 plate (250 x 210).
//
// Built on Mini_Conveyor_Belt_New.3mf (Apr 2025), which is the newer and
// much smaller machine:  rail 150 x 34 x 20.5, roller 19.2 x 36 (so a
// 36 mm belt, not 60), wheel 34, link 36 x 10.6 x 4.
//
// Only the rail is modified. It is 150 long with end tabs in x 0..33 and
// x 117..150, and featureless extrusion between. 70 mm is cut out of that
// middle, 150 -> 80 mm, which is what brings the rollers together.
// Nothing else is redrawn.
// =====================================================================
part = "plate";   // plate | rail | roller | wheel | link | pin

rail_cut     = 70;   // rail becomes 150 - this
rail_keep_lo = 40;   // featureless from 33.5, so 40 is safely inside
n_links      = 20;   // loop = 2x64 + pi x 19.2 = 188 mm, /10.6 = 17.8 -> 18 + 2 spare
n_pins       = 24;
big = 400;

module rail_short(cut = rail_cut) {
    intersection() { import("obj37.stl"); translate([-1,-1,-1]) cube([rail_keep_lo+1.02, big, big]); }
    translate([-cut,0,0]) intersection() {
        import("obj37.stl"); translate([rail_keep_lo+cut,-1,-1]) cube([big,big,big]); }
}
module pin_flat() { translate([0,0,2.8]) rotate([0,90,0]) import("obj7.stl"); }

module plate() {
    translate([  8,   8, 0]) rail_short();          // rails, 80 x 34
    translate([  8,  46, 0]) rail_short();
    translate([ 95,   8, 0]) import("obj23.stl");   // drive wheel, 34 sq
    translate([135,   8, 0]) import("obj19.stl");   // rollers, 19.2 sq x 36 tall
    translate([160,   8, 0]) import("obj19.stl");
    translate([135,  35, 0]) import("obj25.stl");   // shaft collars
    translate([147,  35, 0]) import("obj29.stl");
    translate([159,  35, 0]) import("obj27.stl");
    translate([ 95,  48, 0]) import("obj33.stl");   // rail connectors
    translate([112,  48, 0]) import("obj35.stl");
    for (i=[0:n_pins-1])                            // pins, laid flat
        translate([190 + floor(i/8)*20, 8 + (i%8)*5, 0]) pin_flat();
    for (i=[0:n_links-1])                           // chain links, 36 x 10.6
        translate([8 + floor(i/5)*39, 90 + (i%5)*13, 0]) import("obj5.stl");
}

if      (part == "plate")  plate();
else if (part == "rail")   rail_short();
else if (part == "roller") import("obj19.stl");
else if (part == "wheel")  import("obj23.stl");
else if (part == "link")   import("obj5.stl");
else if (part == "pin")    pin_flat();

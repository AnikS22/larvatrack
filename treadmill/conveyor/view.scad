part = "all";
if (part == "all") {
    translate([0,0,0])     import("rama.stl");
    translate([0,120,0])   import("walek.stl");
    translate([120,120,0]) import("bloczek.stl");
    translate([0,200,0])   import("uchwyt-lozyska.stl");
    translate([120,200,0]) import("uchwyt-lozyska_b.stl");
} else import(str(part, ".stl"));

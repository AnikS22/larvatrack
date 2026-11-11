// What IS the black part? Slice it at fly height and look from above.
// STL axes: x = along the belt, y = height, z = across the belt. Rotate so height is up.
mode = "slab";
rotate([90,0,0]) {
    if (mode == "solo") color("#404040") import("Treadmill_Chamber.stl");
    else color("#404040") intersection() {
        import("Treadmill_Chamber.stl");
        translate([-30, 0.4, -5]) cube([80, 0.8, 20]);   // slab through the walking channel
    }
}

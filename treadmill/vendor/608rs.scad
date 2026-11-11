// 608RS — 8 x 22 x 7, nominal. Reference solid for CAD, not a printable part.
// The SLDPRT is proprietary binary with no extractable mesh, so this is built
// from the standard dimensions instead.
id=8; od=22; w=7; $fn=160;
race=1.6;                 // visual only: the seal face sits inboard of the races
difference(){
  union(){
    difference(){ cylinder(d=od,h=w); translate([0,0,-1]) cylinder(d=od-race*2,h=w+2); }
    difference(){ cylinder(d=id+race*2,h=w); translate([0,0,-1]) cylinder(d=id,h=w+2); }
    for(z=[0.35, w-0.35-0.7]) translate([0,0,z])
      difference(){ cylinder(d=od-race*2+0.2,h=0.7); translate([0,0,-1]) cylinder(d=id+race*2-0.2,h=3); }
  }
  translate([0,0,-1]) cylinder(d=id,h=w+2);
}

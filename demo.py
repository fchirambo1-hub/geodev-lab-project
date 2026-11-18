"""Run:  python demo.py   - shows each COGO tool working on sample numbers."""

from surveycore import Point
from surveycore.angles import format_dms, parse_dms
from surveycore.cogo import Observation, area, intersect_bearings, join, resection, tachymetry
from surveycore.traverse import bowditch_traverse

print("=== Join (inverse) ===")
a, b = Point("A", 512000.000, 8734000.000), Point("B", 512300.000, 8734400.000)
br, d = join(a, b)
print(f"A -> B  bearing {format_dms(br)}  distance {d:.3f} m\n")

print("=== Tachymetry (one setup, two detail shots) ===")
st = Point("STN1", 512000.000, 8734000.000, h=1254.320)
for p in tachymetry(st, b, hz_backsight=0.0, inst_h=1.55, shots=[
        Observation("D1", parse_dms("45.1230"), parse_dms("88.3000"), 85.412, 1.80),
        Observation("D2", parse_dms("97.0545"), parse_dms("91.1520"), 120.903, 1.80)]):
    print(" ", p)
print()

print("=== Intersection by bearings ===")
print(" ", intersect_bearings(a, parse_dms("20"), Point("C", 512500, 8734000), parse_dms("320"), "X"), "\n")

print("=== Resection ===")
print(" ", resection(Point("A", 0, 1000), Point("B", 1000, 1000), Point("C", 500, 0),
                     parse_dms("297.5051"), parse_dms("27.2017"), parse_dms("165.4234")), "\n")

print("=== Area of a parcel ===")
parcel = [Point("1", 0, 0), Point("2", 45.2, 3.1), Point("3", 50.8, 60.4), Point("4", -2.3, 55.0)]
sq_m, perim = area(parcel)
print(f"  {sq_m:.2f} m²  ({sq_m / 10000:.4f} ha), perimeter {perim:.2f} m\n")

print("=== Link traverse, Bowditch adjustment ===")
r = bowditch_traverse(
    start=Point("S", 1000, 1000), start_ref=Point("RS", 900, 1300),
    end=Point("E", 1655.0, 1105.3), end_ref=Point("RE", 1800, 900),
    # field book: angles in DDD.MMSS, horizontal distances in metres
    angles=[parse_dms(x) for x in ["80.2945", "231.4901", "108.5455", "248.5614", "213.0221"]],
    distances=[204.045, 186.506, 205.511, 177.197],
    names=["T1", "T2", "T3"])
print("\n".join(r.report))

print("\n=== Import a Netcad-style CSV, export CSV + DXF ===")
from pathlib import Path
from surveycore.dxfexport import write_dxf
from surveycore.pointio import read_points, write_points

out = Path("output")
out.mkdir(exist_ok=True)
imp = read_points("data/sample_parcel.csv")
for w in imp.warnings:
    print("  note:", w)
print(f"  read {len(imp.points)} points")
beacons = [p for p in imp.points if imp.codes.get(p.name) == "BEACON"]
write_points(out / "sample_parcel_clean.csv", imp.points, imp.codes)
write_dxf(out / "sample_parcel.dxf", points=imp.points, parcels=[beacons],
          codes=imp.codes, layer_by_code=True)
write_dxf(out / "traverse.dxf", points=r.points, lines=[r.points])
print(f"  wrote {out / 'sample_parcel_clean.csv'}, {out / 'sample_parcel.dxf'}, {out / 'traverse.dxf'}")

"""Tests for point-file import/export and DXF export."""

import ezdxf
import pytest

from surveycore import Point
from surveycore.dxfexport import write_dxf
from surveycore.pointio import read_points, read_points_text, write_points


def test_header_with_easting_northing():
    r = read_points_text("Name,Easting,Northing,Height,Code\n"
                         "BM1,612345.120,8734567.890,1254.320,BEACON\n"
                         "P2,612400.000,8734600.000,,TREE\n")
    assert [p.name for p in r.points] == ["BM1", "P2"]
    assert (r.points[0].e, r.points[0].n, r.points[0].h) == (612345.12, 8734567.89, 1254.32)
    assert r.points[1].h is None
    assert r.codes == {"BM1": "BEACON", "P2": "TREE"}


def test_netcad_headerless_space_separated():
    # Netcad coordinate list: PointNo  Y(East)  X(North)  Z
    r = read_points_text("1 612345.120 8734567.890 1254.320\n"
                         "2 612400.000 8734600.000 1256.000\n")
    assert (r.points[0].e, r.points[0].n, r.points[0].h) == (612345.12, 8734567.89, 1254.32)


def test_xy_header_auto_detects_netcad_order():
    r = read_points_text("Point;Y;X;Z\nA;612345,120;8734567,890;1254,320\n")   # decimal commas
    p = r.points[0]
    assert (p.e, p.n) == (612345.12, 8734567.89)
    assert any("Netcad" in w for w in r.warnings)


def test_xy_header_auto_detects_math_order():
    r = read_points_text("id\tx\ty\nA\t612345.12\t8734567.89\n")
    assert (r.points[0].e, r.points[0].n) == (612345.12, 8734567.89)


def test_xy_order_forced():
    text = "pt,X,Y\nA,100,200\n"                  # small local grid - can't auto-detect
    assert read_points_text(text, "math").points[0].e == 100
    assert read_points_text(text, "netcad").points[0].e == 200
    assert any("Check" in w for w in read_points_text(text).warnings)


def test_bad_lines_and_duplicates_are_reported():
    r = read_points_text("name,e,n\nA,1,2\nB,oops,3\nA,5,6\n# a comment\n")
    assert len(r.points) == 2
    assert any("skipped" in w for w in r.warnings)
    assert any("duplicate" in w for w in r.warnings)


def test_missing_coordinate_columns():
    with pytest.raises(ValueError):
        read_points_text("name,foo,bar\nA,1,2\n")


def test_write_then_read_roundtrip(tmp_path):
    pts = [Point("BM1", 612345.123, 8734567.891, 1254.32), Point("P2", 612400.0, 8734600.0)]
    f = tmp_path / "out.csv"
    write_points(f, pts, codes={"BM1": "BEACON"})
    r = read_points(f)
    assert [(p.name, p.e, p.n, p.h) for p in r.points] == \
           [("BM1", 612345.123, 8734567.891, 1254.32), ("P2", 612400.0, 8734600.0, None)]
    assert r.codes == {"BM1": "BEACON"}


def test_dxf_contents(tmp_path):
    pts = [Point("1", 0, 0, 100.0), Point("2", 100, 0), Point("3", 100, 50), Point("4", 0, 50)]
    f = write_dxf(tmp_path / "plan.dxf", points=pts, lines=[pts[:3]], parcels=[pts],
                  codes={"1": "BEACON"}, layer_by_code=True)
    doc = ezdxf.readfile(f)
    msp = doc.modelspace()
    points = msp.query("POINT")
    assert len(points) == 4
    first = [p for p in points if p.dxf.layer == "PT_BEACON"][0]
    assert tuple(first.dxf.location) == (0, 0, 100.0)        # X = Easting, Y = Northing, Z = H
    texts = [t.dxf.text for t in msp.query("TEXT")]
    assert "1" in texts and "100.000" in texts
    assert any("5,000.00 m²" in t and "0.5000 ha" in t for t in texts)
    polys = msp.query("LWPOLYLINE")
    assert sorted(p.closed for p in polys) == [False, True]

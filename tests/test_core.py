"""Tests: every calculation is checked against geometry where the answer is known.

Later, add the Survey Department's own worked examples here - if the code
agrees with their hand computations, they will trust the software.
"""

import math

import pytest

from surveycore import Point
from surveycore.angles import dms_to_deg, deg_to_dms, format_dms, normalize, parse_dms
from surveycore.cogo import (Observation, area, intersect_bearings, intersect_distances,
                             join, polar, reduce_slope, resection, tachymetry)
from surveycore.traverse import bowditch_traverse

MM = 0.001


# ------------------------------------------------------------------ angles

def test_dms_roundtrip():
    assert dms_to_deg(45, 30, 15) == pytest.approx(45.5041667, abs=1e-7)
    assert deg_to_dms(45.5041666667) == (45, 30, 15.0)
    assert deg_to_dms(29.99999999) == (30, 0, 0.0)          # no 60 seconds
    assert format_dms(45.5041666667) == "45°30'15.0\""


def test_parse_dms():
    assert parse_dms("45.3015") == pytest.approx(dms_to_deg(45, 30, 15))
    assert parse_dms("45 30 15.5") == pytest.approx(dms_to_deg(45, 30, 15.5))
    assert parse_dms("-12.0030") == pytest.approx(-dms_to_deg(12, 0, 30))


def test_normalize():
    assert normalize(-10) == pytest.approx(350)
    assert normalize(725) == pytest.approx(5)


# -------------------------------------------------------------- join/polar

@pytest.mark.parametrize("de,dn,bearing", [(100, 100, 45), (100, -100, 135),
                                           (-100, -100, 225), (-100, 100, 315),
                                           (0, 50, 0), (50, 0, 90)])
def test_join_quadrants(de, dn, bearing):
    b, d = join(Point("A", 1000, 5000), Point("B", 1000 + de, 5000 + dn))
    assert b == pytest.approx(bearing)
    assert d == pytest.approx(math.hypot(de, dn))


def test_polar_is_inverse_of_join():
    a, b = Point("A", 512345.678, 8734567.891), Point("B", 512801.234, 8734123.456)
    br, d = join(a, b)
    p = polar(a, br, d)
    assert (p.e, p.n) == pytest.approx((b.e, b.n), abs=MM)


# ------------------------------------------------------------- slope/tachy

def test_reduce_slope():
    hd, dh = reduce_slope(100.0, 90.0)
    assert (hd, dh) == pytest.approx((100.0, 0.0), abs=1e-9)
    hd, dh = reduce_slope(100.0, 60.0, inst_h=1.5, target_h=1.5)
    assert hd == pytest.approx(86.6025, abs=1e-4)
    assert dh == pytest.approx(50.0, abs=1e-9)


def test_tachymetry_orientation():
    st = Point("ST", 1000, 1000, h=1200.0)
    bs = Point("BS", 1000, 1100)                      # due north
    # instrument reads 30° on the backsight -> orientation correction = -30°
    shots = [Observation("D1", hz=120.0, zenith=90.0, slope_dist=50.0)]
    (d1,) = tachymetry(st, bs, hz_backsight=30.0, shots=shots)
    assert (d1.e, d1.n, d1.h) == pytest.approx((1050, 1000, 1200.0), abs=MM)


# ----------------------------------------------------------- intersections

def test_intersect_bearings():
    p = intersect_bearings(Point("A", 0, 0), 45, Point("B", 100, 0), 315)
    assert (p.e, p.n) == pytest.approx((50, 50), abs=MM)


def test_intersect_distances_sides():
    a, b = Point("A", 0, 0), Point("B", 100, 0)       # line runs due east
    right = intersect_distances(a, 50 * math.sqrt(2), b, 50 * math.sqrt(2), "right")
    left = intersect_distances(a, 50 * math.sqrt(2), b, 50 * math.sqrt(2), "left")
    assert (right.e, right.n) == pytest.approx((50, -50), abs=MM)   # right of east = south
    assert (left.e, left.n) == pytest.approx((50, 50), abs=MM)


def test_intersect_distances_no_solution():
    with pytest.raises(ValueError):
        intersect_distances(Point("A", 0, 0), 10, Point("B", 100, 0), 10)


# --------------------------------------------------------------- resection

@pytest.mark.parametrize("true", [(520, 430), (300, 900), (950, 200), (-200, -150)])
def test_resection(true):
    a, b, c = Point("A", 0, 1000), Point("B", 1000, 1000), Point("C", 500, 0)
    p = Point("P", *true)
    orient = 17.3                                     # arbitrary circle zero
    dirs = [normalize(join(p, k)[0] - orient) for k in (a, b, c)]
    r = resection(a, b, c, *dirs)
    assert (r.e, r.n) == pytest.approx(true, abs=MM)


# -------------------------------------------------------------------- area

def test_area_square():
    sq = [Point("1", 0, 0), Point("2", 100, 0), Point("3", 100, 100), Point("4", 0, 100)]
    a, perim = area(sq)
    assert a == pytest.approx(10000)
    assert perim == pytest.approx(400)


# ---------------------------------------------------------------- traverse

def _observe(stations, start_ref, end_ref):
    """Make perfect field observations from true coordinates."""
    chain = [start_ref] + stations + [end_ref]
    angles = []
    for i in range(1, len(chain) - 1):
        back, _ = join(chain[i], chain[i - 1])
        fwd, _ = join(chain[i], chain[i + 1])
        angles.append(normalize(fwd - back))
    dists = [join(stations[i], stations[i + 1])[1] for i in range(len(stations) - 1)]
    return angles, dists


TRUE = [Point("S", 1000, 1000), Point("T1", 1180.25, 1095.6),
        Point("T2", 1350.8, 1020.1), Point("T3", 1490.4, 1170.9), Point("E", 1655.0, 1105.3)]
REF_S, REF_E = Point("RS", 900, 1300), Point("RE", 1800, 900)


def test_traverse_perfect_data_closes_exactly():
    angles, dists = _observe(TRUE, REF_S, REF_E)
    r = bowditch_traverse(TRUE[0], REF_S, TRUE[-1], REF_E, angles, dists, ["T1", "T2", "T3"])
    assert r.angular_misclosure == pytest.approx(0, abs=1e-9)
    assert r.linear_misclosure == pytest.approx(0, abs=1e-6)
    for got, want in zip(r.points, TRUE):
        assert (got.e, got.n) == pytest.approx((want.e, want.n), abs=MM)


def test_traverse_with_errors_is_adjusted():
    angles, dists = _observe(TRUE, REF_S, REF_E)
    angles[2] += 20 / 3600            # 20" angle error
    dists[1] += 0.03                  # 3 cm distance error
    r = bowditch_traverse(TRUE[0], REF_S, TRUE[-1], REF_E, angles, dists, ["T1", "T2", "T3"])
    assert r.angular_misclosure * 3600 == pytest.approx(20, abs=0.01)
    assert r.linear_misclosure > 0
    # the adjusted traverse must finish exactly on the known end point
    assert (r.points[-1].e, r.points[-1].n) == pytest.approx((TRUE[-1].e, TRUE[-1].n), abs=1e-6)
    # and intermediate stations should be within a few cm of the truth
    for got, want in zip(r.points, TRUE):
        assert math.hypot(got.e - want.e, got.n - want.n) < 0.05


def test_closed_loop_traverse():
    loop = [Point("A", 0, 0), Point("B", 100, 0), Point("C", 100, 100),
            Point("D", 0, 100), Point("A", 0, 0)]
    ref = Point("R", -50, -50)
    angles, dists = _observe(loop, ref, ref)
    r = bowditch_traverse(loop[0], ref, loop[-1], ref, angles, dists, ["B", "C", "D"])
    assert r.linear_misclosure == pytest.approx(0, abs=1e-6)


def test_traverse_wrong_angle_count():
    with pytest.raises(ValueError):
        bowditch_traverse(TRUE[0], REF_S, TRUE[-1], REF_E, [0, 0], [100, 100, 100])

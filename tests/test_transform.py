"""Tests for the transformation module.

The most important ones compare our results with PROJ (the library behind QGIS):
if both agree, the sign conventions are right and the office can trust the
+towgs84 string this module writes.
"""

import math
import random

import pytest
from pyproj import Transformer
from pyproj.transformer import TransformerGroup

from surveycore import Point
from surveycore.transform import (CLARKE_1880_ARC, WGS84, Helmert7, arc1950_to_wgs84,
                                  estimate_helmert7, fit_2d, geodetic_to_xyz,
                                  geographic_to_utm, utm_to_geographic, wgs84_to_arc1950,
                                  xyz_to_geodetic)

TRUE = Helmert7(-170.25, -78.40, -312.10, 2.1, -1.5, 3.2, 4.5)


def make_control(n=12, seed=1):
    """Fake control points spread over northern/central Malawi on Arc 1950."""
    rnd = random.Random(seed)
    src = {}
    for i in range(n):
        lat, lon = rnd.uniform(-12.5, -9.5), rnd.uniform(33.0, 34.6)
        src[f"CP{i + 1:02d}"] = geodetic_to_xyz(lat, lon, rnd.uniform(470, 2000), CLARKE_1880_ARC)
    dst = {k: TRUE.apply(*v) for k, v in src.items()}
    return src, dst


# ------------------------------------------------------------- conversions

@pytest.mark.parametrize("ell", [CLARKE_1880_ARC, WGS84])
def test_geodetic_xyz_roundtrip(ell):
    for lat, lon, h in [(-11.43, 33.99, 1254.3), (-9.5, 32.7, 0.0), (-17.1, 35.3, 3002.0)]:
        lat2, lon2, h2 = xyz_to_geodetic(*geodetic_to_xyz(lat, lon, h, ell), ell)
        assert (lat2, lon2, h2) == pytest.approx((lat, lon, h), abs=1e-9)


def test_xyz_matches_proj():
    t = Transformer.from_crs(4979, 4978, always_xy=True)          # WGS84 3D -> geocentric
    for lat, lon, h in [(-11.43, 33.99, 1254.3), (-15.8, 35.0, 600.0)]:
        assert geodetic_to_xyz(lat, lon, h, WGS84) == pytest.approx(t.transform(lon, lat, h),
                                                                     abs=1e-4)


def test_utm_roundtrip_mzuzu():
    e, n = geographic_to_utm(-11.4596, 34.0158, "arc1950")
    assert 600_000 < e < 620_000 and 8_720_000 < n < 8_750_000
    assert utm_to_geographic(e, n, "arc1950") == pytest.approx((-11.4596, 34.0158), abs=1e-9)


def test_published_epsg1117_matches_proj():
    """Our chain (UTM -> geog -> XYZ -> shift -> back) equals PROJ's EPSG:1117."""
    op = [t for t in TransformerGroup(4209, 4326, always_xy=True).transformers
          if "Arc 1950 to WGS 84 (5)" in t.description][0]
    h7 = Helmert7(-161, -73, -317, 0, 0, 0, 0)
    lat, lon = -11.4596, 34.0158
    x, y, z = h7.apply(*geodetic_to_xyz(lat, lon, 0.0, CLARKE_1880_ARC))
    lat2, lon2, _ = xyz_to_geodetic(x, y, z, WGS84)
    plon, plat = op.transform(lon, lat)
    assert (lat2, lon2) == pytest.approx((plat, plon), abs=1e-8)   # ~1 mm


# --------------------------------------------------------------- Helmert

def test_helmert_recovers_exact_parameters():
    src, dst = make_control()
    fit = estimate_helmert7(src, dst)
    P = fit.params
    assert (P.tx, P.ty, P.tz) == pytest.approx((TRUE.tx, TRUE.ty, TRUE.tz), abs=1e-3)
    assert (P.rx, P.ry, P.rz) == pytest.approx((TRUE.rx, TRUE.ry, TRUE.rz), abs=1e-5)
    assert P.s_ppm == pytest.approx(TRUE.s_ppm, abs=1e-5)
    assert fit.sigma0 < 1e-6


def test_helmert_with_noise_and_check_points():
    src, dst = make_control(n=15)
    rnd = random.Random(7)
    noisy = {k: tuple(c + rnd.gauss(0, 0.01) for c in v) for k, v in dst.items()}  # 1 cm
    fit = estimate_helmert7(src, noisy, check=["CP14", "CP15"])
    assert 0.005 < fit.sigma0 < 0.02
    assert set(fit.checks) == {"CP14", "CP15"}
    for e, n, u in fit.checks.values():
        assert math.hypot(e, n) < 0.05
    assert not fit.flagged


def test_helmert_flags_a_blunder():
    src, dst = make_control(n=10)
    rnd = random.Random(3)
    noisy = {k: tuple(c + rnd.gauss(0, 0.01) for c in v) for k, v in dst.items()}
    x, y, z = noisy["CP05"]
    noisy["CP05"] = (x + 0.8, y, z)                     # 80 cm blunder
    fit = estimate_helmert7(src, noisy)
    assert "CP05" in fit.flagged


def test_helmert_needs_three_points():
    src, dst = make_control(n=2)
    with pytest.raises(ValueError):
        estimate_helmert7(src, dst)


def test_towgs84_string_agrees_with_proj():
    """The +towgs84 string we hand to QGIS must give the same answer as our own code."""
    src, dst = make_control()
    h7 = estimate_helmert7(src, dst).params
    arc = ("+proj=longlat +a=6378249.145 +rf=293.4663077 " + h7.towgs84() + " +no_defs")
    t = Transformer.from_crs(arc, "EPSG:4326", always_xy=True)
    for lat, lon in [(-11.46, 34.02), (-10.0, 33.5), (-12.3, 34.4)]:
        x, y, z = h7.apply(*geodetic_to_xyz(lat, lon, 0.0, CLARKE_1880_ARC))
        mlat, mlon, _ = xyz_to_geodetic(x, y, z, WGS84)
        plon, plat = t.transform(lon, lat)
        assert (mlat, mlon) == pytest.approx((plat, plon), abs=2e-8)   # ~2 mm


def test_utm_point_round_trip():
    p = Point("BM1", 612345.678, 8734567.891, 1254.32)
    w = arc1950_to_wgs84(p, TRUE)
    assert math.hypot(w.e - p.e, w.n - p.n) > 50          # datum shift is real
    back = wgs84_to_arc1950(w, TRUE)
    assert (back.e, back.n, back.h) == pytest.approx((p.e, p.n, p.h), abs=1e-4)


def test_coordinate_frame_flips_rotations_only():
    cf = TRUE.coordinate_frame()
    assert cf == (TRUE.tx, TRUE.ty, TRUE.tz, -TRUE.rx, -TRUE.ry, -TRUE.rz, TRUE.s_ppm)


# --------------------------------------------------------------- 2D fits

def _local_and_utm(kind):
    local = [Point(str(i), e, n) for i, (e, n) in
             enumerate([(1000, 1000), (1400, 1050), (1350, 1500), (950, 1450), (1200, 1250)])]
    th, k = math.radians(1.25), 1.0004
    out = []
    for p in local:
        if kind == "similarity":
            e = 612000 + k * (p.e * math.cos(th) - p.n * math.sin(th))
            n = 8734000 + k * (p.e * math.sin(th) + p.n * math.cos(th))
        else:
            e = 612000 + 1.0003 * p.e + 0.0002 * p.n
            n = 8734000 - 0.0001 * p.e + 0.9995 * p.n
        out.append(Point(p.name, e, n))
    return local, out


def test_similarity_2d():
    local, utm = _local_and_utm("similarity")
    f = fit_2d(local, utm)
    assert f.scale == pytest.approx(1.0004, abs=1e-9)
    assert f.rotation_deg == pytest.approx(1.25, abs=1e-9)
    assert f.rms < 1e-6
    assert f.apply(1100, 1100) == pytest.approx(
        (612000 + 1.0004 * (1100 * math.cos(math.radians(1.25)) - 1100 * math.sin(math.radians(1.25))),
         8734000 + 1.0004 * (1100 * math.sin(math.radians(1.25)) + 1100 * math.cos(math.radians(1.25)))),
        abs=1e-6)


def test_affine_2d():
    local, utm = _local_and_utm("affine")
    f = fit_2d(local, utm, "affine")
    assert f.rms < 1e-6
    assert f.apply(1000, 2000) == pytest.approx(
        (612000 + 1.0003 * 1000 + 0.0002 * 2000, 8734000 - 0.0001 * 1000 + 0.9995 * 2000), abs=1e-6)

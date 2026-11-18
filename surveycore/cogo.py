"""COGO (coordinate geometry) - the calculations behind Netcad's COGO tab.

All functions use E/N grid coordinates and whole-circle bearings in decimal degrees.
"""

import math
from dataclasses import dataclass

from .angles import normalize
from .point import Point


# ---------------------------------------------------------------- join & polar

def join(p1: Point, p2: Point) -> tuple[float, float]:
    """Inverse / 'join': bearing (deg) and horizontal distance from p1 to p2."""
    de, dn = p2.e - p1.e, p2.n - p1.n
    dist = math.hypot(de, dn)
    if dist == 0:
        raise ValueError(f"{p1.name} and {p2.name} are the same point")
    return normalize(math.degrees(math.atan2(de, dn))), dist


def polar(p: Point, bearing: float, distance: float, name: str = "") -> Point:
    """Polar / radiation: new point at a bearing and horizontal distance from p."""
    b = math.radians(bearing)
    return Point(name, p.e + distance * math.sin(b), p.n + distance * math.cos(b))


# ------------------------------------------------------- slope & tachymetry

def reduce_slope(slope_dist: float, zenith: float,
                 inst_h: float = 0.0, target_h: float = 0.0) -> tuple[float, float]:
    """Slope distance + zenith angle (deg, 90 = horizontal) ->
    (horizontal distance, height difference ground-to-ground)."""
    z = math.radians(zenith)
    hd = slope_dist * math.sin(z)
    dh = slope_dist * math.cos(z) + inst_h - target_h
    return hd, dh


@dataclass
class Observation:
    """One total-station shot to a detail point."""
    name: str
    hz: float          # horizontal circle reading (deg)
    zenith: float      # zenith angle (deg)
    slope_dist: float  # slope distance (m)
    target_h: float = 0.0


def tachymetry(station: Point, backsight: Point, hz_backsight: float,
               shots: list[Observation], inst_h: float = 0.0) -> list[Point]:
    """Netcad 'Tachometry Calculation': coordinate detail points from one setup.

    The instrument is oriented by reading hz_backsight on the backsight point.
    Heights are computed only if the station has a height.
    """
    bs_bearing, _ = join(station, backsight)
    orientation = bs_bearing - hz_backsight          # add to any reading -> bearing
    out = []
    for s in shots:
        hd, dh = reduce_slope(s.slope_dist, s.zenith, inst_h, s.target_h)
        p = polar(station, normalize(s.hz + orientation), hd, s.name)
        if station.h is not None:
            p.h = station.h + dh
        out.append(p)
    return out


# --------------------------------------------------------------- intersections

def intersect_bearings(p1: Point, b1: float, p2: Point, b2: float,
                       name: str = "") -> Point:
    """Intersection of two rays: from p1 on bearing b1 and from p2 on bearing b2."""
    s1, c1 = math.sin(math.radians(b1)), math.cos(math.radians(b1))
    s2, c2 = math.sin(math.radians(b2)), math.cos(math.radians(b2))
    det = s1 * (-c2) - (-s2) * c1        # = sin(b2 - b1)
    if abs(det) < 1e-12:
        raise ValueError("Bearings are parallel - no intersection")
    de, dn = p2.e - p1.e, p2.n - p1.n
    t1 = (de * (-c2) - (-s2) * dn) / det
    return Point(name, p1.e + t1 * s1, p1.n + t1 * c1)


def intersect_distances(p1: Point, d1: float, p2: Point, d2: float,
                        side: str = "right", name: str = "") -> Point:
    """Distance-distance intersection (two arcs).

    side = 'right' or 'left' of the line p1 -> p2 picks one of the two solutions.
    """
    bearing, base = join(p1, p2)
    if base > d1 + d2 or base < abs(d1 - d2):
        raise ValueError("Circles do not intersect - check the distances")
    # angle at p1 between the base line and the line to the new point (cosine rule)
    cos_a = (d1**2 + base**2 - d2**2) / (2 * d1 * base)
    a = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
    if side == "right":
        b = bearing + a
    elif side == "left":
        b = bearing - a
    else:
        raise ValueError("side must be 'right' or 'left'")
    return polar(p1, normalize(b), d1, name)


# ------------------------------------------------------------------- resection

def resection(a: Point, b: Point, c: Point,
              dir_a: float, dir_b: float, dir_c: float, name: str = "P") -> Point:
    """Three-point resection (Tienstra).

    dir_a, dir_b, dir_c are horizontal circle readings (deg) observed at the
    unknown station towards the known points A, B, C.
    Fails near the 'danger circle' (station on the circle through A, B, C).
    """
    # observed angles at P, each opposite the named point
    alpha = math.radians(normalize(dir_c - dir_b))   # angle BPC
    beta = math.radians(normalize(dir_a - dir_c))    # angle CPA
    gamma = math.radians(normalize(dir_b - dir_a))   # angle APB

    def interior(p, q, r):
        """Angle at p from direction p->q clockwise to p->r (radians).
        Same rotation sense as the observed angles above, so the formula
        works whether the triangle is labelled clockwise or anticlockwise."""
        bq, _ = join(p, q)
        br, _ = join(p, r)
        return math.radians(normalize(br - bq))

    A = interior(a, b, c)
    B = interior(b, c, a)
    C = interior(c, a, b)

    def cot(x):
        t = math.tan(x)
        if abs(t) < 1e-15:
            raise ValueError("Degenerate geometry (angle of 0 or 180 deg)")
        return 1.0 / t

    try:
        k1 = 1.0 / (cot(A) - cot(alpha))
        k2 = 1.0 / (cot(B) - cot(beta))
        k3 = 1.0 / (cot(C) - cot(gamma))
    except ZeroDivisionError:
        raise ValueError("Station lies on the danger circle - resection impossible")
    k = k1 + k2 + k3
    if abs(k) < 1e-12:
        raise ValueError("Station lies on the danger circle - resection impossible")
    return Point(name, (k1 * a.e + k2 * b.e + k3 * c.e) / k,
                 (k1 * a.n + k2 * b.n + k3 * c.n) / k)


# ------------------------------------------------------------------------ area

def area(points: list[Point]) -> tuple[float, float]:
    """Area (m²) and perimeter (m) of a polygon by coordinates (shoelace formula)."""
    if len(points) < 3:
        raise ValueError("Need at least 3 points for an area")
    s = 0.0
    perim = 0.0
    for i, p in enumerate(points):
        q = points[(i + 1) % len(points)]
        s += p.e * q.n - q.e * p.n
        perim += math.hypot(q.e - p.e, q.n - p.n)
    return abs(s) / 2.0, perim

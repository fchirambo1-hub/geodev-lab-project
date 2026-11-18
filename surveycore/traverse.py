"""Traverse calculation with angular adjustment and Bowditch (compass rule).

Works for a link traverse (start and end on different known points) and for a
closed loop (end point = start point, closing reference = starting reference).

Angles are clockwise horizontal angles measured at each station
from the back station to the forward station (as observed in the field).
"""

import math
from dataclasses import dataclass, field

from .angles import angle_diff, format_dms, normalize
from .cogo import join
from .point import Point


@dataclass
class TraverseResult:
    points: list[Point]               # adjusted stations, start ... end
    bearings: list[float]             # adjusted leg bearings
    angular_misclosure: float         # degrees (observed - known)
    misclosure_e: float               # metres, before Bowditch
    misclosure_n: float
    linear_misclosure: float
    total_length: float
    precision: float                  # 1 : precision
    report: list[str] = field(default_factory=list)


def bowditch_traverse(start: Point, start_ref: Point,
                      end: Point, end_ref: Point,
                      angles: list[float], distances: list[float],
                      names: list[str] | None = None) -> TraverseResult:
    """Compute and adjust a traverse.

    start_ref : known point backsighted from the start station
    end_ref   : known point foresighted from the end station (closing direction)
    angles    : len(distances) + 1 observed angles: at start, every new station, and end
    distances : horizontal leg lengths
    names     : names for the new (intermediate) stations
    """
    n_legs = len(distances)
    if len(angles) != n_legs + 1:
        raise ValueError(f"Need {n_legs + 1} angles for {n_legs} legs, got {len(angles)}")
    if names is None:
        names = [f"T{i}" for i in range(1, n_legs)]
    if len(names) != n_legs - 1:
        raise ValueError(f"Need {n_legs - 1} station names")

    # 1. angular misclosure -------------------------------------------------
    b_in, _ = join(start_ref, start)          # bearing arriving at the start station
    b = b_in
    for ang in angles:
        b = normalize(b + ang - 180.0)
    b_close_known, _ = join(end, end_ref)
    ang_misc = angle_diff(b, b_close_known)   # observed - known
    corr = -ang_misc / len(angles)            # equal share per angle

    # 2. adjusted bearings of each leg -------------------------------------
    bearings = []
    b = b_in
    for ang in angles[:-1]:
        b = normalize(b + ang + corr - 180.0)
        bearings.append(b)

    # 3. latitudes / departures and linear misclosure -----------------------
    de = [d * math.sin(math.radians(br)) for d, br in zip(distances, bearings)]
    dn = [d * math.cos(math.radians(br)) for d, br in zip(distances, bearings)]
    mis_e = start.e + sum(de) - end.e
    mis_n = start.n + sum(dn) - end.n
    linear = math.hypot(mis_e, mis_n)
    total = sum(distances)
    precision = total / linear if linear > 0 else float("inf")

    # 4. Bowditch: correction proportional to cumulative distance -----------
    pts = [Point(start.name, start.e, start.n)]
    e, n = start.e, start.n
    for i in range(n_legs):
        e += de[i] - mis_e * distances[i] / total
        n += dn[i] - mis_n * distances[i] / total
        name = names[i] if i < n_legs - 1 else end.name
        pts.append(Point(name, e, n))

    report = [
        f"Angular misclosure : {ang_misc * 3600:+.1f}\"  ({len(angles)} angles, "
        f"{corr * 3600:+.1f}\" each)",
        f"Misclosure dE, dN  : {mis_e:+.4f} m, {mis_n:+.4f} m",
        f"Linear misclosure  : {linear:.4f} m over {total:.3f} m",
        f"Precision          : 1 : {precision:,.0f}" if linear > 0 else "Precision          : exact",
        "",
        f"{'Station':<10}{'Bearing':>16}{'Dist':>11}{'Easting':>14}{'Northing':>14}",
    ]
    report.append(f"{pts[0].name:<10}{'':>16}{'':>11}{pts[0].e:>14.3f}{pts[0].n:>14.3f}")
    for i in range(n_legs):
        report.append(f"{pts[i + 1].name:<10}{format_dms(bearings[i]):>16}"
                      f"{distances[i]:>11.3f}{pts[i + 1].e:>14.3f}{pts[i + 1].n:>14.3f}")

    return TraverseResult(pts, bearings, ang_misc, mis_e, mis_n, linear,
                          total, precision, report)

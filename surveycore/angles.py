"""Angle conversions: DMS <-> decimal degrees, normalising bearings."""

import math


def dms_to_deg(d: float, m: float = 0.0, s: float = 0.0) -> float:
    """45, 30, 15 -> 45.504166...  A negative sign on any part makes it negative."""
    sign = -1.0 if (d < 0 or m < 0 or s < 0) else 1.0
    return sign * (abs(d) + abs(m) / 60.0 + abs(s) / 3600.0)


def deg_to_dms(deg: float, sec_decimals: int = 1) -> tuple[int, int, float]:
    """45.504166 -> (45, 30, 15.0). Handles rounding so seconds never show 60."""
    sign = -1 if deg < 0 else 1
    total_sec = round(abs(deg) * 3600.0, sec_decimals)
    d, rem = divmod(total_sec, 3600.0)
    m, s = divmod(rem, 60.0)
    return sign * int(d), int(m), round(s, sec_decimals)


def format_dms(deg: float, sec_decimals: int = 1) -> str:
    """45.504166 -> '45°30'15.0"'"""
    d, m, s = deg_to_dms(deg, sec_decimals)
    sign = "-" if deg < 0 and d == 0 else ""
    return f"{sign}{d}°{m:02d}'{s:0{3 + sec_decimals}.{sec_decimals}f}\""


def parse_dms(text: str) -> float:
    """Parse '45.3015' (DDD.MMSS, common on calculators/instruments) or '45 30 15'."""
    text = text.strip()
    if " " in text:
        parts = [float(p) for p in text.split()]
        return dms_to_deg(*parts)
    neg = text.startswith("-")
    text = text.lstrip("-")
    if "." not in text:
        value = float(text)
    else:
        whole, frac = text.split(".")
        frac = (frac + "0000")
        value = dms_to_deg(float(whole), float(frac[:2]), float(frac[2:4] + "." + frac[4:]))
    return -value if neg else value


def normalize(deg: float) -> float:
    """Bring any angle into the range 0 <= a < 360."""
    a = math.fmod(deg, 360.0)
    if a < 0:
        a += 360.0
    if a >= 360.0 - 1e-12:
        a = 0.0
    return a


def angle_diff(a: float, b: float) -> float:
    """Smallest signed difference a - b in degrees, in the range -180..180."""
    d = normalize(a - b)
    return d - 360.0 if d > 180.0 else d

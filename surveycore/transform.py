"""Datum transformations: Arc 1950 (Clarke 1880) <-> WGS 84 for Malawi.

What is in here
  * ellipsoids and geodetic (lat, lon, h) <-> geocentric (X, Y, Z) conversion
  * UTM zone 36S grid <-> geographic, via pyproj
  * estimate a 7-parameter Helmert (Bursa-Wolf) from common points, with
    residuals, standard deviations and check-point validation
  * apply it, and write it out for QGIS / PROJ (+towgs84) so the office can use it
  * 2D similarity (4-parameter) and affine (6-parameter) fits for local grids

Sign conventions - the most common source of errors in transformations:
  'position_vector'  (EPSG method 9606, used by +towgs84 and by this module)
  'coordinate_frame' (EPSG method 9607) - the SAME numbers with the 3 rotations
                       negated. Always state which one you publish.

Heights: XYZ needs ELLIPSOIDAL heights (h). Arc 1950 heights are normally
orthometric (H, above mean sea level), so use h = H + N with a geoid
undulation N (e.g. from EGM2008). In Malawi N is roughly -10 to -20 m relative
to WGS 84; an error in h mostly ends up in tz and the scale, not in E/N.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from pyproj import Transformer

from .point import Point

RHO = 180 / math.pi * 3600          # arc-seconds per radian


# ---------------------------------------------------------------- ellipsoids

@dataclass(frozen=True)
class Ellipsoid:
    name: str
    a: float        # semi-major axis (m)
    rf: float       # inverse flattening

    @property
    def f(self):
        return 1 / self.rf

    @property
    def e2(self):
        return self.f * (2 - self.f)


CLARKE_1880_ARC = Ellipsoid("Clarke 1880 (Arc)", 6378249.145, 293.4663077)   # EPSG:7013
WGS84 = Ellipsoid("WGS 84", 6378137.0, 298.257223563)                        # EPSG:7030

EPSG = {
    "arc1950_geog": 4209,
    "arc1950_utm36s": 20936,
    "wgs84_geog": 4326,
    "wgs84_utm36s": 32736,
}

# Published Arc 1950 -> WGS 84 shifts for Malawi (3-parameter, metres)
PUBLISHED_MALAWI = {
    "EPSG:1117": {"t": (-161.0, -73.0, -317.0), "accuracy_m": 27},
    "EPSG:6904": {"t": (-179.0, -81.0, -314.0), "accuracy_m": 29},
}


def geodetic_to_xyz(lat, lon, h, ell: Ellipsoid):
    """Latitude, longitude (deg) and ellipsoidal height (m) -> X, Y, Z (m)."""
    p, l = math.radians(lat), math.radians(lon)
    nu = ell.a / math.sqrt(1 - ell.e2 * math.sin(p) ** 2)
    return ((nu + h) * math.cos(p) * math.cos(l),
            (nu + h) * math.cos(p) * math.sin(l),
            (nu * (1 - ell.e2) + h) * math.sin(p))


def xyz_to_geodetic(x, y, z, ell: Ellipsoid):
    """X, Y, Z (m) -> latitude, longitude (deg), ellipsoidal height (m). Iterative,
    converges to well below 0.1 mm."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - ell.e2))
    for _ in range(10):
        nu = ell.a / math.sqrt(1 - ell.e2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - nu
        new = math.atan2(z, p * (1 - ell.e2 * nu / (nu + h)))
        if abs(new - lat) < 1e-13:
            lat = new
            break
        lat = new
    nu = ell.a / math.sqrt(1 - ell.e2 * math.sin(lat) ** 2)
    h = p / math.cos(lat) - nu
    return math.degrees(lat), math.degrees(lon), h


# ----------------------------------------------------------------------- UTM

_utm_cache: dict = {}


def _utm(epsg_utm: int, epsg_geog: int, inverse: bool):
    key = (epsg_utm, epsg_geog, inverse)
    if key not in _utm_cache:
        src, dst = (epsg_utm, epsg_geog) if inverse else (epsg_geog, epsg_utm)
        _utm_cache[key] = Transformer.from_crs(src, dst, always_xy=True)
    return _utm_cache[key]


def utm_to_geographic(e, n, datum="arc1950"):
    """UTM 36S grid -> (lat, lon) on the same datum ('arc1950' or 'wgs84')."""
    lon, lat = _utm(EPSG[f"{datum}_utm36s"], EPSG[f"{datum}_geog"], True).transform(e, n)
    return lat, lon


def geographic_to_utm(lat, lon, datum="arc1950"):
    """(lat, lon) -> UTM 36S Easting, Northing on the same datum."""
    return _utm(EPSG[f"{datum}_utm36s"], EPSG[f"{datum}_geog"], False).transform(lon, lat)


def utm_point_to_xyz(p: Point, datum: str, geoid_n: float = 0.0):
    """UTM point with orthometric height -> geocentric XYZ.
    geoid_n: geoid undulation N (m) so that h = H + N. If p.h is None, H = 0."""
    lat, lon = utm_to_geographic(p.e, p.n, datum)
    h = (p.h or 0.0) + geoid_n
    return geodetic_to_xyz(lat, lon, h, CLARKE_1880_ARC if datum == "arc1950" else WGS84)


def xyz_to_utm_point(name, x, y, z, datum: str, geoid_n: float = 0.0) -> Point:
    lat, lon, h = xyz_to_geodetic(x, y, z, CLARKE_1880_ARC if datum == "arc1950" else WGS84)
    e, n = geographic_to_utm(lat, lon, datum)
    return Point(name, e, n, h - geoid_n)


# ------------------------------------------------------------ Helmert 7-par

@dataclass
class Helmert7:
    """Position-vector convention. Rotations in arc-seconds, scale in ppm."""
    tx: float
    ty: float
    tz: float
    rx: float
    ry: float
    rz: float
    s_ppm: float

    def apply(self, x, y, z):
        rx, ry, rz = (math.radians(r / 3600) for r in (self.rx, self.ry, self.rz))
        m = 1 + self.s_ppm * 1e-6
        return (self.tx + m * (x - rz * y + ry * z),
                self.ty + m * (rz * x + y - rx * z),
                self.tz + m * (-ry * x + rx * y + z))

    def _matrix(self):
        rx, ry, rz = (math.radians(r / 3600) for r in (self.rx, self.ry, self.rz))
        return (1 + self.s_ppm * 1e-6) * np.array([[1, -rz, ry], [rz, 1, -rx], [-ry, rx, 1]])

    def apply_inverse(self, x, y, z):
        """Exact reverse direction (target -> source) of apply()."""
        v = np.linalg.solve(self._matrix(), np.array([x - self.tx, y - self.ty, z - self.tz]))
        return float(v[0]), float(v[1]), float(v[2])

    def coordinate_frame(self) -> tuple:
        """Same parameters in the coordinate-frame convention (EPSG 9607)."""
        return (self.tx, self.ty, self.tz, -self.rx, -self.ry, -self.rz, self.s_ppm)

    def towgs84(self) -> str:
        """String for a PROJ / QGIS custom CRS: +towgs84=..."""
        v = (self.tx, self.ty, self.tz, self.rx, self.ry, self.rz, self.s_ppm)
        return "+towgs84=" + ",".join(f"{x:.4f}" for x in v)

    def proj4_arc1950_utm36s(self) -> str:
        """Complete custom CRS for QGIS: Arc 1950 / UTM 36S using these parameters."""
        return ("+proj=utm +zone=36 +south +a=6378249.145 +rf=293.4663077 "
                f"{self.towgs84()} +units=m +no_defs")

    def __str__(self):
        return (f"tx {self.tx:+.4f} m  ty {self.ty:+.4f} m  tz {self.tz:+.4f} m\n"
                f"rx {self.rx:+.4f}\"  ry {self.ry:+.4f}\"  rz {self.rz:+.4f}\"  "
                f"scale {self.s_ppm:+.4f} ppm   (position-vector convention)")


@dataclass
class HelmertFit:
    params: Helmert7
    std: Helmert7                      # standard deviations, same units
    sigma0: float                      # std. dev. of unit weight (m)
    residuals: dict                    # name -> (vx, vy, vz) m  (observed - computed)
    flagged: list                      # names with suspiciously large residuals
    checks: dict = field(default_factory=dict)   # name -> (dE, dN, dH) at check points
    report: list = field(default_factory=list)


def estimate_helmert7(src: dict, dst: dict, check: list[str] | None = None,
                      flag_factor: float = 3.0) -> HelmertFit:
    """Least-squares 7-parameter Helmert from common points.

    src, dst : point name -> (X, Y, Z) geocentric metres, source and target datum
    check    : names held OUT of the fit and used only to test it (strongly advised)
    Needs at least 3 common points (better 6+ spread over the whole area).
    """
    check = set(check or [])
    names = [k for k in src if k in dst and k not in check]
    if len(names) < 3:
        raise ValueError(f"Need at least 3 common points in the fit, got {len(names)}")
    X1 = np.array([src[k] for k in names], dtype=float)
    X2 = np.array([dst[k] for k in names], dtype=float)

    # centre coordinates for numerical stability; translations restored afterwards
    c = X1.mean(axis=0)
    Xc = X1 - c
    p = np.zeros(7)                    # tx,ty,tz (centred), rx,ry,rz (rad), s
    for _ in range(10):                # Gauss-Newton (model is almost linear)
        J, r = _jacobian_residual(p, Xc, X2 - c)
        dp, *_ = np.linalg.lstsq(J, r, rcond=None)
        p += dp
        if np.max(np.abs(dp)) < 1e-12:
            break
    J, r = _jacobian_residual(p, Xc, X2 - c)
    dof = 3 * len(names) - 7
    sigma0 = math.sqrt(float(r @ r) / dof) if dof > 0 else 0.0
    cov = sigma0 ** 2 * np.linalg.inv(J.T @ J) if dof > 0 else np.zeros((7, 7))

    # translation for un-centred coordinates:  T = Tc + c - (1+s) R c
    tc, (rx, ry, rz), s = p[:3], p[3:6], p[6]
    R = np.array([[1, -rz, ry], [rz, 1, -rx], [-ry, rx, 1]])
    t = tc + c - (1 + s) * R @ c
    params = Helmert7(*t, *(np.array([rx, ry, rz]) * RHO), s * 1e6)
    sd = np.sqrt(np.diag(cov))
    std = Helmert7(*sd[:3], *(sd[3:6] * RHO), sd[6] * 1e6)   # translation sd at centroid

    # r = observed - computed, per point (vX, vY, vZ)
    res = {k: tuple(float(x) for x in r[3 * i:3 * i + 3]) for i, k in enumerate(names)}
    limit = flag_factor * sigma0
    flagged = [k for k, v in res.items() if max(abs(x) for x in v) > limit] if dof > 0 else []

    fit = HelmertFit(params, std, sigma0, res, flagged)
    for k in sorted(check):
        if k in src and k in dst:
            fx = params.apply(*src[k])
            fit.checks[k] = _enh_diff(dst[k], fx)

    fit.report = _report(fit, names)
    return fit


def _jacobian_residual(p, X1, X2):
    tx, ty, tz, rx, ry, rz, s = p
    m = 1 + s
    J = np.zeros((3 * len(X1), 7))
    r = np.zeros(3 * len(X1))
    for i, (x, y, z) in enumerate(X1):
        rot = np.array([x - rz * y + ry * z, rz * x + y - rx * z, -ry * x + rx * y + z])
        model = np.array([tx, ty, tz]) + m * rot
        r[3 * i:3 * i + 3] = X2[i] - model
        J[3 * i:3 * i + 3, 0:3] = np.eye(3)
        J[3 * i:3 * i + 3, 3] = m * np.array([0, -z, y])
        J[3 * i:3 * i + 3, 4] = m * np.array([z, 0, -x])
        J[3 * i:3 * i + 3, 5] = m * np.array([-y, x, 0])
        J[3 * i:3 * i + 3, 6] = rot
    return J, r


def _enh_diff(xyz_true, xyz_calc):
    """Difference true - calc expressed as local East, North, Up (m)."""
    lat, lon, _ = xyz_to_geodetic(*xyz_true, WGS84)
    p, l = math.radians(lat), math.radians(lon)
    d = np.array(xyz_true) - np.array(xyz_calc)
    e = -math.sin(l) * d[0] + math.cos(l) * d[1]
    n = -math.sin(p) * math.cos(l) * d[0] - math.sin(p) * math.sin(l) * d[1] + math.cos(p) * d[2]
    u = math.cos(p) * math.cos(l) * d[0] + math.cos(p) * math.sin(l) * d[1] + math.sin(p) * d[2]
    return e, n, u


def _report(fit: HelmertFit, names) -> list[str]:
    P, S = fit.params, fit.std
    out = ["7-PARAMETER HELMERT (position-vector, EPSG 9606)",
           f"Points in fit: {len(names)}   sigma0 = {fit.sigma0 * 1000:.1f} mm", "",
           f"  tx {P.tx:+12.4f} m      ty {P.ty:+12.4f} m      tz {P.tz:+12.4f} m",
           f"  rx {P.rx:+12.4f}\" ±{S.rx:.4f}  ry {P.ry:+12.4f}\" ±{S.ry:.4f}  "
           f"rz {P.rz:+12.4f}\" ±{S.rz:.4f}",
           f"  scale {P.s_ppm:+.4f} ppm ±{S.s_ppm:.4f}", "",
           f"{'Point':<10}{'vX mm':>10}{'vY mm':>10}{'vZ mm':>10}"]
    for k, v in fit.residuals.items():
        flag = "  <-- check this point" if k in fit.flagged else ""
        out.append(f"{k:<10}" + "".join(f"{x * 1000:>10.1f}" for x in v) + flag)
    if fit.checks:
        out += ["", "CHECK POINTS (not used in fit)",
                f"{'Point':<10}{'dE mm':>10}{'dN mm':>10}{'dU mm':>10}{'horiz mm':>10}"]
        for k, (e, n, u) in fit.checks.items():
            out.append(f"{k:<10}{e * 1000:>10.1f}{n * 1000:>10.1f}{u * 1000:>10.1f}"
                       f"{math.hypot(e, n) * 1000:>10.1f}")
    out += ["", "QGIS custom CRS (Arc 1950 / UTM 36S, this fit):", "  " + P.proj4_arc1950_utm36s()]
    return out


# ------------------------------------------------------------ convenience

def arc1950_to_wgs84(p: Point, h7: Helmert7, n_arc: float = 0.0, n_wgs: float = 0.0) -> Point:
    """Arc 1950 / UTM 36S point -> WGS 84 / UTM 36S point.

    n_arc, n_wgs: geoid undulation relative to each ellipsoid at this point.
    With both 0, the input height is treated as ellipsoidal and the output
    height is the WGS 84 ellipsoidal height. E/N are hardly affected either way.
    """
    x, y, z = utm_point_to_xyz(p, "arc1950", n_arc)
    return xyz_to_utm_point(p.name, *h7.apply(x, y, z), "wgs84", n_wgs)


def wgs84_to_arc1950(p: Point, h7: Helmert7, n_arc: float = 0.0, n_wgs: float = 0.0) -> Point:
    """WGS 84 / UTM 36S point -> Arc 1950 / UTM 36S point (exact inverse of h7)."""
    x, y, z = utm_point_to_xyz(p, "wgs84", n_wgs)
    return xyz_to_utm_point(p.name, *h7.apply_inverse(x, y, z), "arc1950", n_arc)


# --------------------------------------------------------------- 2D fits

@dataclass
class Fit2D:
    kind: str
    coeffs: np.ndarray             # see apply()
    residuals: dict                # name -> (vE, vN) metres
    rms: float
    scale: float = 1.0
    rotation_deg: float = 0.0

    def apply(self, e, n):
        if self.kind == "similarity":
            a, b, te, tn = self.coeffs
            return te + a * e - b * n, tn + b * e + a * n
        a1, a2, a3, b1, b2, b3 = self.coeffs
        return a1 + a2 * e + a3 * n, b1 + b2 * e + b3 * n


def fit_2d(src: list[Point], dst: list[Point], kind: str = "similarity") -> Fit2D:
    """Fit a 2D transformation from matching points (same names, same order).

    'similarity' (4 parameters: shift E/N, rotation, one scale) - keeps shapes;
                 the normal choice for putting a local/assumed grid on UTM.
    'affine'     (6 parameters) - also absorbs different E/N scales and shear,
                 e.g. digitised paper plans that have shrunk unevenly.
    """
    if [p.name for p in src] != [p.name for p in dst]:
        raise ValueError("src and dst must list the same point names in the same order")
    need = 2 if kind == "similarity" else 3
    if len(src) < need:
        raise ValueError(f"{kind} needs at least {need} points")
    # centre for numerical stability
    ce, cn = np.mean([p.e for p in src]), np.mean([p.n for p in src])
    A, L = [], []
    for s, d in zip(src, dst):
        e, n = s.e - ce, s.n - cn
        if kind == "similarity":
            A += [[e, -n, 1, 0], [n, e, 0, 1]]
        elif kind == "affine":
            A += [[1, e, n, 0, 0, 0], [0, 0, 0, 1, e, n]]
        else:
            raise ValueError("kind must be 'similarity' or 'affine'")
        L += [d.e, d.n]
    A, L = np.array(A, float), np.array(L, float)
    x, *_ = np.linalg.lstsq(A, L, rcond=None)
    v = A @ x - L
    # convert from centred to raw source coordinates
    if kind == "similarity":
        a, b, te, tn = x
        coeffs = np.array([a, b, te - a * ce + b * cn, tn - b * ce - a * cn])
        scale, rot = math.hypot(a, b), math.degrees(math.atan2(b, a))
    else:
        a1, a2, a3, b1, b2, b3 = x
        coeffs = np.array([a1 - a2 * ce - a3 * cn, a2, a3, b1 - b2 * ce - b3 * cn, b2, b3])
        scale, rot = 1.0, 0.0
    res = {s.name: (-v[2 * i], -v[2 * i + 1]) for i, s in enumerate(src)}
    rms = math.sqrt(float(v @ v) / len(src))
    return Fit2D(kind, coeffs, res, rms, scale, rot)

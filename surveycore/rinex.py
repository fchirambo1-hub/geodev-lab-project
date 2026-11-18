"""RINEX observation file reader and quality check (versions 2.10/2.11 and 3.0x).

Why this exists: before sending GNSS data to a processing service (CSRS-PPP,
AUSPOS, RTKLIB) you must know what is inside - which station, which receiver
and antenna, the antenna height, how long it logged, at what interval, which
satellite systems, and whether there are gaps. A bad antenna height or a
6-hour gap ruins the coordinates that the transformation (transform.py) relies on.

Supported: plain text files, also gzip-compressed (*.gz).
Not supported: Hatanaka-compressed files (*.crx, *.YYd) - decompress with CRX2RNX first.
"""

import gzip
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

SYSTEM_NAMES = {"G": "GPS", "R": "GLONASS", "E": "Galileo", "C": "BeiDou",
                "J": "QZSS", "I": "NavIC", "S": "SBAS"}


class RinexError(ValueError):
    pass


@dataclass
class RinexHeader:
    version: float = 0.0
    file_type: str = ""
    system: str = ""                       # G, R, E, M (mixed) ...
    program: str = ""
    marker_name: str = ""
    marker_number: str = ""
    observer: str = ""
    agency: str = ""
    receiver: str = ""                     # number / type / firmware
    antenna: str = ""                      # number / type
    antenna_type: str = ""
    approx_xyz: tuple | None = None        # metres, WGS 84 / ITRF (approximate!)
    antenna_delta_hen: tuple = (0.0, 0.0, 0.0)   # height, east, north (m)
    obs_types: dict = field(default_factory=dict)  # system -> list of codes
    interval: float | None = None          # seconds
    first_obs: datetime | None = None
    last_obs: datetime | None = None
    time_system: str = ""
    n_lines: int = 0


@dataclass
class Epoch:
    time: datetime
    flag: int
    sats: list[str]


# ------------------------------------------------------------------ opening

def _open(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="ascii", errors="replace")
    return open(path, "r", encoding="ascii", errors="replace")


def _float(s: str, default=None):
    s = s.strip()
    if not s:
        return default
    return float(s.replace("D", "E").replace("d", "e"))


def _time_from_header(s: str) -> datetime | None:
    """Parse TIME OF FIRST/LAST OBS. Some receivers write the line blank -> None."""
    try:
        parts = s[:43].split()
        y, mo, d, h, mi = (int(x) for x in parts[:5])
        return datetime(y, mo, d, h, mi) + timedelta(seconds=float(parts[5]))
    except (ValueError, IndexError):
        return None


# ------------------------------------------------------------------ header

def read_header(path: str | Path) -> RinexHeader:
    path = Path(path)
    with _open(path) as f:
        return _read_header(f, path)


def _read_header(f, path: Path) -> RinexHeader:
    hdr = RinexHeader()
    v2_types: list[str] = []
    v2_count = 0
    v3_sys = ""
    for line in f:
        hdr.n_lines += 1
        label = line[60:80].strip()
        data = line[:60]
        if hdr.n_lines == 1:
            if "COMPACT RINEX" in line or "CRINEX" in line:
                raise RinexError(f"{path.name} is Hatanaka-compressed: run CRX2RNX first")
            if label != "RINEX VERSION / TYPE":
                raise RinexError(f"{path.name} does not start with a RINEX header")
            hdr.version = float(data[:9])
            hdr.file_type = data[20:21]
            hdr.system = data[40:41].strip() or "G"
            if hdr.file_type != "O":
                raise RinexError(f"{path.name} is RINEX type '{hdr.file_type}', "
                                 "not an observation (O) file")
            continue
        if label == "PGM / RUN BY / DATE":
            hdr.program = data[:20].strip()
        elif label == "MARKER NAME":
            hdr.marker_name = data.strip()
        elif label == "MARKER NUMBER":
            hdr.marker_number = data[:20].strip()
        elif label == "OBSERVER / AGENCY":
            hdr.observer, hdr.agency = data[:20].strip(), data[20:60].strip()
        elif label == "REC # / TYPE / VERS":
            hdr.receiver = " / ".join(x.strip() for x in (data[:20], data[20:40], data[40:60]))
        elif label == "ANT # / TYPE":
            hdr.antenna = " / ".join(x.strip() for x in (data[:20], data[20:40]))
            hdr.antenna_type = data[20:40].strip()
        elif label == "APPROX POSITION XYZ":
            hdr.approx_xyz = tuple(_float(data[i:i + 14], 0.0) for i in (0, 14, 28))
        elif label == "ANTENNA: DELTA H/E/N":
            hdr.antenna_delta_hen = tuple(_float(data[i:i + 14], 0.0) for i in (0, 14, 28))
        elif label == "# / TYPES OF OBSERV":                  # RINEX 2
            if data[:6].strip():
                v2_count = int(data[:6])
            v2_types += data[6:60].split()
        elif label == "SYS / # / OBS TYPES":                  # RINEX 3
            if data[0] != " ":
                v3_sys = data[0]
                hdr.obs_types[v3_sys] = []
            hdr.obs_types[v3_sys] += data[7:60].split()
        elif label == "INTERVAL":
            hdr.interval = _float(data[:10])
        elif label == "TIME OF FIRST OBS":
            hdr.first_obs = _time_from_header(data)
            hdr.time_system = data[48:51].strip()
        elif label == "TIME OF LAST OBS":
            hdr.last_obs = _time_from_header(data)
        elif label == "END OF HEADER":
            break
    else:
        raise RinexError(f"{path.name}: no END OF HEADER found")
    if hdr.version < 3:
        if v2_count and len(v2_types) != v2_count:
            raise RinexError(f"{path.name}: header says {v2_count} obs types, found {len(v2_types)}")
        hdr.obs_types = {"*": v2_types}       # same list for every system in RINEX 2
    return hdr


# ------------------------------------------------------------------ epochs

def iter_epochs(path: str | Path) -> Iterator[Epoch]:
    """Yield every observation epoch: time, flag and the satellites observed.
    (Measurement values are skipped - this is for quality checking.)"""
    path = Path(path)
    with _open(path) as f:
        hdr = _read_header(f, path)
        if hdr.version >= 3:
            yield from _epochs_v3(f)
        else:
            yield from _epochs_v2(f, len(hdr.obs_types["*"]), hdr.system)


def _sat_id(s: str, default_sys: str) -> str:
    s = s.strip()
    if not s:
        return ""
    if s[0].isdigit():
        s = (default_sys if default_sys != "M" else "G") + s
    return f"{s[0]}{int(s[1:]):02d}"


def _epochs_v2(f, n_types: int, default_sys: str):
    lines_per_sat = max(1, math.ceil(n_types / 5))
    for line in f:
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        flag = int(line[28:29].strip() or 0)
        n = int(line[29:32])
        if flag > 1:                             # event: n header-type lines follow
            for _ in range(n):
                next(f, None)
            continue
        yy = int(line[1:3])
        year = 2000 + yy if yy < 80 else 1900 + yy
        t = (datetime(year, int(line[4:6]), int(line[7:9]), int(line[10:12]), int(line[13:15]))
             + timedelta(seconds=float(line[15:26])))
        sat_text = line[32:68]
        while len(sat_text) < 3 * n:             # more than 12 satellites: continuation lines
            sat_text += next(f).rstrip("\r\n")[32:68]
        sats = [_sat_id(sat_text[3 * i:3 * i + 3], default_sys) for i in range(n)]
        for _ in range(n * lines_per_sat):
            next(f, None)
        yield Epoch(t, flag, sats)


def _epochs_v3(f):
    for line in f:
        if not line.startswith(">"):
            continue
        flag = int(line[31:32].strip() or 0)
        n = int(line[32:35])
        if flag > 1:
            for _ in range(n):
                next(f, None)
            continue
        p = line[1:29].split()
        t = (datetime(int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4]))
             + timedelta(seconds=float(p[5])))
        sats = []
        for _ in range(n):
            obs_line = next(f, "")
            sats.append(_sat_id(obs_line[:3], "G"))
        yield Epoch(t, flag, sats)


# ------------------------------------------------------------------ quality check

@dataclass
class QCResult:
    path: Path
    header: RinexHeader
    n_epochs: int
    first: datetime | None
    last: datetime | None
    interval: float | None
    expected_epochs: int
    completeness: float                         # %
    gaps: list[tuple[datetime, datetime]]       # periods with no data
    sats_by_system: dict                        # system -> (min, mean, max) per epoch
    unique_sats: dict                           # system -> sorted satellite list
    lat_lon_h: tuple | None = None
    utm36s: tuple | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> timedelta:
        return (self.last - self.first) if self.first and self.last else timedelta(0)

    def report(self) -> str:
        h = self.header
        L = [f"RINEX QUALITY CHECK - {self.path.name}",
             f"  RINEX version     : {h.version:.2f}   (system {h.system})",
             f"  Station (marker)  : {h.marker_name or '-'}  {h.marker_number}",
             f"  Receiver          : {h.receiver or '-'}",
             f"  Antenna           : {h.antenna or '-'}",
             f"  Antenna height    : {h.antenna_delta_hen[0]:.4f} m  (E {h.antenna_delta_hen[1]:.4f}, "
             f"N {h.antenna_delta_hen[2]:.4f})",
             f"  Observer / agency : {h.observer or '-'} / {h.agency or '-'}"]
        if self.lat_lon_h:
            lat, lon, hh = self.lat_lon_h
            L.append(f"  Approx. position  : {abs(lat):.5f}°{'S' if lat < 0 else 'N'}  "
                     f"{abs(lon):.5f}°{'E' if lon >= 0 else 'W'}  h {hh:.1f} m")
        if self.utm36s:
            L.append(f"  Approx. UTM 36S   : E {self.utm36s[0]:.1f}  N {self.utm36s[1]:.1f}"
                     "  (header value, metres-level only)")
        L += ["",
              f"  First epoch       : {self.first}",
              f"  Last epoch        : {self.last}",
              f"  Duration          : {_fmt_td(self.duration)}",
              f"  Interval          : {self.interval:g} s" if self.interval else "  Interval          : ?",
              f"  Epochs            : {self.n_epochs:,} of {self.expected_epochs:,} expected "
              f"({self.completeness:.1f} % complete)",
              f"  Gaps              : {len(self.gaps)}"]
        for a, b in self.gaps[:10]:
            L.append(f"      {a}  ->  {b}   ({_fmt_td(b - a)})")
        if len(self.gaps) > 10:
            L.append(f"      … and {len(self.gaps) - 10} more")
        L += ["", "  Satellites per epoch   min   mean   max   (different satellites seen)"]
        for s, (mn, mean, mx) in self.sats_by_system.items():
            L.append(f"    {SYSTEM_NAMES.get(s, s):<18}{mn:>6}{mean:>7.1f}{mx:>6}"
                     f"   ({len(self.unique_sats[s])})")
        L += ["", "  Observation types:"]
        for s, types in self.header.obs_types.items():
            name = "all systems" if s == "*" else SYSTEM_NAMES.get(s, s)
            L.append(f"    {name:<12} {' '.join(types)}")
        if self.warnings:
            L += ["", "  WARNINGS"] + [f"   ! {w}" for w in self.warnings]
        return "\n".join(L)


def _fmt_td(td: timedelta) -> str:
    s = int(td.total_seconds())
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return (f"{d} d " if d else "") + f"{h:02d}:{m:02d}:{s:02d}"


def quality_check(path: str | Path, gap_factor: float = 2.0) -> QCResult:
    """Read the whole file and summarise data quality.
    A gap is any jump between epochs longer than gap_factor x interval."""
    path = Path(path)
    hdr = read_header(path)
    times: list[datetime] = []
    per_sys_counts: dict[str, list[int]] = {}
    unique: dict[str, set] = {}
    for ep in iter_epochs(path):
        times.append(ep.time)
        counts: dict[str, int] = {}
        for s in ep.sats:
            if s:
                counts[s[0]] = counts.get(s[0], 0) + 1
                unique.setdefault(s[0], set()).add(s)
        for sys_ in set(per_sys_counts) | set(counts):
            per_sys_counts.setdefault(sys_, [0] * (len(times) - 1)).append(counts.get(sys_, 0))

    warnings = []
    if not times:
        raise RinexError(f"{path.name}: no observation epochs found")
    diffs = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    interval = hdr.interval or (statistics.median(diffs) if diffs else None)
    if hdr.interval and diffs and abs(statistics.median(diffs) - hdr.interval) > 1e-3:
        warnings.append(f"Header INTERVAL {hdr.interval:g} s but data spacing is "
                        f"{statistics.median(diffs):g} s")
    gaps = []
    if interval:
        gaps = [(a, b) for a, b, d in zip(times, times[1:], diffs) if d > gap_factor * interval]
    span = (times[-1] - times[0]).total_seconds()
    expected = int(round(span / interval)) + 1 if interval else len(times)
    completeness = 100.0 * len(times) / expected if expected else 100.0
    if any(d <= 0 for d in diffs):
        warnings.append("Epochs out of order or duplicated")

    stats = {s: (min(v), statistics.mean(v), max(v)) for s, v in sorted(per_sys_counts.items())}
    res = QCResult(path, hdr, len(times), times[0], times[-1], interval, expected,
                   completeness, gaps, stats, {s: sorted(v) for s, v in sorted(unique.items())},
                   warnings=warnings)

    # position from header (approximate - the receiver's own quick solution)
    if hdr.approx_xyz and any(hdr.approx_xyz):
        from .transform import WGS84, geographic_to_utm, xyz_to_geodetic
        lat, lon, h = xyz_to_geodetic(*hdr.approx_xyz, WGS84)
        res.lat_lon_h = (lat, lon, h)
        if 30 <= lon < 36 and lat < 0:
            res.utm36s = geographic_to_utm(lat, lon, "wgs84")
        elif lat < 0:
            warnings.append("Station is outside UTM zone 36S (30°E–36°E)")
    else:
        warnings.append("No APPROX POSITION XYZ in header")

    # advice for static processing
    hrs = res.duration.total_seconds() / 3600
    if hdr.antenna_delta_hen[0] == 0:
        warnings.append("Antenna height is 0.000 m - was it entered in the receiver? "
                        "Check the field book before processing")
    if not hdr.antenna_type or hdr.antenna_type.upper() in ("", "UNKNOWN"):
        warnings.append("Antenna type missing - PPP services need it for phase-centre corrections")
    if hrs < 2:
        warnings.append(f"Only {hrs:.1f} h of data: PPP needs 2 h minimum, ideally 6–24 h for "
                        "control points")
    elif hrs < 6:
        warnings.append(f"{hrs:.1f} h of data: fine for PPP at the ~2–5 cm level; 24 h is "
                        "better for geodetic control")
    if completeness < 90:
        warnings.append(f"Only {completeness:.0f} % of expected epochs - check the gaps")
    if "G" in stats and stats["G"][0] < 4:
        warnings.append(f"Some epochs have fewer than 4 GPS satellites (min {stats['G'][0]})")
    # file names like 99NY1170.26o carry the 2-digit year; a different year in the data
    # usually means a receiver clock / GPS week-rollover problem
    suffix = path.name.lower().removesuffix(".gz")[-3:]
    if len(suffix) == 3 and suffix[:2].isdigit() and suffix[2] == "o":
        yy = 2000 + int(suffix[:2])
        if times[0].year != yy:
            warnings.append(f"File name says {yy} but data starts {times[0]:%Y-%m-%d} - "
                            "receiver date is wrong (GPS week rollover?) or file is misnamed")
    if hdr.last_obs and abs((hdr.last_obs - times[-1]).total_seconds()) > (interval or 1):
        warnings.append(f"Header TIME OF LAST OBS ({hdr.last_obs}) differs from the data "
                        f"({times[-1]}) - file may be truncated")
    return res

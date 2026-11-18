"""Tests for the RINEX reader, using small files written in exact RINEX column format."""

import gzip
from datetime import datetime, timedelta

import pytest

from surveycore.rinex import RinexError, iter_epochs, quality_check, read_header
from surveycore.transform import WGS84, geodetic_to_xyz

XYZ = geodetic_to_xyz(-11.40, 33.50, 1300.0, WGS84)          # near Mzuzu


def H(data: str, label: str) -> str:
    return f"{data:<60}{label:<20}\n"


def common_header(version_line, obs_type_lines, interval=30.0, ant_h=1.5250,
                  first=datetime(2026, 4, 27), last=None):
    s = version_line
    s += H(f"{'teqc':<20}{'Survey Dept':<20}{'20260509':<20}", "PGM / RUN BY / DATE")
    s += H("99NY", "MARKER NAME")
    s += H("99NY", "MARKER NUMBER")
    s += H(f"{'Field Team':<20}{'Geodetic Office':<40}", "OBSERVER / AGENCY")
    s += H(f"{'1234567':<20}{'GEOMAX ZENITH60':<20}{'1.2':<20}", "REC # / TYPE / VERS")
    s += H(f"{'A987':<20}{'GMXZENITH60     NONE':<20}", "ANT # / TYPE")
    s += H("".join(f"{v:14.4f}" for v in XYZ), "APPROX POSITION XYZ")
    s += H(f"{ant_h:14.4f}{0:14.4f}{0:14.4f}", "ANTENNA: DELTA H/E/N")
    s += "".join(obs_type_lines)
    s += H(f"{interval:10.3f}", "INTERVAL")
    s += H(f"{first.year:6d}{first.month:6d}{first.day:6d}{0:6d}{0:6d}{0:13.7f}     GPS",
           "TIME OF FIRST OBS")
    if last:
        sec = last.second
        s += H(f"{last.year:6d}{last.month:6d}{last.day:6d}{last.hour:6d}{last.minute:6d}"
               f"{sec:13.7f}     GPS", "TIME OF LAST OBS")
    s += H("", "END OF HEADER")
    return s


def v2_file(times, sats_fn, n_types=8, event_after=None):
    types = ["L1", "L2", "C1", "P1", "P2", "D1", "D2", "S1"][:n_types]
    lines = [H(f"{n_types:6d}" + "".join(f"{t:>6}" for t in types), "# / TYPES OF OBSERV")]
    out = common_header(H(f"{2.11:9.2f}{'':11}{'O':<20}{'M (MIXED)':<20}",
                          "RINEX VERSION / TYPE"), lines, last=times[-1])
    per_sat = -(-n_types // 5)
    for i, t in enumerate(times):
        sats = sats_fn(i)
        head = (f" {t.year % 100:02d} {t.month:2d} {t.day:2d} {t.hour:2d} {t.minute:2d}"
                f"{t.second + t.microsecond / 1e6:11.7f}  0{len(sats):3d}")
        ids = "".join(sats)
        out += head + ids[:36] + "\n"
        rest = ids[36:]
        while rest:
            out += " " * 32 + rest[:36] + "\n"
            rest = rest[36:]
        for _ in sats:
            for _ in range(per_sat):
                out += "  21345678.12345 6" * 5 + "\n"
        if event_after == i:
            out += f"{'':28}4  1\n" + H("antenna moved? no", "COMMENT")
    return out


def v3_file(times, sats_fn):
    lines = [H("G   4 C1C L1C D1C S1C", "SYS / # / OBS TYPES"),
             H("R   4 C1C L1C D1C S1C", "SYS / # / OBS TYPES"),
             H("E  16 C1C L1C D1C S1C C5Q L5Q D5Q S5Q C7Q L7Q D7Q S7Q C8Q", "SYS / # / OBS TYPES"),
             H("       L8Q D8Q S8Q", "SYS / # / OBS TYPES")]   # continuation line (16 total)
    out = common_header(H(f"{3.04:9.2f}{'':11}{'OBSERVATION DATA':<20}{'M':<20}",
                          "RINEX VERSION / TYPE"), lines, interval=1.0, last=times[-1])
    for i, t in enumerate(times):
        sats = sats_fn(i)
        out += (f"> {t.year:4d} {t.month:02d} {t.day:02d} {t.hour:02d} {t.minute:02d}"
                f"{t.second:11.7f}  0{len(sats):3d}\n")
        for s in sats:
            out += s + "  21345678.123   112233445.123 6\n"
    return out


def gps(n, start=1):
    return [f"G{k:02d}" for k in range(start, start + n)]


# ---------------------------------------------------------------- RINEX 2

@pytest.fixture
def v2_path(tmp_path):
    t0 = datetime(2026, 4, 27)
    # 3 hours at 30 s with a 20-minute gap after epoch 100
    times = [t0 + timedelta(seconds=30 * i) for i in range(361) if not 100 < i <= 140]
    sats = lambda i: gps(14 if i == 0 else 8) + [f"R{k:02d}" for k in (3, 4, 12)]
    p = tmp_path / "99NY1170.26o"
    p.write_text(v2_file(times, sats, event_after=5), encoding="ascii")
    return p, times


def test_v2_header(v2_path):
    h = read_header(v2_path[0])
    assert h.version == 2.11 and h.system == "M"
    assert h.marker_name == "99NY"
    assert "GEOMAX ZENITH60" in h.receiver
    assert h.antenna_type == "GMXZENITH60     NONE"
    assert h.antenna_delta_hen == (1.525, 0.0, 0.0)
    assert h.obs_types["*"] == ["L1", "L2", "C1", "P1", "P2", "D1", "D2", "S1"]
    assert h.interval == 30.0


def test_v2_epochs_continuation_and_events(v2_path):
    path, times = v2_path
    eps = list(iter_epochs(path))
    assert [e.time for e in eps] == times            # event record skipped
    assert len(eps[0].sats) == 17                     # 14 GPS on 2 lines + 3 GLONASS
    assert eps[0].sats[12:15] == ["G13", "G14", "R03"]


def test_v2_quality_check(v2_path):
    qc = quality_check(v2_path[0])
    assert qc.n_epochs == 321 and qc.expected_epochs == 361
    assert qc.completeness == pytest.approx(100 * 321 / 361)
    assert len(qc.gaps) == 1
    assert qc.gaps[0][1] - qc.gaps[0][0] == timedelta(seconds=30 * 41)
    assert qc.sats_by_system["G"][2] == 14 and qc.sats_by_system["R"] == (3, 3, 3)
    lat, lon, h = qc.lat_lon_h
    assert (lat, lon, h) == pytest.approx((-11.40, 33.50, 1300.0), abs=1e-6)
    assert 600_000 > qc.utm36s[0] > 500_000
    assert any("3.0 h" in w for w in qc.warnings)     # short session advice
    assert "99NY" in qc.report()


# ---------------------------------------------------------------- RINEX 3

def test_v3_mixed_file_and_gzip(tmp_path):
    t0 = datetime(2026, 5, 9, 6)
    times = [t0 + timedelta(seconds=i) for i in range(600)]
    sats = lambda i: gps(9) + ["R01", "R02"] + ["E05", "E09", "E24"]
    text = v3_file(times, sats)
    p = tmp_path / "27NY00MWI_R_20261290600_10M_01S_MO.rnx.gz"
    with gzip.open(p, "wt", encoding="ascii") as f:
        f.write(text)
    h = read_header(p)
    assert h.version == 3.04
    assert len(h.obs_types["E"]) == 16 and h.obs_types["E"][-1] == "S8Q"
    qc = quality_check(p)
    assert qc.n_epochs == 600 and qc.completeness == 100 and not qc.gaps
    assert set(qc.sats_by_system) == {"G", "R", "E"}
    assert qc.unique_sats["E"] == ["E05", "E09", "E24"]


# ---------------------------------------------------------------- errors

def test_rejects_navigation_file(tmp_path):
    p = tmp_path / "99NY1170.26n"
    p.write_text(H(f"{2.11:9.2f}{'':11}{'N: GPS NAV DATA':<20}", "RINEX VERSION / TYPE"))
    with pytest.raises(RinexError, match="not an observation"):
        read_header(p)


def test_rejects_hatanaka(tmp_path):
    p = tmp_path / "x.crx"
    p.write_text(H("3.0                 COMPACT RINEX FORMAT", "CRINEX VERS   / TYPE"))
    with pytest.raises(RinexError, match="CRX2RNX"):
        read_header(p)


def test_warns_on_zero_antenna_height(tmp_path):
    t0 = datetime(2026, 4, 27)
    times = [t0 + timedelta(seconds=30 * i) for i in range(10)]
    text = v2_file(times, lambda i: gps(6))
    text = text.replace(H(f"{1.525:14.4f}{0:14.4f}{0:14.4f}", "ANTENNA: DELTA H/E/N"),
                        H(f"{0:14.4f}{0:14.4f}{0:14.4f}", "ANTENNA: DELTA H/E/N"))
    p = tmp_path / "a.26o"
    p.write_text(text)
    qc = quality_check(p)
    assert any("Antenna height is 0.000" in w for w in qc.warnings)

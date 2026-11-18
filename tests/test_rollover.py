"""Tests for the GPS week-rollover repair."""

from datetime import date, datetime, timedelta

import pytest

from surveycore.rinex import RinexError, iter_epochs, quality_check, read_header
from surveycore.rollover import cycles_needed, date_from_name, fix_rollover
from test_rinex import gps, v2_file, v3_file

T_BAD = datetime(2006, 9, 11, 10, 15, 30)       # what the Spectra receivers recorded
T_TRUE = datetime(2026, 4, 27, 10, 15, 30)      # 1024 weeks later


def test_date_from_name():
    assert date_from_name(__import__("pathlib").Path("08941170.26o")) == date(2026, 4, 27)
    assert date_from_name(__import__("pathlib").Path("27NY1220.26O.gz")) == date(2026, 5, 2)
    assert date_from_name(__import__("pathlib").Path("random.txt")) is None


def test_cycles_needed():
    assert cycles_needed(T_BAD, date(2026, 4, 27)) == 1
    assert cycles_needed(T_BAD, date(2026, 4, 26)) == 1     # session started the day before
    assert cycles_needed(T_TRUE, date(2026, 4, 27)) == 0
    assert cycles_needed(datetime(1987, 1, 26), date(2026, 4, 27)) == 2


def test_fix_v2_file(tmp_path):
    times = [T_BAD + timedelta(seconds=30 * i) for i in range(50)]
    sats = lambda i: gps(14 if i == 3 else 7) + ["R05"]           # epoch 3 needs 2 lines
    src = tmp_path / "in" / "08941170.26o"
    src.parent.mkdir()
    src.write_text(v2_file(times, sats, event_after=10), encoding="ascii")
    r = fix_rollover(src, tmp_path / "out")
    assert r.cycles == 1 and r.epochs_changed == 50
    assert r.first_after == T_TRUE

    fixed = [e.time for e in iter_epochs(r.dst)]
    assert fixed == [t + timedelta(weeks=1024) for t in times]
    h = read_header(r.dst)
    assert h.first_obs.date() == date(2026, 4, 27)
    assert h.last_obs.date() == date(2026, 4, 27)
    assert "WEEK ROLLOVER FIX" in r.dst.read_text()
    # measurements untouched: every non-epoch line is identical
    before = [l for l in src.read_text().splitlines() if not l.startswith(" 06 ")]
    after = [l for l in r.dst.read_text().splitlines() if not l.startswith(" 26 ")]
    assert [l for l in after if "WEEK ROLLOVER" not in l and "TIME OF" not in l] == \
           [l for l in before if "TIME OF" not in l]
    assert not any("week rollover" in w for w in quality_check(r.dst).warnings)
    assert src.read_text().count(" 06  9 11") == 50          # original unchanged


def test_header_already_correct_is_not_shifted(tmp_path):
    """Converter wrote the header from the PC clock (2026) but data from the receiver (2006)."""
    times = [T_BAD + timedelta(seconds=30 * i) for i in range(5)]
    text = v2_file(times, lambda i: gps(6))
    bad_first = f"{2006:6d}{9:6d}{11:6d}{0:6d}{0:6d}"
    assert bad_first in text
    text = text.replace(bad_first, f"{2026:6d}{4:6d}{27:6d}{0:6d}{0:6d}", 1)
    src = tmp_path / "in" / "08941170.26o"
    src.parent.mkdir()
    src.write_text(text, encoding="ascii")
    r = fix_rollover(src, tmp_path / "out")
    h = read_header(r.dst)
    assert h.first_obs.date() == date(2026, 4, 27)      # not 2045
    assert h.last_obs.date() == date(2026, 4, 27)       # this one was shifted


def test_fix_v3_file(tmp_path):
    times = [T_BAD + timedelta(seconds=i) for i in range(20)]
    src = tmp_path / "in" / "STAT1170.26o"
    src.parent.mkdir()
    src.write_text(v3_file(times, lambda i: gps(6) + ["E11"]), encoding="ascii")
    r = fix_rollover(src, tmp_path / "out")
    assert [e.time for e in iter_epochs(r.dst)] == [t + timedelta(weeks=1024) for t in times]


def test_correct_file_is_left_alone(tmp_path):
    times = [T_TRUE + timedelta(seconds=30 * i) for i in range(5)]
    src = tmp_path / "08941170.26o"
    src.write_text(v2_file(times, lambda i: gps(6)), encoding="ascii")
    r = fix_rollover(src, tmp_path / "out")
    assert r.dst is None and r.cycles == 0
    assert not (tmp_path / "out").exists()


def test_never_overwrites_original(tmp_path):
    times = [T_BAD + timedelta(seconds=30 * i) for i in range(5)]
    src = tmp_path / "08941170.26o"
    src.write_text(v2_file(times, lambda i: gps(6)), encoding="ascii")
    with pytest.raises(RinexError, match="overwrite the original"):
        fix_rollover(src, tmp_path)


def test_unknown_name_needs_cycles(tmp_path):
    times = [T_BAD + timedelta(seconds=30 * i) for i in range(5)]
    src = tmp_path / "session.obs"
    src.write_text(v2_file(times, lambda i: gps(6)), encoding="ascii")
    with pytest.raises(RinexError, match="cycles=1"):
        fix_rollover(src, tmp_path / "out")
    assert fix_rollover(src, tmp_path / "out", cycles=1).first_after == T_TRUE

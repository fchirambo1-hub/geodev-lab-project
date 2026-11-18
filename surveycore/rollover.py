"""Repair RINEX observation files hit by the GPS week-number rollover.

The GPS signal counts weeks in a 10-bit number, which starts again at 0 every
1024 weeks (19.6 years). Receivers with old firmware that do not handle this
put dates exactly 1024 weeks (7168 days) too early: the Spectra R4S files from
the April-May 2026 campaign say September 2006.

The fix is simple and exact: move every date forward by 1024 weeks. Times of
day and all measurements stay the same, because the shift is a whole number
of days. Original files are never changed: corrected copies are written.

RINEX file names (SSSSDDDF.YYo) carry the true year (YY) and day of year (DDD),
which is how the number of 1024-week cycles is worked out.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .rinex import RinexError, _open, read_header

ROLLOVER = timedelta(weeks=1024)
_SHORT_NAME = re.compile(r"^.{4}(\d{3}).\.(\d{2})o(\.gz)?$", re.IGNORECASE)


@dataclass
class RolloverResult:
    src: Path
    dst: Path | None            # None when nothing needed fixing
    cycles: int                 # number of 1024-week shifts applied
    first_before: datetime
    first_after: datetime
    epochs_changed: int
    note: str = ""


def date_from_name(path: Path) -> date | None:
    """True observation date from a short RINEX 2 name, e.g. 08941170.26o -> 2026-04-27."""
    m = _SHORT_NAME.match(path.name)
    if not m:
        return None
    doy, yy = int(m.group(1)), int(m.group(2))
    year = 2000 + yy if yy < 80 else 1900 + yy
    if not 1 <= doy <= 366:
        return None
    return date(year, 1, 1) + timedelta(days=doy - 1)


def cycles_needed(first_epoch: datetime, true_date: date) -> int:
    """How many 1024-week cycles separate the recorded date from the true one."""
    return round((true_date - first_epoch.date()).days / ROLLOVER.days)


def fix_rollover(src: str | Path, out_dir: str | Path, cycles: int | None = None,
                 overwrite: bool = False) -> RolloverResult:
    """Write a corrected copy of src into out_dir (same file name).

    cycles: number of 1024-week cycles to add. If None it is worked out from
            the file name (needs the short RINEX 2 name SSSSDDDF.YYo).
    """
    src = Path(src)
    hdr = read_header(src)
    first = _first_epoch(src, hdr.version)
    if cycles is None:
        true_date = date_from_name(src)
        if true_date is None:
            raise RinexError(f"{src.name}: cannot tell the true date from the file name - "
                             "pass cycles=1 if you are sure the dates are 1024 weeks early")
        cycles = cycles_needed(first, true_date)
    shift = ROLLOVER * cycles
    if cycles == 0:
        return RolloverResult(src, None, 0, first, first, 0, "dates already correct")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / src.name.removesuffix(".gz").removesuffix(".GZ")
    if dst.resolve() == src.resolve():
        raise RinexError("Output would overwrite the original file - choose another folder")
    if dst.exists() and not overwrite:
        raise RinexError(f"{dst} already exists (use overwrite=True)")

    n_changed = 0
    with _open(src) as fin, open(dst, "w", encoding="ascii", newline="") as fout:
        # ---- header
        for raw in fin:
            body, end = _split(raw)
            label = body[60:80].strip()
            if label in ("TIME OF FIRST OBS", "TIME OF LAST OBS") and body[:18].strip():
                body = _shift_header_time(body, shift, first)
            if label == "END OF HEADER":
                note = f"DATES +{1024 * cycles} GPS WEEKS (WEEK ROLLOVER FIX)"
                fout.write(f"{note:<60}{'COMMENT':<20}{end or chr(10)}")
            fout.write(body + end)
            if label == "END OF HEADER":
                break
        # ---- data
        if hdr.version >= 3:
            n_changed = _copy_v3(fin, fout, shift)
        else:
            n_changed = _copy_v2(fin, fout, shift, len(hdr.obs_types["*"]))

    return RolloverResult(src, dst, cycles, first, first + shift, n_changed)


# ----------------------------------------------------------------- helpers

def _split(raw: str) -> tuple[str, str]:
    body = raw.rstrip("\r\n")
    return body, raw[len(body):]


def _first_epoch(path: Path, version: float) -> datetime:
    from .rinex import iter_epochs
    for ep in iter_epochs(path):
        return ep.time
    raise RinexError(f"{path.name}: no observation epochs found")


def _shift_header_time(body: str, shift: timedelta, first_bad: datetime) -> str:
    """Shift a header time only if it carries the same faulty date as the data.
    (Some converters write the header from the PC clock, which is already right.)"""
    y, m, d = (int(x) for x in body[:18].split())
    old = date(y, m, d)
    if abs((old - first_bad.date()).days) > 60:
        return body
    new = old + shift
    return f"{new.year:6d}{new.month:6d}{new.day:6d}" + body[18:]


def _copy_v2(fin, fout, shift: timedelta, n_types: int) -> int:
    lines_per_sat = max(1, -(-n_types // 5))
    changed = 0
    for raw in fin:
        body, end = _split(raw)
        if not body.strip():
            fout.write(raw)
            continue
        flag = int(body[28:29].strip() or 0)
        n = int(body[29:32])
        follow = n if flag > 1 else (-(-n // 12) - 1) + n * lines_per_sat
        if flag <= 1 or body[1:9].strip():         # event records may have a blank date
            yy, mo, dd = int(body[1:3]), int(body[4:6]), int(body[7:9])
            year = 2000 + yy if yy < 80 else 1900 + yy
            new = date(year, mo, dd) + shift
            body = f" {new.year % 100:02d} {new.month:2d} {new.day:2d}" + body[9:]
            changed += flag <= 1
        fout.write(body + end)
        for _ in range(follow):
            line = next(fin, None)
            if line is None:
                break
            fout.write(line)
    return changed


def _copy_v3(fin, fout, shift: timedelta) -> int:
    changed = 0
    for raw in fin:
        body, end = _split(raw)
        if body.startswith(">") and body[2:12].strip():
            y, mo, dd = int(body[2:6]), int(body[7:9]), int(body[10:12])
            new = date(y, mo, dd) + shift
            body = f"> {new.year:4d} {new.month:02d} {new.day:02d}" + body[12:]
            changed += int(body[31:32].strip() or 0) <= 1
        fout.write(body + end)
    return changed

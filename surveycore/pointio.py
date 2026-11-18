"""Read and write point files (CSV / TXT / Netcad-style coordinate lists).

Handles what turns up in a survey office:
  * comma, semicolon, tab or space separated
  * with a header row (any common column names) or without one
  * Netcad's Y = Easting / X = Northing, or the 'maths' X = Easting / Y = Northing
"""

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from .point import Point

NAME_KEYS = {"name", "point", "pt", "pointno", "point_no", "no", "id", "station", "stn", "nokta"}
EAST_KEYS = {"e", "east", "easting"}
NORTH_KEYS = {"n", "north", "northing"}
HEIGHT_KEYS = {"h", "z", "height", "elev", "elevation", "rl", "level"}
CODE_KEYS = {"code", "desc", "description", "feature", "remark", "remarks"}

# Malawi on UTM zone 36S: northings ~8.4–9.0 million, eastings ~0.4–0.9 million
NORTHING_MIN = 1_000_000.0


@dataclass
class ImportResult:
    points: list[Point]
    codes: dict[str, str] = field(default_factory=dict)   # point name -> code
    warnings: list[str] = field(default_factory=list)


def _norm(h: str) -> str:
    return h.strip().lower().replace(" ", "").replace(".", "").replace("-", "_")


def _to_float(s: str) -> float:
    return float(s.strip().replace(",", "."))   # accept 1234,567 decimal commas


def _split_lines(text: str) -> list[list[str]]:
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return []
    sample = "\n".join(lines[:20])
    for delim in [",", ";", "\t"]:
        if delim in sample:
            # a decimal comma with ';' separators is common in Europe-style exports
            if delim == "," and ";" in sample:
                continue
            return [[c.strip() for c in row] for row in csv.reader(io.StringIO("\n".join(lines)),
                                                                     delimiter=delim)]
    return [ln.split() for ln in lines]                 # whitespace separated


def _is_number(s: str) -> bool:
    try:
        _to_float(s)
        return True
    except ValueError:
        return False


def read_points(path: str | Path, xy_order: str = "auto",
                encoding: str = "utf-8-sig") -> ImportResult:
    """Read a point file.

    xy_order (only used when columns are called X and Y, or there is no header):
      'netcad' : Y = Easting, X = Northing   (Netcad, Turkish and many African offices)
      'math'   : X = Easting, Y = Northing   (QGIS, AutoCAD)
      'auto'   : decide from the numbers (a value > 1,000,000 is a UTM southern northing),
                 otherwise fall back to 'netcad'
    Files without a header are read as:  name  Y  X  [H]  [code]  (Netcad order).
    """
    text = Path(path).read_text(encoding=encoding)
    return read_points_text(text, xy_order)


def read_points_text(text: str, xy_order: str = "auto") -> ImportResult:
    if xy_order not in ("auto", "netcad", "math"):
        raise ValueError("xy_order must be 'auto', 'netcad' or 'math'")
    rows = _split_lines(text)
    res = ImportResult(points=[])
    if not rows:
        res.warnings.append("File is empty")
        return res

    header = [_norm(c) for c in rows[0]]
    has_header = not any(_is_number(c) for c in rows[0][1:3])
    if has_header:
        body = rows[1:]
        col = {}
        for i, h in enumerate(header):
            for role, keys in (("name", NAME_KEYS), ("e", EAST_KEYS), ("n", NORTH_KEYS),
                               ("h", HEIGHT_KEYS), ("code", CODE_KEYS), ("x", {"x"}), ("y", {"y"})):
                if h in keys and role not in col:
                    col[role] = i
        if "e" not in col or "n" not in col:
            if "x" in col and "y" in col:
                col.update(_resolve_xy(body, col["x"], col["y"], xy_order, res))
            else:
                raise ValueError(f"Cannot find coordinate columns in header: {rows[0]}")
        if "name" not in col:
            res.warnings.append("No point-name column; points numbered 1, 2, 3 …")
    else:
        body = rows
        # name, Y, X, [H], [code]  - Netcad order; columns 1 and 2 are the 'Y' and 'X'
        col = {"name": 0, **_resolve_xy(body, x_idx=2, y_idx=1, xy_order=xy_order, res=res)}
        if len(rows[0]) >= 4 and _is_number(rows[0][3]):
            col["h"] = 3
        code_idx = 4 if "h" in col else 3
        if len(rows[0]) > code_idx:
            col["code"] = code_idx

    seen = set()
    for line_no, row in enumerate(body, start=2 if has_header else 1):
        try:
            name = row[col["name"]] if "name" in col else str(len(res.points) + 1)
            e = _to_float(row[col["e"]])
            n = _to_float(row[col["n"]])
            h = None
            if "h" in col and col["h"] < len(row) and row[col["h"]].strip():
                h = _to_float(row[col["h"]])
        except (ValueError, IndexError):
            res.warnings.append(f"Line {line_no}: skipped, could not read {row}")
            continue
        if name in seen:
            res.warnings.append(f"Line {line_no}: duplicate point name '{name}'")
        seen.add(name)
        res.points.append(Point(name, e, n, h))
        if "code" in col and col["code"] < len(row) and row[col["code"]].strip():
            res.codes[name] = row[col["code"]].strip()
    return res


def _resolve_xy(body, x_idx, y_idx, xy_order, res) -> dict:
    """Decide which of the X/Y columns is the Easting."""
    netcad = {"e": y_idx, "n": x_idx}
    math_ = {"e": x_idx, "n": y_idx}
    if xy_order == "netcad":
        return netcad
    if xy_order == "math":
        return math_
    xs, ys = [], []
    for row in body[:50]:
        try:
            xs.append(abs(_to_float(row[x_idx])))
            ys.append(abs(_to_float(row[y_idx])))
        except (ValueError, IndexError):
            pass
    if xs and min(xs) > NORTHING_MIN and max(ys) < NORTHING_MIN:
        res.warnings.append("Auto-detected X = Northing, Y = Easting (Netcad order)")
        return netcad
    if ys and min(ys) > NORTHING_MIN and max(xs) < NORTHING_MIN:
        res.warnings.append("Auto-detected X = Easting, Y = Northing")
        return math_
    res.warnings.append("Could not tell X/Y order from the numbers; assumed Netcad "
                        "(Y = Easting, X = Northing). Check the result!")
    return netcad


def write_points(path: str | Path, points: list[Point], codes: dict[str, str] | None = None,
                 decimals: int = 3, delimiter: str = ",") -> None:
    """Write points to CSV with a clear header: Name,Easting,Northing,Height[,Code]."""
    codes = codes or {}
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=delimiter)
        header = ["Name", "Easting", "Northing", "Height"] + (["Code"] if codes else [])
        w.writerow(header)
        for p in points:
            row = [p.name, f"{p.e:.{decimals}f}", f"{p.n:.{decimals}f}",
                   "" if p.h is None else f"{p.h:.{decimals}f}"]
            if codes:
                row.append(codes.get(p.name, ""))
            w.writerow(row)

# Malawi Survey Tools

A Netcad-style survey computation system for the Malawi Survey Department / LIMS.
BSc Land Surveying project (2026–2028).

## Quick start

```bash
python -m pip install -r requirements.txt
python -m pytest -q      # run all checks
python demo.py           # see every tool working
```

## Conventions

| Here | Netcad | Meaning |
|---|---|---|
| `E` | Y | Easting |
| `N` | X | Northing |
| bearing | azimuth | whole-circle, clockwise from grid north, decimal degrees |
| `parse_dms("45.3015")` | — | field-book DDD.MMSS → 45°30'15" |

## Netcad COGO tab → this project

| Netcad tool | Module / function | Status |
|---|---|---|
| Point Editor | `Point`, `pointio.read_points` / `write_points` | ✅ CSV/TXT import & export |
| Export to CAD | `dxfexport.write_dxf` | ✅ points, names, heights, lines, parcels with area |
| Map Sheet Editor | `mapsheet.py` | later |
| Transformations | `transform.py` 7-param Helmert, 2D similarity/affine | ✅ (needs real control points) |
| Intersection (4 Point) | `cogo.intersect_bearings`, `intersect_distances` | ✅ |
| Slope Distance–Vertical Angle | `cogo.reduce_slope` | ✅ |
| Tachometry Calculation | `cogo.tachymetry` | ✅ |
| Traverse Calculation | `traverse.bowditch_traverse` | ✅ link + closed |
| Automatic Point Generation | `cogo.divide_line`, offsets | next |
| Ground Reduction | `reduction.py` (scale factor, height) | needs projection (Stage 2) |
| Resection | `cogo.resection` (Tienstra) | ✅ |
| Forward Resection | = intersection from angles | next |
| Coordinate Summary / Reports | `reports.py` (PDF/CSV) | Stage 6 |
| Area Outputs | `cogo.area` | ✅ area, perimeter |

## Structure

```
surveycore/   calculations only — no screens (the "backend" core)
  angles.py   DMS, normalising, parsing field-book angles
  cogo.py     join, polar, slope, tachymetry, intersections, resection, area
  traverse.py angular + Bowditch adjustment with printed report
  pointio.py  read/write point files (comma/semicolon/tab/space, header or not,
              decimal commas, Netcad Y/X or maths X/Y order - auto-detected)
  dxfexport.py DXF drawing: layers POINTS, POINT_NAMES, HEIGHTS, LINES, PARCELS
data/         sample input files
output/       files written by demo.py (not committed)
tests/        pytest checks — add the office's worked examples here
demo.py       runnable examples
```

## Datum transformation (Arc 1950 ↔ WGS 84)

The published Malawi shifts (EPSG:1117 and EPSG:6904) are 3-parameter and only good to
27–29 m. Compute a local 7-parameter fit from points known in both datums:

```bash
python fit_transformation.py arc1950_points.csv wgs84_points.csv --check CP09 CP10
```

- Both files: UTM 36S E, N and height, same point names.
- `--check` holds points out of the fit and reports how well they agree. **Always use check points.**
- Points with residuals above 3 × sigma0 are flagged "check this point".
- The report ends with a `+towgs84` custom CRS string for QGIS
  (Settings → Custom Projections), so the office can use the fit immediately.
- Parameters use the **position-vector** convention (EPSG 9606). For coordinate-frame
  (EPSG 9607) flip the signs of the three rotations: `Helmert7.coordinate_frame()`.
- Tests confirm our maths agrees with PROJ to about 2 mm.

`data/SYNTHETIC_control_*.csv` are invented test points. **Do not use them for real work.**

For local/assumed grids, `fit_2d(local_pts, utm_pts, "similarity" | "affine")`.

## Point files

```python
from surveycore.pointio import read_points
res = read_points("field.csv")            # xy_order="auto" | "netcad" | "math"
for w in res.warnings: print(w)          # always read the warnings!
```

A file with no header is read in Netcad order: `name  Y(East)  X(North)  [H]  [code]`.
In DXF, X = Easting and Y = Northing (CAD convention) — the values are the same as Netcad's Y/X.

## Rules for this codebase

1. Calculations live in `surveycore/` and never depend on a screen.
2. Every new function gets a test before it is used anywhere.
3. When the office gives a worked example, it becomes a test.

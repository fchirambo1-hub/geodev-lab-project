# My GeoDev Lab Africa project

Can OCR and rule-based parsing reliably extract coordinate schedules from scanned Mzuzu City cadastral survey plans and auto-generate GIS-ready polygon files, within the Survey Department's 0.025 m accuracy tolerance?

Built over twelve months with GeoDev Lab Africa, Cohort One.
See project-brief.md for the full brief.

---

The coordinate engine below does the survey maths the OCR system needs: reading
and validating coordinates, Arc 1950 → WGS 84 / UTM 36S transformation, parcel
areas and GIS/CAD export.

## Survey computation engine (`surveycore/`)

A Netcad-style survey computation system for the Malawi Survey Department / LIMS.
BSc Land Surveying project (2026–2028).

### Quick start

```bash
python -m pip install -r requirements.txt
python -m pytest -q      # run all checks
python demo.py           # see every tool working
```

### Conventions

| Here | Netcad | Meaning |
|---|---|---|
| `E` | Y | Easting |
| `N` | X | Northing |
| bearing | azimuth | whole-circle, clockwise from grid north, decimal degrees |
| `parse_dms("45.3015")` | — | field-book DDD.MMSS → 45°30'15" |

### Netcad COGO tab → this project

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
| Gps (data check) | `rinex.quality_check`, `rinex_qc.py` | ✅ RINEX 2/3 reader + QC |
| Gps (date repair) | `rollover.fix_rollover`, `fix_rollover.py` | ✅ GPS week-rollover fix |
| Coordinate Summary / Reports | `reports.py` (PDF/CSV) | Stage 6 |
| Area Outputs | `cogo.area` | ✅ area, perimeter |

### Structure

```
surveycore/   calculations only — no screens (the "backend" core)
  angles.py   DMS, normalising, parsing field-book angles
  cogo.py     join, polar, slope, tachymetry, intersections, resection, area
  traverse.py angular + Bowditch adjustment with printed report
  pointio.py  read/write point files (comma/semicolon/tab/space, header or not,
              decimal commas, Netcad Y/X or maths X/Y order - auto-detected)
  dxfexport.py DXF drawing: layers POINTS, POINT_NAMES, HEIGHTS, LINES, PARCELS
  transform.py Arc 1950 <-> WGS 84 7-parameter Helmert, 2D similarity/affine
  rinex.py    RINEX 2/3 observation reader and quality check
  rollover.py GPS week-rollover date repair
data/         sample input files
output/       files written by demo.py (not committed)
tests/        pytest checks — add the office's worked examples here
demo.py       runnable examples
```

### GNSS data check (RINEX)

Check every observation file **before** sending it for processing (CSRS-PPP, AUSPOS, RTKLIB):

```bash
python rinex_qc.py data/gnss/*.26o --csv output/rinex_summary.csv
```

Reads RINEX 2.10/2.11 and 3.0x observation files (also `.gz`). Reports station, receiver,
antenna type and height, start/end, duration, interval, completeness, gaps, satellites per
system and the approximate position (lat/lon and UTM 36S). Warns about a zero antenna height,
a missing antenna type, short sessions and truncated files.

- Hatanaka files (`.crx`, `.26d`) must be decompressed with CRX2RNX first.
- Navigation files (`.26n/.26g/.26l`) are not observation files; they are skipped with a message.
- Receiver binary files (`.dat`) must first be converted to RINEX with GeoMax software.
- `data/SYNTHETIC_99NY1170.26o` is an invented example file.

#### GPS week rollover (Spectra R4S receivers)

Some receivers date their data exactly 1024 weeks (19.6 years) too early, e.g. September 2006
instead of April 2026. PPP services reject such files. `rinex_qc.py` warns about it; fix with:

```bash
python fix_rollover.py "data/gnss/rinex_obs/*/*/*.26o" --out data/gnss/rinex_fixed
```

- Writes corrected **copies**; originals are never touched. Correct files are skipped.
- Only the epoch dates and the header TIME OF FIRST/LAST OBS change; every measurement
  stays byte-for-byte identical. A COMMENT line records the fix in the header.
- The true date comes from the RINEX file name (`SSSSDDDF.YYo`); for other names pass `--cycles 1`.
- Navigation files (`.26n/.26g`) from these receivers have the same fault, but PPP services
  use their own precise orbits, so only the observation files matter for processing.

### Datum transformation (Arc 1950 ↔ WGS 84)

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

### Point files

```python
from surveycore.pointio import read_points
res = read_points("field.csv")            # xy_order="auto" | "netcad" | "math"
for w in res.warnings: print(w)          # always read the warnings!
```

A file with no header is read in Netcad order: `name  Y(East)  X(North)  [H]  [code]`.
In DXF, X = Easting and Y = Northing (CAD convention) — the values are the same as Netcad's Y/X.

### Rules for this codebase

1. Calculations live in `surveycore/` and never depend on a screen.
2. Every new function gets a test before it is used anywhere.
3. When the office gives a worked example, it becomes a test.

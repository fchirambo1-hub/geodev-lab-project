# Project brief: Malawi Survey Software

## MAIN GOAL

Develop survey software for the Department of Surveys and the Lands Information Management
System (LIMS) office in Malawi: a Netcad-style system that does the everyday survey
computations and produces results the office can use directly in GIS and CAD.

## WHY IT MATTERS

- Experts at the Department of Surveys and the LIMS office were shown Netcad's COGO tools
  and said tools like these would help their work. Many systems built for offices like
  theirs have failed because they were not what the users wanted to use, so this one is
  built step by step with the people who will use it.
- The only published conversions between Malawi's old datum (Arc 1950) and WGS 84 are
  3-parameter shifts accurate to about 27–29 m (EPSG:1117 and EPSG:6904). Land parcels
  need centimetres. A local 7-parameter transformation computed from the department's own
  GNSS and control data is needed.
- Field GNSS data needs checking before processing. The April–May 2026 campaign data
  showed receivers recording dates 19.6 years early (GPS week rollover) and doubtful
  antenna heights, which would ruin coordinates if not caught.

## WHAT IS BEING BUILT

A calculation core first, then screens on top of it. Every calculation is tested against
known answers and, as they become available, the department's own worked examples.

| Module | Netcad equivalent | Status |
|---|---|---|
| COGO: join, polar, intersections, resection, area | COGO tab | Built |
| Slope reduction and tachymetry | Slope Distance, Tachometry | Built |
| Traverse with Bowditch adjustment | Traverse Calculation | Built |
| Point file import/export, DXF export | Point Editor, CAD export | Built |
| Arc 1950 ↔ WGS 84 7-parameter transformation | Transformations | Built, needs real control points |
| GNSS RINEX quality check and date repair | Gps | Built, run on 2026 campaign data |
| Reports (PDF/CSV computation sheets) | Reports | Planned |
| User interface (QGIS plugin first, then desktop/web) | — | Planned |

## DATA I NEED

- Raw GNSS observations from the department's static campaigns. **Obtained**: three
  sessions, April–May 2026, about 29 station folders.
- Arc 1950 coordinates (UTM 36S, with heights) for the same beacons, to compute the
  transformation. **Still needed.**
- Worked examples computed by hand at the office (traverse, tachymetry, transformation),
  to test the software against. **Still needed.**

## WHERE EACH ONE COMES FROM

All from the Department of Surveys, Ministry of Lands (Geodetic Office), for academic use.
None of it is publicly downloadable, and raw data is never committed to this repository.

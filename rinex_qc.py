"""Quality-check one or more RINEX observation files before processing.

Usage:
  python rinex_qc.py data/gnss/99NY1170.26o data/gnss/27NY1170.26o
  python rinex_qc.py data/gnss/*.26o --csv output/rinex_summary.csv

Prints a report per file and (optionally) one summary row per file to CSV,
which is handy for a field-campaign log.
"""

import argparse
import csv
import glob
from pathlib import Path

from surveycore.rinex import RinexError, quality_check


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--csv", help="write a one-line-per-file summary here")
    a = ap.parse_args()

    paths = [Path(p) for pattern in a.files for p in (glob.glob(pattern) or [pattern])]
    rows = []
    for p in paths:
        try:
            qc = quality_check(p)
        except (RinexError, OSError) as e:
            print(f"\n{p}: SKIPPED - {e}")
            continue
        print("\n" + qc.report())
        h = qc.header
        rows.append({
            "file": p.name, "station": h.marker_name, "receiver": h.receiver,
            "antenna": h.antenna_type, "ant_height_m": h.antenna_delta_hen[0],
            "first": qc.first, "last": qc.last, "hours": round(qc.duration.total_seconds() / 3600, 2),
            "interval_s": qc.interval, "completeness_pct": round(qc.completeness, 1),
            "gaps": len(qc.gaps), "systems": "".join(qc.sats_by_system),
            "approx_lat": round(qc.lat_lon_h[0], 6) if qc.lat_lon_h else "",
            "approx_lon": round(qc.lat_lon_h[1], 6) if qc.lat_lon_h else "",
            "warnings": " | ".join(qc.warnings),
        })
    if a.csv and rows:
        out = Path(a.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nSummary written to {out}")


if __name__ == "__main__":
    main()

"""Compute Arc 1950 -> WGS 84 7-parameter transformation from two point files.

Usage:
  python fit_transformation.py ARC1950.csv WGS84.csv [--check CP09 CP10] [--n-arc 0] [--n-wgs 0]

Both files: UTM zone 36S coordinates with heights, same point names in each
(any format read_points understands). Points present in only one file are ignored.

Heights: use ellipsoidal heights if you have them (GNSS gives WGS 84 ellipsoidal
heights directly). For Arc 1950 orthometric heights, pass an average geoid
undulation with --n-arc (h = H + N). E/N results are hardly affected by heights.
"""

import argparse
from pathlib import Path

from surveycore.pointio import read_points
from surveycore.transform import estimate_helmert7, utm_point_to_xyz


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arc1950")
    ap.add_argument("wgs84")
    ap.add_argument("--check", nargs="*", default=[], help="points held out to test the fit")
    ap.add_argument("--n-arc", type=float, default=0.0, help="geoid undulation for Arc 1950 heights (m)")
    ap.add_argument("--n-wgs", type=float, default=0.0, help="geoid undulation for WGS 84 heights (m)")
    ap.add_argument("--out", default="output/transformation_report.txt")
    a = ap.parse_args()

    arc = read_points(a.arc1950)
    wgs = read_points(a.wgs84)
    for label, r in (("Arc 1950", arc), ("WGS 84", wgs)):
        for w in r.warnings:
            print(f"[{label}] {w}")

    src = {p.name: utm_point_to_xyz(p, "arc1950", a.n_arc) for p in arc.points}
    dst = {p.name: utm_point_to_xyz(p, "wgs84", a.n_wgs) for p in wgs.points}
    common = sorted(set(src) & set(dst))
    print(f"Common points: {len(common)}  ({', '.join(common)})")
    missing = [c for c in a.check if c not in common]
    if missing:
        print(f"Check points not found in both files: {missing}")

    fit = estimate_helmert7(src, dst, check=a.check)
    text = "\n".join(fit.report)
    print("\n" + text)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\nReport saved to {out}")


if __name__ == "__main__":
    main()

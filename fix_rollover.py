"""Fix GPS week-rollover dates in RINEX observation files (corrected copies only).

Usage:
  python fix_rollover.py "data/gnss/rinex_obs/*/*/*.26o" --out data/gnss/rinex_fixed

Files whose dates are already right are skipped. The folder structure under the
common input folder is kept, so stations with identical file names don't collide.
The true date comes from the file name (SSSSDDDF.YYo); for other names use --cycles 1.
"""

import argparse
import glob
import os
from pathlib import Path

from surveycore.rinex import RinexError
from surveycore.rollover import fix_rollover


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True, help="folder for corrected copies")
    ap.add_argument("--cycles", type=int, help="force this many 1024-week cycles")
    ap.add_argument("--overwrite", action="store_true", help="replace earlier corrected copies")
    a = ap.parse_args()

    paths = [Path(p) for pattern in a.files for p in (glob.glob(pattern) or [pattern])]
    if not paths:
        print("No files found")
        return
    root = Path(os.path.commonpath([p.resolve().parent for p in paths]))
    fixed = skipped = failed = 0
    for p in paths:
        out_dir = Path(a.out) / p.resolve().parent.relative_to(root)
        try:
            r = fix_rollover(p, out_dir, a.cycles, a.overwrite)
        except (RinexError, OSError, ValueError) as e:
            print(f"FAILED   {p}: {e}")
            failed += 1
            continue
        if r.dst is None:
            print(f"ok       {p}  ({r.first_before:%Y-%m-%d}, {r.note})")
            skipped += 1
        else:
            print(f"FIXED    {p}  {r.first_before:%Y-%m-%d} -> {r.first_after:%Y-%m-%d}  "
                  f"({r.epochs_changed:,} epochs)  -> {r.dst}")
            fixed += 1
    print(f"\n{fixed} fixed, {skipped} already correct, {failed} failed")


if __name__ == "__main__":
    main()

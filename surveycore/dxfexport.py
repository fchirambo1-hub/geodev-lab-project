"""Export survey results to DXF (opens in AutoCAD, QGIS, Netcad, BricsCAD, LibreCAD).

DXF uses the CAD convention X = Easting, Y = Northing, Z = Height.
(This is the opposite of Netcad's on-screen Y/X labels - the values are the same.)
"""

import re
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from .cogo import area
from .point import Point

# layer name -> AutoCAD colour index
LAYERS = {
    "POINTS": 7,        # white/black
    "POINT_NAMES": 3,   # green
    "HEIGHTS": 4,       # cyan
    "LINES": 1,         # red
    "PARCELS": 5,       # blue
    "AREA_LABELS": 5,
}


def _safe_layer(name: str) -> str:
    """DXF layer names cannot contain  < > / \\ " : ; ? * | = '"""
    return re.sub(r'[<>/\\":;?*|=\']', "_", name).strip()[:255] or "0"


def write_dxf(path: str | Path,
              points: list[Point] | None = None,
              lines: list[list[Point]] | None = None,
              parcels: list[list[Point]] | None = None,
              codes: dict[str, str] | None = None,
              text_height: float = 0.5,
              layer_by_code: bool = False,
              decimals: int = 3) -> Path:
    """Write a DXF drawing.

    points        : survey points (drawn as POINT + name label + height label)
    lines         : open polylines, e.g. a traverse or a road centre line
    parcels       : closed polygons, labelled with their area in m² and ha
    codes         : point name -> feature code (e.g. 'BEACON', 'TREE')
    layer_by_code : put each point on a layer named after its code ('PT_BEACON' …)
    text_height   : label height in drawing units (metres) - use ~0.5 for 1:500, 2.5 for 1:2500
    """
    points = points or []
    lines = lines or []
    parcels = parcels or []
    codes = codes or {}

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.M
    doc.header["$PDMODE"] = 35          # points shown as a circle with a cross
    doc.header["$PDSIZE"] = text_height * 0.6
    for name, colour in LAYERS.items():
        doc.layers.add(name, color=colour)
    msp = doc.modelspace()

    off = text_height * 0.6
    for p in points:
        layer = "POINTS"
        if layer_by_code and p.name in codes:
            layer = _safe_layer(f"PT_{codes[p.name]}")
            if layer not in doc.layers:
                doc.layers.add(layer)
        z = p.h if p.h is not None else 0.0
        msp.add_point((p.e, p.n, z), dxfattribs={"layer": layer})
        msp.add_text(p.name, height=text_height,
                     dxfattribs={"layer": "POINT_NAMES"}).set_placement(
            (p.e + off, p.n + off), align=TextEntityAlignment.BOTTOM_LEFT)
        if p.h is not None:
            msp.add_text(f"{p.h:.{decimals}f}", height=text_height * 0.8,
                         dxfattribs={"layer": "HEIGHTS"}).set_placement(
                (p.e + off, p.n - off), align=TextEntityAlignment.TOP_LEFT)

    for chain in lines:
        if len(chain) >= 2:
            msp.add_lwpolyline([(p.e, p.n) for p in chain], dxfattribs={"layer": "LINES"})

    for poly in parcels:
        if len(poly) < 3:
            continue
        msp.add_lwpolyline([(p.e, p.n) for p in poly], close=True,
                           dxfattribs={"layer": "PARCELS"})
        a, _ = area(poly)
        ce = sum(p.e for p in poly) / len(poly)
        cn = sum(p.n for p in poly) / len(poly)
        msp.add_text(f"{a:,.2f} m²  ({a / 10000:.4f} ha)", height=text_height,
                     dxfattribs={"layer": "AREA_LABELS"}).set_placement(
            (ce, cn), align=TextEntityAlignment.MIDDLE_CENTER)

    if points or lines or parcels:
        allp = points + [p for c in lines for p in c] + [p for c in parcels for p in c]
        doc.set_modelspace_vport(
            height=max(max(p.n for p in allp) - min(p.n for p in allp), 10) * 1.2,
            center=((max(p.e for p in allp) + min(p.e for p in allp)) / 2,
                    (max(p.n for p in allp) + min(p.n for p in allp)) / 2))

    path = Path(path)
    doc.saveas(path)
    return path

"""surveycore - survey calculations for the Malawi Survey Department.

Convention used everywhere in this package:
  E = Easting (Netcad calls this Y), N = Northing (Netcad calls this X).
  Bearings are whole-circle bearings in decimal degrees, clockwise from grid north.
"""

from .point import Point

__all__ = ["Point"]

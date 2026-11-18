from dataclasses import dataclass
from typing import Optional


@dataclass
class Point:
    """A survey point. E = Easting (Netcad 'Y'), N = Northing (Netcad 'X')."""

    name: str
    e: float
    n: float
    h: Optional[float] = None

    def __str__(self) -> str:
        h = f"  H {self.h:.3f}" if self.h is not None else ""
        return f"{self.name}: E {self.e:.3f}  N {self.n:.3f}{h}"

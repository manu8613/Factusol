"""Compara tu pinza con el contador oficial y calcula la corrección.

Con las horas en que hay medida propia y oficial se ajusta, por separado para
importación y exportación, ``oficial = factor * propio + desfase`` por mínimos
cuadrados. El factor corrige un error de escala (pinza mal calibrada) y el desfase un
error constante por hora (consumo propio del medidor, deriva).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Fit:
    horas: int
    propio_kwh: float
    oficial_kwh: float
    desfase_pct: float  # (propio - oficial) / oficial * 100
    factor: float  # solo escala: oficial / propio
    factor_ls: float  # pendiente de mínimos cuadrados
    offset_wh: float  # ordenada (Wh por hora)
    r2: float


def fit_pairs(pairs: list[tuple[float, float]], min_hours: int = 24) -> Fit | None:
    """Ajusta (propio_wh, oficial_wh) por hora. ``None`` si hay pocas horas."""
    n = len(pairs)
    if n < min_hours:
        return None
    sx = sum(p for p, _ in pairs)
    sy = sum(o for _, o in pairs)
    sxx = sum(p * p for p, _ in pairs)
    sxy = sum(p * o for p, o in pairs)
    syy = sum(o * o for _, o in pairs)
    var_x = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / var_x if var_x > 1e-9 else 1.0
    intercept = (sy - slope * sx) / n
    var_y = n * syy - sy * sy
    denom = math.sqrt(max(var_x, 0.0) * max(var_y, 0.0))
    r2 = ((n * sxy - sx * sy) / denom) ** 2 if denom > 1e-9 else 0.0
    return Fit(
        horas=n,
        propio_kwh=sx / 1000,
        oficial_kwh=sy / 1000,
        desfase_pct=((sx - sy) / sy * 100) if sy > 1e-9 else 0.0,
        factor=(sy / sx) if sx > 1e-9 else 1.0,
        factor_ls=slope,
        offset_wh=intercept,
        r2=r2,
    )

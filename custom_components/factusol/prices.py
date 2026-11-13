"""Precios que cobra cada factura: histórico y detección de cambios (sin Home Assistant)."""

from __future__ import annotations

from typing import Any, Final

# campo -> (nombre, unidad). El orden es el de presentación.
PRICE_FIELDS: Final[dict[str, tuple[str, str]]] = {
    "precio_potencia_punta": ("Potencia punta", "€/kW día"),
    "precio_potencia_valle": ("Potencia valle", "€/kW día"),
    "potencia_punta_kw": ("Potencia contratada punta", "kW"),
    "potencia_valle_kw": ("Potencia contratada valle", "kW"),
    "precio_punta": ("Energía punta", "€/kWh"),
    "precio_llano": ("Energía llano", "€/kWh"),
    "precio_valle": ("Energía valle", "€/kWh"),
    "precio_excedentes": ("Compensación de excedentes", "€/kWh"),
    "bono_social_dia": ("Bono social", "€/día"),
    "alquiler_dia": ("Alquiler del equipo de medida", "€/día"),
}
_EPS: Final = 1e-9


def keep_prices(values: dict[str, Any]) -> dict[str, float]:
    """Se queda con los precios que se siguen y los pasa a float."""
    return {k: float(values[k]) for k in PRICE_FIELDS if values.get(k) is not None}


def diff_prices(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Campos cuyo valor cambia entre dos conjuntos de precios (solo los que están en los dos)."""
    out: list[dict[str, Any]] = []
    for key, (label, unit) in PRICE_FIELDS.items():
        if before.get(key) is None or after.get(key) is None:
            continue
        old, new = float(before[key]), float(after[key])
        if abs(old - new) <= _EPS:
            continue
        out.append(
            {
                "campo": key,
                "nombre": label,
                "unidad": unit,
                "antes": old,
                "despues": new,
                "variacion_pct": round((new - old) / old * 100, 2) if old else None,
            }
        )
    return out


def price_history(invoices: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Precios de cada factura registrada con ellos, de la más antigua a la más reciente.

    Cada fila lleva los cambios frente a la factura anterior; la primera no tiene con qué
    compararse, así que sale sin cambios (``comparada`` falso).
    """
    rows: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for start in sorted(invoices):
        rec = invoices[start]
        prices = rec.get("precios")
        if not isinstance(prices, dict) or not prices:
            continue
        rows.append(
            {
                "inicio": start,
                "fin": rec.get("fecha_fin"),
                "precios": dict(prices),
                "cambios": diff_prices(previous, prices) if previous is not None else [],
                "comparada": previous is not None,
            }
        )
        previous = prices
    return rows


def last_change(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """La factura más reciente si trae cambios de precio frente a la anterior."""
    if history and history[-1]["cambios"]:
        return history[-1]
    return None


def describe_changes(changes: list[dict[str, Any]]) -> str:
    """Texto corto para una notificación."""
    lines = []
    for c in changes:
        pct = "" if c["variacion_pct"] is None else f" ({c['variacion_pct']:+.2f} %)".replace(".", ",")
        lines.append(f"- {c['nombre']}: {c['antes']:g} → {c['despues']:g} {c['unidad']}{pct}")
    return "\n".join(lines)

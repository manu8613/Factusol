"""Histórico de precios por factura y detección de cambios."""

from __future__ import annotations

from custom_components.factusol.prices import describe_changes, diff_prices, keep_prices, last_change, price_history

BASE = {"precio_punta": 0.2, "precio_llano": 0.14, "precio_potencia_punta": 0.09, "potencia_punta_kw": 4.6}


def test_keep_prices_filters_and_floats():
    assert keep_prices({"precio_punta": 1, "otro": 21, "precio_llano": None}) == {"precio_punta": 1.0}


def test_diff_detects_only_real_changes():
    after = {**BASE, "precio_punta": 0.21, "precio_potencia_punta": 0.1}
    changes = diff_prices(BASE, after)
    assert [c["campo"] for c in changes] == ["precio_potencia_punta", "precio_punta"]
    assert changes[1]["antes"] == 0.2 and changes[1]["despues"] == 0.21 and changes[1]["variacion_pct"] == 5.0
    assert diff_prices(BASE, dict(BASE)) == []


def test_diff_ignores_fields_missing_on_one_side():
    assert diff_prices({"precio_punta": 0.2}, {"precio_llano": 0.3}) == []


def test_history_orders_by_date_and_compares_with_previous_invoice():
    invoices = {
        "2026-10-15": {"fecha_fin": "2026-10-31", "precios": {**BASE, "precio_punta": 0.22}},
        "2026-09-01": {"fecha_fin": "2026-09-30", "precios": dict(BASE)},
        "2026-08-01": {"total_bruto": 20.0},  # sin precios: no aparece
        "2026-10-01": {"fecha_fin": "2026-10-14", "precios": dict(BASE)},
    }
    rows = price_history(invoices)
    assert [r["inicio"] for r in rows] == ["2026-09-01", "2026-10-01", "2026-10-15"]
    assert not rows[0]["comparada"] and rows[0]["cambios"] == []
    assert rows[1]["comparada"] and rows[1]["cambios"] == []
    assert [c["campo"] for c in rows[2]["cambios"]] == ["precio_punta"]
    assert last_change(rows) is rows[2]
    assert last_change(rows[:2]) is None


def test_describe_changes_is_readable():
    text = describe_changes(diff_prices(BASE, {**BASE, "precio_punta": 0.21}))
    assert text == "- Energía punta: 0.2 → 0.21 €/kWh (+5,00 %)"

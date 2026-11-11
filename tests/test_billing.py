"""El motor reproduce al céntimo dos facturas reales de autoconsumo con hucha."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from custom_components.factusol.billing import Segment, Tariff, compute_bill, money, tariff_on

TARIFF = Tariff.from_dict(
    {
        "desde": "2000-01-01",
        "potencia_punta_kw": 4.6,
        "potencia_valle_kw": 4.6,
        "precio_potencia_punta": 0.091074,
        "precio_potencia_valle": 0.013483,
        "precio_punta": 0.196495,
        "precio_llano": 0.138209,
        "precio_valle": 0.104479,
        "precio_excedentes": 0.07,
        "bono_social_dia": 0.024688,
        "alquiler_dia": 0.02663,
        "impuesto_electrico": 5.11269632,
        "impuesto_minimo_mwh": 1.0,
        "iva": 21,
    }
)


def _segment(days: int, punta: str, llano: str, valle: str, excedente: str) -> list[Segment]:
    return [
        Segment(
            tariff=TARIFF,
            days=D(days),
            kwh={"punta": D(punta), "llano": D(llano), "valle": D(valle)},
            excedente_kwh=D(excedente),
        )
    ]


def test_month_31_days_matches_invoice() -> None:
    bill = compute_bill(_segment(31, "9.25", "6.01", "21.23", "522.63"), D("164.53"))
    assert bill.potencia == D("14.91")
    assert bill.energia_total == D("4.87")
    assert bill.compensacion == D("4.87")
    assert bill.bono_social == D("0.77")
    assert bill.base_impuesto == D("15.68")
    assert bill.impuesto_electrico == D("0.80")
    assert bill.total_energia == D("16.48")
    assert bill.servicios == D("0.83")
    assert bill.importe_total == D("17.31")
    assert bill.iva == D("3.64")
    assert bill.total_bruto == D("20.95")
    assert bill.hucha_ingreso == D("31.71")
    assert bill.hucha_aplicada == D("20.95")
    assert bill.total_a_pagar == D("0.00")
    assert bill.saldo_hucha_final == D("175.29")
    assert bill.coste_real == D("20.95") - D("31.71")


def test_month_30_days_matches_invoice() -> None:
    bill = compute_bill(_segment(30, "8.69", "5.88", "18.15", "563.52"), D("175.29"))
    assert bill.potencia == D("14.43")
    assert bill.energia_total == D("4.42")
    assert bill.compensacion == D("4.42")
    assert bill.bono_social == D("0.74")
    assert bill.base_impuesto == D("15.17")
    assert bill.impuesto_electrico == D("0.78")
    assert bill.servicios == D("0.80")
    assert bill.importe_total == D("16.75")
    assert bill.iva == D("3.52")
    assert bill.total_bruto == D("20.27")
    assert bill.hucha_ingreso == D("35.03")
    assert bill.saldo_hucha_final == D("190.05")


def test_compensation_is_capped_by_energy_cost() -> None:
    bill = compute_bill(_segment(30, "100", "0", "0", "10"), D(0))
    # 10 kWh * 0,07 = 0,70 € < coste de energía: no hay límite ni ingreso en la hucha
    assert bill.compensacion == D("0.70")
    assert bill.hucha_ingreso == D("0.00")


def test_hucha_applies_only_up_to_balance_and_bill() -> None:
    bill = compute_bill(_segment(30, "100", "50", "50", "0"), D("5"))
    assert bill.hucha_aplicada == D("5")
    assert bill.total_a_pagar == bill.total_bruto - D("5")
    assert bill.saldo_hucha_final == D("0")


def test_without_hucha_nothing_is_stored_or_applied() -> None:
    bill = compute_bill(_segment(30, "8.69", "5.88", "18.15", "563.52"), D("100"), hucha_activa=False)
    assert bill.hucha_ingreso == D(0)
    assert bill.hucha_aplicada == D(0)
    assert bill.coste_real == bill.total_bruto


def test_rounding_is_half_up() -> None:
    assert money(D("3.5175")) == D("3.52")
    assert money(D("0.125")) == D("0.13")


def test_tariff_versions_split_a_cycle() -> None:
    later = Tariff.from_dict(
        {
            "desde": "2026-09-16",
            "potencia_punta_kw": 4.6,
            "potencia_valle_kw": 4.6,
            "precio_potencia_punta": 0.1,
            "precio_potencia_valle": 0.02,
            "precio_punta": 0.2,
            "precio_llano": 0.15,
            "precio_valle": 0.1,
            "precio_excedentes": 0.07,
        }
    )
    tariffs = [TARIFF, later]
    assert tariff_on(tariffs, date(2026, 9, 15)) is TARIFF
    assert tariff_on(tariffs, date(2026, 9, 16)) is later
    segs = [
        Segment(tariff=TARIFF, days=D(15), kwh={"punta": D(1), "llano": D(1), "valle": D(1)}),
        Segment(tariff=later, days=D(15), kwh={"punta": D(1), "llano": D(1), "valle": D(1)}),
    ]
    bill = compute_bill(segs)
    assert bill.dias == D(30)
    assert bill.potencia == money(D("4.6") * 15 * D("0.091074")) + money(D("4.6") * 15 * D("0.013483")) + money(
        D("4.6") * 15 * D("0.1")
    ) + money(D("4.6") * 15 * D("0.02"))

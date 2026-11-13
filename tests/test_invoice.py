"""Lectura de facturas en PDF: cifras, comprobaciones cruzadas y errores."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.factusol.invoice import InvoiceError, extract_text, parse_invoice

from .invoice_sample import sample_invoice


def test_reads_period_and_figures():
    p = parse_invoice(sample_invoice())
    assert (p.inicio, p.fin, p.dias) == (date(2026, 10, 1), date(2026, 10, 14), 14)
    assert p.factura == {
        "consumo_punta": 3.0,
        "consumo_llano": 2.0,
        "consumo_valle": 7.0,
        "excedente_kwh": 40.0,
        "total_bruto": 9.68,
        "hucha_aplicada": 9.68,
        "total_a_pagar": 0.0,
        "hucha_ingreso": 1.2,
        "saldo_hucha_final": 150.0,
    }
    assert p.tarifa["precio_punta"] == 0.196495
    assert p.tarifa["potencia_valle_kw"] == 4.6
    assert p.tarifa["impuesto_electrico"] == 5.11269632
    assert p.tarifa["iva"] == 21.0
    assert p.tarifa["precio_excedentes"] == 0.07
    assert p.avisos == []


def test_invoice_without_solar_has_no_hucha_fields():
    p = parse_invoice(sample_invoice(surplus=False).replace("TOTAL IMPORTE FACTURA 0,00 €", "TOTAL IMPORTE FACTURA 9,68 €"))
    assert p.factura["total_a_pagar"] == 9.68
    assert "hucha_aplicada" not in p.factura and "excedente_kwh" not in p.factura


def test_thousands_separator():
    text = sample_invoice().replace("Punta 3,00 kWh", "Punta 1.003,00 kWh").replace("Total 12,00 kWh", "Total 1.012,00 kWh")
    assert parse_invoice(text).factura["consumo_punta"] == 1003.0


def test_rejects_inconsistent_totals():
    with pytest.raises(InvoiceError, match="no cuadran"):
        parse_invoice(sample_invoice().replace("TOTAL IMPORTE FACTURA 0,00 €", "TOTAL IMPORTE FACTURA 3,00 €"))
    with pytest.raises(InvoiceError, match="suman"):
        parse_invoice(sample_invoice().replace("Total 12,00 kWh", "Total 15,00 kWh"))


def test_rejects_other_documents():
    with pytest.raises(InvoiceError):
        parse_invoice("Recibo de agua. Total 12,00 €")
    with pytest.raises(InvoiceError, match="coherentes"):
        parse_invoice(sample_invoice(prev_end="14/10/2026", end="30/09/2026"))


def test_changing_price_inside_the_period_is_flagged_not_applied():
    text = sample_invoice().replace(
        "Llano 2,00 kWh x 0,138209 €/kWh 0,28 €",
        "Punta 1,00 kWh x 0,200000 €/kWh 0,20 €\nLlano 2,00 kWh x 0,138209 €/kWh 0,28 €",
    ).replace("Total 12,00 kWh", "Total 13,00 kWh")
    p = parse_invoice(text)
    assert p.factura["consumo_punta"] == 4.0
    assert "precio_punta" not in p.tarifa
    assert p.avisos


def test_pdf_limits():
    with pytest.raises(InvoiceError, match="no es un PDF"):
        extract_text(b"hola")
    with pytest.raises(InvoiceError, match="grande"):
        extract_text(b"%PDF-" + b"0" * 5_000_001)


@pytest.mark.parametrize("label", ["IVA", "IVA (*)", "IVA Reducido (*)"])
def test_vat_line_variants(label):
    """El IVA sale como «IVA», «IVA (*)» o «IVA Reducido (*)» según el periodo."""
    p = parse_invoice(sample_invoice(vat_label=label))
    assert p.factura["total_bruto"] == 9.68
    assert p.tarifa["iva"] == 21.0

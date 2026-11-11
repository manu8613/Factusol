"""Texto de factura SINTÉTICO (cifras inventadas) con el mismo formato que las facturas reales."""

from __future__ import annotations


def sample_invoice(
    prev_end: str = "30/09/2026",
    end: str = "14/10/2026",
    days: int = 14,
    price_peak: str = "0,196495",
    surplus: bool = True,
) -> str:
    solar = (
        "Compensación de excedentes (2) -1,60 €\n"
        "(2) La energía excedentaria del último mes es -40,00 kWh y el precio de compensación "
        "de los excedentes es 0,07 € /kWh, según el RD 244/2019.\n"
        "Le recordamos que, gracias al servicio Solar Cloud, en esta factura se le ha aplicado un ahorro de 9,68 €.\n"
        "Además, este mes, el importe almacenado en Solar Cloud (por excedentes no compensados), ha sido de 1,20 €. "
        "Esto hace que su saldo Solar Cloud disponible a la fecha, ascienda a un total de 150,00 \n€. Este saldo se aplicará.\n"
        "Bono Solar Cloud (1) -9,68 €\n"
        if surplus
        else ""
    )
    return f"""FACTURA DE ELECTRICIDAD
RESUMEN DE FACTURA
PERIODO DE FACTURACIÓN: Nº FACTURA:
{prev_end} - {end} 000000000000000000
DETALLE DE FACTURA
Potencia facturada Punta 4,6 kW x {days} días x 0,091074 €/kW día 5,87 €
Valle 4,6 kW x {days} días x 0,013483 €/kW día 0,87 €
Energía consumida Punta 3,00 kWh x {price_peak} €/kWh 0,59 €
Llano 2,00 kWh x 0,138209 €/kWh 0,28 €
Valle 7,00 kWh x 0,104479 €/kWh 0,73 €
Total 12,00 kWh hasta {end} 1,60 €
{solar}Financiación bono social fijo {days} días x 0,024688 €/día 0,35 €
Impuesto sobre electricidad 5,11269632 % s/7,87 € 0,40 €
Alquiler equipos medida {days} días x 0,02663 €/día 0,37 €
IMPORTE TOTAL 8,00 €
IVA 21 % s/8,00 € 1,68 €
TOTAL IMPORTE FACTURA 0,00 €
"""

"""Constantes de Factusol."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "factusol"

# Configuración (entry.data / entry.options)
CONF_IMPORT_ENTITY: Final = "import_entity"
CONF_EXPORT_ENTITY: Final = "export_entity"
CONF_CYCLE_DAY: Final = "cycle_day"
CONF_EXTRA_HOLIDAYS: Final = "extra_holidays"
CONF_HUCHA_ENABLED: Final = "hucha_enabled"
CONF_HUCHA_BALANCE: Final = "hucha_balance"
CONF_HUCHA_DATE: Final = "hucha_date"
CONF_TARIFFS: Final = "tarifas"

# Campos de una versión de tarifa (coinciden con billing.Tariff)
T_FROM: Final = "desde"
T_POWER_PEAK: Final = "potencia_punta_kw"
T_POWER_VALLEY: Final = "potencia_valle_kw"
T_POWER_PRICE_PEAK: Final = "precio_potencia_punta"
T_POWER_PRICE_VALLEY: Final = "precio_potencia_valle"
T_PRICE_PEAK: Final = "precio_punta"
T_PRICE_FLAT: Final = "precio_llano"
T_PRICE_VALLEY: Final = "precio_valle"
T_PRICE_SURPLUS: Final = "precio_excedentes"
T_SOCIAL: Final = "bono_social_dia"
T_RENTAL: Final = "alquiler_dia"
T_OTHER_DAY: Final = "otros_dia"
T_OTHER_MONTH: Final = "otros_mes"
T_TAX: Final = "impuesto_electrico"
T_TAX_MIN: Final = "impuesto_minimo_mwh"
T_VAT: Final = "iva"

TARIFF_FIELDS: Final = (
    T_POWER_PEAK,
    T_POWER_VALLEY,
    T_POWER_PRICE_PEAK,
    T_POWER_PRICE_VALLEY,
    T_PRICE_PEAK,
    T_PRICE_FLAT,
    T_PRICE_VALLEY,
    T_PRICE_SURPLUS,
    T_SOCIAL,
    T_RENTAL,
    T_OTHER_DAY,
    T_OTHER_MONTH,
    T_TAX,
    T_TAX_MIN,
    T_VAT,
)

# Valores de ejemplo (contrato doméstico 2.0TD con compensación de excedentes).
# Son un punto de partida: cada usuario pone los de su factura.
DEFAULT_TARIFF: Final = {
    T_FROM: "2000-01-01",
    T_POWER_PEAK: 4.6,
    T_POWER_VALLEY: 4.6,
    T_POWER_PRICE_PEAK: 0.091074,
    T_POWER_PRICE_VALLEY: 0.013483,
    T_PRICE_PEAK: 0.196495,
    T_PRICE_FLAT: 0.138209,
    T_PRICE_VALLEY: 0.104479,
    T_PRICE_SURPLUS: 0.07,
    T_SOCIAL: 0.024688,
    T_RENTAL: 0.02663,
    T_OTHER_DAY: 0.0,
    T_OTHER_MONTH: 0.0,
    T_TAX: 5.11269632,
    T_TAX_MIN: 1.0,
    T_VAT: 21.0,
}

DEFAULT_NAME: Final = "Factusol"
DEFAULT_CYCLE_DAY: Final = 1

TICK: Final = timedelta(seconds=30)
STORAGE_VERSION: Final = 1
MAX_PDF_B64_CHARS: Final = 7_000_000  # un PDF de 5 MB en base64
MAX_CSV_CHARS: Final = 8_000_000  # un año de CSV horario ocupa menos de 1 MB
MAX_GAP_HOURS: Final = 24 * 14  # un hueco mayor se reparte igualmente, pero se avisa

# Claves de los valores que se ajustan desde entidades number
KEY_FACTOR_IMP: Final = "factor_importacion"
KEY_FACTOR_EXP: Final = "factor_exportacion"
KEY_OFFSET_IMP: Final = "desfase_importacion_wh"
KEY_OFFSET_EXP: Final = "desfase_exportacion_wh"

# Servicios
SERVICE_NEW_TARIFF: Final = "nueva_tarifa"
SERVICE_IMPORT: Final = "importar_datos_distribuidora"
SERVICE_CALIBRATE: Final = "calibrar"
SERVICE_REBUILD: Final = "reconstruir_historial"
SERVICE_REGISTER_BILL: Final = "registrar_factura"
SERVICE_IMPORT_INVOICE: Final = "importar_factura_pdf"
SERVICE_SET_HUCHA: Final = "ajustar_hucha"
SERVICE_SET_FIXED: Final = "ajustar_costes_fijos"

ATTR_ENTRY: Final = "config_entry_id"

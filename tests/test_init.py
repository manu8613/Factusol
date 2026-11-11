"""Pruebas de integración en un Home Assistant real (pytest-homeassistant-custom-component)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import voluptuous as vol

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant import config_entries  # noqa: E402
from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.exceptions import HomeAssistantError  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.factusol.const import DEFAULT_TARIFF, DOMAIN  # noqa: E402
from custom_components.factusol.hours import eh_of  # noqa: E402

IMPORT = "sensor.red_importada"
EXPORT = "sensor.red_exportada"
NOW = datetime(2026, 11, 11, 9, 30, tzinfo=UTC)  # 10:30 en Madrid: hora punta


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture(autouse=True)
async def madrid(hass):
    await hass.config.async_set_time_zone("Europe/Madrid")


@pytest.fixture(autouse=True)
def frozen(freezer):
    freezer.move_to(NOW)
    return freezer


@pytest.fixture
def expected_lingering_timers() -> bool:
    return True


def _eh(frozen) -> int:
    return eh_of(frozen().replace(tzinfo=UTC))


def _state(hass: HomeAssistant, entity_id: str, value: float, unit: str = "kWh") -> None:
    hass.states.async_set(entity_id, str(value), {"unit_of_measurement": unit, "device_class": "energy"})


def _entry(**data) -> MockConfigEntry:
    base = {
        "import_entity": IMPORT,
        "export_entity": EXPORT,
        "cycle_day": 1,
        "hucha_enabled": True,
        "hucha_balance": 190.05,
        "hucha_date": "2026-09-30",
    }
    return MockConfigEntry(
        domain=DOMAIN,
        title="Luz",
        unique_id=IMPORT,
        data={**base, **data},
        options={"tarifas": [dict(DEFAULT_TARIFF)]},
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry | None = None) -> MockConfigEntry:
    entry = entry or _entry()
    _state(hass, IMPORT, 1000.0)
    _state(hass, EXPORT, 2000.0)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def _sensor(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    reg = er.async_get(hass)
    entity_id = reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


async def test_config_flow_creates_entry_with_tariff(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Casa", "import_entity": IMPORT, "export_entity": EXPORT, "cycle_day": 1, "extra_holidays": ""},
    )
    assert result["step_id"] == "precios"
    prices = {k: v for k, v in DEFAULT_TARIFF.items() if k in (
        "potencia_punta_kw", "potencia_valle_kw", "precio_potencia_punta", "precio_potencia_valle",
        "precio_punta", "precio_llano", "precio_valle", "precio_excedentes")}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], prices)
    assert result["step_id"] == "cargos"
    charges = {k: v for k, v in DEFAULT_TARIFF.items() if k in (
        "bono_social_dia", "alquiler_dia", "otros_dia", "otros_mes", "impuesto_electrico", "impuesto_minimo_mwh", "iva")}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], charges)
    assert result["step_id"] == "hucha"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"hucha_enabled": True, "hucha_balance": 190.05, "hucha_date": "2026-09-30"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Casa"
    assert result["data"]["import_entity"] == IMPORT
    assert result["options"]["tarifas"][0]["precio_punta"] == 0.196495


async def test_same_import_sensor_cannot_be_added_twice(hass: HomeAssistant) -> None:
    _entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Otra", "import_entity": IMPORT, "cycle_day": 1}
    )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_live_measurement_builds_the_cycle(hass: HomeAssistant, frozen) -> None:
    entry = await _setup(hass)
    manager = entry.runtime_data
    frozen.tick(timedelta(minutes=10))
    _state(hass, IMPORT, 1000.4)  # +400 Wh en hora punta
    _state(hass, EXPORT, 2000.1)
    await hass.async_block_till_done()
    await manager.async_refresh()
    assert _sensor(hass, entry, "periodo_actual").state == "punta"
    consumo = _sensor(hass, entry, "consumo_punta")
    # 400 Wh importados - 100 Wh exportados en la misma hora = 300 Wh netos
    assert float(consumo.state) == pytest.approx(0.3, abs=0.005)
    assert _sensor(hass, entry, "excedentes").state == "0.0"
    factura = _sensor(hass, entry, "factura_estimada")
    assert float(factura.state) > 0
    assert factura.attributes["horas_propias"] == 1
    assert _sensor(hass, entry, "saldo_hucha_facturado") is not None


async def test_counter_reset_is_not_counted(hass: HomeAssistant, frozen) -> None:
    entry = await _setup(hass)
    manager = entry.runtime_data
    frozen.tick(timedelta(minutes=5))
    _state(hass, IMPORT, 3.0)  # el contador se reinicia
    await hass.async_block_till_done()
    rec = manager.ledger.get(_eh(frozen))
    assert rec is None or (rec[0] or 0) == 0


async def test_unit_conversion_from_wh(hass: HomeAssistant, frozen) -> None:
    entry = _entry()
    hass.states.async_set(IMPORT, "1000000", {"unit_of_measurement": "Wh"})
    hass.states.async_set(EXPORT, "0", {"unit_of_measurement": "Wh"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    frozen.tick(timedelta(minutes=1))
    hass.states.async_set(IMPORT, "1000250", {"unit_of_measurement": "Wh"})
    await hass.async_block_till_done()
    rec = entry.runtime_data.ledger.get(_eh(frozen))
    assert rec[0] == pytest.approx(250.0)


def _write_csv(hass: HomeAssistant, name: str = "datos.csv") -> str:
    rows = ["CUPS;FECHA-HORA;INV / VER;PERIODO TARIFARIO;CONSUMO Wh;GENERACION Wh;"]
    for h in range(1, 24):
        rows.append(f"ES0000000000000000XX;2026/11/05 {h:02d}:00;0;Valle;{100 + h};{h};")
    folder = Path(hass.config.path(DOMAIN))
    folder.mkdir(exist_ok=True)
    (folder / name).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return name


async def test_import_official_csv_and_cycle_counts(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    path = _write_csv(hass)
    result = await hass.services.async_call(
        DOMAIN, "importar_datos_distribuidora", {"ruta": path}, blocking=True, return_response=True
    )
    assert result["horas"] == 23
    assert _sensor(hass, entry, "ultimo_dato_oficial").state not in ("unknown", "unavailable")
    factura = _sensor(hass, entry, "factura_estimada")
    assert factura.attributes["horas_oficiales"] == 23


async def test_import_official_csv_from_content(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    name = _write_csv(hass, "temporal.csv")
    text = (Path(hass.config.path(DOMAIN)) / name).read_text(encoding="utf-8")
    result = await hass.services.async_call(
        DOMAIN, "importar_datos_distribuidora", {"contenido": text}, blocking=True, return_response=True
    )
    assert result["horas"] == 23
    assert _sensor(hass, entry, "factura_estimada").attributes["horas_oficiales"] == 23


async def test_import_needs_exactly_one_source(hass: HomeAssistant) -> None:
    await _setup(hass)
    for data in ({}, {"ruta": "a.csv", "contenido": "x"}):
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(DOMAIN, "importar_datos_distribuidora", data, blocking=True)


async def test_import_rejects_unknown_or_huge_content(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "importar_datos_distribuidora", {"contenido": "a;b\n1;2"}, blocking=True)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "importar_datos_distribuidora", {"contenido": "x" * 8_000_001}, blocking=True
        )


@pytest.mark.parametrize("ruta", ["/etc/passwd", "../configuration.yaml", "no_existe.csv"])
async def test_import_rejects_paths_outside_the_folder(hass: HomeAssistant, ruta: str) -> None:
    await _setup(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "importar_datos_distribuidora", {"ruta": ruta}, blocking=True)


async def test_calibration_finds_the_clamp_error_and_applies_it(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    manager = entry.runtime_data
    base = eh_of(datetime(2026, 11, 3, 0, tzinfo=UTC))
    for i in range(72):  # la pinza lee un 4 % de menos
        official = 200 + (i % 7) * 40
        manager.ledger.add_own(base + i, official * 0.96, official * 0.5 * 0.96)
        manager.ledger.set_official(base + i, official, official * 0.5, None)
    report = await hass.services.async_call(
        DOMAIN, "calibrar", {"modo": "factor", "aplicar": True}, blocking=True, return_response=True
    )
    assert report["importacion"]["factor"] == pytest.approx(1 / 0.96, rel=1e-3)
    assert report["aplicada"] is True
    assert manager.settings["factor_importacion"] == pytest.approx(1 / 0.96, rel=1e-3)
    assert float(_sensor(hass, entry, "desfase_importacion").state) == pytest.approx(-4.0, abs=0.1)


async def test_register_real_bill_fixes_the_balance(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.services.async_call(
        DOMAIN,
        "registrar_factura",
        {"fecha_fin": "2026-10-31", "total_bruto": 20.5, "hucha_aplicada": 20.5, "hucha_ingreso": 30.0, "saldo_hucha_final": 199.55},
        blocking=True,
        return_response=True,
    )
    assert result["ciclo"] == "2026-10-01"
    snap = entry.runtime_data.data
    october = next(c for c in snap.cycles if c.key == "2026-10-01")
    assert float(october.bill.total_bruto) == 20.5
    assert float(october.bill.coste_real) == pytest.approx(-9.5)
    assert float(snap.current.bill.saldo_hucha_inicial) == pytest.approx(199.55)
    assert _sensor(hass, entry, "coste_real_anterior").state == "-9.5"


async def test_new_tariff_is_stored_and_reloads(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    await hass.services.async_call(
        DOMAIN, "nueva_tarifa", {"fecha": "2026-12-01", "precio_punta": 0.25}, blocking=True
    )
    await hass.async_block_till_done()
    tariffs = entry.options["tarifas"]
    assert [t["desde"] for t in tariffs] == ["2000-01-01", "2026-12-01"]
    assert tariffs[1]["precio_punta"] == 0.25
    assert tariffs[1]["precio_llano"] == DEFAULT_TARIFF["precio_llano"]
    assert entry.state is ConfigEntryState.LOADED


async def test_options_flow_edits_current_tariff(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "precios"})
    prices = {k: DEFAULT_TARIFF[k] for k in (
        "potencia_punta_kw", "potencia_valle_kw", "precio_potencia_punta", "precio_potencia_valle",
        "precio_punta", "precio_llano", "precio_valle", "precio_excedentes")}
    prices["precio_punta"] = 0.3
    result = await hass.config_entries.options.async_configure(result["flow_id"], prices)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["tarifas"][0]["precio_punta"] == 0.3


async def test_rebuild_history_fills_missing_hours(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    manager = entry.runtime_data
    start = eh_of(datetime(2026, 11, 2, 0, tzinfo=UTC))
    rows = {
        IMPORT: [{"start": (start + i) * 3600.0, "end": (start + i + 1) * 3600.0, "change": 200.0} for i in range(5)],
        EXPORT: [{"start": (start + i) * 3600.0, "end": (start + i + 1) * 3600.0, "change": 50.0} for i in range(5)],
    }

    async def run(fn, *args):
        return fn(*args)

    with (
        patch("homeassistant.components.recorder.get_instance", return_value=SimpleNamespace(async_add_executor_job=run)),
        patch("homeassistant.components.recorder.statistics.statistics_during_period", return_value=rows),
    ):
        out = await hass.services.async_call(
            DOMAIN, "reconstruir_historial", {"desde": "2026-11-01"}, blocking=True, return_response=True
        )
    assert out["horas_añadidas"] == 5
    assert manager.ledger.get(start)[:2] == [pytest.approx(200.0), pytest.approx(50.0)]


async def test_fixed_costs_accumulate_and_can_be_set(hass: HomeAssistant, frozen) -> None:
    entry = await _setup(hass)
    manager = entry.runtime_data
    await hass.services.async_call(DOMAIN, "ajustar_costes_fijos", {"valor": 100.0}, blocking=True)
    frozen.tick(timedelta(hours=24))
    await manager.async_refresh()
    daily = float(manager.tariffs[0].fixed_daily())
    assert manager.fixed_total == pytest.approx(100.0 + daily, rel=1e-3)
    assert float(_sensor(hass, entry, "costes_fijos").state) == pytest.approx(100.0 + daily, abs=0.01)


async def test_unload_and_remove(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert await hass.config_entries.async_remove(entry.entry_id)


def _pdf_b64() -> str:
    import base64

    return base64.b64encode(b"%PDF-1.4 sintetico").decode()


async def test_import_invoice_pdf_sets_real_cycle_days(hass: HomeAssistant) -> None:
    from tests.invoice_sample import sample_invoice

    entry = await _setup(hass)
    with patch("custom_components.factusol.manager.extract_text", return_value=sample_invoice()):
        result = await hass.services.async_call(
            DOMAIN, "importar_factura_pdf", {"contenido": _pdf_b64()}, blocking=True, return_response=True
        )
    assert result["periodo"]["inicio"] == "2026-10-01" and result["periodo"]["fin"] == "2026-10-14"
    assert result["ciclo"] == "2026-10-01"
    assert "tarifa_actualizada" not in result  # los precios coinciden con los guardados
    snap = entry.runtime_data.data
    assert [c.key for c in snap.cycles] == ["2026-10-01", "2026-10-15"]
    first = snap.cycles[0]
    assert first.end == date(2026, 10, 15) and first.closed
    assert float(first.bill.total_bruto) == 9.68
    assert float(first.bill.saldo_hucha_final) == pytest.approx(150.0)
    assert snap.current.start == date(2026, 10, 15)
    assert float(snap.current.bill.saldo_hucha_inicial) == pytest.approx(150.0)


async def test_import_invoice_pdf_updates_changed_prices(hass: HomeAssistant) -> None:
    from tests.invoice_sample import sample_invoice

    entry = await _setup(hass)
    with patch("custom_components.factusol.manager.extract_text", return_value=sample_invoice(price_peak="0,210000")):
        result = await hass.services.async_call(
            DOMAIN, "importar_factura_pdf", {"contenido": _pdf_b64()}, blocking=True, return_response=True
        )
    assert result["tarifa_actualizada"] == {"precio_punta": 0.21}
    await hass.async_block_till_done()
    tariffs = entry.options["tarifas"]
    assert tariffs[-1]["desde"] == "2026-10-01" and tariffs[-1]["precio_punta"] == 0.21


async def test_import_invoice_pdf_rejects_garbage(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(HomeAssistantError, match="no es un PDF"):
        await hass.services.async_call(DOMAIN, "importar_factura_pdf", {"contenido": "aG9sYQ=="}, blocking=True, return_response=True)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "importar_factura_pdf", {"contenido": "###"}, blocking=True, return_response=True)


async def test_register_bill_with_explicit_start_keeps_cycle_days(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.services.async_call(
        DOMAIN,
        "registrar_factura",
        {"fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-20", "total_bruto": 12.0},
        blocking=True,
        return_response=True,
    )
    assert result["ciclo"] == "2026-10-01"
    assert [c.key for c in entry.runtime_data.data.cycles] == ["2026-10-01", "2026-10-21"]


async def test_history_lists_invoices_older_than_the_initial_balance(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    await hass.services.async_call(
        DOMAIN,
        "registrar_factura",
        {"fecha_fin": "2026-08-31", "total_bruto": 20.95, "hucha_aplicada": 20.95, "hucha_ingreso": 31.71, "saldo_hucha_final": 175.29, "consumo_punta": 9.25, "consumo_llano": 6.01, "consumo_valle": 21.23, "excedente_kwh": 522.63},
        blocking=True,
        return_response=True,
    )
    months = _sensor(hass, entry, "historial_facturas").attributes["meses"]
    assert months[0]["ciclo"] == "2026-08-01" and months[0]["real"] is True
    assert months[0]["total_bruto"] == 20.95 and months[0]["consumo_kwh"] == 36.49
    assert months[0]["coste_real"] == pytest.approx(-10.76)
    assert months[1]["ciclo"] == "2026-10-01"

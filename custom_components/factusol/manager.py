"""Estado, medida horaria y facturación de un contador."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .billing import Bill, Tariff, compute_bill, dec, tariff_on
from .calibration import Fit, fit_pairs
from .const import (
    CONF_CYCLE_DAY,
    CONF_EXPORT_ENTITY,
    CONF_EXTRA_HOLIDAYS,
    CONF_HUCHA_BALANCE,
    CONF_HUCHA_DATE,
    CONF_HUCHA_ENABLED,
    CONF_IMPORT_ENTITY,
    CONF_TARIFFS,
    DEFAULT_CYCLE_DAY,
    DEFAULT_TARIFF,
    DOMAIN,
    KEY_FACTOR_EXP,
    KEY_FACTOR_IMP,
    KEY_OFFSET_EXP,
    KEY_OFFSET_IMP,
    MAX_CSV_CHARS,
    STORAGE_VERSION,
    T_FROM,
    TARIFF_FIELDS,
    TICK,
)
from .hours import add_months, eh_local, eh_of, local_midnight_eh, month_key
from .importer import CsvFormatError, parse_csv
from .invoice import InvoiceError, as_service_data, extract_text, parse_invoice
from .ledger import (
    DIST_EXP,
    DIST_IMP,
    OWN_EXP,
    OWN_IMP,
    Calibration,
    CycleTotals,
    Ledger,
    aggregate_cycle,
)
from .schedule import LLANO, PUNTA, VALLE, parse_extra_holidays, period_of

_LOGGER = logging.getLogger(__name__)

type FactusolConfigEntry = ConfigEntry[FactusolManager]

_UNIT_TO_WH = {"wh": 1.0, "kwh": 1000.0, "mwh": 1_000_000.0}


@dataclass
class CycleResult:
    """Ciclo de facturación calculado."""

    start: date
    end: date
    closed: bool
    totals: CycleTotals
    bill: Bill
    real: dict[str, Any] | None = None  # factura real registrada, si la hay

    @property
    def key(self) -> str:
        return self.start.isoformat()


@dataclass
class Snapshot:
    """Lo que ven las entidades."""

    now: datetime
    period: str
    price_kwh: float
    price_surplus: float
    current: CycleResult
    previous: CycleResult | None
    cycles: list[CycleResult]
    hucha_billed: float
    cost_year: float


def _as_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def cycle_start_for(day: date, cycle_day: int) -> date:
    """Inicio del ciclo de facturación que contiene ``day``."""
    if day.day >= cycle_day:
        return day.replace(day=cycle_day)
    return add_months(day.replace(day=cycle_day), -1)


class FactusolManager(DataUpdateCoordinator[Snapshot]):
    """Mide por horas, factura y mantiene la hucha."""

    config_entry: FactusolConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FactusolConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {entry.title}", update_interval=TICK
        )
        self.tz = ZoneInfo(hass.config.time_zone)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._month_stores: dict[str, Store[dict[str, Any]]] = {}
        self.ledger = Ledger(self.tz)
        self.baselines: dict[str, dict[str, float]] = {}
        self.fixed_total: float = 0.0
        self.fixed_ts: float | None = None
        self.settings: dict[str, float] = {
            KEY_FACTOR_IMP: 1.0,
            KEY_FACTOR_EXP: 1.0,
            KEY_OFFSET_IMP: 0.0,
            KEY_OFFSET_EXP: 0.0,
        }
        self.invoices: dict[str, dict[str, Any]] = {}
        self.report: dict[str, Any] = {}
        self._rev = 0
        self._closed_cache: dict[str, tuple[int, CycleTotals]] = {}

    # ------------------------------------------------------------ configuración
    def _opt(self, key: str, default: Any) -> Any:
        entry = self.config_entry
        return entry.options.get(key, entry.data.get(key, default))

    @property
    def import_entity(self) -> str:
        return self._opt(CONF_IMPORT_ENTITY, "")

    @property
    def export_entity(self) -> str | None:
        return self._opt(CONF_EXPORT_ENTITY, None) or None

    @property
    def cycle_day(self) -> int:
        return int(self._opt(CONF_CYCLE_DAY, DEFAULT_CYCLE_DAY))

    @property
    def extra_holidays(self) -> frozenset[tuple[int, int]]:
        return parse_extra_holidays(self._opt(CONF_EXTRA_HOLIDAYS, ""))

    @property
    def hucha_enabled(self) -> bool:
        return bool(self._opt(CONF_HUCHA_ENABLED, True))

    @property
    def tariff_dicts(self) -> list[dict[str, Any]]:
        raw = self.config_entry.options.get(CONF_TARIFFS) or self.config_entry.data.get(CONF_TARIFFS)
        return list(raw) if raw else [dict(DEFAULT_TARIFF)]

    @property
    def tariffs(self) -> list[Tariff]:
        items = sorted(self.tariff_dicts, key=lambda t: t[T_FROM])
        return [Tariff.from_dict(t) for t in items]

    @property
    def calibration(self) -> Calibration:
        s = self.settings
        return Calibration(
            s[KEY_FACTOR_IMP], s[KEY_OFFSET_IMP], s[KEY_FACTOR_EXP], s[KEY_OFFSET_EXP]
        )

    # ------------------------------------------------------------ ciclo de vida
    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self.baselines = data.get("baselines", {})
            self.fixed_total = float(data.get("fixed_total", 0.0))
            self.fixed_ts = data.get("fixed_ts")
            self.settings.update(data.get("settings", {}))
            self.invoices = data.get("invoices", {})
            self.report = data.get("report", {})
            for key in data.get("months", []):
                store = self._month_store(key)
                if month := await store.async_load():
                    self.ledger.load_month(key, month)

    def _month_store(self, key: str) -> Store[dict[str, Any]]:
        if key not in self._month_stores:
            self._month_stores[key] = Store(
                self.hass, STORAGE_VERSION, f"{DOMAIN}.{self.config_entry.entry_id}.{key}"
            )
        return self._month_stores[key]

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "baselines": self.baselines,
            "fixed_total": self.fixed_total,
            "fixed_ts": self.fixed_ts,
            "settings": self.settings,
            "invoices": self.invoices,
            "report": self.report,
            "months": sorted(self.ledger.months),
        }

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(self._data_to_save, 10)
        for key in list(self.ledger.dirty):
            self._month_store(key).async_delay_save(
                lambda k=key: self.ledger.dump_month(k), 20  # type: ignore[misc]
            )
        self.ledger.dirty.clear()

    async def async_flush(self) -> None:
        await self._store.async_save(self._data_to_save())
        for key in list(self.ledger.months):
            await self._month_store(key).async_save(self.ledger.dump_month(key))

    async def async_remove_stores(self) -> None:
        for key in list(self.ledger.months):
            await self._month_store(key).async_remove()
        await self._store.async_remove()

    @callback
    def async_start(self) -> None:
        entities = [e for e in (self.import_entity, self.export_entity) if e]
        self.config_entry.async_on_unload(
            async_track_state_change_event(self.hass, entities, self._handle_state)
        )
        # Lectura inicial: fija la base sin contar nada.
        for entity_id in entities:
            if (state := self.hass.states.get(entity_id)) is not None:
                self._ingest(entity_id, state.state, dict(state.attributes), state.last_updated)

    # ------------------------------------------------------------ medida propia
    @callback
    def _handle_state(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        if new is None:
            return
        self._ingest(new.entity_id, new.state, dict(new.attributes), new.last_updated)

    def _ingest(self, entity_id: str, raw: str, attrs: dict[str, Any], when: datetime) -> None:
        if raw in (STATE_UNKNOWN, STATE_UNAVAILABLE, "", None):
            return
        try:
            value = float(raw)
        except ValueError:
            return
        unit = str(attrs.get("unit_of_measurement", "kWh")).lower()
        value_wh = value * _UNIT_TO_WH.get(unit, 1000.0)
        when_ts = when.timestamp()
        base = self.baselines.get(entity_id)
        self.baselines[entity_id] = {"wh": value_wh, "ts": when_ts}
        if base is None:
            self._save()
            return
        delta = value_wh - base["wh"]
        if delta < 0:  # reinicio del contador: se toma como nueva base
            _LOGGER.debug("%s ha bajado: se toma como reinicio", entity_id)
            self._save()
            return
        if delta > 0:
            self._spread(entity_id == self.import_entity, delta, base["ts"], when_ts)
        self._save()

    def _spread(self, is_import: bool, delta_wh: float, t0: float, t1: float) -> None:
        """Reparte el incremento entre las horas del intervalo, en proporción al tiempo."""
        if t1 <= t0:
            slices = [(eh_of(datetime.fromtimestamp(t1, UTC)), 1.0)]
        else:
            slices = []
            first, last = int(t0 // 3600), int(t1 // 3600)
            for eh in range(first, last + 1):
                lo, hi = max(t0, eh * 3600), min(t1, (eh + 1) * 3600)
                if hi > lo:
                    slices.append((eh, (hi - lo) / (t1 - t0)))
        for eh, share in slices:
            amount = delta_wh * share
            if is_import:
                self.ledger.add_own(eh, amount, 0.0)
            else:
                self.ledger.add_own(eh, 0.0, amount)

    # ------------------------------------------------------------ cálculo
    def _cycle_totals(self, start: date, end: date, now: datetime, closed: bool) -> CycleTotals:
        key = start.isoformat()
        if closed and (cached := self._closed_cache.get(key)) and cached[0] == self._rev:
            return cached[1]
        totals = aggregate_cycle(
            self.ledger, self.tariffs, start, end, now, self.calibration, self.extra_holidays
        )
        if closed:
            self._closed_cache[key] = (self._rev, totals)
        return totals

    def _build_chain(self, now: datetime) -> list[CycleResult]:
        today = now.astimezone(self.tz).date()
        base_day = date.fromisoformat(
            self._opt(CONF_HUCHA_DATE, (today - timedelta(days=today.day)).isoformat())
        )
        balance = dec(self._opt(CONF_HUCHA_BALANCE, 0.0))
        start = cycle_start_for(base_day + timedelta(days=1), self.cycle_day)
        if start > today:
            start = cycle_start_for(today, self.cycle_day)
        invoice_starts = sorted(d for k in self.invoices if (d := _as_date(k)) is not None)
        results: list[CycleResult] = []
        guard = 0
        while start <= today and guard < 240:
            guard += 1
            end = add_months(start, 1)
            rec = self.invoices.get(start.isoformat())
            if rec and (last := _as_date(rec.get("fecha_fin"))) and last >= start:
                end = last + timedelta(days=1)  # los días reales que cobró la factura
            elif later := [d for d in invoice_starts if start < d < end]:
                end = later[0]  # una factura empieza antes de lo previsto
            closed = end <= today
            totals = self._cycle_totals(start, end, now, closed)
            bill = compute_bill(totals.segments, balance, self.hucha_enabled)
            if rec:
                bill = _with_real(bill, rec)
            results.append(CycleResult(start, end, closed, totals, bill, rec or None))
            balance = bill.saldo_hucha_final
            start = end
        return results

    def _prices_now(self, now: datetime) -> tuple[str, float, float]:
        local = now.astimezone(self.tz)
        tariff = tariff_on(self.tariffs, local.date())
        period = period_of(local, self.extra_holidays)
        gross = tariff.price(period) * (1 + tariff.impuesto_electrico / 100) * (1 + tariff.iva / 100)
        return period, float(gross), float(tariff.precio_excedentes)

    def _accumulate_fixed(self, now: datetime) -> None:
        ts = now.timestamp()
        if self.fixed_ts is None:
            self.fixed_ts = ts
            return
        if ts <= self.fixed_ts:
            return
        cursor = datetime.fromtimestamp(self.fixed_ts, UTC).astimezone(self.tz)
        end = now.astimezone(self.tz)
        total = 0.0
        while cursor < end:
            midnight_next = datetime(cursor.year, cursor.month, cursor.day, tzinfo=self.tz) + timedelta(days=1)
            stop = min(end, midnight_next)
            days = (stop - cursor).total_seconds() / 86400
            total += float(tariff_on(self.tariffs, cursor.date()).fixed_daily()) * days
            cursor = stop
        self.fixed_total += total
        self.fixed_ts = ts

    async def _async_update_data(self) -> Snapshot:
        now = dt_util.utcnow()
        self._accumulate_fixed(now)
        cycles = self._build_chain(now)
        current = cycles[-1]
        previous = cycles[-2] if len(cycles) > 1 else None
        period, price, surplus = self._prices_now(now)
        year = now.astimezone(self.tz).year
        cost_year = sum(c.bill.coste_real for c in cycles if c.start.year == year)
        billed = next((c for c in reversed(cycles) if c.closed), None)
        if self.ledger.dirty:
            self._save()
        return Snapshot(
            now=now,
            period=period,
            price_kwh=price,
            price_surplus=surplus,
            current=current,
            previous=previous,
            cycles=cycles,
            hucha_billed=float(billed.bill.saldo_hucha_final) if billed else 0.0,
            cost_year=float(cost_year),
        )

    @callback
    def invalidate(self) -> None:
        """Cambió algo que afecta a los ciclos cerrados (datos, calibración, tarifa)."""
        self._rev += 1
        self._save()

    # ------------------------------------------------------------ servicios
    async def async_set_setting(self, key: str, value: float) -> None:
        self.settings[key] = float(value)
        self.invalidate()
        await self.async_request_refresh()

    async def async_new_tariff(self, since: date, values: dict[str, Any]) -> None:
        tariffs = [dict(t) for t in self.tariff_dicts]
        latest = dict(max(tariffs, key=lambda t: t[T_FROM]))
        latest.update({k: v for k, v in values.items() if k in TARIFF_FIELDS and v is not None})
        latest[T_FROM] = since.isoformat()
        tariffs = [t for t in tariffs if t[T_FROM] != latest[T_FROM]] + [latest]
        self._update_options({CONF_TARIFFS: sorted(tariffs, key=lambda t: t[T_FROM])})

    def _update_options(self, changes: dict[str, Any]) -> None:
        entry = self.config_entry
        self.hass.config_entries.async_update_entry(entry, options={**entry.options, **changes})

    async def async_set_hucha(self, balance: float, since: date) -> None:
        self._update_options(
            {CONF_HUCHA_BALANCE: float(balance), CONF_HUCHA_DATE: since.isoformat()}
        )

    async def async_set_fixed(self, value: float) -> None:
        self.fixed_total = float(value)
        self.fixed_ts = dt_util.utcnow().timestamp()
        self._save()
        await self.async_request_refresh()

    async def async_register_bill(
        self, end: date, data: dict[str, Any], start: date | None = None
    ) -> dict[str, Any]:
        """Guarda los datos reales de una factura y compara con la estimación.

        Con ``start`` (primer día facturado) el ciclo pasa a durar exactamente los días que
        cobró la factura; sin él se usa el día de ciclo configurado.
        """
        if start is None:
            start = cycle_start_for(end, self.cycle_day)
        elif end < start or (end - start).days > 400:
            raise HomeAssistantError("Las fechas de la factura no son coherentes")
        clean = {k: v for k, v in data.items() if v is not None}
        if start != cycle_start_for(end, self.cycle_day) or end != add_months(start, 1) - timedelta(days=1):
            clean["fecha_fin"] = end.isoformat()
        self.invoices.pop(start.isoformat(), None)
        await self.async_refresh()
        estimate = next((c for c in self.data.cycles if c.start == start), None)
        self.invoices[start.isoformat()] = clean
        self.invalidate()
        await self.async_refresh()
        out: dict[str, Any] = {"ciclo": start.isoformat()}
        if estimate is not None:
            out["estimado"] = estimate.bill.as_dict()
            if (real := clean.get("total_bruto")) is not None:
                out["desviacion_total_bruto"] = round(float(estimate.bill.total_bruto) - float(real), 2)
        else:
            out["aviso"] = "Es anterior al saldo inicial de la hucha: se guarda, pero no cambia el cálculo actual"
        return out

    async def async_import_invoice(self, content: str, apply_tariff: bool = True) -> dict[str, Any]:
        """Lee una factura en PDF (base64), la registra y, si hace falta, actualiza la tarifa.

        El PDF solo existe en memoria durante la llamada: no se guarda en ningún sitio.
        """
        try:
            raw = base64.b64decode(content, validate=False)
        except (ValueError, TypeError) as err:
            raise HomeAssistantError("El contenido del PDF no es base64 válido") from err
        try:
            text = await self.hass.async_add_executor_job(extract_text, raw)
            parsed = parse_invoice(text)
        except InvoiceError as err:
            raise HomeAssistantError(str(err)) from err
        del raw, text
        result = await self.async_register_bill(parsed.fin, dict(parsed.factura), start=parsed.inicio)
        out: dict[str, Any] = {"periodo": as_service_data(parsed), **result}
        if parsed.avisos:
            out["avisos"] = list(parsed.avisos)
        if apply_tariff and parsed.tarifa:
            eligible = [t for t in self.tariff_dicts if t[T_FROM] <= parsed.inicio.isoformat()]
            current = max(eligible, key=lambda t: t[T_FROM]) if eligible else None
            changes = {
                k: v
                for k, v in parsed.tarifa.items()
                if current is None or abs(float(current.get(k, 0.0)) - v) > 1e-9
            }
            if changes:
                out["tarifa_actualizada"] = changes
                await self.async_new_tariff(parsed.inicio, changes)  # recarga la integración: va el último
        return out

    async def async_import_official(self, path: str | None = None, content: str | None = None) -> dict[str, Any]:
        """Importa un CSV del contador oficial a las horas del libro (desde un fichero o su contenido)."""
        if content is not None:
            if len(content) > MAX_CSV_CHARS:
                raise HomeAssistantError("El CSV es demasiado grande")
            text = content
        elif path:
            text = await self.hass.async_add_executor_job(self._read_allowed, path)
        else:
            raise HomeAssistantError("Indica la ruta o el contenido del CSV")
        try:
            hours = parse_csv(text, self.tz)
        except CsvFormatError as err:
            raise HomeAssistantError(f"No reconozco el formato del CSV: {err}") from err
        for hour in hours:
            self.ledger.set_official(hour.eh, hour.imp_wh, hour.exp_wh, hour.net_imp_wh)
        self.invalidate()
        await self.async_refresh()
        first = eh_local(min(h.eh for h in hours), self.tz) if hours else None
        last = eh_local(max(h.eh for h in hours), self.tz) if hours else None
        return {
            "horas": len(hours),
            "desde": first.isoformat() if first else None,
            "hasta": last.isoformat() if last else None,
        }

    @property
    def data_dir(self) -> Path:
        """Carpeta ``<config>/factusol``: aquí se dejan los CSV de la distribuidora."""
        return Path(self.hass.config.path(DOMAIN))

    def _read_allowed(self, path: str) -> str:
        """Lee un CSV de la carpeta de Factusol o de una carpeta permitida (bloquea: en executor)."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.data_dir / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, PermissionError) as err:
            raise HomeAssistantError(f"No encuentro el fichero {path}") from err
        if self.data_dir.resolve() not in resolved.parents and not self.hass.config.is_allowed_path(str(resolved)):
            raise HomeAssistantError(
                f"Ruta no permitida: deja el CSV en {self.data_dir} o añade su carpeta a allowlist_external_dirs"
            )
        return _read_text(str(resolved))

    async def async_rebuild_history(self, since: date) -> dict[str, Any]:
        """Rellena horas propias a partir de las estadísticas del recorder."""
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import statistics_during_period

        start = datetime(since.year, since.month, since.day, tzinfo=self.tz)
        end = dt_util.utcnow()
        ids = {e for e in (self.import_entity, self.export_entity) if e}
        stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            end,
            ids,
            "hour",
            {"energy": "Wh"},
            {"change"},
        )
        by_hour: dict[int, list[float]] = {}
        for entity_id, rows in stats.items():
            idx = 0 if entity_id == self.import_entity else 1
            for row in rows:
                ts = float(row["start"])
                if ts > 1e11:
                    ts /= 1000
                change = row.get("change")
                if change is None:
                    continue
                by_hour.setdefault(int(ts // 3600), [0.0, 0.0])[idx] += max(float(change), 0.0)
        added = 0
        for eh, (imp, exp) in by_hour.items():
            if self.ledger.set_own_if_missing(eh, imp, exp):
                added += 1
        self.invalidate()
        await self.async_refresh()
        return {"horas_añadidas": added, "horas_con_estadistica": len(by_hour)}

    async def async_calibrate(
        self, since: date | None, until: date | None, mode: str, apply: bool
    ) -> dict[str, Any]:
        """Compara hora a hora la pinza con el contador oficial."""
        lo = local_midnight_eh(since, self.tz) if since else -(10**9)
        hi = local_midnight_eh(until + timedelta(days=1), self.tz) if until else 10**9
        now_eh = eh_of(dt_util.utcnow())
        pairs_imp: list[tuple[float, float]] = []
        pairs_exp: list[tuple[float, float]] = []
        months: dict[str, dict[str, float]] = {}
        for eh, rec in self.ledger.iter_hours(lo, min(hi, now_eh)):
            if rec[OWN_IMP] is None or rec[DIST_IMP] is None or rec[DIST_EXP] is None:
                continue
            own_imp, own_exp = float(rec[OWN_IMP]), float(rec[OWN_EXP] or 0.0)
            pairs_imp.append((own_imp, float(rec[DIST_IMP])))
            pairs_exp.append((own_exp, float(rec[DIST_EXP])))
            m = months.setdefault(
                month_key(eh_local(eh, self.tz)),
                {"horas": 0, "propio_imp": 0.0, "oficial_imp": 0.0, "propio_exp": 0.0, "oficial_exp": 0.0},
            )
            m["horas"] += 1
            m["propio_imp"] += own_imp / 1000
            m["oficial_imp"] += float(rec[DIST_IMP]) / 1000
            m["propio_exp"] += own_exp / 1000
            m["oficial_exp"] += float(rec[DIST_EXP]) / 1000
        fit_i, fit_e = fit_pairs(pairs_imp), fit_pairs(pairs_exp)
        report: dict[str, Any] = {
            "fecha": dt_util.utcnow().isoformat(),
            "importacion": _fit_dict(fit_i),
            "exportacion": _fit_dict(fit_e),
            "meses": {
                k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in sorted(months.items())
            },
            "aplicada": False,
        }
        if apply and (fit_i or fit_e):
            for fit, f_key, o_key in (
                (fit_i, KEY_FACTOR_IMP, KEY_OFFSET_IMP),
                (fit_e, KEY_FACTOR_EXP, KEY_OFFSET_EXP),
            ):
                if fit is None:
                    continue
                if mode == "factor_y_desfase":
                    self.settings[f_key], self.settings[o_key] = fit.factor_ls, fit.offset_wh
                else:
                    self.settings[f_key], self.settings[o_key] = fit.factor, 0.0
            report["aplicada"] = True
            self.invalidate()
        self.report = report
        await self.async_refresh()
        return report


def _with_real(bill: Bill, real: dict[str, Any]) -> Bill:
    """Sustituye lo estimado por los datos de la factura real que el usuario ha registrado."""
    changes: dict[str, Any] = {}
    if (v := real.get("total_bruto")) is not None:
        changes["total_bruto"] = dec(v)
    if (v := real.get("hucha_aplicada")) is not None:
        changes["hucha_aplicada"] = dec(v)
    if (v := real.get("hucha_ingreso")) is not None:
        changes["hucha_ingreso"] = dec(v)
    for period, key in ((PUNTA, "consumo_punta"), (LLANO, "consumo_llano"), (VALLE, "consumo_valle")):
        if (v := real.get(key)) is not None:
            changes.setdefault("kwh", dict(bill.kwh))[period] = dec(v)
    if (v := real.get("excedente_kwh")) is not None:
        changes["excedente_kwh"] = dec(v)
    new = replace(bill, **changes)
    gross, applied, stored = new.total_bruto, new.hucha_aplicada, new.hucha_ingreso
    paid = dec(real["total_a_pagar"]) if real.get("total_a_pagar") is not None else gross - applied
    balance = (
        dec(real["saldo_hucha_final"])
        if real.get("saldo_hucha_final") is not None
        else bill.saldo_hucha_inicial + stored - applied
    )
    return replace(new, total_a_pagar=paid, coste_real=gross - stored, saldo_hucha_final=balance)


def _fit_dict(fit: Fit | None) -> dict[str, float] | None:
    if fit is None:
        return None
    return {
        "horas": fit.horas,
        "propio_kwh": round(fit.propio_kwh, 3),
        "oficial_kwh": round(fit.oficial_kwh, 3),
        "desfase_pct": round(fit.desfase_pct, 2),
        "factor": round(fit.factor, 5),
        "factor_minimos_cuadrados": round(fit.factor_ls, 5),
        "desfase_wh_por_hora": round(fit.offset_wh, 3),
        "r2": round(fit.r2, 4),
    }


def _read_text(path: str) -> str:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


__all__ = ["CycleResult", "FactusolConfigEntry", "FactusolManager", "Snapshot", "cycle_start_for"]

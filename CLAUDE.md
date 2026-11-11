# CLAUDE.md — Factusol

## Qué es
Integración HACS pública (`custom_components/factusol`): factura de luz 2.0TD con neteo horario, compensación de excedentes, hucha de excedentes y calibración de la pinza contra el contador oficial.

## Por dónde empezar
1. `CHANGELOG.md` y `docs/STATUS.md`.
2. Solo el módulo afectado:
   - `billing.py` cálculo de la factura (sin Home Assistant, probado contra facturas reales).
   - `schedule.py` periodos punta/llano/valle y festivos. `hours.py` horas absolutas UTC.
   - `ledger.py` libro de horas y agregación por ciclo. `importer.py` CSV. `calibration.py` ajuste.
   - `manager.py` estado, medida y servicios. `sensor.py`/`number.py` entidades. `config_flow.py` asistente.

## Reglas
- Público y anónimo: sin nombres de empresas, personas, lugares, IPs ni CUPS en código, tests ni docs; autor manu8613.
- Las cifras de los tests son sintéticas o de facturas sin datos personales.
- Cada línea de la factura se redondea a céntimos (mitad hacia arriba) con `Decimal`; no mezclar `float` en `billing.py`.
- Las horas se guardan por hora absoluta UTC; nunca por hora local (cambios de hora).
- Versión en `manifest.json` + `## [X.Y.Z]` en CHANGELOG → `release.yml` crea etiqueta y release.
- Pruebas: `pip install -r requirements_test.txt ruff && ruff check . && pytest -q`.
- Cambios en rama y por PR. Nada de merge sin autorización.
- Al terminar: bloque CIERRE (ver abajo) y actualizar `docs/STATUS.md` en el mismo PR.

## Bloque CIERRE
Proyecto · repo/rama/commit · objetivo · cambios · pruebas · resultado verificado · issues/PR · pendientes · próximo paso.

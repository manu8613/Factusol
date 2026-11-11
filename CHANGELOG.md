# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · Versiones: [SemVer](https://semver.org/lang/es/).

## [0.1.0] - 2026-11-11
- Primera versión: factura de luz 2.0TD calculada como la real, con neteo horario consumo/excedente, compensación de excedentes limitada por el coste de la energía, hucha de excedentes (saldo en euros) y coste real del ciclo.
- Medida propia por horas a partir de tus sensores de energía (importación y exportación), con recuperación de huecos y reconstrucción desde las estadísticas de Home Assistant.
- Importación de los CSV horarios de la distribuidora (consumo por periodo y consumo facturado) y calibración de la pinza: factor y desfase por hora, con informe por meses.
- Precios con fecha de efecto (servicio `nueva_tarifa`), registro de facturas reales (`registrar_factura`) y sensores de precio, periodo, costes fijos acumulados y desfase.

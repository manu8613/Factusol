# Estado

Versión: v0.1.0 (sin publicar) · Rama: `feat/v0.1.0` · Actualizado: 2026-11-11

## Funciona (comprobado)
- Motor de facturación 2.0TD: reproduce al céntimo dos facturas reales de autoconsumo con hucha (importe a pagar, ingreso en la hucha y saldo).
- Con un año de CSV horarios reales de la distribuidora (8.784 horas): neteo horario, periodos y festivos sin ninguna discrepancia; ambos formatos de CSV coinciden hora a hora, incluido el cambio de hora.
- 40 pruebas en Home Assistant 2026.10.4 / Python 3.14 y ruff en verde (asistente, opciones, medida en vivo, importación, calibración, factura real, tarifa con fecha, reconstrucción, costes fijos, descarga).
- Auditoría de dependencias de prueba: solo avisa Pillow 12.3.0 (fijada por Home Assistant, solo en el entorno de test; Factusol no tiene dependencias propias).

## Pendiente / por verificar
- Probar en una instalación real de Home Assistant (no hecho aún): asistente en la interfaz, entidades, panel de Energía y `reconstruir_historial` con el recorder real.
- CI de GitHub sin ejecutar todavía (hassfest y validación HACS solo corren en GitHub). Las versiones de las acciones se copiaron de gas-tur y no se han podido contrastar con las últimas publicadas: Dependabot las propondrá.
- Proyección a fin de ciclo, panel propio, otras tarifas (3.0TD) y varios contratos.

## Últimos cierres
<!-- Pegar aquí el bloque CIERRE de cada tarea (ver CLAUDE.md). Conservar solo los 5 últimos. -->

### 2026-11-11 · Primera versión
- Proyecto: Factusol · Repo/rama: manu8613/Factusol · `feat/v0.1.0`
- Objetivo: integración que calcule sola la factura de luz, lleve la hucha y calibre la pinza contra el contador oficial.
- Cambios: motor, libro de horas, importador, calibración, gestor, asistente, 24 sensores, 4 números, 7 servicios, traducciones es/en, CI y documentación.
- Pruebas: 40 en verde (HA 2026.10.4, Python 3.14) + prueba con CSV reales fuera del repo.
- Resultado verificado: agosto y septiembre cuadran al céntimo con sus facturas.
- Pendientes: ver arriba. Próximo paso: configurarla en la instalación real y migrar las plantillas actuales.

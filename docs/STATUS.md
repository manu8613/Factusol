# Estado

Versión: v0.1.1 (rama `feat/v0.1.1`, en PR) · Publicada: v0.1.0 (`a6036d5`) · Actualizado: 2026-11-11

## Funciona (comprobado)
- Motor de facturación 2.0TD: reproduce al céntimo dos facturas reales de autoconsumo con hucha (importe a pagar, ingreso en la hucha y saldo).
- Con un año de CSV horarios reales de la distribuidora (8.784 horas): neteo horario, periodos y festivos sin ninguna discrepancia; ambos formatos de CSV coinciden hora a hora, incluido el cambio de hora.
- 43 pruebas en Home Assistant 2026.10.4 / Python 3.14 y ruff en verde (asistente, opciones, medida en vivo, importación, calibración, factura real, tarifa con fecha, reconstrucción, costes fijos, descarga).
- Auditoría de dependencias de prueba: solo avisa Pillow 12.3.0 (fijada por Home Assistant, solo en el entorno de test; Factusol no tiene dependencias propias).

## Pendiente / por verificar
- Probado en una instalación real (v0.1.0): alta con el asistente, 28 entidades, periodo y precios correctos, sin tocar plantillas ni panel de Energía. Falta probar en real la importación de CSV (v0.1.1), `reconstruir_historial` con el recorder y `calibrar`.
- CI de GitHub sin ejecutar todavía (hassfest y validación HACS solo corren en GitHub). Las versiones de las acciones se copiaron de gas-tur y no se han podido contrastar con las últimas publicadas: Dependabot las propondrá.
- Proyección a fin de ciclo, panel propio, otras tarifas (3.0TD) y varios contratos.

## Últimos cierres
<!-- Pegar aquí el bloque CIERRE de cada tarea (ver CLAUDE.md). Conservar solo los 5 últimos. -->

### 2026-11-11 · v0.1.1 importación por contenido
- Proyecto: Factusol · Repo/rama: manu8613/Factusol · `feat/v0.1.1`
- Objetivo: poder cargar los CSV de la distribuidora desde un script en el PC, sin copiar ficheros a Home Assistant.
- Cambios: `importar_datos_distribuidora` acepta `contenido` (o `ruta`, exclusivos, máx. 8 MB); traducciones, README, CHANGELOG, versión 0.1.1.
- Pruebas: 43 en verde (3 nuevas: contenido válido, origen único, contenido inválido o enorme) y ruff limpio.
- Resultado verificado: en entorno de pruebas; pendiente en la instalación real.
- Pendientes: ver arriba. Próximo paso: script de carga (CSV, historial, calibración).

### 2026-11-11 · Primera versión
- Proyecto: Factusol · Repo/rama: manu8613/Factusol · `feat/v0.1.0`
- Objetivo: integración que calcule sola la factura de luz, lleve la hucha y calibre la pinza contra el contador oficial.
- Cambios: motor, libro de horas, importador, calibración, gestor, asistente, 24 sensores, 4 números, 7 servicios, traducciones es/en, CI y documentación.
- Pruebas: 40 en verde (HA 2026.10.4, Python 3.14) + prueba con CSV reales fuera del repo.
- Resultado verificado: agosto y septiembre cuadran al céntimo con sus facturas.
- Pendientes: ver arriba. Próximo paso: configurarla en la instalación real y migrar las plantillas actuales.

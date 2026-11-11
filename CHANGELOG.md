# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · Versiones: [SemVer](https://semver.org/lang/es/).

## [0.2.1] - 2026-11-11
- El historial de facturas incluye también las facturas registradas anteriores al saldo inicial de la hucha (antes se guardaban pero no se veían).

## [0.2.0] - 2026-11-11
- Nuevo servicio `importar_factura_pdf`: lee una factura de luz en PDF (formato con hucha de excedentes) recibida en base64, extrae el periodo, los kWh por tramo, los excedentes, el total, la hucha aplicada, el ingreso y el saldo, y la registra. El PDF solo vive en memoria durante la llamada: no se guarda y del texto solo se conservan cifras. Comprueba que las cifras cuadran entre sí y, si los precios de la factura difieren de los guardados, crea una tarifa nueva desde el primer día del periodo (`actualizar_tarifa`).
- Los ciclos pueden seguir los días reales de cada factura: `registrar_factura` admite `fecha_inicio`, y el ciclo dura exactamente lo que cobró la factura; el siguiente empieza al día siguiente.
- Nueva dependencia: `pypdf>=6.21.4` (Python puro; límites de 5 MB y 12 páginas por PDF).

## [0.1.2] - 2026-11-11
- Icono y logo propios (Home Assistant 2026.3 o posterior los toma de `brand/`): un sol que sale por detrás de una factura, con un rayo y el símbolo del euro. Dibujo original, sin marcas ni personajes.

## [0.1.1] - 2026-11-11
- `importar_datos_distribuidora` acepta el texto del CSV en `contenido` como alternativa a `ruta`, para cargar los datos de la distribuidora desde un script sin copiar ficheros a Home Assistant (máximo 8 MB; se indica una de las dos opciones).

## [0.1.0] - 2026-11-11
- Primera versión: factura de luz 2.0TD calculada como la real, con neteo horario consumo/excedente, compensación de excedentes limitada por el coste de la energía, hucha de excedentes (saldo en euros) y coste real del ciclo.
- Medida propia por horas a partir de tus sensores de energía (importación y exportación), con recuperación de huecos y reconstrucción desde las estadísticas de Home Assistant.
- Importación de los CSV horarios de la distribuidora (consumo por periodo y consumo facturado) y calibración de la pinza: factor y desfase por hora, con informe por meses.
- Precios con fecha de efecto (servicio `nueva_tarifa`), registro de facturas reales (`registrar_factura`) y sensores de precio, periodo, costes fijos acumulados y desfase.

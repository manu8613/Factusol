# Factusol

**Factura de luz 2.0TD al céntimo en Home Assistant: neteo horario, excedentes, hucha y calibración de tu pinza.**

*Computes a Spanish 2.0TD electricity bill the way the retailer does (hourly netting of consumption and surplus, capped surplus compensation, euro surplus balance) from your own energy sensors, and calibrates your clamp against the distributor's official hourly data.*

Con tu pinza (o el medidor que ya tengas en Home Assistant) y esta integración tienes:

- La **factura del ciclo en curso** calculada como la real, línea a línea: potencia, energía por periodo, compensación de excedentes, bono social, impuesto eléctrico, alquiler, IVA.
- El **neteo horario**: en cada hora solo cuenta el saldo (consumo − excedente), que es como se factura. Con solar eso cambia mucho el resultado respecto a sumar kWh sueltos.
- La **hucha de excedentes**: lo que no se compensa se guarda en euros y se descuenta de las siguientes facturas. Factusol lleva el saldo y te da el **coste real** del mes (lo que habrías pagado menos lo que has guardado).
- La **calibración de la pinza**: importas los CSV horarios que descarga la distribuidora, Factusol compara hora a hora con tu medida y calcula el factor y el desfase. Los meses con dato oficial se facturan con el dato oficial.
- Tus **estadísticas conservadas**: no toca tus sensores; puede reconstruir el libro de horas desde las estadísticas que Home Assistant ya tiene.

## Instalación

[![Abrir en HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=manu8613&repository=Factusol&category=integration)

1. **HACS → ⋮ → Repositorios personalizados**, añade `https://github.com/manu8613/Factusol` con categoría **Integración** e instala **Factusol**.
2. Reinicia Home Assistant.
3. **Ajustes → Dispositivos y servicios → Añadir integración → Factusol**.

## Configuración

El asistente pide cuatro pasos. Los valores por defecto son un ejemplo de contrato doméstico: **cámbialos por los de tu factura**.

| Paso | Qué poner |
|---|---|
| Origen de los datos | Sensor de **energía importada** (kWh acumulados que compras a la red) y, si tienes solar, el de **energía exportada**. Día en que empieza tu ciclo de facturación (1 si es mes natural) y festivos extra si tu contrato los cuenta como valle. |
| Precios | Potencia contratada en punta y valle, precio de la potencia (€/kW·día), precio de la energía por periodo (€/kWh) y precio de compensación de excedentes (€/kWh). |
| Cargos e impuestos | Bono social (€/día), alquiler de equipos (€/día), otros servicios, impuesto eléctrico (%), mínimo (€/MWh) e IVA (%). |
| Hucha | Si tienes hucha, su **saldo y la fecha** a la que corresponde (el último día del periodo de tu última factura). |

Todo se puede cambiar después en **Configurar**. Los precios de ese menú editan la tarifa vigente; para un cambio de precios **con fecha** usa el servicio `factusol.nueva_tarifa`: la tarifa anterior sigue valiendo hasta ese día y el ciclo se reparte por días.

### Cómo se calcula

```
potencia + (energía − compensación) + bono social      → base del impuesto eléctrico
+ impuesto eléctrico + servicios (alquiler…)            → base del IVA
+ IVA                                                   → total bruto  (factura estimada)
− hucha aplicada                                        → total a pagar
coste real = total bruto − lo que se ingresa en la hucha este ciclo
```

- La compensación de excedentes está **limitada por el coste de la energía** del ciclo; el sobrante va a la hucha al mismo precio.
- La hucha aplicada es el menor de su saldo anterior y el total bruto.
- Periodos 2.0TD: valle de 0 a 8 h y todo el día en fines de semana y festivos nacionales de fecha fija; llano 8-10, 14-18 y 22-24 h; punta 10-14 y 18-22 h. Los cambios de hora se tratan por hora absoluta.
- Cada línea se redondea a céntimos y las bases suman líneas ya redondeadas, como en la factura.

## Calibrar la pinza con los datos de la distribuidora

1. Descarga de la oficina virtual de tu distribuidora el CSV horario (**consumo por periodo**, con consumo y generación) y, si quieres, el de **consumo facturado**.
2. Copia los ficheros a la carpeta `factusol` dentro de tu carpeta de configuración (Factusol la crea al arrancar).
3. **Herramientas para desarrolladores → Acciones → `factusol.importar_datos_distribuidora`** con el nombre del fichero. Las horas oficiales sustituyen a las propias en la factura. Como alternativa a la ruta puedes pasar el texto del CSV en `contenido` (para cargarlo desde un script sin copiar ficheros; máximo 8 MB; indica `ruta` o `contenido`, no ambos).
4. Si Home Assistant ya tenía estadísticas de tus sensores de antes de instalar Factusol, ejecuta `factusol.reconstruir_historial` con la fecha de inicio: rellena las horas que faltan.
5. `factusol.calibrar` compara hora a hora y devuelve, para importación y exportación, el **desfase en %**, el factor de escala, el desfase por hora y el R². Con `aplicar: true` lo guarda en las entidades **Factor** y **Desfase** de Factusol (se pueden editar a mano). Los sensores *Desfase de importación/exportación* muestran el resultado y el detalle por meses.

El dato oficial suele tardar uno o dos días: las horas sin dato oficial se calculan con tu pinza corregida y el sensor de factura indica cuántas horas son oficiales, propias y cuántas faltan.

## Registrar una factura real

Cuando llegue la factura, `factusol.registrar_factura` guarda sus importes (total bruto, hucha aplicada, importe almacenado, saldo final y kWh). Sustituyen a la estimación de ese ciclo, fijan el saldo de la hucha para los siguientes y el servicio devuelve la desviación entre lo estimado y lo real.

## Panel de Energía

En **Ajustes → Paneles → Energía**:

- **Consumo de red** → tu sensor de importación, con **Utilizar una entidad con el precio actual** → *Precio de la energía con impuestos*.
- **Retorno a la red** → tu sensor de exportación, con *Precio de compensación de excedentes*.
- Para los **costes fijos**, añade otra fuente de consumo de red con *Energía de costes fijos* (siempre 0 kWh) y **Utilizar una entidad que rastree el coste total** → *Costes fijos acumulados*.

## Conservar tus estadísticas al sustituir plantillas anteriores

Si ya calculabas el precio con ayudantes de plantilla, puedes mantener su historial:

1. Apunta el valor actual del sensor antiguo y haz una copia de seguridad.
2. Elimina el ayudante antiguo (su historial queda en la base de datos).
3. **Ajustes → Entidades**, abre la entidad equivalente de Factusol y cambia su **ID de entidad** por el del sensor antiguo. Home Assistant avisa de que no puede renombrar las estadísticas porque el ID ya existe: es lo esperado, la entidad pasa a escribir en las antiguas.
4. Para los costes fijos acumulados, ejecuta `factusol.ajustar_costes_fijos` con el último valor del sensor antiguo.
5. En **Herramientas → Estadísticas**, borra las estadísticas sueltas del ID original si aparecen.

Las unidades y clases deben coincidir (euros, kWh, mismo tipo de estado).

## Entidades

| Entidad | Qué es |
|---|---|
| Periodo tarifario | `punta`, `llano` o `valle` ahora mismo (útil para automatizaciones). |
| Precio de la energía con impuestos / de compensación | €/kWh vigentes. |
| Consumo punta / llano / valle / neto, Excedentes netos | kWh netos por horas del ciclo en curso. |
| Factura estimada | Total bruto del ciclo hasta ahora; los atributos traen todas las líneas, las horas oficiales, propias y sin datos. |
| Hucha aplicada, Factura a pagar, Ingreso en la hucha, Coste real | Resultado del ciclo en curso. |
| Saldo de la hucha previsto / facturado | Saldo al final del ciclo en curso y al cierre del último ciclo cerrado. |
| Factura / Coste real del ciclo anterior, Coste real del año | Para comparar. |
| Historial de facturas | Atributo `meses` con cada ciclo: estimado o real, total, hucha y coste real. |
| Costes fijos acumulados, Energía de costes fijos | Para el panel de Energía. |
| Desfase de importación / exportación, Último dato oficial | Calibración. |
| Factor y desfase (importación/exportación) | Valores editables de la corrección. |

## Servicios

`nueva_tarifa` · `importar_datos_distribuidora` · `calibrar` · `reconstruir_historial` · `registrar_factura` · `ajustar_hucha` · `ajustar_costes_fijos`

## Límites de la versión 0.1

- Solo tarifa 2.0TD (tres periodos de energía y dos de potencia) y un contrato por instalación.
- El ciclo en curso se factura **hasta ahora** (días transcurridos y energía acumulada); aún no hay proyección a fin de ciclo.
- No crea panel propio: los sensores se pueden usar en cualquier tarjeta.
- Los datos de la distribuidora se importan con un servicio; no se conecta a ninguna oficina virtual.

## Autor y licencia

Creado por [manu8613](https://github.com/manu8613). Licencia MIT.

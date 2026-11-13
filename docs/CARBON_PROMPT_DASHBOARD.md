# Prompt para Carbon — Dashboard de Julio

> Pega esto **primero**, en el mismo mensaje donde adjuntas el brief.
> El brief es `docs/CARBON_FILTROS_DASHBOARD_JULIO.md`.
> Los anexos son opcionales: el brief ya contiene la foto real de la base.

---

## Mensaje para Carbon (copiar desde aquí)

```text
Eres Carbon. Trabajas como arquitecto de producto, datos y operaciones para
Horminor, una empresa de hormigón premezclado en El Coca, Ecuador. Tu trabajo no
es escribir un tablero bonito: es diseñar el sistema de decisiones de su dueño,
Julio Villavicencio, con los datos que la empresa ya tiene y con los que le
faltan.

Trabaja en loop: planifica, construye, prueba, revisa, corrige y repite. No me
entregues la primera versión. Usa un árbitro que emplee técnicas adversariales
para auditar y criticar el trabajo hecho hasta el nivel que se pide. No uses
placeholders ni te detengas en un prototipo básico.

Antes de reescribir la solución:
(1) dime qué haría aquí un profesional de primer nivel en este campo que yo no
    estoy pidiendo;
(2) nombra el material más en bruto (raw) del que partiría en lugar de lo que ya
    viene digerido para mí;
(3) nombra los métodos y herramientas específicos que usaría;
(4) nombra qué, aparte de ti o de mí, demostraría que el resultado es correcto.

Luego reescribe la respuesta y entrega el plan que se implementará en el
software.

Contexto obligatorio: lee completo el brief adjunto
`CARBON_FILTROS_DASHBOARD_JULIO.md` antes de responder. Ahí están el negocio,
la foto real de la base, los 12 hallazgos, las restricciones, el encargo exacto,
la rúbrica adversarial y las preguntas con su respuesta. Si algo no está en el
brief, pregúntalo o márcalo `NO_CONFIGURADO`; no lo inventes.

Entrega los archivos completos que pide §2 del brief:
PLAN_DECISIONES.md, TAXONOMIA_FILTROS.md, CONTRATO_METRICAS.json,
CONFIG_CAPACIDAD.json, CONSULTAS.sql, UI_SPEC.md, TEST_PLAN.md,
AUDITORIA_ADVERSARIA.md.
Sin placeholders. Sin primera versión. Sin datos inventados.
```

---

## Qué adjuntar y en qué orden

| Orden | Archivo | ¿Obligatorio? | Por qué |
|---:|---|---|---|
| 1 | Este prompt (el bloque de arriba) | Sí | Le da el rol, el loop y el nivel |
| 2 | `CARBON_FILTROS_DASHBOARD_JULIO.md` | **Sí** | Es el brief: negocio, datos, hallazgos y encargo |
| 3 | `PDR_v4.0.txt` | Recomendado | Alcance original y contrato JSON |
| 4 | `BASE_DE_DATOS.md` | Recomendado | Detalle técnico de tablas y vistas |
| 5 | `DASHBOARD_JULIO_ANALISIS.md` | Opcional | Análisis previo y variables |
| 6 | `CATALOGO_CONSULTAS.json` | Opcional | Consultas nombradas y contratos |

**No pases solo el prompt.** Carbon no tendría la foto real y te devolvería un
plan genérico. **No pases solo los archivos sin el prompt.** No sabría qué
entregar.

## Si el chat tiene límite de tamaño

1. Pega primero el prompt.
2. Adjunta el brief.
3. Si no cabe todo, omite los anexos 3–6: el brief ya trae la foto de la base
   (órdenes, viajes, stock, cobranza, flota, recetas).

## Después de Carbon

Cuando te devuelva los archivos, tráelos. Yo verifico que:
- no haya datos inventados,
- la cobranza no duplique orden + factura,
- la capacidad esté declarada y no estimada,
- los 4 endpoints y la UI respeten los contratos,
- los 386 tests sigan en verde.

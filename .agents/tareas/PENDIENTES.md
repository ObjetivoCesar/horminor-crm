# Tareas pendientes por módulo

> **Vivo:** se actualiza, no se archiva. Cada tarea tiene criterio de cierre
> verificable. Si una tarea no tiene criterio, no está lista para empezar.
>
> Última actualización: 2026-11-13 (sesión de cotizaciones y contratos).

## 1. Dashboard operativo

| # | Tarea | Depende de | Criterio de cierre |
|---|---|---|---|
| D2 | Endpoint `GET /api/v1/dashboard/operacion` | 079 aplicada | Devuelve timeline de mixers con `fuente`, `consultado`, `filtros`, `vacio`; tests con caso vacío |
| D3 | Indicadores de cotizaciones abiertas y excedente | 080 | Pipeline y fuga de margen visibles sin pestaña nueva |

## 2. Cotizaciones

| # | Tarea | Depende de | Criterio de cierre |
|---|---|---|---|
| Q2 | Migración `080`: `cotizaciones`, `cotizacion_extras` (rubro global), `cotizacion_versiones`, `orden_extras`, `cliente_etiquetas`, `precio_estado` | Q1 cerrada | Esquema aplicado; precios semilla en `PROVISIONAL` |
| Q3 | API: alta, edición, envío, aceptación, conversión | Q2 | No se convierte una `VENCIDA`; aceptar asigna `VENTA`; activo no se edita |
| Q4 | PDF cliente e interno + WhatsApp + `media_assets` | Q3 | PDF con hash visible en la carpeta del cliente y `whatsapp_msg_id` guardado |
| Q5 | Gato: borrador, consulta y envío con ratificación | Q3 | Un mensaje + “sí” = PDF enviado; Gato no aprueba ni cambia precios |
| Q6 | Pestaña de cotizaciones en el panel | Q4 | Se crea y convierte sin salir del panel |
| Q7 | Cerrar en Superadmin qué precios son `OFICIAL` | Julio | Ningún precio `PROVISIONAL` puede emitir fuera de SANDBOX |

## 3. Contratos y horas extra

| # | Tarea | Depende de | Criterio de cierre |
|---|---|---|---|
| C1 | Revisión del texto legal con Julio y contadora | — | Contrato de suministro y de trabajo aprobados o corregidos |
| C2 | Migración `081`: `contratos`, `contrato_versiones`, `anticipos_salario`, `jornada_eventos`, settings | C1, Q2 | Esquema aplicado; salarios y tarifas `NULL` donde falta dato |
| C3 | API con firma exclusiva de Julio | C2 | Solo Julio pasa `BORRADOR → ACTIVO`; test de rechazo para Secretaría |
| C4 | PDF de contrato con hash | C3 | Un contrato de prueba con hash verificable |
| C5 | Horas extra desde Gato + barra en Ocupación | C2, D4 | Un mensaje + “sí” = `jornada_eventos`; se muestran horas sin tarifa si el contrato no la tiene |
| C6 | Lista de contratos en el panel | C4 | Secretaría prepara y descarga; Julio firma |

## 4. Cobranza e inventario (bloqueados por datos)

| # | Tarea | Depende de | Criterio de cierre |
|---|---|---|---|
| F1 | Capturar `fecha_vencimiento` en formularios de orden y factura | diseño de formularios | Documentos dejan de caer en `SIN_VENCIMIENTO` |
| F2 | Regla de imputación pago → documento | contadora | Aging por factura con saldo real, no con total del documento |
| F3 | Conteo físico de los 5 materiales | Bodega | `v_stock_proyectado` deja de decir `SIN_LEVANTAR` |

## 5. Deuda técnica registrada

| # | Tarea | Por qué importa | Criterio de cierre |
|---|---|---|---|
| T1 | Normalizar encoding en `ESTADO.md` y `BITACORA.md` | Hay texto con doble codificación (`PrÃ³ximo`) que se lee mal | Los dos archivos en UTF-8 sin secuencias `Ã`; contenido intacto |
| T2 | Revisar los tests del panel que dependen de textos del HTML | Cambiar pestañas puede romper asserts por cadena | `pytest` en verde después de D3 |
| T3 | Actualizar `AGENTS.md` §7 cuando una skill propuesta exista | Hoy lista 5 skills; el mapa de pilares propone 14 | La tabla coincide con `.agents/skills/` |

## 6. Preguntas abiertas (no se decide por Julio)

Cerradas el 2026-11-13:

- **Toda venta pasa primero por cotización.** La orden no nace suelta.
- **Precios en Superadmin** (`concrete_recipes.precio_m3`), hoy ficticios y
  marcados `PROVISIONAL`; Julio los dará después y serán variables.
- **IVA desglosado** en la cotización y la factura.
- **Contrato de trabajo: obra cierta.** Anticipos y saldo final.

Siguen abiertas:

1. ¿Qué umbral de excedente despachado debe avisar en el tablero?
2. ¿La lista de precios lleva un valor por resistencia o uno solo por planta?
3. Anticipos de salario: ¿porcentaje y forma de descuento?

Mientras no haya respuesta, el sistema deja el campo `NULL` y lo marca
`PENDIENTE`. No se rellena con un valor “razonable”.

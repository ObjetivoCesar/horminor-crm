# Tareas pendientes por módulo

> **Vivo:** se actualiza, no se archiva. Cada tarea tiene criterio de cierre
> verificable. Si una tarea no tiene criterio, no está lista para empezar.
>
> Última actualización: 2026-11-17 (multimedia de WhatsApp y Bunny por cliente;
> cierre del espejo v9.7 en el VPS).

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

## 6. Multimedia de WhatsApp (espejo v9.7)

> Alcance añadido por Julio el **2026-11-17**: recibir **audio, imagen, video,
> documento y sticker**, y acumular la media de cada cliente en su **carpeta
> independiente en Bunny.net**. W1 y W2 están hechos (2026-11-18): la media se
> descarga y se guarda en la carpeta del cliente en el sandbox local. Falta
> Bunny (W3) y el resto.

| # | Tarea | Depende de | Criterio de cierre |
|---|---|---|---|
| W1 | Recibir media entrante completa — ✅ **hecho 2026-11-18** | webhook del espejo | Un audio, una imagen y un video enviados desde el número autorizado quedan en `chat_mensajes.adjuntos` con su `whatsapp_media`, `mimetype`, tamaño y nombre; ninguno se pierde |
| W2 | Descarga real desde Evolution — ✅ **hecho 2026-11-18** | W1 | El espejo obtiene el binario (`base64`/`media` de Evolution) con timeout y reintento; un fallo se marca `pendiente_descarga` y **no** bloquea el texto |
| W3 | Carpeta independiente por cliente en Bunny - ok. **hecho 2026-11-18** | W2, credenciales Bunny | Ruta `clientes/<cliente_id>/<canal>/<aaaa-mm>/<mensaje_id>.<ext>`; dos clientes distintos nunca comparten prefijo; el prefijo se verifica con una subida real |
| W4 | Enlazar la media al expediente - ok. **hecho 2026-11-18** | W3 | El Chat muestra la imagen/audio/video desde la URL de Bunny y `v_chat_conversacion` devuelve la URL; el archivo se abre desde la carpeta del cliente |
| W5 | Multimedia saliente desde el CRM - ok. **hecho 2026-11-18** | W3 | Adjuntar desde el Chat sube a la carpeta del cliente y envía por Evolution con `whatsapp_msg_id` conciliado, sin duplicar |
| W6 | Cuota, formatos y retención | W3 | Límite por archivo y por cliente definido; formatos aceptados documentados; política de borrado/retención escrita antes de producción |

Criterio de cierre de la sección: con el número autorizado, enviar audio,
imagen y video desde el teléfono y verlos en la carpeta del cliente del CRM,
cada uno en la carpeta del cliente correcto de Bunny, sin duplicados y sin
afectar a otros números.

## 6.1 Chat en vivo (espejo v9.8)

| # | Tarea | Estado |
|---|---|---|
| S1 | Aviso SSE del espejo al panel (`BusEventos`, `/whatsapp/espejo/eventos`) | ✅ **hecho 2026-11-18** — verificado con el webhook real |
| S2 | Desplegar el cambio en el VPS | ✅ **hecho 2026-11-18** — SSE responde, Caddy sin buffering (38 ms), webhook llega al aviso |
| S3 | Si algún día hay varios workers, mover el fan-out a Redis | ⏳ sin fecha |
| S4 | Confirmación humana en el VPS: WhatsApp real al 0967491847 y verlo aparecer sin recargar | ⏳ pendiente (única comprobación que falta) |

## 7. Preguntas abiertas (no se decide por Julio)

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

## 8. Correo y avisos de cabecera

| # | Tarea | Depende de | Criterio de cierre |
|---|---|---|---|
| G1 | Conectar Gmail al CRM | credenciales OAuth de Julio | El icono de Gmail de la cabecera muestra el total de correos sin leer y abre la bandeja del cliente |
| G2 | Responder/citar mensajes de WhatsApp como en WhatsApp | - | Citar un mensaje desde el Chat, guardar `quoted_msg_id` y verlo en el telefono del cliente |
| G3 | Aviso sonoro o de escritorio al entrar un mensaje | G1/G2 | Con el panel abierto en otra pestana, entra un WhatsApp y se avisa sin recargar |
| G4 | Dictado por audio desde Gato | hecho 2026-11-19 | Micrófono en Gato → `app/voz` → Cerebro; la transcripción se muestra en el hilo |
| G5 | Confirmar y ejecutar desde Gato | G4 | Un "sí, confirma el encargo 1" en Gato ejecuta lo que el Cerebro ya tiene aprobado, con registro y sin doble ejecución |

## 9. Momento cero (Miau)

| # | Tarea | Estado |
|---|---|---|
| M1 | Ejecutor crear_cliente con ratificacion y auditoria | hecho 2026-11-18 |
| M2 | Carpeta del cliente (CRM + Bunny) como paso del alta | hecho 2026-11-18 |
| M3 | Manos en Bunny: listar, mover, renombrar y borrar con vista previa y enlaces de respaldo | hecho 2026-11-18 (sin auditoria persistente aun) |
| M4 | Lectores de contacto, ubicacion, cedula/RUC, reenviados y capturas | pendiente |
| M5 | Mover la multimedia al confirmar el alta | hecho 2026-11-18 (motor; falta enganchar el origen de archivos al borrador) |

| M6 | Paquete de archivos al borrador (vista previa y confirmacion) | hecho 2026-11-18 (API + boton en el laboratorio) |
| L1 | Migracion leads + lead_eventos + lead_reglas_caida | **hecho 2026-11-19** (096) |
| L2 | Reglas de caida por intencion (rechazo, competencia, precio, aplazamiento, silencio) | **hecho 2026-11-19**; reglas en `lead_reglas_caida` |
| L3 | Parametros de recontacto en system_settings (leads.recontacto_dias, leads.max_intentos) | creados en `NULL`; esperando a Julio |

## 10. Gato publico y agendamiento

| # | Tarea | Estado |
|---|---|---|
| P1 | Independizar el agendamiento: `citas` propia, sin tocar `dispatch_schedule` | **hecho 2026-11-19** (`docs/AGENDAMIENTO.md`) |
| P2 | Gato publico: revisar la skill antes de implementar | skill `.agents/skills/gato-publico/SKILL.md`; implementacion 2026-11-19 |
| P3 | Audio por Gato: reutilizar el componente de voz (`app/voz`), no duplicarlo | **hecho 2026-11-19** (`POST /api/v1/asistente/audio`) |

## 11. Acceso, correo y deuda

| # | Tarea | Estado |
|---|---|---|
| B1 | Login propio del CRM (hoy solo basic auth de Caddy) | pendiente |
| B2 | Actualizar Evolution / contenedor propio (el silencio de sesion se repite) | pendiente para la entrega |
| B3 | Backups programados y prueba de restauracion | pendiente |
| B4 | Decidir versionado del arbol del VPS | pendiente |
| B5 | Correr la suite completa en el VPS | pendiente |
| C1 | Responder/citar mensajes como WhatsApp | pendiente |
| C2 | Aviso sonoro o de escritorio | pendiente |
| C3 | Conectar Gmail | pendiente |
| C4 | Cuota y retencion de multimedia (W6) | pendiente |
| D1 | Limpiar documentos que contradigan el plan | pendiente |
| D2 | Normalizar encoding de ESTADO y BITACORA | pendiente |
| D3 | Probar restauracion de un backup | pendiente |
| E1-E4 | Decisiones de negocio (leads, precios, merma) | esperando a Julio |

| B6 | Vigilante de WhatsApp (cron + reinicio + estado) | hecho 2026-11-18 |
| B7 | Configurar canal de alerta del vigilante (Telegram o correo) | pendiente |

## 12. Núcleo comercial (H1)

| # | Tarea | Estado |
|---|---|---|
| N1 | Migración 096: `leads`, `lead_eventos`, `lead_reglas_caida`, `citas` | hecho 2026-11-19 |
| N2 | `app/tiempo.py` (fecha de Ecuador en una sola fuente) | hecho 2026-11-19 |
| N3 | API `/api/v1/comercial/*` (leads, respuesta, citas, disponibilidad) | hecho 2026-11-19 |
| N4 | UI de leads y citas en Secretaria (lista + alta + confirmar/cancelar) | hecho 2026-11-19 (basica) |
| N5 | Conectar los tres origenes (WhatsApp, Gato, panel) al mismo modulo: panel, Gato y WhatsApp | **hecho 2026-11-19** |
| N6 | Borrado de leads: no hay endpoint de baja fisica; se usa baja logica por estado (`CAIDO`/`CONVERTIDO`). La cascada `lead_eventos ON DELETE CASCADE` queda documentada como deuda | **hecho como regla 2026-11-19** |
| N7 | Claves Groq en el `.env` del VPS y cascada principal/respaldo | hecho |
| N8 | Conectar WhatsApp (Gato publico) al modulo comercial: `ComercialWhatsApp` + parser compartido | **hecho 2026-11-19** |
| N9 | Auditoria de citas (`cita_eventos`) y maquina de estados | **hecho 2026-11-19** |
| N10 | Desplegar migraciones 096-097 y el cierre H1 en el VPS | **hecho 2026-11-19** (097 aplicada, imagen reconstruida, 26 pruebas H1 y `[H1 COMERCIAL: OK]` en el servidor) |

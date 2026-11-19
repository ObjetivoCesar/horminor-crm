# Momento cero — cómo Julio trae la información de un cliente

> **Qué es.** El momento en que se contrata un cliente y se trae "toda la
> infraestructura": Julio manda audios, videos, fotos, documentos, ubicaciones,
> contactos o enlaces, y pide que queden registrados en el cliente X.
>
> **Para qué sirve este documento.** Para que cualquiera pueda **extender** el
> momento cero con una entrada nueva (un formato, un dato, una fuente) sin leer
> todo el proyecto. Es el contrato del área, no un manual de uso.
>
> **Dueño del tema:** este archivo. Si algo cambia, se actualiza aquí y se borra
> lo que dejó de ser cierto.
>
> **Fecha:** 2026-11-18.

---

## 1. Principio

1. **Nada se escribe sin ratificación humana.** El sistema propone un paquete;
   Julio (o quien tenga el rol) lo aprueba con el "pasito".
2. **Ningún dato sin cita.** Cada hecho apunta al fragmento del audio, texto o
   archivo que lo sostiene.
3. **Nada se inventa.** Lo que falta queda `NULL` y se pregunta.
4. **La IA no calcula dinero.** Montos y saldos se registran con doble
   confirmación y por el módulo dueño.
5. **Todo se audita.** `cerebro_ejecuciones` guarda qué se ejecutó, con qué
   parámetros y qué entidad se creó.

---

## 2. Catálogo de entradas (v1)

| Entrada | Ejemplo | Qué produce | Estado |
|---|---|---|---|
| Texto / dictado | "Registra esto en el cliente Reyes" | Hechos citados + acciones | Funciona |
| Audio / nota de voz | Audio de 122 s | Transcripción + hechos citados | Funciona (voz) |
| Imagen / foto | Foto de la obra o de una cédula | Adjunto + clasificación | Funciona (media) |
| Video | Recorrido o avance de obra | Adjunto + clasificación | Funciona (media) |
| Documento | PDF, Word, Excel | Adjunto `DOCUMENTO` | Funciona (media) |
| Ubicación | Pin de WhatsApp o GPS | Dato `ubicacion.*` + pin | Parcial |
| Contacto | Tarjeta vCard | Datos de contacto del cliente | Pendiente |
| Enlace | URL de Drive, mapa o cotización | Texto + referencia | Funciona como texto |
| Reenviado de WhatsApp | Mensaje hacia adelante | Texto + contexto | Pendiente |
| Captura de pantalla | Chat o comprobante | Imagen + lectura | Pendiente |
| Cédula / RUC en foto | Documento de identidad | `cliente.cedula` / `cliente.ruc` | Pendiente |
| Comprobante bancario | Transferencia | Pago propuesto (nunca automático) | Pendiente |
| Correo | Gmail (futuro) | Hechos + adjuntos | Futuro |

**Regla:** esta tabla es el inventario. Si una entrada no está aquí, no existe
todavía.

---

## 3. El pipeline canónico

```
entrada
  → 1. recibir y guardar el original (hash, canal, remitente)
  → 2. normalizar (texto, unidades, fechas, teléfonos)
  → 3. extraer hechos con cita
  → 4. clasificar los adjuntos (tipo, cliente, carpeta)
  → 5. armar el paquete de alta (cliente + carpetas + archivos)
  → 6. RATIFICAR (el pasito humano)
  → 7. ejecutar por el módulo dueño
  → 8. auditar y devolver el resultado
```

El paquete de alta es siempre el mismo, aunque la entrada cambie:
`cliente` + `carpeta CRM` + `carpeta Bunny` + `archivos clasificados`.

---

## 4. Cómo extender sin leer todo el proyecto

Para agregar una entrada nueva:

1. **Descriptor:** define `tipo_entrada` (mime, extensión, canal).
2. **Normalizador:** una función que devuelva texto + metadatos; sin tocar el
   compilador.
3. **Mapa de hechos:** a qué clave canónica alimenta (`cliente.*`,
   `cotizacion.*`, `ubicacion.*`, ...), con su cita.
4. **Clasificador de adjuntos:** tipo de media y carpeta destino.
5. **Pruebas:** un fixture real anonimizado y la prueba de que no inventa.
6. **Documentación:** añade la fila en la tabla §2 y, si es visible, la entrada
   en `docs/HORMINOR_MANUAL_FUNCIONAL.md`.

**No cambies el núcleo** salvo que aparezca una clave de hecho nueva. Si la
entrada no encaja en el pipeline, el problema es el contrato, no el código:
discútelo antes de programar.

---

## 5. Qué existe hoy y qué falta

- **Existe:** ingesta de texto y audio, hechos citados, borradores versionados,
  tareas internas, media entrante al chat, el ejecutor `crear_cliente` con
  ratificación, la **carpeta del cliente en Bunny** con su manifiesto
  `_momento_cero.json`, y las **manos** para listar, mover, renombrar y borrar
  con vista previa y enlaces (2026-11-18).
- **Falta:** mover la multimedia al confirmar el alta, lectura de contactos,
  ubicaciones, cédula/RUC en foto, reenviados y capturas; auditoría persistente
  de las operaciones de Bunny; y el flujo público de WhatsApp (Gato).

---

## 6. Checklist para una sesión nueva

- [ ] ¿La entrada que voy a agregar ya está en la tabla §2?
- [ ] ¿Necesito una clave de hecho nueva o reutilizo una?
- [ ] ¿La ratificación sigue siendo humana?
- [ ] ¿Qué pasa si el cliente ya existe?
- [ ] ¿Qué documento actualizo y qué documento borro?

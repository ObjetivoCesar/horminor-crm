# Traspaso al chat de dirección — Hito 3 (Módulo 1 WhatsApp)

> **Cómo usar este archivo:** copiar desde el título hasta el final y pegarlo en
> el chat que guía el proyecto (Nohan / Abel), o subirlo como adjunto. Está
> escrito para que ese chat pueda decidir sin volver a preguntar el contexto.

---

## 1. Estado en una línea

**Hito 3 construido y verificado en local.** El Módulo 1 (WhatsApp con debounce
de 14 s, Juez Binario "Jeb" y evidencia en Bunny.net) ejecuta las cuatro
compuertas contra PostgreSQL real. El candado está **abierto solo por falta de
credenciales y teléfonos reales**, no por falta de código.

Repositorio: `https://github.com/CesarReyesJaramillo/horinor`

## 2. Qué está hecho y con qué evidencia

| Pieza | Qué hace | Evidencia real |
|---|---|---|
| Webhook de Evolution | Normaliza texto, imágenes y grupos; ignora ecos del bot | tests unitarios |
| Debounce de 14 s | Agrupa los mensajes del mismo remitente en un lote; si Redis falla, cae a memoria | candado Hito 3 |
| Identidad | Número registrado > código de operador (`#BODEGA`, `#CAJA`, `#ADMIN`, `#M<n>`) > lead | candado Hito 3 |
| Juez "Jeb" | Contrato estricto `{cumple, codigo_accion, confianza, datos_extraidos}`; Gemini Flash con JSON forzado y fallback determinístico | tests unitarios |
| Gate #1 despacho | Bodega confirma salida → `EN_RUTA` + límite térmico + aviso al cliente | 8 aserciones `[OK]` |
| Gate #2 cliente | Sella `CONFIRMADO_CLIENTE`; si hay reclamo, `INCIDENCIA_RECLAMO` y alerta | 7 aserciones `[OK]` |
| Gate #3 evidencia | Sube adjuntos a Bunny y guarda la URL en el contrato JSONB | 3 aserciones `[OK]` |
| Gate #4 lead | Crea prospecto sin duplicar; no toca ventas | tests unitarios |
| Centinela | 12 checks, incluido `recetas_provisionales` y dos bandas térmicas | `daily-audit` 77.3 ms |

**Comandos reproducibles:**

```powershell
# 134 tests (los 33 originales siguen intactos)
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# candado del Hito 3: 28 verificaciones contra PostgreSQL real
docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py

# candado del Hito 1: sin regresión
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py
```

Resultados registrados en `.agents/evidencias/`:
`hito3_pytest.txt`, `hito3_lock.txt`, `hito1_lock_post_hito3.txt`,
`hito3_centinela.json`, `hito3_whatsapp_health.json`.

## 3. Ajustes que ustedes ratificaron (ya implementados)

1. **Receta PROVISIONAL no bloquea la venta.** La orden se crea, el viaje
   declara `"receta_provisional": true` y el Centinela lo reporta como `WARN`.
   No se genera kardex teórico hasta que la receta esté validada.
2. **Dos umbrales térmicos** sobre el límite de 150 min:
   - `ALERTA_TEMPRANA` a los 60 min antes (minuto 90) → `WARN`.
   - `POR_VENCER_CRITICO` a los 30 min antes (minuto 120) → `CRÍTICO`.
3. **Identidad de WhatsApp:** primaria por número registrado; fallback por
   código en el texto. Un desconocido es lead, no personal.
4. **Facturación electrónica SRI:** fuera de alcance, no se implementa.
5. **Claves:** `SENTINEL_MASTER_KEY` gana sobre `AGENCY_MASTER_KEY`;
   `AGENCY_CRM_WEBHOOK_URL` vacío ⇒ la alerta queda `NO_CONFIGURADO` en
   `error_logs`, sin fingir el envío.

## 4. Lo que falta para cerrar el Hito 3

| # | Dato | Quién lo entrega | Dónde se carga |
|---|---|---|---|
| 1 | URL, instancia y API key de Evolution API | Agencia / Julio | `.env`: `EVOLUTION_URL`, `EVOLUTION_INSTANCE`, `EVOLUTION_API_KEY` |
| 2 | Storage Zone, host CDN y API key de Bunny.net | Agencia / Julio | `.env`: `BUNNY_STORAGE_ZONE`, `BUNNY_STORAGE_API_KEY`, `BUNNY_CDN_HOST` |
| 3 | API key de Gemini | Agencia | `.env`: `GEMINI_API_KEY` (sin ella usa el juez determinístico) |
| 4 | Teléfonos reales del personal | Julio | `system_settings['whatsapp.staff']` (teléfono → rol) |
| 5 | Número corporativo de WhatsApp | Julio | `system_settings['whatsapp.numero_corporativo']` |

**No se inventó ninguno de estos datos.** Mientras falten, el sistema funciona
en local con juez determinístico y Bunny en memoria, y el Centinela reporta
`NO_CONFIGURADO`.

## 5. Bloqueo operativo (git)

El `git push` falla con **403** porque las credenciales de Windows pertenecen a
la cuenta `ObjetivoCesar`, que no tiene permiso sobre el repositorio. El commit
local queda hecho. Para publicar:

```powershell
git credential-manager logout https://github.com
git remote set-url origin https://CesarReyesJaramillo@github.com/CesarReyesJaramillo/horinor.git
git push -u origin main
```

## 6. Siguiente paso recomendado

1. **Publicar el repositorio** con las credenciales correctas.
2. **Entregar credenciales y teléfonos** de la tabla §4; con eso se repite el
   candado con servicios reales y se cierra el Hito 3.
3. **Insistir con Julio por las recetas** (FC-180/210/280/350): es lo único que
   bloquea el Hito 1 y el kardex real.
4. Después: decidir el stack del panel (Módulo 3) y las fórmulas del dashboard
   (Módulo 4).

## 7. Lo que NO está en este alcance

- Facturación electrónica SRI.
- Proxy inverso, TLS, backups y despliegue en VPS.
- Panel web (Módulo 3) y dashboard (Módulo 4).
- Datos de negocio inventados de cualquier tipo.

# Tarea — Cerebro y Voz (fases 0–4)

**Creada:** 2026-11-14
**Diseño:** `docs/CEREBRO_VOZ_DISENO.md`
**Brief de origen:** `docs/BRIEF_CEREBRO_VOZ.md`
**Estado:** Fases 0 y 1 cerradas. Fase 2 en curso: **alineación, hechos citados,
compilador, sobre, extractor, endpoints y adaptador Groq** (485 tests). Falta
persistencia de la confirmación/ejecución, UI y audio humano real.

## Reglas de ejecución

1. No se toca una migración aplicada: la 085 se escribe una vez y se corrige
   con la 086 si hace falta.
2. Cada fase cierra con `pytest` y, donde aplique, su propia prueba de
   comportamiento. Sin salida real no se marca la casilla.
3. Nada de datos de negocio en el código: topes, precios y textos viven en
   `system_settings` o `concrete_recipes`.
4. El Cerebro no ejecuta SQL de negocio: llama a los servicios existentes.
5. Si falta un dato, el borrador pregunta; no se rellena.

## Fase 0 — Extraer servicios (sin cambiar comportamiento) — **cerrada**

- [x] Extraer de `routers/cotizaciones.py` la función transaccional
      `crear_cotizacion_borrador(pool, datos, actor)` a
      `services/cotizaciones.py` (numeración, IVA con `Decimal`, versión 1,
      `cotizacion_eventos`).
- [x] El router `POST /api/v1/cotizaciones` pasa a llamar ese servicio.
- [x] Extraer el alta de cliente a `services/clients.py` (incluye
      `telefono_whatsapp` único y `cedula` única parcial).
- [x] Tests: los actuales siguen verdes; verificación en vivo de alta + PUT.
- [x] Salida: `pytest /app/tests` **439 passed** y el panel crea y edita igual.
      Evidencia: `.agents/evidencias/fase0_servicios_2026-11-14.txt`.

## Fase 1 — Migración 085 + `app/voz/` — **cerrada (sin proveedor real)**

- [x] `db/migrations/085_voz_cerebro.sql` con las 16 correcciones de la §2 del
      diseño.
- [x] Semilla de settings: `voz.enabled=false`, `cerebro.enabled=false`,
      `voz.max_duracion_seg=300`, `voz.cuota_usd_dia=null`,
      `whatsapp.mineria_usd_dia=null`.
- [x] Semilla de módulos `voz` y `cerebro` en los 5 perfiles (Julio en true).
- [x] `app/voz/ingesta.py`: valida MIME/tamaño, calcula SHA-256, guarda el
      audio (Bunny o `media_sandbox`), crea `voz_ingestas` y reutiliza la
      ingesta si el mismo audio se reenvía.
- [x] `app/voz/stt.py`: protocolo `ProveedorSTT` + degradación
      `DEGRADADO_SIN_CREDENCIAL` sin inventar texto.
- [x] `app/voz/normalizador_ec.py`: **hecho** (16 tests).
- [x] `POST /api/v1/voz/transcribir` y `GET /api/v1/voz/ingestas/{id}` con ACL
      de módulo `voz` y feature flag apagado por defecto.
- [x] Tests: audio falso, hash estable, degradación, límite de tamaño y MIME
      (445 en la suite).
- [x] Salida: audio guardado una sola vez, reintentos auditados, sin texto
      inventado. Evidencia: `.agents/evidencias/fase1_voz_2026-11-14.txt`.
- [x] **Adaptador Groq/Whisper** con palabras y tiempos
      (`app/voz/proveedores/groq.py`), probado con audio real.
- [ ] **Pendiente:** conversión `ogg/opus → wav/mp3` si el audio de WhatsApp
      falla en Groq. Se medirá con audios reales.

## Fase 2 — `app/cerebro/` + borradores

- [x] **Alineación primero:** `normalizar_ec` devuelve el mapa
      `token_normalizado → span_crudo → palabras STT` (offsets y tiempos).
      Implementado con `normalizar_con_mapa`, `localizar_palabras`,
      `alinear_con_palabras` y `alinear_secuencias`; 10 tests nuevos.
      Evidencia: `.agents/evidencias/fase2_alineacion_2026-11-14.txt`.
- [x] `app/cerebro/hechos.py`: AST de hechos citados (`valor`, `cita`,
      `span`, `ventana_ms`, `hablante`, `confianza`), validado con Pydantic.
      Evidencia: `.agents/evidencias/fase2_hechos_compilador_2026-11-14.txt`.
- [x] `app/cerebro/compilador.py`: convierte hechos en acciones y **falla** si
      no se cumplen los invariantes del dominio. No llama al LLM. 14 tests.
- [x] `app/cerebro/sobre.py`: contrato JSON del sobre
      (`intenciones_ordenadas`, `hechos`, `campos_faltantes`, `ambiguedades`).
- [x] `app/cerebro/extractor.py`: LLM con salida JSON validada; verificador
      determinístico de números/cédulas/fechas contra el texto y la base.
      Evidencia: `.agents/evidencias/fase2_audio_groq_2026-11-14.txt`.
- [x] `POST /api/v1/cerebro/interpretar` (texto o `transcripcion_id`) y
      `GET /api/v1/cerebro/borradores/{id}`, con persistencia en
      `cerebro_extracciones` y `cerebro_borradores`.
- [ ] `app/cerebro/borradores.py`: creación, corrección versionada, confirmación
      con `lock_version`, ejecución secuencial por `orden` y reintento por
      `intento_num`.
- [ ] Catálogo de 9 acciones con permisos reales (`rol_base` + módulo).
- [ ] UI: tarjeta de borrador con campos críticos primero, reproducción del
      fragmento dudoso y confirmación separada para dinero.
- [ ] `tests/cerebro/`: Caso A (4 acciones, sin escribir), Caso B (abono ≠
      traslado), Caso C (consulta, no crea orden), doble confirmación,
      corrección y reintento parcial.
- [ ] **Evaluación:** harness con `dev_set` / `held_out`, métricas por campo y
      cotas (no «100 %» con n chico); property-based tests del normalizador.
- [ ] **Modo sombra:** procesar sin escribir y reconciliar contra lo cargado a
      mano. Requiere decidir si se agrega un estado/columna (migración 086) o
      se usa un flag aparte.
- [ ] **PII:** redactor en logs/trazas para cédulas, teléfonos y nombres.
- [ ] Salida: los 3 casos producen borradores correctos y cero escrituras
      antes de confirmar; el held-out no se usa para escribir prompts.

## Fase 3 — Expediente y minería (bloqueada)

- [ ] Prerrequisito: M1 persiste entrantes de WhatsApp en `chat_mensajes`.
- [ ] `client_facts` + `client_fact_supersedes` + vista de hechos vigentes.
- [ ] `GET /api/v1/clients/{id}/expediente/timeline` con filtros.
- [ ] Worker de minería por lotes con cursor y tope diario.
- [ ] Salida: 5 clientes de prueba reconstruidos sin duplicar hechos.

## Fase 4 — Hardening

- [ ] Feature flags y cuotas reales.
- [ ] Métricas de costo por proveedor y latencia P95.
- [ ] Carga simulada + candados.

## Comandos

```powershell
docker compose up -d --build core-api
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto
docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py
```

## Evidencia de esta sesión

| Comando | Resultado |
|---|---|
| `pytest test_v85_voz_normalizador.py` | `16 passed` |
| `pytest /app/tests` | `439 passed`, exit 0 |

Archivo nuevo: `services/core-api/app/voz/normalizador_ec.py` y su test.

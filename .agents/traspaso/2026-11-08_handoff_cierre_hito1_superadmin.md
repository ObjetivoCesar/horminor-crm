# Traspaso al chat de dirección — Cierre Hito 1 + Superadmin

> **Cómo usar este archivo:** copiar desde el título hasta el final y pegarlo en
> el chat que guía el proyecto (Nohan / Abel), o subirlo como adjunto. Está
> escrito para decidir sin volver a preguntar el contexto.

---

## 1. Estado en una línea

**Hito 1 CERRADO.** Las 5 recetas oficiales quedaron confirmadas con la semilla
de Dirección, el kardex se genera y el candado terminó en `[CANDADO CERRADO]`.
Además, el **Centro de Configuración Superadmin** ya opera con 7 secciones
editables en caliente, y el Módulo 1 lee toda su configuración desde ahí.

Repositorio: `https://github.com/CesarReyesJaramillo/horinor`

## 2. Qué se cerró y con qué evidencia

| Pieza | Qué hace | Evidencia |
|---|---|---|
| Semilla oficial | FC-180/210/240/280/350 con sacos de 50 kg, precio/m³ sin IVA y uso comercial; `confirmado=true` | candado Hito 1 |
| Flota y política | `MIXER-01/02/03`; política `PARCIAL` (52 m³ → 6×8 + 4) | candado Hito 1 |
| Stock Planta Coca | cemento 3500/500/$8.20, arena 450/80/$14.00, ripio 550/100/$16.50, retardante 600/100/$3.80 | candado Hito 1 |
| Reloj térmico | `150` min; alertas a los `90` y `120` min | candado Hito 1/3 |
| Superadmin | 7 secciones + CRUD de recetas y flota, **sin login** en esta etapa | 23 tests + prueba HTTP real |
| Recarga en caliente | cambiar debounce o identidad se aplica sin reiniciar | evidencia `14 → 9 → 14` |
| Gate #4 | responde a leads con datos de la empresa y precios leídos de la BD; registra prospecto | candado Hito 3 |
| Centinela | 12 checks; `recetas_provisionales` ahora en `OK` | `daily-audit` |

**Comandos reproducibles:**

```powershell
# 157 tests (los 134 previos siguen intactos)
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# Hito 1: 17 [OK] y [CANDADO CERRADO]
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py

# Hito 3: 34 [OK], incluido el Gate #4 contra PostgreSQL real
docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py
```

## 3. Las 7 secciones del Superadmin

1. `formulas_y_precios` — CRUD de recetas, precio/m³, IVA y uso comercial.
2. `whatsapp_evolution_y_cdn` — Evolution, debounce y Bunny.
3. `empresa_bot_publico` — nombre, RUC, planta, cobertura, horario, planta
   móvil, bancos y servicios.
4. `flota_y_operacion` — mixers, política de último viaje y reloj térmico.
5. `directorio_roles_whatsapp` — teléfonos por rol y códigos PIN de fallback.
6. `bodega_y_umbrales` — stock, mínimos y costos por material/planta.
7. `finanzas_y_ases_gerenciales` — tope de crédito, simulador y benchmarks.

Endpoints:

```
GET  /api/v1/superadmin/config
GET  /api/v1/superadmin/config/{seccion}
PUT  /api/v1/superadmin/config/{seccion}
CRUD /api/v1/superadmin/recetas
CRUD /api/v1/superadmin/flota
```

## 4. Decisiones tomadas (para no re-discutirlas)

- **Sin login en Superadmin/Secretaría por ahora.** Se desacopla para el final
  para no frenar el Frontend. Riesgo: no exponer esas rutas a Internet todavía.
- **Todo dato de negocio vive en PostgreSQL.** El código no contiene precios,
  teléfonos ni recetas.
- **El bot no calcula ni inventa.** Gemini solo decide SÍ/NO; el texto y los
  precios salen de la base. Si un dato no existe, la línea se omite.
- **Precio base sin IVA.** El IVA (15%) es una columna editable y el Frontend
  decide cuándo mostrarlo.
- **La semilla es punto de partida, no camisa de fuerza.** Todo se edita desde
  el Superadmin.

## 5. Lo que sigue pendiente (solo datos y accesos)

1. **Credenciales reales** de Evolution API, Bunny.net y Gemini.
2. **Teléfonos del personal** para `whatsapp.staff` y sus roles.
3. **Datos que Julio no entregó:** RUC, horario, cuentas bancarias, placas,
   choferes y tope de crédito automático. Quedan `NULL`/vacíos a propósito.
4. **Frontend** del Centro de Configuración (consumir los endpoints ya listos).
5. **`git push`**: las credenciales de Windows son de `ObjetivoCesar`, sin
   permiso sobre `CesarReyesJaramillo/horinor`. El commit local sí está hecho.

## 6. Próximo paso exacto

1. Corregir credenciales de git y hacer `git push`.
2. Entregar credenciales de Evolution/Bunny/Gemini y los teléfonos del personal.
3. Cargarlos desde el Superadmin y repetir `hito3_lock_test.py` con servicios
   reales para cerrar el Hito 3.
4. Arrancar el Frontend del panel con los endpoints de la sección 3.

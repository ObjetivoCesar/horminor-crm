# Bancos: estado, columnas y preguntas abiertas (v6.11)

> Última actualización: **2026-11-12**.
> Documento de traspaso para una conversación nueva. Responde tres preguntas:
> qué columnas existen, si el cierre de caja menciona el banco y dónde se
> configuran las cuentas. **No se inventan saldos ni números.**

---

## 1. Qué está implementado hoy

- Migración `072_bancos_detalle.sql`: tabla `bank_accounts` con Pichincha,
  Guayaquil e Internacional; cuentas contables hijas `1102.01`, `1102.02` y
  `1102.03`; `financial_liabilities.bank_account_id`.
- `GET /api/v1/dashboard/bancos` → catálogo con saldo contable y resumen.
- `GET /api/v1/dashboard/bancos/{slug}` → detalle con saldo, préstamos y movimientos.
- `PUT /api/v1/dashboard/bancos/{slug}` → edita número, tipo, estado, titular, notas y saldo informado (ACL `finanzas_balance_auditoria`).
- UI: tarjeta activa en amarillo, detalle debajo y diálogo **Editar datos**.
- Saldo contable desde `v_balance_general`; saldo informado manual; préstamos
  desde `financial_liabilities`; movimientos desde `payments` con
  `account_id` = cuenta hija del banco.

---

## 2. Columnas: qué hay y qué falta

### 2.1 Tarjetas de la cabecera

| Dato | Fuente |
|---|---|
| Logo del banco | `static/brand/bancos/` |
| Nombre | `bank_accounts.nombre` |
| Tipo y número | `tipo_cuenta` + `numero_cuenta` (enmascarado) |
| Estado | `estado` + si el número tiene `X` se muestra “Provisional” |

### 2.2 Panel de detalle

| Bloque | Columnas |
|---|---|
| Cuenta | tipo, número, titular, estado |
| KPIs | saldo contable, saldo informado, entradas, salidas, préstamos, movimientos |
| Préstamos | operación, entidad, saldo de capital, tasa, cuota, plazo, pagos |
| Movimientos | fecha, tipo, método, monto, referencia, cliente, orden |

### 2.3 Tabla `bank_accounts`

`id`, `slug`, `nombre`, `tipo_cuenta`, `numero_cuenta`, `titular`, `moneda`,
`accounting_account_id`, `saldo_informado`, `saldo_informado_at`, `estado`,
`notas`, `metadata`, `created_at`, `updated_at`.

### 2.4 Previsto pero **no** implementado

1. **Selector de banco en el pago** y en el cierre: hoy no existe.
2. **Cierre de caja por banco**: ver §3.
3. **Transferencias entre bancos** (asiento doble y UI): no modelado.
4. **Conciliación bancaria** (extracto vs libro): no modelada.
5. **Historial del saldo informado**: solo se guarda el último valor y su fecha.
6. **Saldo disponible / sobregiro / línea de crédito**: no modelado.
7. **Carga de extractos** (CSV/OFX): no existe.
8. **Sección de configuración de bancos en Superadmin**: no existe.

---

## 3. ¿El cierre de caja menciona a qué banco se guarda?

**No.** Hoy el cierre distingue **método** (`EFECTIVO`, `TRANSFERENCIA`,
`FIADO`) y **bolsa** (`CAJA_DIARIA`, `BANCO_GERENCIA`), pero **no un banco
concreto**.

Evidencia:

- `cash_closures` no tiene `bank_account_id` ni columna por banco. Columnas:
  `fecha`, `estado`, `efectivo_sistema`, `efectivo_contado`, `transferencias`,
  `fiado_otorgado`, `caja_chica`, `diferencia`, `snapshot`, `cerrado_por`,
  `cerrado_at`.
- `calcular_resumen_caja()` suma `cobros` por método y `caja_chica`; no agrupa
  por cuenta bancaria.
- `_movimientos()` selecciona `id`, `order_id`, `cliente_id`, `fecha`,
  `tipo_movimiento`, `metodo`, `monto`, `referencia`, `created_at`; **no**
  selecciona `account_id` ni `bolsa`.
- `payments` sí tiene `account_id` y `bolsa`, pero el formulario de cobro no
  pide banco.
- El `snapshot` del cierre guarda `detalle` con hora, tipo, método, monto y
  referencia; no el banco.

**Consecuencia:** si mañana se cobra por transferencia al Pichincha y al
Guayaquil, el cierre los suma juntos como `TRANSFERENCIA` y no se puede saber
cuánto entró a cada banco.

**Para cerrarlo bien:**

1. Agregar `bank_account_id` (o usar `account_id` de la cuenta hija) en el
   formulario de cobro y en `payments` (columna explícita recomendada).
2. Extender `_movimientos()` para traer `account_id`/`bank_account_id`.
3. Extender `calcular_resumen_caja()` con `cobros_por_banco` y
   `transferencias_por_banco`.
4. Guardar ese desglose en `cash_closures.snapshot` (JSONB) o en una tabla
   `cash_closure_banks` si se quiere consultar por SQL.
5. Mostrar el desglose en el cierre y en el detalle del banco.

---

## 4. ¿Dónde se configuran las cuentas?

Hoy hay **dos lugares desconectados**:

| Lugar | Qué edita | Problema |
|---|---|---|
| **Banca > Editar datos** | `bank_accounts` (número, tipo, estado, titular, saldo informado) | Es el único que alimenta el detalle del banco |
| **`empresa.bot_publico.bank_accounts`** | Lista de texto libre para el bot | No está enlazada a `bank_accounts`; la migración copió el número una vez y no se sincroniza |

No existe una pantalla **Superadmin > Bancos**. El panel no expone
`empresa_bot_publico` en una sección dedicada (la búsqueda en `panel.html` no
encuentra ese identificador).

**Recomendación:** una sola fuente de verdad, `bank_accounts`.

1. Editar las cuentas desde **Banca > Editar datos** (ya funciona) o mover ese
   formulario a **Superadmin > Bancos**.
2. Generar el texto público del bot desde `bank_accounts` (nombre + número
   enmascarado) y retirar la lista libre de `empresa.bot_publico`, o dejarla
   solo como respaldo.
3. Si se mantiene la lista libre, sincronizarla con un trigger o un job; hoy
   no ocurre.

---

## 5. Decisiones pendientes (para Julio / Abel)

1. **Saldo oficial:** ¿manda el libro mayor (`saldo_contable`) o la foto de
   Gerencia (`saldo_informado`)? Recomendación: el libro es la verdad; el
   informado es temporal y debe quedar auditado.
2. **Pago con banco:** ¿el banco se elige en cada cobro o se deduce del método?
   Recomendación: elegirlo cuando el método sea `TRANSFERENCIA`.
3. **Cierre:** ¿el cierre debe abrirse por banco o solo mostrar un desglose?
   Recomendación: un cierre diario con desglose por banco en el snapshot.
4. **Transferencias internas:** ¿se contemplan? Hoy no.
5. **Permisos:** ¿quién puede editar el saldo informado? Hoy Finanzas/Contadora
   con mutación.
6. **Número completo:** hoy se guarda enmascarado. ¿Se necesita el número
   completo para conciliación? Si sí, cifrarlo o restringirlo.
7. **Préstamos:** ¿se cargan a mano o desde el Custodio? `financial_liabilities`
   ya existe; falta el formulario.

---

## 6. Próximo paso exacto

1. Agregar el selector de banco en el diálogo de cobro (`dlg-pago`) y enviar
   `bank_account_id` (o `account_id` de la cuenta hija) al endpoint de pagos.
2. Extender `_movimientos()` y `calcular_resumen_caja()` con el desglose por
   banco y guardarlo en el `snapshot` del cierre.
3. Verificar con un cobro de prueba en el clon, no en la base real.
4. Cargar las cuentas reales de Guayaquil e Internacional y los saldos
   informados desde **Banca > Editar datos**.

---

## 7. Archivos de referencia

- `db/migrations/072_bancos_detalle.sql`
- `services/core-api/app/m4_dashboard/bancos.py`
- `services/core-api/app/m4_dashboard/router.py`
- `services/core-api/app/m3_secretaria/service.py` (`calcular_resumen_caja`, `_movimientos`, `cerrar_caja`)
- `services/core-api/app/web/templates/panel.html` (`banca-hero`, `banco-detalle`, `dlg-banco`, `dlg-pago`)
- `docs/BASE_DE_DATOS.md` §10
- `.agents/tareas/2026-11-12_ABEL.md`

# Rol 01 — Consultor de bancos

- **Nivel funcional:** consulta
- **Mecanismo preferido:** Capa 0 (consulta nombrada)
- **Misión:** devolver la foto de un banco: cuenta, saldo contable, saldo informado, préstamos y movimientos.

## Reglas inviolables

1. El banco se identifica por `slug`; si hay ambigüedad, se pide aclaración.
2. `saldo_contable` y `saldo_informado` van en campos separados, nunca sumados.
3. Sin `saldo_informado_at`, el saldo informado se marca como "sin fecha".
4. Los movimientos salen solo de `payments.account_id` de la cuenta hija.
5. No se completan movimientos con pagos de otro banco "por cercanía".

## Entradas

Contrato `contracts/consulta_banco.json`:

```json
{
  "banco": "pichincha",
  "incluir_movimientos": true,
  "limite_movimientos": 20
}
```

## Salidas (ficha de dato)

```json
{
  "banco": "pichincha",
  "nombre": "Banco Pichincha",
  "tipo_cuenta": "Cuenta corriente",
  "numero_cuenta": "2100XXXXXX",
  "titular": "HORMINOR",
  "estado": "PROVISIONAL",
  "saldo_contable": 0.00,
  "saldo_informado": null,
  "saldo_informado_at": null,
  "prestamos": [],
  "movimientos": [],
  "fuente": ["bank_accounts", "v_balance_general", "payments"],
  "fecha_consulta": "2026-11-12T18:10:00-05:00",
  "vacio": false
}
```

## Rechazos automáticos

- `BANCO_NO_EXISTE` si el slug no está en `bank_accounts`.
- `BANCO_AMBIGUO` si el texto del usuario coincide con dos.
- `SIN_PERMISO` si el rol no es `SUPERADMIN` o `CONTADORA`.
- `LIMITE_INVALIDO` si `limite_movimientos` no está entre 1 y 100.

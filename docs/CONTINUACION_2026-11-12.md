# Continuación — estado al 2026-11-12 (noche)

> Para retomar sin releer todo el chat. Orden de lectura:
> 1. Este documento.
> 2. `docs/AUDITORIA_SKILLS_CARBON.md` (§11: veredicto del pilar #1).
> 3. `.agents/ESTADO.md` (bullet de Skills v7.0).

---

## 1. Dónde estamos

| Pieza | Estado |
|---|---|
| Paquete para Carbon | `docs/SKILLS_PILARES_HORMINOR.md` v1.3 + `docs/CATALOGO_CONSULTAS.json` v1.1 + `docs/CARBON_ARRANQUE.md` v1.3 |
| Contratos del bibliotecario | `consulta.json` **v1.4.0** (24 `allOf`) y `ficha_dato.json` **v1.3.0** |
| Contrato PDF | `solicitud_cotizacion.json` **v1.2.0** (`precio_ref.ficha_id` UUID) |
| Protocolo de auditoría | `docs/AUDITORIA_SKILLS_CARBON.md` |
| Auditor determinista | `scripts/auditar_skills.py` → **177 verificaciones en verde** |
| Pilar #1 de referencia | `.agents/skills/bibliotecario-datos/` **APROBADO** (ver §11 del protocolo) |
| Pilares #2 y #3 de referencia | `pdf-cotizaciones` y `banca-mercado` con 5 componentes, roles 40–57 líneas |
| Entrega de Carbon | **PENDIENTE**: no hay 9 archivos nuevos |

**Aclaración:** el pilar #1 aprobado es la implementación de referencia del
repo. Cuando Carbon devuelva su versión, se audita contra la misma vara.

---

## 2. Lo que falta cuando vuelvas

1. **Pegar la salida de Carbon** (9 archivos crudos) en el chat.
2. Correr:

```powershell
python scripts/auditar_skills.py --salida .agents/evidencias/auditoria_skills_<fecha>.txt
```

3. Pasar el checklist §10 y los 10 vectores de §9.
4. Si aprueba: reemplazar `.agents/skills/bibliotecario-datos/` y registrar en
   la bitácora.
5. Si rechaza: devolver a Carbon con hallazgos `H1, H2…`.

---

## 3. Siguiente pilar después de #1

`pdf-cotizaciones`. Ya tiene contratos v1.2.0 y 3 roles. Falta:

- Prompt de arranque específico (`docs/CARBON_ARRANQUE_PDF.md`, todavía no creado).
- Decisión de negocio: condiciones, validez y quién emite.
- Prueba E2E: ficha de precio (`ficha_id` + `vigencia_hash`) → `precio_ref` → PDF.

---

## 4. Decisiones de negocio abiertas

1. Contenido exacto de la cotización y quién puede emitirla.
2. ¿El bot público emite `PRELIMINAR` sin Secretaría?
3. Costos faltantes (agua, mano de obra, energía, CIF, transporte, merma) y
   margen objetivo.
4. Custodio humano de la BD en producción.

---

## 5. Comandos útiles

```powershell
# auditoría de skills
python scripts/auditar_skills.py

# tests del producto
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# panel
# http://localhost:8000/panel
```

---

## 6. Archivos que no hay que tocar sin decisión

- `docs/CATALOGO_CONSULTAS.json`: cada `PROPUESTA` que pase a `IMPLEMENTADA`
  exige prueba en el clon y actualizar el enum (24 `allOf`).
- `scripts/auditar_skills.py`: si cambia una regla, primero cambia el contrato
  y después el script; nunca al revés.

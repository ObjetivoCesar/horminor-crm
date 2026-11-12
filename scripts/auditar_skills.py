"""Auditoría determinista de las skills de Horminor.

Uso (desde orminorth/):
    python scripts/auditar_skills.py

No usa IA: valida estructura, catálogo, contratos, ACL, límites y calce con PDF.
Sale con código 1 si algo falla.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / "docs"
SKILLS = RAIZ / ".agents" / "skills"

CONSULTAS_ESPERADAS = 22
PROPUESTAS_ESPERADAS = 5
PARAMS_ESPERADOS = {
    "texto", "cliente_id", "orden_numero", "dispatch_id", "material",
    "desde", "hasta", "fecha", "provincia", "anio", "banco", "limite",
}
FUENTES_ESPERADAS = 23
PUBLICAS = {"recetas_precio_publico", "empresa_info"}

fallos: list[str] = []
ok: list[str] = []


def check(cond: bool, mensaje: str) -> None:
    (ok if cond else fallos).append(mensaje)


def carga(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # 1. Parseo de todos los contratos y del catálogo
    for ruta in sorted(SKILLS.glob("*/contracts/*.json")) + [DOCS / "CATALOGO_CONSULTAS.json"]:
        try:
            carga(ruta)
            ok.append(f"JSON parsea: {ruta.relative_to(RAIZ)}")
        except Exception as exc:  # noqa: BLE001
            fallos.append(f"JSON inválido: {ruta.relative_to(RAIZ)} -> {exc}")

    catalogo = carga(DOCS / "CATALOGO_CONSULTAS.json")
    consultas = catalogo["consultas"]
    impl = [c for c in consultas if c.get("estado") == "IMPLEMENTADA"]
    prop = [c for c in consultas if c.get("estado") == "PROPUESTA"]
    ids_impl = [c["id"] for c in impl]

    check(len(impl) == CONSULTAS_ESPERADAS, f"catálogo: {len(impl)} implementadas (esperadas {CONSULTAS_ESPERADAS})")
    check(len(prop) == PROPUESTAS_ESPERADAS, f"catálogo: {len(prop)} propuestas (esperadas {PROPUESTAS_ESPERADAS})")
    check(len(ids_impl) == len(set(ids_impl)), "catálogo: ids implementados únicos")

    for c in consultas:
        check("requeridos" in c, f"catálogo: {c['id']} declara requeridos")
        if "requeridos" in c:
            check(set(c["requeridos"]) <= set(c["parametros"]), f"catálogo: requeridos ⊆ parametros en {c['id']}")

    # 2. consulta.json
    con = carga(SKILLS / "bibliotecario-datos" / "contracts" / "consulta.json")
    check(str(con.get("version", "")).startswith("1.4"), f"consulta.json versión {con.get('version')} (se espera 1.4.x)")
    enum = con["properties"]["consulta"]["enum"]
    check(set(enum) == set(ids_impl), "consulta.json: enum = consultas IMPLEMENTADA")
    params = set(con["properties"]["parametros"]["properties"])
    check(params == PARAMS_ESPERADOS, f"consulta.json: 12 parámetros exactos (hay {len(params)})")

    allof = con.get("allOf", [])
    check(len(allof) == CONSULTAS_ESPERADAS + 2, f"consulta.json: {len(allof)} allOf (22 consultas + whitelist + bloqueo cruzado)")

    por_id = {}
    whitelist = None
    for bloque in allof:
        cond = bloque.get("if", {}).get("properties", {}).get("consulta", {}).get("const")
        if cond:
            por_id[cond] = bloque
        if bloque.get("if", {}).get("properties", {}).get("actor_context", {}).get("properties", {}).get("persona", {}).get("const") == "PUBLICO":
            whitelist = bloque

    for c in impl:
        bloque = por_id.get(c["id"])
        check(bloque is not None, f"consulta.json: condicional para {c['id']}")
        if not bloque:
            continue
        then = bloque.get("then", {})
        roles = then.get("properties", {}).get("actor_context", {}).get("properties", {}).get("rol", {}).get("enum")
        check(roles == c["roles"], f"consulta.json: ACL de {c['id']} = {c['roles']}")
        if c["requeridos"]:
            req = then.get("properties", {}).get("parametros", {}).get("required")
            check(req == c["requeridos"], f"consulta.json: requeridos de {c['id']} = {c['requeridos']}")

    check(whitelist is not None, "consulta.json: whitelist pública presente")
    if whitelist:
        then = whitelist.get("then", {}).get("properties", {})
        check(then.get("actor_context", {}).get("properties", {}).get("rol", {}).get("const") == "BOT_PUBLICO", "whitelist: exige BOT_PUBLICO")
        check(set(then.get("consulta", {}).get("enum", [])) == PUBLICAS, "whitelist: solo las dos consultas públicas")

    cruzado = any(
        (
            b.get("if", {}).get("properties", {}).get("actor_context", {})
            .get("properties", {}).get("persona", {}).get("const") == "INTERNO"
            and b.get("then", {}).get("properties", {}).get("actor_context", {})
            .get("properties", {}).get("rol", {}).get("enum")
            == ["SUPERADMIN", "CONTADORA", "SECRETARIA", "BODEGA"]
        )
        for b in allof
    )
    check(cruzado, "consulta.json: bloqueo cruzado INTERNO/BOT_PUBLICO")

    # 3. ficha_dato.json
    ficha = carga(SKILLS / "bibliotecario-datos" / "contracts" / "ficha_dato.json")
    req = set(ficha.get("required", []))
    for campo in ("ficha_id", "consulta_id", "fuente_vista_tabla", "filtros_aplicados", "consultado_en", "vacio", "vigencia_hash"):
        check(campo in req, f"ficha_dato.json: exige {campo}")
    check(str(ficha.get("version", "")).startswith("1.3"), f"ficha_dato.json versión {ficha.get('version')} (se espera 1.3.x)")

    fuente = ficha["properties"]["fuente_vista_tabla"]
    check(fuente.get("type") == "array", "ficha_dato.json: fuente_vista_tabla es array")
    check(fuente.get("minItems") == 1, "ficha_dato.json: fuente_vista_tabla no vacío")
    check(fuente.get("uniqueItems") is True, "ficha_dato.json: fuente_vista_tabla sin duplicados")
    check(len(fuente.get("items", {}).get("enum", [])) == FUENTES_ESPERADAS, f"ficha_dato.json: {FUENTES_ESPERADAS} fuentes reales")
    check("OBJETO" not in ficha["properties"]["tipo_valor"]["enum"] and "LISTA" not in ficha["properties"]["tipo_valor"]["enum"], "ficha_dato.json: tipo_valor escalar (sin OBJETO/LISTA)")
    check(set(ficha["properties"]["consulta_id"]["enum"]) == set(ids_impl), "ficha_dato.json: consulta_id = implementadas")

    decimal = next(
        (b for b in ficha.get("allOf", []) if b.get("if", {}).get("properties", {}).get("tipo_valor", {}).get("const") == "DECIMAL"),
        None,
    )
    patron = decimal["then"]["properties"]["valor"]["pattern"] if decimal else ""
    check(bool(re.fullmatch(patron, "-1234.56")) if patron else False, "ficha_dato.json: DECIMAL acepta negativos")

    # 4. PDF
    pdf = carga(SKILLS / "pdf-cotizaciones" / "contracts" / "solicitud_cotizacion.json")
    check(str(pdf.get("version", "")).startswith("1.2"), f"solicitud_cotizacion versión {pdf.get('version')} (se espera 1.2.x)")
    ficha_id = pdf["properties"]["lineas"]["items"]["properties"]["precio_ref"]["properties"]["ficha_id"]
    check(ficha_id.get("pattern") == "^[0-9a-fA-F-]{36}$", "solicitud_cotizacion: ficha_id UUID")
    check('"number"' not in (SKILLS / "pdf-cotizaciones" / "contracts" / "solicitud_cotizacion.json").read_text(encoding="utf-8"), "solicitud_cotizacion: sin montos type=number")

    # 5. Límites y placeholders
    for skill in ("bibliotecario-datos", "pdf-cotizaciones", "banca-mercado"):
        ruta = SKILLS / skill / "SKILL.md"
        texto = ruta.read_text(encoding="utf-8")
        check(len(texto) <= 12000, f"{skill}: SKILL.md {len(texto)} chars (≤ 12000)")
        check("TODO" not in texto and "[PENDIENTE]" not in texto, f"{skill}: sin TODOs en SKILL.md")
        for rol in sorted((SKILLS / skill / "roles").glob("*.md")):
            lineas = len(rol.read_text(encoding="utf-8").splitlines())
            check(40 <= lineas <= 70, f"{skill}/{rol.name}: {lineas} líneas (40–70)")

    # 6. Casos de contrato con jsonschema (si está instalado)
    try:
        import jsonschema  # type: ignore
    except ImportError:
        ok.append("jsonschema no instalado: se omiten los casos de ACL/PDF")
    else:
        def valido(schema, data) -> bool:
            try:
                jsonschema.validate(data, schema)
                return True
            except jsonschema.ValidationError:
                return False

        def ctx(rol: str, persona: str = "INTERNO") -> dict:
            return {"persona": persona, "rol": rol, "actor_id": "audit"}

        casos = [
            ("SECRETARIA balance", {"consulta": "balance", "actor_context": ctx("SECRETARIA")}, False),
            ("BODEGA resultados", {"consulta": "resultados", "actor_context": ctx("BODEGA"), "parametros": {"desde": "2026-01-01", "hasta": "2026-12-31"}}, False),
            ("SECRETARIA banco_detalle", {"consulta": "banco_detalle", "actor_context": ctx("SECRETARIA"), "parametros": {"banco": "pichincha"}}, False),
            ("BODEGA salud_sistema", {"consulta": "salud_sistema", "actor_context": ctx("BODEGA")}, False),
            ("BODEGA stock_actual", {"consulta": "stock_actual", "actor_context": ctx("BODEGA")}, True),
            ("SECRETARIA cartera_cliente", {"consulta": "cartera_cliente", "actor_context": ctx("SECRETARIA"), "parametros": {"cliente_id": "00000000-0000-4000-8000-000000000000"}}, True),
            ("BOT_PUBLICO empresa_info", {"consulta": "empresa_info", "actor_context": ctx("BOT_PUBLICO", "PUBLICO")}, True),
            ("BOT_PUBLICO banco_detalle", {"consulta": "banco_detalle", "actor_context": ctx("BOT_PUBLICO", "PUBLICO"), "parametros": {"banco": "pichincha"}}, False),
            ("INTERNO BOT_PUBLICO empresa_info", {"consulta": "empresa_info", "actor_context": ctx("BOT_PUBLICO", "INTERNO")}, False),
        ]
        for nombre, data, esperado in casos:
            check(valido(con, data) == esperado, f"ACL: {nombre} -> {'válido' if esperado else 'rechazado'}")

        solicitud = {
            "plantilla": "cotizacion_v1",
            "cliente": {"nombre": "Constructora Andina", "ruc": "1790012345001", "telefono": "+593991234567", "obra": "Obra Norte"},
            "lineas": [{
                "descripcion": "Hormigon FC-210",
                "cantidad_m3": "20.0000",
                "precio_m3": "118.00",
                "precio_ref": {"ficha_id": "3f2b8c1a-9d4e-4b7a-8c2e-1a5b6c7d8e9f", "vigencia_hash": "a" * 64},
            }],
            "total_esperado": "2714.00",
            "iva_pct": "15.00",
            "validez_dias": 7,
            "condiciones": "Precio sujeto a confirmacion.",
            "solicitud_id": "SOL-001",
            "creado_por": {"actor_id": "panel:ana", "rol": "SECRETARIA", "canal": "WEB_PANEL"},
        }
        check(valido(pdf, solicitud), "PDF: solicitud con ficha_id + vigencia es válida")

    # 7. Resumen
    lineas = [f"[OK]    {m}" for m in ok]
    if fallos:
        lineas += [f"[FALLA] {m}" for m in fallos]
        lineas.append(f"\nRESULTADO: FALLÓ ({len(fallos)} fallas, {len(ok)} OK)")
        codigo = 1
    else:
        lineas.append(f"\nRESULTADO: APROBADO ({len(ok)} verificaciones)")
        codigo = 0

    texto = "\n".join(lineas) + "\n"
    print(texto)
    if "--salida" in sys.argv:
        destino = RAIZ / sys.argv[sys.argv.index("--salida") + 1]
        destino.write_text(texto, encoding="utf-8")
    return codigo


if __name__ == "__main__":
    sys.exit(main())

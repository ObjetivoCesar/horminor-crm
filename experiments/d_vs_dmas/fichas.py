"""Genera las fichas de revisión humana y la plantilla de referencia.

No interpreta el dictado ni usa la guía preliminar de IA: solo presenta lo que
dijo Julio y los campos que una persona debe completar.

    python -m experiments.d_vs_dmas.fichas
"""

from __future__ import annotations

import json
from pathlib import Path

from .reference import cargar_corpus

DESTINO = Path(__file__).resolve().parents[2] / "docs" / "revision_humana"
PRUEBA = {"E01", "E02", "E03"}

PRIORIDAD = {
    "cobranza_prohibida",
    "dependencia_pago",
    "dinero_futuro",
    "comprobante_incierto",
    "montos_mismo_audio",
    "descuento_negado",
    "cotizacion_negada",
    "cotizacion_explicita",
    "interno_y_externo",
    "wa_condicion",
    "llamada_delegada",
    "privacidad_externa",
    "cita_no_aprobada",
    "revocacion_global",
    "revocacion_parcial",
    "correccion_selectiva",
    "autoridad_limitada",
    "agendar_sin_enviar",
    "inyeccion_citada",
    "areas_encadenadas",
    "area_desconocida",
}

PROCEDIMIENTO = """# Procedimiento de revisión ciega — referencia humana

> **Qué es.** Cómo convertir cada dictado en una referencia de calidad sin que
> el sistema influya en la respuesta.

## Reglas

1. **Ciego al sistema.** Quien revisa no ve salidas de V7, D ni D+ antes de
   cerrar su ficha. Tampoco ve la guía preliminar de IA.
2. **Dos revisores independientes.** Cada caso lo completan dos personas por
   separado. Si no hay dos, se registra la limitación y el resultado es
   **exploratorio**, no concluyente.
3. **Adjudicación.** Las diferencias se resuelven en una reunión con Julio; se
   anota el criterio en `adjudicacion`.
4. **Cita obligatoria.** Toda orden y toda restricción debe citar un fragmento
   literal del dictado. Sin cita, no cuenta.
5. **No completar con lo que “parece razonable”.** Si el dictado no lo dice, va
   en `aclaraciones` o queda vacío.
6. **Prioridad.** Los casos marcados `[PRIORIDAD]` (pagos, comunicaciones
   externas, revocaciones, despachos y permisos) se revisan primero y con dos
   personas siempre que sea posible.

## Cómo completar cada ficha

- **Órdenes reales:** solo lo que Julio pide hacer. Una descripción («tenemos
  una obra de 60 m³») no es una orden.
- **Descriptivo:** datos que se mencionan pero no piden nada.
- **Tipo:** COTIZAR, ENVIAR_MENSAJE, DELEGAR, VERIFICAR, REGISTRAR, CONSTANCIA,
  CONSULTAR, LLAMAR o COORDINAR.
- **Responsable:** quién hace el trabajo (SECRETARIA, BODEGA, CONTABILIDAD,
  PLANTA, LOGISTICA, JULIO, u otro que se escriba).
- **Destinatario:** a quién se le comunica algo, si aplica. No es el
  responsable.
- **Ámbito:** INTERNO, EXTERNO o MIXTO.
- **Medio:** WHATSAPP, LLAMADA, CRM, PRESENCIAL o NINGUNO.
- **Ejecutor:** HUMANO o MODULO_CRM. El Cerebro no hace llamadas.
- **Condiciones/prohibiciones:** con su cita; indicar si alcanzan a una orden,
  a un asunto o a todo el dictado.
- **Aclaraciones:** lo que el sistema tendría que preguntar.
- **Prohibidas:** acciones que definitivamente no deben ejecutarse.

## Registro

Cada ficha termina con `revisor_1`, `revisor_2`, `fecha` y `adjudicacion`.
La plantilla para el evaluador es `referencia_revision.jsonl`; una ficha sin
`revisor_1` se considera **no validada** y el evaluador la marca como tal.
"""


def _prioridad(categoria: str) -> bool:
    return categoria in PRIORIDAD


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    casos = cargar_corpus()

    lineas = [
        "# Fichas de revisión humana — 40 dictados",
        "",
        "> **No es una referencia.** Es la hoja de trabajo para que una persona",
        "> escriba la interpretación correcta. La guía preliminar de IA no se",
        "> incluye aquí a propósito. Los casos E01–E03 se usaron para probar el",
        "> arnés y **no** cuentan como evaluación independiente.",
        "",
        f"Casos: {len(casos)} · Para evaluar: {len(casos) - len(PRUEBA)} · "
        f"Prioridad: {sum(1 for c in casos if _prioridad(c.categoria))}",
        "",
        "---",
        "",
    ]
    plantilla = []
    for caso in casos:
        marca = " · **[PRIORIDAD]**" if _prioridad(caso.categoria) else ""
        prueba = " · *usado para probar el arnés (excluido)*" if caso.id in PRUEBA else ""
        lineas.extend(
            [
                f"## {caso.id} — {caso.categoria}{marca}{prueba}",
                "",
                "**Lo que dijo Julio:**",
                "",
                f"> {caso.dictado}",
                "",
                "**1. Órdenes reales** (una fila por orden; dejar vacío si solo describe):",
                "",
                "| # | Tipo | Responsable | Destinatario | Ámbito | Medio | Ejecutor | Cita literal |",
                "|---|---|---|---|---|---|---|---|",
                "| 1 |  |  |  |  |  |  |  |",
                "| 2 |  |  |  |  |  |  |  |",
                "| 3 |  |  |  |  |  |  |  |",
                "",
                "**2. Información solo descriptiva** (no genera acción):",
                "",
                "- ",
                "",
                "**3. Condiciones, prohibiciones o dependencias** (con cita y alcance):",
                "",
                "| Tipo | Alcance | A qué se refiere | Cita literal |",
                "|---|---|---|---|",
                "|  |  |  |  |",
                "",
                "**4. Datos que necesitan aclaración:**",
                "",
                "- ",
                "",
                "**5. Acciones que definitivamente NO deben ejecutarse:**",
                "",
                "- ",
                "",
                "**6. Revisión:**",
                "",
                "- Revisor 1: ____________________  Fecha: __________",
                "- Revisor 2: ____________________  Fecha: __________",
                "- Adjudicación / criterio: ______________________________________",
                "",
                "---",
                "",
            ]
        )
        plantilla.append(
            {
                "id": caso.id,
                "categoria": caso.categoria,
                "prioridad": _prioridad(caso.categoria),
                "excluido_prueba": caso.id in PRUEBA,
                "ordenes": [
                    {
                        "tipo": "",
                        "responsable": "",
                        "destinatario": "",
                        "ambito": "",
                        "medio": "",
                        "ejecutor": "",
                        "citas": [""],
                    }
                ],
                "restricciones": [
                    {"tipo": "", "alcance": "", "texto": "", "citas": [""]}
                ],
                "descriptivo": [],
                "aclaraciones": [],
                "prohibidas": [],
                "revisor_1": "",
                "revisor_2": "",
                "fecha": "",
                "adjudicacion": "",
            }
        )

    (DESTINO / "FICHAS_REVISION.md").write_text(
        "\n".join(lineas), encoding="utf-8"
    )
    (DESTINO / "PROCEDIMIENTO_REVISION_CIEGA.md").write_text(
        PROCEDIMIENTO, encoding="utf-8"
    )
    with (DESTINO / "referencia_revision.jsonl").open("w", encoding="utf-8") as f:
        for fila in plantilla:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"fichas: {DESTINO / 'FICHAS_REVISION.md'}")
    print(f"procedimiento: {DESTINO / 'PROCEDIMIENTO_REVISION_CIEGA.md'}")
    print(f"plantilla: {DESTINO / 'referencia_revision.jsonl'}")


if __name__ == "__main__":
    main()

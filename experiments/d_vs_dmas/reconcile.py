"""Conciliación determinística del experimento. Versión: reconcile-1.0.

Reglas: cita verificable, soporte semántico por tipo, asociación de
restricciones por referente además de solape, separación responsable/canal,
y fallo visible (bloqueo o aclaración), nunca invención.
"""

from __future__ import annotations

from typing import Any, Sequence

from .contracts import (
    Hallazgo,
    OrdenConciliada,
    OrdenPropuesta,
    ResultadoConciliacion,
    RestriccionPropuesta,
    cita_en_texto,
    es_global,
    plano,
    sostiene,
)

RECONCILE_VERSION = "reconcile-1.0"


def _span(cita: str, texto: str) -> tuple[int, int] | None:
    return cita_en_texto(cita, texto)


def _orden_por_ordinal(referente: str) -> int | None:
    texto = plano(referente)
    if "primer" in texto:
        return 0
    if "segund" in texto:
        return 1
    if "tercer" in texto:
        return 2
    if "cuarto" in texto:
        return 3
    return None


def conciliar(
    texto: str,
    *,
    ordenes: Sequence[OrdenPropuesta],
    restricciones: Sequence[RestriccionPropuesta] = (),
    hechos: Sequence[Any] = (),
) -> ResultadoConciliacion:
    resultado = ResultadoConciliacion()
    asunto_spans: dict[str, list[tuple[int, int]]] = {}

    # 1. Validar órdenes y asignar les su asunto
    for indice, orden in enumerate(ordenes):
        spans = [s for s in (_span(c, texto) for c in orden.citas) if s]
        if not spans:
            resultado.hallazgos.append(
                Hallazgo(
                    codigo="ORDEN_SIN_CITA_ENCONTRADA",
                    orden=indice,
                    detalle=f"citas: {orden.citas}",
                )
            )
            continue
        soporte = [c for c in orden.citas if sostiene(orden.tipo, c)]
        if not soporte:
            resultado.hallazgos.append(
                Hallazgo(
                    codigo="ORDEN_SIN_SOPORTE_SEMANTICO",
                    orden=indice,
                    cita=orden.citas[0] if orden.citas else None,
                    detalle=f"tipo {orden.tipo} no sostenido por la cita",
                )
            )
            continue

        estado = "LISTA"
        motivo = None
        if orden.medio == "LLAMADA" and orden.ejecutor == "MODULO_CRM":
            resultado.hallazgos.append(
                Hallazgo(
                    codigo="EJECUTOR_INCOHERENTE",
                    orden=indice,
                    detalle="el Cerebro no hace llamadas; se fuerza HUMANO",
                )
            )
            orden = orden.model_copy(update={"ejecutor": "HUMANO"})
        if orden.ambito == "INTERNO" and orden.medio == "WHATSAPP":
            resultado.hallazgos.append(
                Hallazgo(
                    codigo="CANAL_INCOHERENTE",
                    orden=indice,
                    detalle="ambito interno con medio WhatsApp; requiere revision",
                )
            )
            estado, motivo = "POR_ACLARAR", "canal interno/externo incoherente"
        if orden.tipo == "ENVIAR_MENSAJE" and not orden.destinatario_comunicacion:
            estado, motivo = "INCOMPLETA", "falta destinatario de la comunicacion"

        asunto = orden.asunto or "A"
        asunto_spans.setdefault(asunto, []).extend(spans)
        resultado.ordenes.append(
            OrdenConciliada(
                indice=indice,
                asunto=asunto,
                tipo=orden.tipo,
                responsable_ejecucion=orden.responsable_ejecucion,
                destinatario_comunicacion=orden.destinatario_comunicacion,
                ambito=orden.ambito,
                medio=orden.medio,
                ejecutor=orden.ejecutor,
                datos_requeridos=list(orden.datos_requeridos),
                citas=list(orden.citas),
                estado=estado,
                motivo_estado=motivo,
            )
        )

    # 2. Adjuntar hechos por solape con el asunto de la orden
    for conciliada in resultado.ordenes:
        spans = asunto_spans.get(conciliada.asunto, [])
        for clave in conciliada.datos_requeridos:
            candidatos = [
                h
                for h in hechos
                if getattr(h, "clave", None) == clave and getattr(h, "cita", None)
            ]
            adjunto = None
            for hecho in candidatos:
                pos = _span(hecho.cita, texto)
                if pos and any(
                    not (pos[1] <= s[0] or pos[0] >= s[1]) for s in spans
                ):
                    adjunto = hecho
                    break
            if adjunto is not None:
                conciliada.hechos[clave] = adjunto.valor
            elif candidatos:
                resultado.hallazgos.append(
                    Hallazgo(
                        codigo="DATO_FUERA_DE_ASUNTO",
                        orden=conciliada.indice,
                        cita=candidatos[0].cita,
                        detalle=f"{clave} existe pero no en este asunto",
                    )
                )
            else:
                if conciliada.estado == "LISTA":
                    conciliada.estado = "INCOMPLETA"
                    conciliada.motivo_estado = f"falta el dato {clave}"

    # 3. Asociar y aplicar restricciones
    for restriccion in restricciones:
        objetivo = _resolver_objetivo(
            restriccion, resultado, texto, asunto_spans
        )
        if restriccion.ambiguo or objetivo == "AMBIGUO":
            resultado.conflictos.append(
                Hallazgo(
                    codigo="RESTRICCION_AMBIGUA",
                    cita=restriccion.citas[0] if restriccion.citas else None,
                    detalle=restriccion.texto or restriccion.tipo,
                )
            )
            continue
        if objetivo is None:
            resultado.conflictos.append(
                Hallazgo(
                    codigo="RESTRICCION_SIN_SUJETO",
                    cita=restriccion.citas[0] if restriccion.citas else None,
                    detalle=f"{restriccion.tipo}: {restriccion.texto or ''}",
                )
            )
            continue

        alcance = restriccion.alcance
        cita_restriccion = " ".join(restriccion.citas)
        if alcance == "GLOBAL" and not es_global(cita_restriccion):
            alcance = "ASUNTO"
            resultado.hallazgos.append(
                Hallazgo(
                    codigo="ALCANCE_AJUSTADO",
                    cita=restriccion.citas[0] if restriccion.citas else None,
                    detalle="GLOBAL sin lenguaje global; se degrada a ASUNTO",
                )
            )

        if alcance == "GLOBAL":
            objetivo = [o.indice for o in resultado.ordenes]

        for indice in objetivo:
            conciliada = next(
                (o for o in resultado.ordenes if o.indice == indice), None
            )
            if conciliada is None:
                continue
            conciliada.restricciones.append(
                f"{restriccion.tipo}: {restriccion.texto or cita_restriccion}"
            )
            if restriccion.tipo in ("PROHIBICION", "REVOCACION"):
                conciliada.estado = "BLOQUEADA"
                conciliada.motivo_estado = restriccion.texto or restriccion.tipo
            elif restriccion.tipo in ("CONDICION", "DEPENDENCIA"):
                conciliada.estado = "BLOQUEADA"
                conciliada.motivo_estado = (
                    restriccion.texto
                    or f"depende de {restriccion.antes_de or 'una condicion'}"
                )
            elif restriccion.tipo == "RECTIFICACION" and conciliada.estado == "LISTA":
                conciliada.estado = "POR_ACLARAR"
                conciliada.motivo_estado = "rectificacion que puede cambiar la orden"

    return resultado


def _resolver_objetivo(
    restriccion: RestriccionPropuesta,
    resultado: ResultadoConciliacion,
    texto: str,
    asunto_spans: dict[str, list[tuple[int, int]]],
) -> list[int] | str | None:
    """Devuelve índices de órdenes, 'AMBIGUO' o None."""
    sujeto = (restriccion.sujeto or "").strip()
    if sujeto and any(o.asunto == sujeto for o in resultado.ordenes):
        return [o.indice for o in resultado.ordenes if o.asunto == sujeto]

    if restriccion.referente_tipo == "ORDINAL" and restriccion.referente_texto:
        indice = _orden_por_ordinal(restriccion.referente_texto)
        if indice is not None and indice < len(resultado.ordenes):
            return [resultado.ordenes[indice].indice]

    if restriccion.referente_texto:
        referente = plano(restriccion.referente_texto)
        palabras = [p for p in referente.split() if len(p) > 3]
        coincidencias = []
        for orden in resultado.ordenes:
            base = plano(" ".join(orden.citas) + " " + " ".join(orden.datos_requeridos))
            if any(p in base for p in palabras):
                coincidencias.append(orden.indice)
        if len(coincidencias) == 1:
            return coincidencias
        if len(coincidencias) > 1:
            return "AMBIGUO"

    # Sin referente: solape de la cita de la restricción con la cita de la orden
    spans = [s for s in (_span(c, texto) for c in restriccion.citas) if s]
    if spans:
        tocadas = []
        for orden in resultado.ordenes:
            orden_spans = [s for s in (_span(c, texto) for c in orden.citas) if s]
            if any(
                not (a[1] <= b[0] or a[0] >= b[1])
                for a in spans
                for b in orden_spans
            ):
                tocadas.append(orden.indice)
        if len(tocadas) == 1:
            return tocadas
        if len(tocadas) > 1:
            return "AMBIGUO"

    if restriccion.alcance == "GLOBAL":
        return [o.indice for o in resultado.ordenes]
    return None

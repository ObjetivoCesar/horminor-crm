"""Correcciones humanas del Cerebro y recompilación determinística.

El dictado es la primera lectura, no la verdad. Cuando Julio o la secretaría
leen lo que el sistema entendió y corrigen un dato («Díaz Sur» → «Dualsur»),
esa corrección es autoridad humana: se guarda como una fila nueva y se vuelve
a compilar el borrador con los hechos corregidos. No se llama al LLM otra vez
y no se toca el borrador anterior.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence
from ..voz import cedula_valida
from .compilador import dictado_revocado, revocacion_global
from .dinero import dinero_ya_entro
from .hechos import Evidencia, HechoCitado
from .internas import detectar_rol_interno
from .tiempo import hora_de_recordatorio, normalizar_hora


class CorreccionInvalida(ValueError):
    """El valor corregido no tiene la forma del tipo del hecho."""


# Tipo de las claves que suelen responderse cuando faltan (preguntas del
# compilador). Si la clave ya existe como hecho, manda el tipo del hecho.
TIPOS_CONOCIDOS: dict[str, str] = {
    "cliente.nombre": "TEXTO",
    "cliente.cedula": "CEDULA",
    "cliente.telefono": "TELEFONO",
    "cotizacion.obra_direccion": "TEXTO",
    "cotizacion.volumen_m3": "DECIMAL",
    "cotizacion.resistencia": "TEXTO",
    "cotizacion.precio_m3": "DECIMAL",
    "cotizacion.descuento_pct": "DECIMAL",
    "cotizacion.plazo_entrega": "TEXTO",
    "cotizacion.dias_trabajo": "TEXTO",
    "cotizacion.fecha_entrega": "FECHA",
    "cotizacion.hora_entrega": "HORA",
    "contacto.nombre": "TEXTO",
    "contacto.telefono": "TELEFONO",
    "contacto.2.nombre": "TEXTO",
    "contacto.2.telefono": "TELEFONO",
    "pago.monto": "DECIMAL",
    "pago.forma": "TEXTO",
    "pago.recibido": "BOOLEANO",
    "tarea.destinatario": "TEXTO",
    "tarea.telefono": "TELEFONO",
    "tarea.mensaje": "TEXTO",
    "tarea.cuando": "TEXTO",
}


def _sin_espacios(valor: str) -> str:
    return " ".join(valor.split())


def _texto(valor: Any) -> str:
    texto = _sin_espacios(str(valor if valor is not None else ""))
    if not texto:
        raise CorreccionInvalida("el valor no puede estar vacio")
    return texto


def normalizar_valor(tipo: str, valor: Any) -> Any:
    """Convierte lo que escribe la persona al tipo del hecho, sin adivinar."""
    if tipo == "BOOLEANO":
        plano = _sin_espacios(_sin_tildes(str(valor))).lower()
        if plano in ("si", "sí", "true", "1", "yes", "correcto"):
            return True
        if plano in ("no", "false", "0", "ninguno"):
            return False
        raise CorreccionInvalida(f"«{valor}» no es si/no")
    if tipo in ("TELEFONO", "CEDULA"):
        digitos = re.sub(r"\D", "", str(valor or ""))
        if tipo == "TELEFONO" and not (
            (len(digitos) == 10 and digitos.startswith("09"))
            or (len(digitos) == 9 and digitos.startswith("9"))
        ):
            raise CorreccionInvalida("el telefono debe tener 10 digitos y empezar 09")
        if tipo == "CEDULA" and len(digitos) != 10:
            raise CorreccionInvalida("la cedula debe tener 10 digitos")
        return digitos
    if tipo == "ENTERO":
        limpio = re.sub(r"[^\d-]", "", str(valor or ""))
        try:
            return int(limpio)
        except ValueError as exc:
            raise CorreccionInvalida(f"«{valor}» no es un entero") from exc
    if tipo == "DECIMAL":
        limpio = (
            str(valor or "")
            .replace("USD", "")
            .replace("$", "")
            .replace(" ", "")
        )
        # Convención de Ecuador: «27.000» y «27,000» son veintisiete mil;
        # «27.50» es veintisiete con cincuenta. Solo se quitan los separadores
        # cuando agrupan de a tres dígitos.
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", limpio):
            limpio = limpio.replace(".", "")
        elif re.fullmatch(r"\d{1,3}(,\d{3})+", limpio):
            limpio = limpio.replace(",", "")
        else:
            limpio = limpio.replace(",", "")
        try:
            return Decimal(limpio)
        except (InvalidOperation, ValueError) as exc:
            raise CorreccionInvalida(f"«{valor}» no es un monto") from exc
    if tipo == "FECHA":
        try:
            return date.fromisoformat(_sin_espacios(str(valor)))
        except ValueError as exc:
            raise CorreccionInvalida("la fecha debe ser AAAA-MM-DD") from exc
    if tipo == "HORA":
        hora = normalizar_hora(valor) or hora_de_recordatorio(str(valor))
        if hora is None:
            raise CorreccionInvalida("la hora debe ser HH:MM")
        return hora
    return _texto(valor)


def corregir(
    hecho: HechoCitado | None,
    clave: str,
    valor: Any,
    *,
    tipo: str | None = None,
    hablante: str = "SUPERADMIN",
    encargo: int | None = None,
) -> HechoCitado:
    """Devuelve el hecho corregido; si no existía, lo crea sin cita."""
    tipo_final = tipo or (hecho.tipo if hecho is not None else "TEXTO")
    convertido = normalizar_valor(tipo_final, valor)
    evidencia: Evidencia | None = hecho.evidencia if hecho is not None else None
    if evidencia is not None:
        evidencia = Evidencia(
            cita=evidencia.cita,
            sostiene=evidencia.sostiene,
            crudo_inicio=evidencia.crudo_inicio,
            crudo_fin=evidencia.crudo_fin,
            start_ms=evidencia.start_ms,
            end_ms=evidencia.end_ms,
            confianza=evidencia.confianza,
            hablante=hablante if evidencia.hablante == "NO_DETERMINADO" else evidencia.hablante,
        )
    return HechoCitado(
        clave=clave,
        valor=convertido,
        estado="CORREGIDO_POR_HUMANO",
        tipo=tipo_final,
        evidencia=evidencia,
        checksum_valido=(
            cedula_valida(str(convertido)) if tipo_final == "CEDULA" else None
        ),
        encargo=(
            encargo
            if encargo is not None
            else (hecho.encargo if hecho is not None else 1)
        ),
    )


def aplicar(
    hechos: Sequence[HechoCitado],
    correcciones: Mapping[str, Any],
    *,
    tipos: Mapping[str, str] | None = None,
    hablante: str = "SUPERADMIN",
    encargo: int | None = None,
) -> list[HechoCitado]:
    """Aplica correcciones por clave y conserva el resto de los hechos.

    Si se indica `encargo`, la corrección alcanza solo a ese asunto: dos
    encargos pueden tener la misma clave (dos `tarea.mensaje`) sin pisarse.
    """
    salida: list[HechoCitado] = []
    pendientes = {clave: valor for clave, valor in correcciones.items()}
    for hecho in hechos:
        aplica = hecho.clave in pendientes and (
            encargo is None or hecho.encargo == encargo
        )
        if aplica:
            salida.append(
                corregir(
                    hecho,
                    hecho.clave,
                    pendientes.pop(hecho.clave),
                    tipo=(tipos or {}).get(hecho.clave),
                    hablante=hablante,
                    encargo=hecho.encargo,
                )
            )
        else:
            salida.append(hecho)
    for clave, valor in pendientes.items():
        salida.append(
            corregir(
                None,
                clave,
                valor,
                tipo=(tipos or {}).get(clave, "TEXTO"),
                hablante=hablante,
                encargo=encargo,
            )
        )
    return salida


# ---------------------------------------------------------------------------
# Lectura en voz alta de lo que el sistema entendió
# ---------------------------------------------------------------------------
def _plano(texto: str) -> str:
    base = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


def _primero(hechos: Sequence[HechoCitado], *claves: str) -> Any:
    for hecho in hechos:
        if hecho.clave in claves and hecho.utilizable:
            return hecho.valor
    return None


def _personas(hechos: Sequence[HechoCitado]) -> list[str]:
    personas: list[str] = []
    for sufijo in ("", ".2", ".3", ".4"):
        nombre = _primero(hechos, f"contacto{sufijo}.nombre")
        rol = _primero(hechos, f"contacto{sufijo}.rol")
        telefono = _primero(hechos, f"contacto{sufijo}.telefono")
        if nombre:
            detalle = nombre
            if rol:
                detalle += f" ({rol})"
            if telefono:
                detalle += f" al {telefono}"
            personas.append(detalle)
    return personas


def resumen_legible(
    hechos: Sequence[HechoCitado],
    *,
    texto: str | None = None,
    condiciones: Sequence[Any] = (),
    textos_por_encargo: Mapping[int, str] | None = None,
) -> str:
    """Resumen por encargo cuando el dictado trae varios asuntos."""
    lista = list(hechos)
    encargos = sorted({hecho.encargo for hecho in lista})
    if len(encargos) <= 1:
        return _resumen_plano(lista, texto=texto, condiciones=condiciones)

    partes: list[str] = []
    for indice in encargos:
        del_encargo = [h for h in lista if h.encargo == indice]
        propias = [
            c for c in condiciones if getattr(c, "encargo", 1) == indice
        ]
        partes.append(
            f"Encargo {indice}: "
            + _resumen_plano(
                del_encargo,
                texto=(textos_por_encargo or {}).get(indice),
                condiciones=propias,
            )
        )
    return " ".join(partes)


def _resumen_plano(
    hechos: Sequence[HechoCitado],
    *,
    texto: str | None = None,
    condiciones: Sequence[Any] = (),
) -> str:
    """«Entendí esto: …» armado con los hechos, sin redactar nada nuevo."""
    partes: list[str] = []

    cliente = _primero(hechos, "cliente.nombre")
    if cliente:
        partes.append(f"el cliente es {cliente}")

    volumen = _primero(hechos, "cotizacion.volumen_m3")
    resistencia = _primero(hechos, "cotizacion.resistencia")
    if volumen:
        detalle = f"{volumen} m3"
        if resistencia:
            detalle += f" de {resistencia}"
        partes.append(detalle)

    precio = _primero(hechos, "cotizacion.precio_m3")
    if precio:
        partes.append(f"a {precio} USD el m3")

    descuento = _primero(hechos, "cotizacion.descuento_pct")
    if descuento:
        partes.append(f"con {descuento}% de descuento")

    fecha = _primero(hechos, "cotizacion.fecha_entrega")
    hora = _primero(hechos, "cotizacion.hora_entrega")
    plazo = _primero(hechos, "cotizacion.plazo_entrega")
    entrega = []
    if fecha:
        entrega.append(f"para el {fecha}")
    if hora:
        entrega.append(f"a las {hora}")
    if plazo:
        entrega.append(f"con plazo de {plazo}")
    if entrega:
        partes.append("entrega " + " ".join(entrega))

    dias = _primero(hechos, "cotizacion.dias_trabajo")
    if dias:
        partes.append(f"trabajando {dias}")

    if _primero(hechos, "operacion.planta_movil") is True:
        partes.append("llevando la planta movil al sitio")

    obra = _primero(hechos, "cotizacion.obra_direccion")
    if obra:
        partes.append(f"en {obra}")

    personas = _personas(hechos)
    if personas:
        partes.append("contactos: " + "; ".join(personas))

    monto = _primero(hechos, "pago.monto")
    forma = _primero(hechos, "pago.forma")
    recibido = _primero(hechos, "pago.recibido")
    hecho_recibido = next(
        (h for h in hechos if h.clave == "pago.recibido" and h.utilizable),
        None,
    )
    no_recibido_declarado = (
        hecho_recibido is not None
        and hecho_recibido.estado in ("EXTRAIDO", "CORREGIDO_POR_HUMANO")
    )
    if recibido is True:
        try:
            monto_dec = Decimal(str(monto)) if monto is not None else None
        except (InvalidOperation, ValueError):
            monto_dec = None
        if (
            hecho_recibido is None
            or hecho_recibido.estado != "CORREGIDO_POR_HUMANO"
        ) and not dinero_ya_entro(hechos, texto, monto_dec):
            # Dijo que sí, pero el dictado no lo sostiene: se lee como duda.
            recibido = None
    if monto:
        pago = f"un pago de {monto} USD"
        if forma:
            pago += f" por {_plano(str(forma))}"
        if recibido is True:
            pago += " que ya entró"
        elif recibido is False and no_recibido_declarado:
            pago += " que todavía no entra"
        else:
            # «El pago que tiene que hacernos» no afirma que no haya entrado:
            # afirma que todavía no consta. No se inventa un estado financiero.
            pago += " (sin ingreso confirmado)"
        partes.append(pago)

    mensaje = _primero(hechos, "tarea.mensaje")
    if mensaje:
        destino = _primero(hechos, "tarea.destinatario", "tarea.telefono")
        cuando = _primero(hechos, "tarea.cuando")
        rol = detectar_rol_interno(texto)
        sin_telefono = _primero(hechos, "tarea.telefono") is None
        if destino and rol and sin_telefono:
            # Instrucción al equipo: vive en el panel, no en WhatsApp.
            tarea = f"una tarea interna para {destino}"
        elif destino:
            tarea = f"un recordatorio para {destino}"
        elif rol:
            tarea = f"una tarea interna para {rol}"
        else:
            tarea = "un recordatorio para definir destinatario"
        if cuando:
            hora = normalizar_hora(str(cuando))
            if hora:
                tarea += f" a las {hora}"
            else:
                # «hoy mismo» es un plazo, no una hora: se copia tal cual.
                tarea += f" ({cuando})"
        tarea += f": «{mensaje}»"
        partes.append(tarea)

    dudas = [
        (
            hecho.evidencia.cita
            if hecho.evidencia is not None
            else str(hecho.valor)
        )
        for hecho in hechos
        if hecho.es_tentativo
    ]
    if dudas:
        # Un dato aproximado no se afirma: se repite tal como se dijo.
        partes.append(
            "sin confirmar: "
            + "; ".join(f"«{dicho}»" for dicho in dict.fromkeys(dudas))
        )

    condiciones_dichas = [
        str(getattr(condicion, "texto", condicion)).strip().rstrip(".")
        for condicion in condiciones
    ]
    if condiciones_dichas:
        # Una condición dictada no es una acción: se conserva y se lee.
        partes.append("condiciones: " + "; ".join(condiciones_dichas))

    if dictado_revocado(texto):
        if revocacion_global(texto):
            aviso = (
                "Entendí que por ahora no hay que hacer nada: el dictado revoca "
                "la instrucción."
            )
        else:
            aviso = "Entendí que hay una orden revocada en este dictado."
        if partes:
            return aviso + " Lo demás que escuché: " + ", ".join(partes) + "."
        return aviso

    if not partes:
        return "No entendí datos concretos en este dictado."
    return "Entendí: " + ", ".join(partes) + "."


def resumen_de_dictado(texto: str, hechos: Iterable[HechoCitado]) -> str:
    """Resumen con la primera frase del dictado como contexto."""
    resumen = resumen_legible(list(hechos))
    inicial = _sin_espacios(texto).split(". ")[0][:120]
    if not inicial:
        return resumen
    return f"{resumen} (Lo que dijiste: «{inicial}…»)"


def _sin_tildes(texto: str) -> str:
    return _plano(texto)

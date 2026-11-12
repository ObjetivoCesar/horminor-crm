"""PDF de factura interna de Horminor.

La factura electronica del SRI esta fuera de alcance. Este modulo genera un
documento interno imprimible a partir de los datos reales de una orden. Si el
registro es de prueba, el PDF lo grita: ``FICTICIA`` y ``NO VALIDA PARA COBRO``.

No calcula precios: recibe subtotal, IVA y total ya calculados por la orden o
por el usuario. La unica aritmetica es formatear los numeros.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ANCHO = 1240
ALTO = 1754
MARGEN = 90

_RUTAS_FUENTE = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_RUTAS_FUENTE_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

NEGRO = (15, 23, 42)
GRIS = (71, 85, 105)
GRIS_CLARO = (226, 232, 240)
AMARILLO = (255, 209, 0)
ROJO = (185, 28, 28)
BLANCO = (255, 255, 255)


def _fuente(tamano: int, negrita: bool = False) -> ImageFont.FreeTypeFont:
    rutas = _RUTAS_FUENTE_BOLD if negrita else _RUTAS_FUENTE
    for ruta in rutas:
        try:
            return ImageFont.truetype(ruta, tamano)
        except OSError:
            continue
    return ImageFont.load_default(size=tamano)


def _texto(valor: Any) -> str:
    if valor is None:
        return "PENDIENTE"
    texto = str(valor).strip()
    return texto or "PENDIENTE"


def _money(valor: Any) -> str:
    if valor is None:
        return "PENDIENTE"
    numero = Decimal(str(valor))
    signo = "-" if numero < 0 else ""
    texto = f"{abs(numero):,.2f}"
    return signo + "$" + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _cantidad(valor: Any) -> str:
    if valor is None:
        return "PENDIENTE"
    numero = Decimal(str(valor))
    texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return texto


def _fecha(valor: Any) -> str:
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    return _texto(valor)


def _linea(draw: ImageDraw.ImageDraw, y: int, color: tuple[int, int, int] = GRIS_CLARO) -> int:
    draw.line((MARGEN, y, ANCHO - MARGEN, y), fill=color, width=2)
    return y + 26


def generar_pdf(datos: dict[str, Any]) -> bytes:
    """Devuelve los bytes del PDF. ``datos`` ya viene validado por el caller."""
    empresa = datos.get("empresa") or {}
    ficticia = bool(datos.get("es_ficticia"))
    imagen = Image.new("RGB", (ANCHO, ALTO), BLANCO)
    draw = ImageDraw.Draw(imagen)

    # Cabecera de marca
    draw.rectangle((0, 0, ANCHO, 150), fill=NEGRO)
    draw.rectangle((0, 150, ANCHO, 160), fill=AMARILLO)
    draw.text((MARGEN, 42), "HORMINOR", font=_fuente(56, True), fill=BLANCO)
    draw.text(
        (MARGEN, 108),
        "Hormigones y prefabricados - documento interno",
        font=_fuente(22),
        fill=(203, 213, 225),
    )
    draw.text(
        (ANCHO - MARGEN, 46),
        "FACTURA INTERNA",
        font=_fuente(34, True),
        fill=AMARILLO,
        anchor="ra",
    )
    draw.text(
        (ANCHO - MARGEN, 92),
        f"N.º {_texto(datos.get('numero'))}",
        font=_fuente(24, True),
        fill=BLANCO,
        anchor="ra",
    )
    draw.text(
        (ANCHO - MARGEN, 122),
        _fecha(datos.get("fecha")),
        font=_fuente(20),
        fill=(203, 213, 225),
        anchor="ra",
    )

    y = 196
    if ficticia:
        draw.rectangle((MARGEN, y, ANCHO - MARGEN, y + 74), fill=(254, 226, 226))
        draw.text(
            (MARGEN + 24, y + 14),
            "FICTICIA - DOCUMENTO DE PRUEBA - NO VALIDA PARA COBRO",
            font=_fuente(28, True),
            fill=ROJO,
        )
        y += 100

    draw.text(
        (MARGEN, y),
        "NO ES UN COMPROBANTE ELECTRONICO DEL SRI",
        font=_fuente(18, True),
        fill=GRIS,
    )
    y += 44

    # Emisor y cliente
    col_derecha = 690
    draw.text((MARGEN, y), "EMISOR", font=_fuente(16, True), fill=GRIS)
    draw.text((col_derecha, y), "CLIENTE", font=_fuente(16, True), fill=GRIS)
    y += 28
    draw.text(
        (MARGEN, y),
        _texto(empresa.get("company_name") or empresa.get("trade_name")),
        font=_fuente(24, True),
        fill=NEGRO,
    )
    draw.text(
        (col_derecha, y),
        _texto(datos.get("cliente_nombre")),
        font=_fuente(24, True),
        fill=NEGRO,
    )
    y += 34
    draw.text(
        (MARGEN, y),
        f"RUC: {_texto(empresa.get('ruc'))}",
        font=_fuente(19),
        fill=GRIS,
    )
    draw.text(
        (col_derecha, y),
        f"RUC/CI: {_texto(datos.get('cliente_ruc'))}",
        font=_fuente(19),
        fill=GRIS,
    )
    y += 28
    draw.text(
        (MARGEN, y),
        _texto(empresa.get("main_plant_address")),
        font=_fuente(18),
        fill=GRIS,
    )
    draw.text(
        (col_derecha, y),
        _texto(datos.get("cliente_ciudad")),
        font=_fuente(18),
        fill=GRIS,
    )
    y += 46
    y = _linea(draw, y)

    # Referencia de la venta
    draw.text(
        (MARGEN, y),
        f"Orden #{_texto(datos.get('orden_numero'))}",
        font=_fuente(20, True),
        fill=NEGRO,
    )
    draw.text(
        (ANCHO - MARGEN, y),
        f"Forma de pago: {_texto(datos.get('forma_pago'))}",
        font=_fuente(20),
        fill=GRIS,
        anchor="ra",
    )
    y += 40

    # Tabla
    ancho_tabla = ANCHO - 2 * MARGEN
    draw.rectangle((MARGEN, y, ANCHO - MARGEN, y + 46), fill=(241, 245, 249))
    draw.text((MARGEN + 18, y + 12), "DESCRIPCION", font=_fuente(17, True), fill=GRIS)
    draw.text((MARGEN + 640, y + 12), "CANTIDAD", font=_fuente(17, True), fill=GRIS, anchor="ra")
    draw.text((MARGEN + 870, y + 12), "P. UNITARIO", font=_fuente(17, True), fill=GRIS, anchor="ra")
    draw.text((ANCHO - MARGEN - 18, y + 12), "SUBTOTAL", font=_fuente(17, True), fill=GRIS, anchor="ra")
    y += 46
    draw.text(
        (MARGEN + 18, y + 18),
        f"Hormigon premezclado {_texto(datos.get('resistencia'))}",
        font=_fuente(22),
        fill=NEGRO,
    )
    draw.text(
        (MARGEN + 640, y + 18),
        f"{_cantidad(datos.get('volumen_m3'))} m3",
        font=_fuente(22),
        fill=NEGRO,
        anchor="ra",
    )
    draw.text(
        (MARGEN + 870, y + 18),
        _money(datos.get("precio_m3")),
        font=_fuente(22),
        fill=NEGRO,
        anchor="ra",
    )
    draw.text(
        (ANCHO - MARGEN - 18, y + 18),
        _money(datos.get("subtotal")),
        font=_fuente(22),
        fill=NEGRO,
        anchor="ra",
    )
    y += 62
    y = _linea(draw, y)

    # Totales
    x_etiqueta = ANCHO - MARGEN - 360
    draw.text((x_etiqueta, y), "Subtotal", font=_fuente(20), fill=GRIS)
    draw.text((ANCHO - MARGEN, y), _money(datos.get("subtotal")), font=_fuente(20), fill=NEGRO, anchor="ra")
    y += 32
    draw.text((x_etiqueta, y), f"IVA {_cantidad(datos.get('iva_pct'))}%", font=_fuente(20), fill=GRIS)
    draw.text((ANCHO - MARGEN, y), _money(datos.get("iva_monto")), font=_fuente(20), fill=NEGRO, anchor="ra")
    y += 38
    draw.rectangle((x_etiqueta - 18, y - 6, ANCHO - MARGEN + 18, y + 52), fill=(254, 249, 195))
    draw.text((x_etiqueta, y + 8), "TOTAL", font=_fuente(24, True), fill=NEGRO)
    draw.text(
        (ANCHO - MARGEN, y + 6),
        _money(datos.get("total")),
        font=_fuente(30, True),
        fill=NEGRO,
        anchor="ra",
    )
    y += 84

    if datos.get("nota"):
        draw.text((MARGEN, y), "NOTA", font=_fuente(15, True), fill=GRIS)
        y += 24
        draw.text((MARGEN, y), str(datos["nota"]), font=_fuente(17), fill=GRIS)
        y += 36

    # Pie
    pie_y = ALTO - 120
    draw.line((MARGEN, pie_y, ANCHO - MARGEN, pie_y), fill=GRIS_CLARO, width=2)
    draw.text(
        (MARGEN, pie_y + 18),
        "Documento interno generado por Horminor. No sustituye la factura electronica del SRI.",
        font=_fuente(16),
        fill=GRIS,
    )
    draw.text(
        (ANCHO - MARGEN, pie_y + 18),
        "HORMINOR",
        font=_fuente(16, True),
        fill=NEGRO,
        anchor="ra",
    )

    salida = io.BytesIO()
    imagen.save(salida, format="PDF", resolution=150.0)
    return salida.getvalue()

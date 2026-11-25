from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import tiempo
from app.asistente import razonador, router
from app.cerebro import ejecutores
from app.services import cotizaciones


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setattr(razonador.proveedores, "disponible", lambda: False)
    monkeypatch.setattr(tiempo, "ahora", lambda: datetime(2026, 11, 24, 8, tzinfo=tiempo.ZONA))


@pytest.mark.asyncio
async def test_dos_cotizaciones_exigen_referencia_y_niego_envio_condicional(monkeypatch):
    asuntos = {
        "a": razonador.Asunto("cotizacion", "cotización de Taller Norte", "ESPERANDO_CONFIRMACION", "v1"),
        "b": razonador.Asunto("cotizacion", "cotización de Taller Sur", "ESPERANDO_CONFIRMACION", "v2"),
    }
    async def lectura(texto, *args):
        if texto.startswith("Volviendo"):
            return razonador.Lectura(
                intencion="Corrige la cotización nombrada", modo="continuar",
                tipo="cotizacion", opcion=1, opciones_plausibles=[1],
            )
        return razonador.Lectura(
            intencion="Falta una elección sin riesgo", modo="aclarar",
            opciones_plausibles=[1, 2] if texto.startswith("Corrige") else [],
        )

    monkeypatch.setattr(razonador, "_leer", lectura)
    contexto = {"foco": "b", "rol": "SUPERADMIN", "historial": []}
    ambiguo = await razonador.decidir("Corrige la cotización", asuntos, **contexto)
    assert ambiguo.modo == "aclarar"
    assert "Taller Norte" in ambiguo.pregunta and "Taller Sur" in ambiguo.pregunta
    assert (await razonador.decidir("¿Ya salió? Si no, envíala", asuntos, **contexto)).modo == "aclarar"
    assert (await razonador.decidir("No envíes la cotización", asuntos, **contexto)).modo == "aclarar"
    for prefijo in ("", "dictado: "):
        cambio = await razonador.decidir(
            prefijo + "Volviendo a la cotización de Taller Norte, cambia la razón social",
            asuntos, **contexto,
        )
        assert (cambio.modo, cambio.asunto) == ("continuar", "a")


@pytest.mark.asyncio
async def test_delegacion_y_contenido_del_mensaje_son_instrucciones_distintas(monkeypatch):
    async def lectura(texto, *args):
        if texto.startswith("Dile"):
            return razonador.Lectura(intencion="Comunica a Franco", modo="nuevo", tipo="recordatorio")
        return razonador.Lectura(intencion="Encarga a Secretaría", modo="nuevo", tipo="encargo")

    monkeypatch.setattr(razonador, "_leer", lectura)
    delegado = await razonador.decidir(
        "Que Secretaría agende la visita a Paz Molina", {},
        foco=None, rol="SUPERADMIN", historial=[],
    )
    assert delegado.modo == "nuevo" and delegado.tipo == "encargo"
    mensaje = await razonador.decidir(
        "Dile a Franco que Secretaría revisará el precio", {},
        foco=None, rol="SUPERADMIN", historial=[],
    )
    assert mensaje.modo == "nuevo" and mensaje.tipo == "recordatorio"


@pytest.mark.asyncio
async def test_chat_conserva_cotizacion_al_intercalar_recordatorio_y_visita(monkeypatch):
    actor = router.Actor(nombre="Julio", rol="SUPERADMIN", actor_id=str(uuid4()))
    conversacion = str(uuid4())
    dialogo = {}
    textos = {}
    borradores = []
    citas = []
    recordatorios = []
    historial = []

    class Pool:
        async def fetch(self, *args):
            return []

    pool = Pool()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(pool=pool)))
    monkeypatch.setattr(router.asyncpg, "Pool", Pool)

    async def actual(*args, **kwargs):
        return {"id": conversacion, "estado_dialogo_json": dialogo}

    async def guardar_estado(_pool, _hilo, *, asunto_id=None, asunto=None, **cambios):
        dialogo.update({k: v for k, v in cambios.items() if v is not None})
        if asunto_id:
            dialogo.setdefault("asuntos", {})[asunto_id] = asunto
            dialogo["foco_asunto"] = asunto_id

    async def texto_borrador(_pool, _hilo, borrador_id):
        return textos.get(borrador_id)

    async def interpretar(texto, *, contexto, borrador_previo_id=None, **kwargs):
        borrador = str(uuid4())
        borradores.append((borrador, texto, contexto, borrador_previo_id))
        textos[borrador] = (contexto + "\n" if contexto else "") + texto
        return {
            "borrador_id": borrador, "estado": "PENDIENTE_CONFIRMACION",
            "resumen": {"texto": "Cotización preparada"},
            "borrador": {"preguntas": [], "acciones": [{"accion_nombre": "crear_cotizacion_borrador"}]},
            "hechos": [{"clave": "cliente.nombre", "valor": "Taller Norte", "estado": "EXTRAIDO"}],
        }

    async def agendar(_pool, texto, *, datos_confirmados, **kwargs):
        assert kwargs["clave_gato"]
        citas.append(datos_confirmados)
        return {
            "estado": "OK", "mensaje": "Visita registrada",
            "cita": {"id": str(uuid4()), "fecha": datos_confirmados["fecha"], "estado": "CONFIRMADA"},
        }

    async def agendar_recordatorio(_biblio, **datos):
        recordatorios.append(datos)
        return SimpleNamespace(
            ok=True, nota="Recordatorio agendado",
            datos={"id": str(uuid4()), "fecha": "2026-11-25", "estado": "AGENDADO"},
        )

    async def vacio(*args, **kwargs):
        return []

    async def cargar(*args):
        return list(historial)

    async def turno(_pool, _hilo, _actor, _rol, pregunta, respuesta, _estado, **kwargs):
        historial.extend((
            {"role": "user", "content": pregunta}, {"role": "assistant", "content": respuesta},
        ))

    async def perfil(*args, **kwargs):
        return {"telefono_whatsapp": None}

    monkeypatch.setattr(router.conversaciones, "actual", actual)
    monkeypatch.setattr(router.conversaciones, "actualizar_estado", guardar_estado)
    monkeypatch.setattr(router.conversaciones, "texto_ultimo_borrador", texto_borrador)
    monkeypatch.setattr(router.conversaciones, "tocar", vacio)
    monkeypatch.setattr(router.memoria, "cargar", cargar)
    monkeypatch.setattr(router.memoria, "guardar", turno)
    monkeypatch.setattr(router.cerebro_bridge, "interpretar", interpretar)
    monkeypatch.setattr(router.comercial_bridge, "agendar", agendar)
    monkeypatch.setattr(router.recordatorios, "agendar_personal", agendar_recordatorio)
    monkeypatch.setattr(router, "exigir_modulo", perfil)
    monkeypatch.setattr(router, "resolver_perfil", perfil)

    lecturas = iter((
        {"modo": "nuevo", "tipo": "cotizacion"},
        {"modo": "nuevo", "tipo": "recordatorio", "datos": {
            "personal": True, "fecha": "mañana", "hora": "a las nueve", "mensaje": "llamar a Franco",
        }},
        {"modo": "confirmar", "tipo": "recordatorio", "opcion": 2},
        {"modo": "nuevo", "tipo": "visita", "datos": {"fecha": "jueves", "contacto": "Paz Molina"}},
        {"modo": "continuar", "tipo": "visita", "opcion": 3, "datos": {"hora": "A las diez de la mañana"}},
        {"modo": "confirmar", "tipo": "visita", "opcion": 3},
        {"modo": "continuar", "tipo": "cotizacion", "opcion": 1},
    ))

    async def lectura(*args):
        return razonador.Lectura(intencion="Resultado simulado del modelo", **next(lecturas))

    monkeypatch.setattr(razonador, "_leer", lectura)

    async def chat(texto):
        return await router.chat(router.MensajeIn(mensaje=texto), request, actor)

    await chat("dictado: Prepara una cotización para Taller Norte de 45 metros cúbicos FC-240 con 10% de descuento")
    aviso = await chat("Recuérdame mañana a las nueve llamar a Franco")
    assert "llamar a Franco" in aviso.respuesta and "09:00" in aviso.respuesta
    assert not recordatorios
    confirmado = await chat("Confirmado")
    assert "agendado" in confirmado.respuesta and len(recordatorios) == 1
    assert confirmado.operacion_agenda.estado == "AGENDADO"
    assert recordatorios[0]["mensaje"] == "llamar a Franco"
    assert recordatorios[0]["cuando"].hour == 9
    assert "destinatario" not in recordatorios[0]

    falta = await chat("El jueves quiero visitar a Paz Molina por lo de la planta")
    assert "¿A qué hora es la visita?" in falta.respuesta
    assert "¿A qué posible cliente" not in falta.respuesta
    hora = await chat("dictado: A las diez de la mañana")
    assert "2026-11-26" in hora.respuesta and "10:00" in hora.respuesta
    assert not citas
    visita = await chat("Confirmado")
    assert visita.operacion_agenda.fecha == date(2026, 11, 26)
    assert visita.operacion_agenda.estado == "CONFIRMADA"
    assert len(citas) == 1 and citas[0]["hora"] == "10:00"

    await chat("Volviendo a la cotización, cambia la razón social a Taller Norte S.A.")
    assert len(borradores) == 2
    assert borradores[1][3] == borradores[0][0]
    assert "45 metros cúbicos" in borradores[1][2] and "10% de descuento" in borradores[1][2]
    assert "llamar a Franco" not in borradores[1][2]
    assert len(dialogo["asuntos"]) == 3


@pytest.mark.asyncio
async def test_cotizacion_pasa_precio_descuento_al_servicio(monkeypatch):
    class Pool:
        async def fetchrow(self, *args):
            return {"numero": "PRUEBA", "total": Decimal("5868.45"), "cliente_nombre": "Taller Norte"}

    guardado = []

    async def alta(pool, body):
        guardado.append(body)
        return str(uuid4())

    monkeypatch.setattr(cotizaciones, "crear_cotizacion_borrador", alta)
    resultado = await ejecutores.crear_cotizacion_desde_accion(
        Pool(), creado_por="Julio",
        parametros={
            "cliente_id": str(uuid4()), "obra_direccion": "Referencia de prueba",
            "volumen_m3": "45", "resistencia": "FC-240", "forma_pago": "TRANSFERENCIA",
            "precio_m3": "126.00", "descuento_pct": "10",
        },
    )
    assert resultado.ok
    assert guardado[0].precio_m3 == Decimal("113.40")


@pytest.mark.asyncio
async def test_ignora_datos_inventados_y_no_confirma_un_asunto_fuera_de_foco(monkeypatch):
    asuntos = {
        "a": razonador.Asunto("cotizacion", "cotización de Taller Norte", "ESPERANDO_CONFIRMACION"),
        "b": razonador.Asunto("visita", "visita", "ESPERANDO_CONFIRMACION"),
    }

    async def confirmacion(*args):
        return razonador.Lectura(intencion="Supone una confirmación", modo="confirmar", opcion=1)

    monkeypatch.setattr(razonador, "_leer", confirmacion)
    contexto = {"foco": "b", "rol": "SUPERADMIN", "historial": []}
    assert (await razonador.decidir("Confirmado", asuntos, **contexto)).modo == "aclarar"

    async def invencion(*args):
        return razonador.Lectura(
            intencion="Completa la visita", modo="continuar", opcion=2,
            datos={
                "hora": "a las 12", "contacto": "Otro cliente", "fecha": "mañana",
                "personal": None, "razon_social": "Dato fuera del contrato",
            },
        )

    monkeypatch.setattr(razonador, "_leer", invencion)
    decision = await razonador.decidir("Mañana", asuntos, **contexto)
    assert decision.datos.fecha == "mañana"
    assert decision.datos.hora is None and decision.datos.contacto is None
    assert "razon_social" not in decision.datos.model_dump()


def test_contexto_acotado_con_mil_asuntos_conserva_referencia_antigua():
    asuntos = {
        str(indice): razonador.Asunto("cotizacion", f"cotización de Taller-{indice:04d}", "LIBRE")
        for indice in range(1000)
    }
    candidatos = razonador.asuntos_para_turno("Retoma la cotización de Taller-0007", asuntos, "999")
    assert len(candidatos) == razonador.LIMITE_ASUNTOS_POR_TURNO
    assert "999" in candidatos and "7" in candidatos

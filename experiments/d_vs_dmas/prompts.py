"""Prompts experimentales congelados. Versiones: a1-v1, a2-v1, a3-v1, d-v1, arb-v1.

No son los prompts operativos. No se ajustan con el corpus de evaluación.
"""

EXPERIMENT_VERSION = "d-vs-dmas-1.0"
PROMPT_VERSIONS = {
    "A1": "a1-v1",
    "A2": "a2-v1",
    "A3": "a3-v1",
    "D": "d-v1",
    "ARB": "arb-v1",
}

CLAVES_HECHOS = (
    "cliente.nombre",
    "cliente.cedula",
    "cliente.telefono",
    "cliente.ciudad",
    "cliente.referencia",
    "contacto.nombre",
    "contacto.telefono",
    "contacto.rol",
    "contacto.2.nombre",
    "contacto.2.telefono",
    "contacto.2.rol",
    "contacto.3.nombre",
    "contacto.3.telefono",
    "contacto.3.rol",
    "cotizacion.obra_direccion",
    "cotizacion.volumen_m3",
    "cotizacion.resistencia",
    "cotizacion.fecha_entrega",
    "cotizacion.hora_entrega",
    "cotizacion.plazo_entrega",
    "cotizacion.descuento_pct",
    "cotizacion.dias_trabajo",
    "cotizacion.precio_m3",
    "cotizacion.forma_pago",
    "cotizacion.enviar",
    "operacion.planta_movil",
    "pago.monto",
    "pago.forma",
    "pago.referencia",
    "pago.recibido",
    "pago.cuenta_destino",
    "traslado.cuenta_banco",
    "tarea.destinatario",
    "tarea.telefono",
    "tarea.mensaje",
    "tarea.cuando",
    "tarea.adjuntar_factura",
)

A1 = """Extraes HECHOS de un dictado de Horminor (hormigon premezclado, El Coca,
Ecuador). NO decides intenciones, ordenes, canales ni responsables.
Devuelve SOLO JSON.

Claves permitidas: {claves}.

Forma:
{"hechos":[{"clave":"...","valor":...,"tipo":"TEXTO|ENTERO|DECIMAL|FECHA|HORA|TELEFONO|CEDULA|BOOLEANO","estado":"EXTRAIDO|TENTATIVO|NO_DIJO","cita":"...","hablante":"SUPERADMIN|SECRETARIA|CLIENTE|TERCERO|NO_DETERMINADO"}],"faltantes":[],"ambiguedades":[]}

Reglas:
1. `cita` es copia exacta de un fragmento del texto.
2. No inventes ningun dato. Si no esta, no lo incluyas.
3. La duda afecta SOLO al dato que la sigue o precede: "creo que eran 30
   metros de hormigon de 240" marca TENTATIVO el volumen, NO la resistencia.
4. Una hora suelta ("a las seis") va en cotizacion.hora_entrega, no en fecha.
5. "plazo de dos meses", "en un mes" va en cotizacion.plazo_entrega como TEXTO.
6. `pago.recibido` true solo si el dinero ya entro; false solo si se declara que
   no ha entrado ("no ha pagado", "todavia no"); si no, no lo incluyas.
7. Un telefono de 10 digitos que empieza 09: cliente.telefono si es del cliente;
   contacto.telefono si es de un ingeniero/maestro/encargado; tarea.telefono si
   es el destinatario de un aviso.
8. No conviertas una descripcion en una orden.
"""

A2 = """Lees un dictado de Horminor y propones ORDENES y ASUNTOS.
No extraes cifras ni valores: solo el tipo de orden, quien la ejecuta, a quien
se comunica, el ambito, el medio, las citas y los datos que harian falta.
Devuelve SOLO JSON.

Tipos de orden: COTIZAR, ENVIAR_MENSAJE, DELEGAR, VERIFICAR, REGISTRAR,
CONSTANCIA, CONSULTAR, LLAMAR, COORDINAR.
Medio: WHATSAPP, LLAMADA, CRM, PRESENCIAL, NINGUNO.
Ambito: INTERNO, EXTERNO, MIXTO.
Ejecutor: HUMANO o MODULO_CRM. El Cerebro NO hace llamadas telefonicas: si el
dictado pide llamar, medio=LLAMADA y ejecutor=HUMANO.

Forma:
{"asuntos":[{"id":"A","citas":["..."]}],
 "ordenes":[{"asunto":"A","tipo":"DELEGAR","responsable_ejecucion":"SECRETARIA","destinatario_comunicacion":null,"ambito":"INTERNO","medio":"CRM","ejecutor":"HUMANO","datos_requeridos":["despachos"],"citas":["..."],"confianza":0.8}]}

Reglas:
1. Separa asuntos cuando cambia el tema, el destinatario o la accion pedida,
   aunque no haya "primero/segundo". No juntes dos instrucciones distintas.
2. Una mencion de datos no es una orden. "Tenemos una obra de 60 m3" no es
   COTIZAR; "preparen una cotizacion" si lo es.
3. Responsable de ejecucion y destinatario de comunicacion son distintos:
   "que secretaria llame al ingeniero" -> responsable=SECRETARIA,
   destinatario=INGENIERO, medio=LLAMADA, ejecutor=HUMANO.
4. "Que secretaria revise", "que bodega compruebe", "que me avisen" son
   internos: medio=CRM o NINGUNO, ambito=INTERNO, ejecutor=HUMANO.
5. "Enviar por WhatsApp", "mandarle un mensaje/recordatorio" -> ENVIAR_MENSAJE,
   medio=WHATSAPP, con destinatario si se nombra.
6. Si pide informacion ("cuales", "cuanto", "informe") sin ordenar cambios ->
   CONSULTAR.
7. Si pide dejar constancia de algo que NO se debe ejecutar -> CONSTANCIA.
8. Cada orden necesita al menos una cita literal que la sostenga. Sin cita, no
   emitas la orden.
9. No emitas valores numericos, telefonos, montos ni fechas.
10. Si no puedes determinar el tipo, no inventes: omite la orden.
"""

A3 = """Lees un dictado de Horminor y extraes RESTRICCIONES, CONDICIONES,
DEPENDENCIAS, PLAZOS, RECTIFICACIONES y REVOCACIONES. No extraes valores.
Devuelve SOLO JSON.

Tipos: PROHIBICION, CONDICION, DEPENDENCIA, PLAZO, RECTIFICACION, REVOCACION,
ACLARACION.
Alcance: ORDEN, ASUNTO, GLOBAL. GLOBAL solo si la cita contiene lenguaje global
("no hagas nada", "nada de eso", "todo queda suspendido"). Si la cita esta
dentro de un asunto, el alcance NO puede ser GLOBAL.
Referente: DIRECTO, DEMOSTRATIVO ("ese pago", "aquella obra"), ORDINAL ("lo
primero"), ANAFORA ("lo anterior", "eso"), IMPLICITO.

Forma:
{"restricciones":[{"tipo":"PROHIBICION","alcance":"ASUNTO","sujeto":null,"referente_texto":"ese pago","referente_tipo":"DEMOSTRATIVO","antes_de":null,"texto":"no autorizar despacho","citas":["..."],"ambiguo":false}],
 "rectificaciones":[]}

Reglas:
1. Toda restriccion necesita cita literal.
2. "No quiero que...", "no cobren", "no preparen", "sin cobrar", "hasta que no"
   son restricciones, no ordenes.
3. "Verificar el pago antes de autorizar el despacho" es DEPENDENCIA: el pago
   antes del despacho.
4. "Todavia no le envies nada hasta que yo confirme" es PROHIBICION (no enviar)
   con una CONDICION (hasta que confirme).
5. Si el referente es ambiguo (varios pagos, varias obras, varias ordenes),
   marca `ambiguo: true` y no elijas.
6. Una rectificacion reemplaza algo dicho antes ("la cotizacion, no, el
   recordatorio"): usa RECTIFICACION y cita la correccion.
7. No conviertas una restriccion en una orden.
"""

D = """Lees un dictado de Horminor y devuelves, en UNA sola lectura, ASUNTOS,
ORDENES y RESTRICCIONES. Devuelve SOLO JSON.

Forma:
{"asuntos":[{"id":"A","citas":["..."]}],
 "ordenes":[{"asunto":"A","tipo":"DELEGAR","responsable_ejecucion":"SECRETARIA","destinatario_comunicacion":null,"ambito":"INTERNO","medio":"CRM","ejecutor":"HUMANO","datos_requeridos":["despachos"],"citas":["..."],"confianza":0.8}],
 "restricciones":[{"tipo":"PROHIBICION","alcance":"ASUNTO","sujeto":"A","referente_texto":null,"referente_tipo":"DIRECTO","antes_de":null,"texto":"no cotizar","citas":["..."],"ambiguo":false}],
 "rectificaciones":[]}

Aplica estas reglas:
- Tipos de orden: COTIZAR, ENVIAR_MENSAJE, DELEGAR, VERIFICAR, REGISTRAR,
  CONSTANCIA, CONSULTAR, LLAMAR, COORDINAR.
- Medio: WHATSAPP, LLAMADA, CRM, PRESENCIAL, NINGUNO. El Cerebro no llama:
  si piden llamar, medio=LLAMADA, ejecutor=HUMANO.
- Separar asuntos por cambio de tema, destinatario o accion, sin ordinales.
- Una mencion de datos no es una orden.
- Responsable de ejecucion != destinatario de comunicacion.
- "Que secretaria/bodega/me avisen" es interno (medio CRM/NINGUNO).
- Restricciones con cita; GLOBAL solo con lenguaje global.
- Referentes "ese pago", "lo primero", "lo anterior": marca el referente y, si
  es ambiguo, `ambiguo: true`.
- No emitas valores numericos, montos, telefonos ni fechas en las ordenes.
- Toda orden y toda restriccion necesitan cita literal.
"""

ARB = """Eres arbitro de una discrepancia entre dos lecturas de un mismo dictado.
Recibes SOLO la discrepancia y las citas. No agregues ordenes nuevas.
Devuelve SOLO JSON:
{"decision":"LECTURA_1|LECTURA_2|POR_ACLARAR","cita":"...","motivo":"..."}

Reglas:
1. Elige la lectura que la cita sostiene literalmente.
2. Si ninguna cita resuelve la discrepancia, responde POR_ACLARAR.
3. No inventes datos ni ordenes.
"""

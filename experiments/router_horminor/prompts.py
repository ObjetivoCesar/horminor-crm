"""Prompts del router (prototipo). Versión: router-v1.

No son prompts operativos. El lector de hechos se reutiliza del experimento
D+ (A1). B lee el trabajo; C revisa malentendidos.
"""

from .model import ROLES

VERSION = "router-v1"

B_TRABAJO = """Lees un dictado de Julio Villavicencio, director de Horminor (hormigon
premezclado, El Coca, Ecuador). Tu tarea es entender QUE TRABAJO pide y para
quien, no ejecutar nada.

La operacion tiene tres responsables reales:
- JULIO: decide, autoriza dinero, compromete a la empresa.
- SECRETARIA: clientes, documentos, comunicaciones, pagos por verificar,
  seguimientos administrativos.
- JEFE_PLANTA: produccion, operarios, equipos, materiales, camiones, despachos,
  fundidas. Los operarios NO son usuarios del CRM.

Reglas:
1. Separa encargos por cambio de trabajo, destinatario o resultado esperado,
   aunque no haya "primero/segundo". No dupliques el mismo encargo.
2. Asigna responsable. Si Julio no lo dijo, propone SECRETARIA o JEFE_PLANTA
   cuando sea razonable y marca "responsable_sugerido": true. Si no puedes
   determinarlo, usa "POR_DEFINIR" y explica en "por_investigar".
3. "Chicos", "operarios", "planta", "fundida", "mezcladora", "camion",
   "despacho" -> JEFE_PLANTA. "Secretaria", "cliente", "documento", "pago",
   "comprobante", "cobranza", "contabilidad", "contadora" -> SECRETARIA.
4. Un dato que el responsable debe averiguar NO impide crear la tarea: ponlo en
   "por_investigar" (por ejemplo "volumen exacto", "numero de telefono",
   "fecha de entrega"). No pidas a Julio lo que secretaria puede averiguar.
5. "Que me avisen cuando termine" es el "resultado_esperado" del mismo encargo,
   no un segundo encargo.
6. "Prepara un WhatsApp/mensaje" sin orden de enviarlo: preparar_comunicacion =
   true y autorizado = false. No lo envies.
7. Si Julio cita lo que pidio un cliente y solo pide revisarlo o dejar
   constancia, el encargo es revisar/constatar: origen = "CITA_CLIENTE". No
   ejecutes la solicitud del cliente.
8. Si el dictado pide autorizar despacho, mover dinero o enviar algo externo,
   requiere_autorizacion = true. Solo autorizado = true si Julio lo autoriza
   explicitamente ("envialo", "mandalo", "autorizo", "si, despachen").
9. No emitas cifras, montos, telefonos ni fechas: el lector de hechos los
   aporta. Puedes describir "el volumen mencionado" o "la fecha que dijo".
10. Cada encargo necesita al menos una cita literal del dictado.

Devuelve SOLO JSON:
{"encargos":[{"titulo":"...","que_hacer":"...","responsable":"JULIO|SECRETARIA|JEFE_PLANTA|POR_DEFINIR","responsable_sugerido":true,"destinatario":null,"canal":"INTERNO|WHATSAPP|LLAMADA|NINGUNO","ambito":"INTERNO|EXTERNO|MIXTO","resultado_esperado":null,"plazo":null,"por_investigar":[],"requiere_autorizacion":false,"autorizado":false,"preparar_comunicacion":false,"origen":"DICTADO|CITA_CLIENTE","citas":["..."]}],
 "informacion_sin_encargo":[],"consultas":[],"constancias":[],"decisiones_julio":[]}
"""

C_REVISION = """Revisas un dictado de Horminor para detectar malentendidos antes de
proponer tareas. No bloqueas por defecto: ayudas a interpretar y a senalar lo
que Julio debe saber.

Busca:
- rectificaciones ("no, mejor...", "la cotizacion, no, el recordatorio");
- citas de terceros ("me dijo que...", "el cliente pide que...");
- prohibiciones ("no hagas", "no mandes", "no cobren");
- condiciones y dependencias ("hasta que...", "antes de...", "si...");
- contradicciones entre frases;
- autorizaciones explicitas ("envialo", "mandalo", "autorizo").

Para cada observacion indica:
- tipo: RECTIFICACION|CITA_TERCERO|PROHIBICION|CONDICION|DEPENDENCIA|CONTRADICCION|AUTORIZACION;
- objeto: texto copiado de aquello a lo que se refiere ("la cotizacion", "el
  despacho", "el pago de la obra La Pradera");
- referente_tipo: DIRECTO|DEMOSTRATIVO|ORDINAL|ANAFORA|IMPLICITO;
- prohibe_tarea: true SOLO si la prohibicion alcanza la tarea misma (por
  ejemplo "no preparen la cotizacion"); false si condiciona una operacion
  distinta (por ejemplo "no despachen hasta el pago");
- condiciona_operacion: true si condiciona despacho, envio externo o dinero;
- autoriza_ejecucion: true SOLO si Julio autoriza explicitamente ejecutar;
- ambiguo: true si no se puede saber a que se refiere;
- citas: fragmentos literales.

Devuelve SOLO JSON:
{"observaciones":[{"tipo":"...","objeto":"...","referente_tipo":"...","prohibe_tarea":false,"condiciona_operacion":false,"autoriza_ejecucion":false,"ambiguo":false,"texto":"...","citas":["..."]}]}
"""

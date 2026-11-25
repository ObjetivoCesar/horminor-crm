# Gato interno de HORMINOR · Skills actuales y propuesta para revisión

**24 de noviembre de 2026 · Documento de diseño para César, Julio y Secretaría.** En cada apartado, **Hoy** describe el comportamiento identificado en el repositorio y **Propuesta** describe lo que se quiere construir. Los diálogos son ejemplos ficticios para revisar las reglas.

Julio está en una obra, frente al cliente. Desde el CRM de su celular pregunta «¿alcanzamos a venir a las siete?». Necesita una respuesta en ese momento. Tal vez la respuesta termine el encargo. Tal vez el cliente acepte y Julio añada «entonces cámbiala». Gato debe reconocer la diferencia. Secretaría usa el mismo asistente desde su propio perfil.

## 1. Razonador · Entender el turno y elegir la herramienta

**Hoy.** El razonador recibe el texto, el rol, el historial reciente, los asuntos abiertos y sus preguntas pendientes. Usa un modelo de lenguaje cuando está disponible. Su salida principal elige un modo y un asunto para el turno. La interpretación está en Python. [Razonador actual](../services/core-api/app/asistente/razonador.py)

**Propuesta de skill.** Interpreta el lenguaje natural en contexto, tanto en un dictado como en una corrección por teclado. Por cada instrucción identifica quién habla, a quién o a qué se refiere, qué quiere averiguar o hacer y hasta dónde llega la autorización. Una frase puede contener varias instrucciones. «¿Ya salió? Si sigue pendiente, envíala» obliga a consultar el envío antes de decidir si corresponde actuar.

| Si ocurre esto | Qué debe hacer el razonador |
|---|---|
| Julio dice «César» y hay dos fichas plausibles | Preguntar «¿César Reyes o César Jaramillo?». Hasta resolverlo, conservar el turno en la conversación. |
| La escuela está identificada y tiene dos obras abiertas | Usar la referencia del diálogo. Si ambas siguen siendo posibles, preguntar por la obra antes de leer o modificar su entrega. |
| La búsqueda no devuelve coincidencia suficiente | Preguntar si figura con otro nombre o si es un cliente nuevo. Un alta explícita del perfil autorizado vuelve al sistema con el identificador del nuevo cliente. |
| Julio pregunta si puede ofrecer otra hora | Consultar Agenda en ese turno. Una consulta autoriza leer la disponibilidad. |
| Dice «si hay cupo, muévela» | Encargar a Agenda el cambio sujeto a disponibilidad. La frase ya autoriza esa operación para la reserva identificada. |
| Responde «sí» | Vincular la respuesta a la última pregunta concreta. Si aceptó llevar la planta, esa aprobación corresponde a la planta. |

**Entrega al extractor y a las operaciones:** pedido identificado, objetos a los que se refiere cada verbo, datos por aclarar y acciones solicitadas o condicionadas. Si hay una referencia ambigua, detener solo la acción que depende de ella.

## 2. Extractor · Determinar qué cambió y dónde corresponde guardarlo

**Hoy.** El extractor obtiene hechos con una cita de respaldo, recupera hechos de turnos previos y alimenta borradores versionados. En la prueba de continuidad, el sistema conservó el volumen y la dirección, pero asignó una aclaración de envío a otro encargo. Conservar las palabras y asignarlas al registro correcto son dos verificaciones distintas. [Extractor actual](../services/core-api/app/cerebro/extractor.py) · [Definición de hechos](../services/core-api/app/cerebro/hechos.py)

**Propuesta de skill.** Con la identidad resuelta, leer el historial de ese asunto e interpretar lo nuevo como alta, corrección, retiro o repetición. Cada cambio conserva su cita, el origen del turno y el identificador de destino. Los campos omitidos conservan su valor. La operación dueña del registro valida y persiste el cambio. Así el dato llega al expediente, la reserva o la tarea que corresponde y puede recuperarse mañana.

| Frase | Destino y alcance |
|---|---|
| «Este es el teléfono del encargado de esta losa» | Contacto de **esa obra**. Si además dice «envíasela ahí», asociar ese número como destinatario de esa propuesta. |
| «La entrega sigue a las diez. Envíale el PDF a las seis y cincuenta de la tarde» | Dos campos en dos objetos vinculados al pedido: entrega a las 10:00 y envío a las 18:50. Recuperar fecha y zona de Ecuador de su contexto o aclararlas si hay duda. |
| «Son los mismos 150 metros que te dije» | Ratificación del volumen del pedido vigente. Evitar crear otra obra u otra línea por la repetición. |
| «Recuérdame visitar la basílica, podría ser cliente» | Recordatorio personal. Una posibilidad comercial por sí sola no identifica a un cliente. |
| «La escuela me pagó 200 dólares» | Reporte atribuido al perfil que lo comunica, vinculado a la escuela identificada. Su destino operativo es un aviso a Secretaría. |

Si en un solo audio se habla de dos clientes, resolver el dueño de **cada** hecho. Una corrección del nombre en una cotización y un cambio de razón social en la ficha general tienen alcances diferentes.

## 3. Skills de operación · Reglas para llevar el encargo a efecto

**Hoy.** Ya existen servicios de CRM para clientes, agenda, cotizaciones, tareas y WhatsApp. El Cerebro conecta un conjunto concreto de acciones con ejecutores. El flujo de recordatorio personal espera confirmación. La skill escrita de PDF empieza con una solicitud armada y el envío del módulo toma el WhatsApp de la ficha. Las seis fichas siguientes son protocolos conversacionales propuestos sobre esa base. [Acciones conectadas](../services/core-api/app/cerebro/router.py) · [Skill actual del PDF](../.agents/skills/pdf-cotizaciones/SKILL.md) · [Envío actual de cotizaciones](../services/core-api/app/routers/cotizaciones.py)

**Regla común propuesta.** Una instrucción clara de Julio o Secretaría autoriza la operación que expresa, dentro de su perfil. Pedir un dato cuando falte para actuar, cuando haya dos destinos posibles o cuando el sistema encuentre un conflicto. Cada skill devuelve el resultado al razonador para contestar y al historiador para actualizar el asunto. Un reintento consulta el resultado anterior antes de repetir un efecto.

### Clientes y expedientes

- **Se activa** al identificar un cliente, buscar un antecedente o retomar una obra. Lee coincidencias en el CRM y recupera el expediente del cliente y la obra seleccionados.
- **Pregunta** si hay homónimos, dos escuelas de nombre parecido o dos obras compatibles. Usa primero lo ya resuelto en la conversación.
- **Devuelve** los identificadores y antecedentes pertinentes. Si el encargo incluía crear o actualizar la ficha, devuelve la referencia del registro guardado. Consultar una ficha no implica modificarla.

### Agenda y reservas

- **Se activa** ante una consulta de disponibilidad, una visita, una reserva o un cambio. «¿Estoy libre?» consulta la agenda del actor. «¿Podemos entregar?» comprueba la franja completa, los mixers y choferes necesarios y la presencia de Julio si la obra la requiere.
- **Consulta y actúa** mediante la Agenda existente. Una petición de cambio del cliente queda registrada como solicitud. «Cámbiala si hay cupo» permite mover la misma reserva al verificar disponibilidad. Si aparece un choque, preserva el compromiso anterior y ofrece una alternativa comprobada. Un recordatorio personal solo bloquea recursos cuando realmente los ocupa.
- **Devuelve** disponibilidad consultada o identificador y horario de la reserva efectivamente guardada. Leer compromisos ajenos para comprobar cupo nunca traslada al expediente de esta obra los detalles de otro cliente. [Agenda actual](../services/core-api/app/agenda/service.py)

### Cotizaciones

- **Se activa** con «prepárame una cotización» o una corrección a una propuesta vigente. Recupera cliente, obra, dirección, volumen, resistencia y precio aplicable. Mantiene separados lugar y hora de entrega, contacto de obra y destinatario del PDF.
- **Antes de cerrar el importe**, si los extras siguen abiertos, pregunta una vez «¿Hay algún gasto extra que quieras incluir?». Si se menciona una retroexcavadora o trabajo de madrugada, aclara monto y si se cobra al cliente. «Ninguno» resuelve la pregunta.
- **Prepara** la versión con precio, descuento, extras cobrables, IVA y validez. Verifica con aritmética decimal los importes que figuran en el documento. Un anticipo futuro figura como condición. Una cuenta de HORMINOR se obtiene de la configuración verificada. Si falta un precio aprobado para enviar, explica a Julio qué precio requiere aprobación y conserva la instrucción de envío pendiente.
- **Devuelve** identificador, versión y referencia del documento cuando exista. «Prepárala» termina con el documento. «Prepárala y mándasela al encargado» pasa a WhatsApp la versión concreta y el destinatario resuelto.

### WhatsApp

- **Se activa** para enviar, programar, consultar, sustituir o cancelar un envío. Lee el documento y su versión, el destinatario y teléfono autorizados, la fecha, la hora y la zona de Ecuador. Con dos documentos o destinatarios posibles, pregunta cuál.
- **Ejecuta** una sola orden de envío. Un cambio de PDF, número u hora requiere reconciliar la programación anterior. Si la aprobación llega después de la hora pedida, pregunta si se envía ahora o se elige otra hora. Si se pierde la respuesta del proveedor, consulta la operación antes de reintentar.
- **Devuelve** la evidencia disponible: registro del programador para «programada», respuesta del proveedor para «aceptada» y acuse de entrega para «entregada». Si Julio delegó el envío a Secretaría, el resultado inmediato es su tarea en bandeja.

### Recordatorios

- **Se activa** cuando el actor pide que Gato le recuerde algo. Recupera de quién es el recordatorio, qué debe recordar y cuándo. Conserva el vínculo a una obra si la mencionó.
- **Registra directamente** un recordatorio personal claro. «Recuérdame hoy a las cinco visitar la basílica» puede completarse en un turno cuando el horario sea inequívoco. Una notificación dirigida a otra persona requiere identificar el destinatario y el canal.
- **Devuelve** identificador, fecha, hora y texto guardados. Un turno posterior como «mejor a las seis» modifica ese recordatorio una vez resuelta la referencia.

### Tareas internas y avisos de dinero

- **Se activa** cuando Julio o Secretaría delegan trabajo y siempre que comuniquen un cobro, abono, pago u otro movimiento de dinero. Registra responsable, cliente o documento relacionado, encargo, plazo si se indicó y perfil que lo reportó.
- **Para dinero, la única ejecución de Gato es crear el aviso para Secretaría.** Conserva el monto reportado, la frase y el respaldo aportado. Secretaría verifica y registra por el proceso contable. Hasta entonces, el estado es «pendiente de verificación» y el saldo conserva su valor. Un «sí, ya pagó» añade evidencia al aviso existente.
- **Devuelve** el identificador de la tarea visible en bandeja. «Que Secretaría revise y se la envíe a Franco» crea una tarea para Secretaría. «Dile a Franco que Secretaría la revisará» encarga a WhatsApp comunicar ese mensaje. La primera instrucción no dispara además un envío directo.

## 4. Historiador · Recuperar y actualizar el historial de quien corresponde

**Hoy.** Gato guarda turnos, conversaciones, estado de diálogo y vínculos con borradores. Su redactor actual compone respuestas. El aporte externo propone un redactor de historial y pruebas de reconstrucción. Es material de diseño pendiente de integración y verificación. [Persistencia actual](../services/core-api/app/asistente/conversaciones.py) · [Redactor actual](../services/core-api/app/asistente/redactor.py) · [Antecedente de memoria](DECISION_GATO_MEMORIA_HISTORIAL.md)

**Propuesta de skill.** Al inicio, cuando el razonador resuelve la referencia, recupera el historial de **ese cliente y esa obra**, o el de la tarea o recordatorio identificado. Al cierre del turno, actualiza solo los asuntos afectados. Un pedido puede enlazar cotización, tarea, reserva y envío sin perder el identificador ni el estado de cada uno.

| Qué conserva | Ejemplo en el expediente de la losa |
|---|---|
| Quién comunicó qué y a qué se refería | Julio informó desde el CRM que el cliente pidió adelantar la entrega de las 09:00 a las 07:00. |
| Qué quedó autorizado | Julio pidió consultar cupo. La autorización para mover surge en el turno «adelántala». |
| Qué ocurrió y con qué evidencia | Agenda consultó cupo. Si después mueve la reserva, el horario vigente se obtiene del registro de esa reserva. |
| Qué queda por resolver | Si hubo choque, la solicitud de adelanto sigue pendiente. Si Julio dice «dejémosla a las nueve», se cierra esa solicitud. |

El código reconstruye hechos, decisiones y resultados desde los registros. El LLM puede expresarlos en un resumen breve para el razonador. Las correcciones conservan la cita original y su reemplazo. Las preguntas resueltas dejan de figurar como pendientes. Un fallo del programador, un corte de red o un resumen convincente jamás bastan para afirmar que se entregó un documento.

## Recorrido de revisión · Julio frente al cliente

| Turno | Herramienta y respuesta esperadas | Qué cambia en el historial |
|---|---|---|
| «Estoy en la losa de la escuela. ¿Podemos venir a las siete?» | Con la obra ya identificada, Agenda comprueba recursos. Si hay cupo: «Sí, tenemos cupo a las siete. Tu entrega sigue reservada a las nueve». | Se registra la consulta en esa obra. La reserva sigue a las 09:00. |
| «Al cliente le sirve. Adelántala». | Agenda vuelve a comprobar la franja al guardar. Si funciona: «La entrega quedó a las siete». Si otro compromiso tomó el cupo, explica el choque y conserva las nueve. | El historiador guarda el resultado real y la referencia de la reserva. |
| «Y recuérdame llamarlo esta tarde a las cinco». | Recordatorios crea el aviso personal de Julio vinculado a la obra y devuelve su registro. | La entrega y el recordatorio tienen identificadores y horarios propios. |
| «También me dijo que ya transfirió el anticipo». | Tareas deja el reporte en la bandeja de Secretaría: «Secretaría tiene el aviso para verificar la transferencia». | Se conserva lo reportado, el responsable y la tarea abierta. El registro contable depende de la verificación de Secretaría. |

**Criterios de revisión manual**

- [ ] Con dos clientes posibles, Gato resuelve la identidad antes de escribir. Puede retomar el asunto por teclado después de un audio.
- [ ] Repetir volumen o dirección mantiene un único pedido. Cambiar la hora del WhatsApp conserva la hora de entrega de la obra.
- [ ] Si el cliente pregunta por disponibilidad, Julio recibe una respuesta ahí mismo. Solo una instrucción de reservar o mover modifica Agenda.
- [ ] Cuando Julio pide un aviso de dinero, el resultado verificable es la tarea para Secretaría. Repetirlo en el mismo asunto no duplica la tarea.
- [ ] Al regenerar el resumen desde los registros se obtiene el mismo cliente, versión, autorización, resultado y pendiente por acción.

**Puntos operativos aún por ratificar:** quién puede aprobar un precio provisional para una propuesta concreta, si Secretaría puede enviar por su cuenta una propuesta ya aprobada y qué margen operativo exige la flota entre reservas. Julio y Secretaría podrán revisar esos puntos sin reabrir la decisión ya tomada sobre los avisos de dinero.

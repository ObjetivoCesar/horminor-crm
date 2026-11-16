# Corrección de `dictado_revocado` y verificación del audio de Díaz Sur

**Fecha:** 2026-11-16
**Alcance:** corrección puntual en el compilador del Cerebro actual. No toca el
router congelado, no agrega interfaces y no conecta Gato.

---

## 1. Defecto

`dictado_revocado()` comparaba marcas de revocación como **subcadenas** del
texto normalizado. La marca `"mejor no"` coincidía dentro de «mejor **nos**
abastecemos», una frase que no cancela nada. El resultado era una revocación
global falsa: el audio real de Díaz Sur (122 s) terminaba en `SIN_ACCIONES`.

## 2. Corrección

En `services/core-api/app/cerebro/compilador.py`:

1. Cada marca se compila como **expresión completa** con límites de palabra
   (`\b`), espacios flexibles y sin distinguir tildes ni mayúsculas. Así
   «mejor no» coincide con «mejor no», pero no con «mejor nos».
2. Se distingue la revocación **global** (`revocacion_global`) de la revocación
   **por encargo**. Solo las marcas que niegan toda la acción («no hagas nada»,
   «no haga nada», «no hagan nada») cortan el dictado completo.
3. Las demás marcas («mejor no», «déjalo», «no lo hagas») se evalúan contra el
   **texto propio de cada encargo**, que el compilador ya separaba. Un encargo
   revocado queda en `SIN_ACCIONES` y los otros siguen su curso.
4. La nota del extractor y el resumen distinguen el caso parcial: ya no dicen
   «no hay que hacer nada» cuando solo se revocó una parte.

No se cambió la lista de marcas, ni la estructura del borrador, ni las reglas de
dinero, permisos o confirmación.

## 3. Pruebas específicas

En `services/core-api/tests/test_v92_adversarial.py`:

| Prueba | Texto | Resultado |
|---|---|---|
| `test_mejor_nos_abastecemos_no_revoca_el_dictado` | «Mejor nos abastecemos de la planta de la Joya…» | No revoca; propone `crear_cotizacion_borrador` |
| `test_mejor_no_prepares_la_cotizacion_revoca_ese_encargo` | «Mejor no preparen la cotización del colegio Central.» | Revoca ese encargo; `SIN_ACCIONES` |
| `test_revocacion_parcial_conserva_los_otros_encargos` | «Primero… Segundo, mejor no preparen la cotización… Tercero…» | Conserva los encargos 1 y 3; el 2 queda `SIN_ACCIONES` |

**Suites:**

- `tests/test_v92_adversarial.py`: **25 passed**.
- Suite completa del CRM: **623 passed** (620 previas + 3 nuevas), 1 warning.

## 4. Verificación del audio real

- **Transcripción:** `37deb787-d140-44fb-80e4-078057dc34ca` (audio original de
  122 216 ms).
- **Frase que antes disparaba el falso positivo:** «…sería de gana estar
  recorriendo desde la planta hasta allá, **mejor nos abastecemos** ahí…».
- **Antes:** `SIN_ACCIONES` (revocación global falsa).
- **Después:** `REQUIERE_ACLARACION`, con **2 encargos** y **1 acción
  propuesta**.
- **Borrador nuevo:** `e133755d-db43-4257-9a50-c9dd8b1e325d`.
- **Extracción:** `0c2b0dc6-2b6b-468c-a12b-1330187930e7`.

### Lo que propone realmente

| Encargo | Estado | Contenido | Acciones |
|---|---|---|---|
| 1 | `REQUIERE_ACLARACION` | Contrato con Díaz Sur: 380 m³, FC-240, 13 % de descuento, entrega en un mes, fines de semana, planta móvil, dos contactos | `crear_cliente` (Dualsur) |
| 2 | `REQUIERE_ACLARACION` | Transferencia de 27 000 USD y recordatorio para pedirla | Ninguna: falta confirmar ingreso y destinatario |

**Preguntas abiertas:** dirección o referencia de la obra; cliente del encargo 2;
si los 27 000 USD ya entraron; a quién se envía el recordatorio.

**Lectura honesta:** el audio ya **no** se interpreta como revocación global,
pero tampoco produce una cotización completa. Propone crear el cliente y deja el
resto bloqueado por datos que el dictado no dio (dirección de obra y precio).
No se registró dinero ni se envió nada.

## 5. Evidencia conservada

- `experiments/router_horminor/evidencias/caso_diaz_sur_original.json` (estado
  anterior: `SIN_ACCIONES`, transcripción y sobre de la corrida original).
- `docs/evidencias/diaz_sur_122s_reinterpretado.json` (respuesta completa de la
  corrida corregida).
- `.agents/evidencias/correccion_revocacion_pytest.txt` (suite 623).

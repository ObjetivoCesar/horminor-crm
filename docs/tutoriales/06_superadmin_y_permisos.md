# Tutorial 06 — Superadmin y Permisos

## Qué hace

Es el centro de control para usuarios, caja chica, horarios de planta, recetas,
flota, precios, tasas y conteo de silos.

![Superadmin](assets/tutoriales/06_superadmin.png)

## Paso a paso

### Usuarios y accesos

1. Entrar a **Superadmin y WhatsApp**.
2. Pulsar la Action Card **Usuarios y accesos**.
3. Pulsar **+ Crear nuevo usuario**.
4. Completar nombre, rol base, WhatsApp opcional y modo de acceso.
5. Marcar al menos un módulo del checklist (10 opciones).
6. Guardar. El usuario aparece en **Perfiles y Accesos**.

### Probar una vista

1. En la fila del usuario, pulsar **Probar vista**.
2. El panel cambia de pestañas y acciones según el checklist.
3. En modo `SOLO_LECTURA`, los botones de mutación se ocultan y el backend
   responde `403 READ_ONLY_PROFILE` si se intenta forzar.
4. Para volver, usar el selector **Viendo como:** y elegir Julio base.

### Caja chica y horarios

1. Abrir la Action Card **Caja chica y horarios**.
2. Editar tope de gasto, tope de compra en efectivo y fondo base.
3. Editar apertura, cierre, duración, intervalo y días laborables.
4. Guardar. La ventanilla y la agenda lo leen en la siguiente petición.

### Recetas, flota y precios

1. Abrir la Action Card **Recetas, flota y precios**.
2. Editar cada receta en su fila: resistencia, consumos, saco, precio, IVA.
3. Editar cada mixer: código, placa, capacidad, chofer y activo.
4. Guardar recetas y guardar flota.

### Tasas y conteo de silos

1. Abrir la Action Card **Tasas y conteo de silos**.
2. Completar WACC, crecimiento, participación, impuesto, inflación y DSCR.
3. Registrar el stock físico contado de cada material.
4. Confirmar que el conteo es real antes de guardar.

## Preguntas frecuentes

**¿Por qué no me deja guardar un usuario?**
El checklist está vacío. Debe tener al menos un módulo marcado.

**¿Un usuario de solo lectura puede registrar pagos?**
No. La UI oculta las acciones y el backend rechaza con `READ_ONLY_PROFILE`.

**¿Dónde cambio el tope de caja chica?**
En Caja chica y horarios. El valor se guarda en `secretaria.pagos`.

**¿Las recetas se editan con JSON?**
No. La UI usa tablas con inputs. Los endpoints siguen aceptando JSON para
integraciones, pero el panel no lo muestra.

## Auditar en 60 segundos

1. Contar usuarios activos en `panel_users_acl`.
2. Verificar que cada perfil tenga al menos un módulo marcado.
3. Confirmar topes y horarios en `system_settings`.
4. Revisar que las recetas tengan precio y confirmación.
5. Revisar que el conteo físico tenga fecha (`ultimo_levantamiento_at`).

## Advertencias

- No crear usuarios genéricos sin nombre real.
- No marcar `superadmin_config` a perfiles operativos.
- No cambiar recetas confirmadas sin autorización de Julio.
- El login real sigue pendiente; esta etapa usa simulación con `X-Panel-User`.

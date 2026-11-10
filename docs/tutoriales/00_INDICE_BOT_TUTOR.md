# Tutorial 00 — Índice para el Bot de Asistencia

Este índice es la base de conocimiento del futuro bot de asistencia de Horminor.
Cada archivo explica un módulo del panel, el flujo operativo y cómo auditar sus
números en menos de 60 segundos.

> Estado: documentación operativa v6.6. No hay botones de tutorial en el panel
> todavía. Las capturas son placeholders hasta que se tome la evidencia real.

## Archivos

1. [Dashboard de Julio](01_dashboard_julio.md)
2. [Secretaría y Caja](02_secretaria_y_caja.md)
3. [Carpetas de Clientes](03_carpetas_clientes.md)
4. [Planta, Flota y Kardex](04_planta_flota_kardex.md)
5. [Banca y Mercado](05_banca_y_mercado.md)
6. [Superadmin y Permisos](06_superadmin_y_permisos.md)

## Reglas que el bot debe respetar

- No inventar precios, stock, teléfonos, RUC ni saldos. Si un dato está vacío,
  responder "sin definir" y señalar dónde se carga.
- No ejecutar pagos, compras, cierres ni cambios de permisos sin confirmación
  explícita del usuario.
- Para auditar, siempre indicar la ruta, el filtro usado y la fecha de consulta.
- Si el usuario pregunta por un número, primero revisar el módulo dueño de ese
  número y luego cruzar con el cierre o el ledger.

## Convención de capturas

Las imágenes se guardarán en `assets/tutoriales/`. Mientras no existan, los
Markdown dejan el placeholder con el nombre exacto que debe usarse.

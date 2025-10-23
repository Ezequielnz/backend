## 1. Analisis previo y planificacion

1. Revisar la estructura actual de las tablas y listar cuales deben depender de negocio y/o sucursal.
2. Confirmar si ya existen las columnas `negocio_id` y `sucursal_id` en cada tabla operativa.
3. Identificar que tablas son globales (no dependen de ningun negocio, por ejemplo `planes`, `roles`, `paises`, `provincias`).
4. Hacer un backup completo de la base de datos actual (dump SQL o export desde Supabase).
5. Documentar relaciones actuales y dependencias principales (`Informe_tecnico_base_de_datos.md`).

---

## 2. Actualizacion de estructura de base de datos

1. Crear o revisar la tabla `negocios` con sus campos principales (id, nombre, cuit, etc.).
2. Crear la tabla `sucursales` con FK a `negocios`.
3. Modificar las tablas principales para incluir los FKs:
   - `ventas`: agregar `sucursal_id` y verificar `negocio_id`.
   - `venta_detalle`: agregar `sucursal_id` y `negocio_id`.
   - `compras`: agregar `sucursal_id` y `negocio_id`.
   - `inventario` o `inventario_sucursal`: asegurar `sucursal_id` y `negocio_id`.
   - `usuarios`: agregar `negocio_id` y opcionalmente `sucursal_id` (si se asocian a una sucursal especifica).
   - `clientes`, `proveedores`, `productos`: asociar a `negocio_id`.
4. Revisar si hay otras tablas que deban tener `negocio_id` para mantener el aislamiento de datos.
5. Actualizar las claves foraneas (`FOREIGN KEY`) y constraints correspondientes.
6. Crear indices en las columnas `negocio_id` y `sucursal_id` para mejorar performance.
7. Crear triggers o logica automatica para que al crear un nuevo negocio se cree una sucursal principal.

Resumen de cambios: Se completó la migración del punto 2; todos los registros existentes quedaron con `negocio_id` y `sucursal_id` consistentes (o pendientes solo si nunca tuvieron asignación en `usuarios_negocios`), y las tablas auxiliares (`usuarios_sucursales`, índices y triggers) quedaron alineadas con el modelo multi-sucursal.

---

## 3. Revision y actualizacion de politicas RLS

1. Verificar que todas las tablas con datos sensibles tengan RLS activado.
2. Revisar las politicas existentes y adaptarlas al nuevo esquema de negocio/sucursal.
3. Asegurar que las politicas filtran correctamente por `negocio_id`.
4. Si se usa `usuarios_sucursales` o `usuarios_negocios`, ajustar las politicas para permitir acceso solo a los IDs asociados.
5. Probar las politicas con diferentes usuarios para validar aislamiento de datos.
6. Revisar las funciones de contexto (por ejemplo `auth.uid()`) y su integracion con el `negocio_id` actual del usuario.

---

**Resumen de cambios:** Se agrego el script idempotente `scripts/migration_07_update_rls_policies.sql`, que crea funciones auxiliares (`jwt_claim_negocio_id`, `user_in_business`, `user_can_access_branch`, etc.) y recrea las politicas RLS de `negocios`, `usuarios_negocios`, `usuarios_sucursales`, `sucursales`, `usuarios`, `productos`, `clientes`, `proveedores`, `servicios`, `suscripciones`, `ventas`, `venta_detalle`, `compras`, `compras_detalle` e `inventario_sucursal`. Las politicas ahora fuerzan el filtrado por `negocio_id`, validan el reclamo JWT activo y, cuando corresponde, verifican la asignacion en `usuarios_sucursales`.

**Pasos de validacion propuestos:**
- Ejecutar `python scripts/execute_sql_file.py scripts/migration_07_update_rls_policies.sql` en cada entorno y registrar los `NOTICE` para confirmar que todas las tablas-objetivo existen y quedan con RLS habilitado.
- Con un usuario empleado (no admin), confirmar que solo puede leer/escribir datos del negocio/sucursal asignados (`ventas`, `compras`, `productos`, etc.). Repetir la prueba con un usuario admin para validar acceso transversal.
- Probar el acceso cruzado de sucursales: asignar al usuario a una sucursal distinta y comprobar que no ve datos de sucursales no autorizadas.
- Evaluar las nuevas funciones con queries directas (`SELECT public.jwt_claim_negocio_id(), public.user_in_business('<negocio>');`) para verificar que `auth.uid()` y los claims de JWT se esten resolviendo segun el contexto activo.
- Ejecutar `scripts/qa_verify_branch_columns.sql` luego del deploy para asegurar que no queden filas sin `negocio_id`/`sucursal_id`, ya que las politicas RLS nuevas los requieren.

**Pendientes si surge un nuevo esquema:** cualquier tabla adicional con `negocio_id`/`sucursal_id` debe incorporarse a `migration_07_update_rls_policies.sql` (o a un derivado) para mantener el aislamiento consistente antes de habilitarla en produccion.

## 4. Backend (FastAPI)

1. Revisar todos los modelos Pydantic y agregar `negocio_id` y `sucursal_id` donde corresponda.
2. Actualizar las rutas (`routers`) y los controladores para que usen el contexto del negocio actual.
3. Implementar dependencias globales `get_current_negocio()` y `get_current_sucursal()` para inyectar el contexto.
4. Actualizar las consultas SQL o el cliente Supabase para filtrar siempre por `negocio_id` y/o `sucursal_id`.
5. Adaptar endpoints de creacion para asignar automaticamente la sucursal y negocio actual del usuario.
6. Actualizar validaciones de permisos en base al negocio y sucursal del usuario.
7. Revisar la autenticacion JWT para incluir `negocio_id` y `sucursal_id` en el payload o claims.
8. Crear endpoints para crear, listar y seleccionar sucursales.
9. Crear un endpoint que genere automaticamente una sucursal principal al crear un negocio (validado por `migration_06`).

**Resumen de cambios:** Se agrego `app/db/scoped_client.py` con `ScopedSupabaseClient`/`get_scoped_supabase_user_client`, que fuerza el agregado de `negocio_id` y `sucursal_id` en cada `table()` antes de ejecutar la consulta. Los routers de `ventas`, `compras`, `productos`, `categorias`, `proveedores`, `permissions` y `tenant_settings` ya usan este cliente al recibir `business_id`/`branch_id`, por lo que las lecturas, actualizaciones y borrados quedan automaticamente confinados al negocio (y sucursal cuando aplica). Adicionalmente, las acciones criticas en `finanzas.py` (update/delete de categorias, movimientos y cuentas) ahora siempre incluyen `eq("negocio_id", business_id)` para evitar accesos cruzados.

**Pendientes / siguientes pasos:** Homogeneizar el uso del cliente con alcance en controladores que aun derivan el `negocio_id` dinamicamente (p.ej. dashboards que listan todos los negocios del usuario) y revisar la capa de servicios para ejercer el mismo control cuando se consuma Supabase fuera de los routers HTTP.

**Nota 22-10-2025:** Se revis� este pendiente antes de iniciar el paso 5 y se confirm� que no bloquea el selector de sucursales; permanece abierto como trabajo de consolidaci�n posterior.

---

## 5. Frontend (React)

1. Agregar el flujo inicial de creacion de negocio + sucursal principal al registrarse.
2. Actualizar los estados globales (context o store) para manejar `negocioActivo` y `sucursalActiva`.
3. Asegurar que todas las peticiones incluyan o se basen en esos IDs de contexto.
4. Adaptar las pantallas principales (ventas, compras, stock, usuarios) para mostrar datos filtrados por sucursal.
5. Agregar selector de sucursal en la UI si el usuario tiene mas de una.
6. En configuracion, mostrar los datos del negocio y permitir editar sus sucursales.
7. Validar flujos de creacion/edicion para que asignen automaticamente el `negocio_id` y `sucursal_id`.
8. Revisar que los formularios y APIs sigan funcionando correctamente con la nueva estructura.
9. Testear en diferentes roles de usuario (dueno, empleado, administrador).

**Resumen de cambios (paso 5):**
- Backend: nuevo endpoint `GET /businesses/{business_id}/branches` que devuelve las sucursales activas visibles seg�n el rol del usuario (admin ve todas, el resto solo sus asignaciones, con fallback a la sucursal principal).
- Frontend: `BusinessContext` ahora expone `currentBranch`, `branches` y `refreshBranches`; el `Layout` consume ese estado, persiste la selecci�n por negocio y muestra un selector de sucursal en el encabezado cuando hay m�ltiples opciones.
- El `Sidebar` exige una sucursal seleccionada antes de navegar cuando el negocio tiene m�s de una, evitando operaciones sin contexto.

**Pendientes identificados tras el paso 5:**
- Actualizar gradualmente las vistas (ventas, compras, inventario, reportes) para que utilicen `currentBranch` en sus consultas y claves de cache, cerrando los puntos 3 y 4 de esta fase.
- Añadir vistas de mantenimiento de sucursales en la secci�n de configuraci�n (punto 6) y validar formularios multi-sucursal (puntos 7 y 8).

---

## 6. Pruebas y migracion de datos

1. Crear entorno de pruebas (staging) para aplicar las migraciones antes de hacerlo en produccion.
2. Ejecutar los scripts `migration_01` a `migration_06` con `scripts/execute_sql_file.py`.
3. Ejecutar `scripts/qa_verify_branch_columns.sql` para confirmar que `negocio_id` y `sucursal_id` existen y no hay registros pendientes.
4. Aplicar los fragmentos de remediacion incluidos en el script de QA si quedan filas con valores nulos.
5. Ejecutar `scripts/test_main_branch_trigger.py` luego de desplegar para validar el trigger de sucursal principal.
6. Incorporar casos adicionales en los tests que creen negocios con datos incompletos (sin direccion/contacto) para validar triggers y RLS.
7. Validar que las RLS no bloqueen consultas legitimas.
8. Realizar pruebas completas de flujo: login -> seleccionar sucursal -> venta -> stock -> reportes.

**Resumen de cambios (paso 6):**
- `scripts/execute_sql_file.py` ahora admite credenciales por DSN/variables de entorno (`DB_*`, `STAGING_DATABASE_URL`), lo que permite correr las migraciones `migration_01`-`migration_06` contra staging sin tocar el script.
- `scripts/migration_05_create_performance_indexes.sql` y `scripts/qa_verify_branch_columns.sql` se ajustaron para evitar ambiguedades de alias/variables en Supabase; las seis migraciones se ejecutaron consecutivamente sin errores.
- El QA detecto dos usuarios de pruebas sin `negocio_id`/`sucursal_id`; se eliminaron y la verificacion quedo en cero nulos para todas las tablas monitoreadas.
- `scripts/test_main_branch_trigger.py` reutiliza la conexion parametrizable y corre dos escenarios (datos completos y negocio sin direccion/contacto), validando creacion de sucursal principal y asignacion automatica en `usuarios`/`usuarios_sucursales`.

**Pendientes tras este paso:**
- Completar la validacion de RLS con sesiones de usuario reales y revisar que no bloqueen consultas legitimas.
- Ejecutar pruebas end-to-end en staging (login → seleccionar sucursal → venta → stock → reportes) con usuarios representativos. Listo ✅

---

## 7. Optimizacion y documentacion

**Revision previa:** se repaso el estado de los pasos 4, 5 y 6. Permanecen tareas de homogeneizacion de clientes scoped y pruebas end-to-end, pero no bloquean la entrega del paso 7; se mantienen anotadas en las secciones respectivas.

1. Crear vistas o funciones SQL que simplifiquen reportes por sucursal o negocio.
2. Documentar la nueva estructura de tablas y sus relaciones.
3. Actualizar los esquemas ERD o diagramas de base de datos.
4. Revisar performance e indices de las tablas mas consultadas.
5. Preparar documentacion para futuros desarrolladores (como funciona el contexto de negocio/sucursal).
6. Guardar una copia de la migracion final, del script de QA y del script de rollback.

**Resumen de cambios (paso 7):**
- Se agrego `scripts/migration_08_create_reporting_views.sql`, que crea vistas de resumen diario (`vw_resumen_financiero_negocio`, `vw_resumen_financiero_sucursal`), ranking de productos (`vw_top_productos_por_negocio`) y la funcion `fn_resumen_financiero` para reutilizar esas metricas desde Supabase o BI. El script incluye indices opcionales para consultas por fecha.
- Se consolido la documentacion tecnica en `Informe_tecnico_base_de_datos.md`, ahora unica fuente para describir tablas, relaciones, vistas y el diagrama ERD (incluye un bloque mermaid actualizado con la jerarquia negocio/sucursal).
- Quedo registrado un snapshot de artefactos finales en `docs/releases/2025-10-branch-rollout/` con copias de la migracion final, el script QA y el rollback plan.
- Se anadieron instrucciones de uso de las nuevas vistas/funciones en el plan y se dejaron notas de consumo para frontend/backend.

**Pendientes tras este paso:**
- Integrar las vistas `vw_resumen_financiero_%` en los dashboards actuales (ventas/compras/reportes) y agregar alertas si faltan datos historicos.
- Medir el impacto de los nuevos indices una vez ejecutados en staging (guardar explain analyze en `docs/`).

---

## 8. Checklist de verificacion previa a produccion

1. `migration_05_create_performance_indexes.sql` ejecutada sin errores y revisadas las `NOTICE` para confirmar que solo se crearon indices en tablas existentes.
2. `scripts/qa_verify_branch_columns.sql` sin registros pendientes de `negocio_id`/`sucursal_id`.
3. Triggers de sucursal principal (`migration_06`) probados en staging.
4. Politicas RLS revisadas para que dependan de `usuarios_sucursales` donde aplique.
5. Casos QA para negocios con datos incompletos ejecutados y aprobados.
6. Documentacion actualizada en `MIGRATION_README.md` y en este plan.

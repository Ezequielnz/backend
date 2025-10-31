## 1. Analisis previo y planificacion

1. Revisar la estructura actual de las tablas y listar cuales deben depender de negocio y/o sucursal.
2. Confirmar si ya existen las columnas `negocio_id` y `sucursal_id` en cada tabla operativa.
3. Identificar que tablas son globales (no dependen de ningun negocio, por ejemplo `planes`, `roles`, `paises`, `provincias`).
4. Hacer un backup completo de la base de datos actual (dump SQL o export desde Supabase).
5. Documentar relaciones actuales y dependencias principales (`Informe_tecnico_base_de_datos.md`).

### Diagnóstico actual (multi-sucursal a octubre 2025)

- **Base de datos:** existen `negocios`, `sucursales`, `usuarios_sucursales`, `usuarios_negocios` e `inventario_sucursal`, lo que permite aislar datos por sede. El inventario se modela únicamente a nivel de sucursal y los catálogos (`productos`, `servicios`) están anclados al `negocio_id` sin distinción de sucursal; no hay una tabla de configuración que defina si el stock o los servicios se gestionan de forma centralizada.
- **Backend:** el `ScopedSupabaseClient` y los endpoints actuales exigen `negocio_id` y `sucursal_id` para ventas, compras e inventario. Existe un `BranchService` básico (ver paso 5) que lista sucursales y asigna contexto, pero no hay endpoints publicados para crear/editar sucursales ni para definir modos de inventario/servicio o transferencias de stock.
- **Frontend:** `BusinessContext` consume `GET /businesses/{business_id}/branches` y permite seleccionar una sucursal activa, pero la sección de configuración todavía no expone formularios para crear sucursales, tampoco hay toggles para decidir inventario centralizado vs distribuido, ni vistas para transferencias de stock.
- **Operación actual:** cada movimiento de inventario se descuenta de `inventario_sucursal` de la sucursal activa. Al compartir productos por `negocio_id`, duplicar un producto en dos sucursales requiere workarounds manuales y los ids permanecen globales. No existen flujos formales de transferencia entre sucursales; cuando se necesita mover stock se hace con ajustes manuales en ventas/compras.

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

### Configuracion multi-sucursal y modos de operacion

- **Tabla `negocio_configuracion`:** nueva tabla 1:1 con `negocios` que persiste las preferencias del dueno. Columnas clave: `inventario_modo` ('centralizado' | 'por_sucursal'), `servicios_modo` ('centralizado' | 'por_sucursal'), `catalogo_producto_modo` ('compartido' | 'por_sucursal'), `permite_transferencias` (`boolean`), `transferencia_auto_confirma`, `default_branch_id` y un `metadata` JSONB para flags futuros. La migracion debe poblarla con valores por defecto ('por_sucursal' + transferencias activas) y crear un trigger para garantizar que cada negocio posea registro.
- **Catalogo de productos y servicios:** mantener `productos` y `servicios` a nivel de negocio, pero agregar tablas puente `producto_sucursal` y `servicio_sucursal` con columnas por sucursal (`precio`, `estado`, `sku_local`, `stock_minimo`, `visibilidad`). Cuando `catalogo_producto_modo` = 'compartido', las entradas se crean automaticamente con `sku_local` = `sku` y banderas de sincronizacion; cuando es 'por_sucursal', se habilita la creacion de productos exclusivos validando unicidad por (`negocio_id`, `sucursal_id`, `sku_local`).
- **Inventario centralizado:** agregar `inventario_negocio` (stock agregado por negocio/producto) y una vista `inventario_visible` que, segun `inventario_modo`, devuelva stock por sucursal (`inventario_sucursal`) o stock consolidado replicado en todas las sucursales. Las operaciones de venta/compra deberan apuntar a `inventario_visible` via funciones para respetar la preferencia. Triggers AFTER INSERT/UPDATE sincronizan `inventario_negocio` con `inventario_sucursal` cuando el negocio cambia de modo.
- **Transferencias de stock:** crear tablas `stock_transferencias` (`id`, `negocio_id`, `origen_sucursal_id`, `destino_sucursal_id`, `estado` ['borrador', 'confirmada', 'cancelada', 'recibida'], `creado_por`, `aprobado_por`, `metadata`) y `stock_transferencias_detalle` (`transferencia_id`, `producto_id`, `cantidad`, `unidad`, `lote`). Incluir columnas `inventario_modo_source`/`inventario_modo_target` para validar que la accion respete la configuracion.
- **Sincronizacion de sucursales nuevas:** extensiones a los triggers existentes (migration_06) para que, al crear una sucursal, se llenen `producto_sucursal`, `servicio_sucursal` y se repliquen los parametros del catalogo cuando el modo sea `compartido`. Para negocios centralizados, duplicar el stock base desde `inventario_negocio` con stock inicial cero o configurable.
- **Migraciones de datos:** crear scripts idempotentes (`migration_08a_create_branch_mode_structures.sql` + `migration_08_backfill_branch_catalog.sql`) que primero levanten las nuevas estructuras (`negocio_configuracion`, `producto_sucursal`, `servicio_sucursal`, `inventario_negocio`, `stock_transferencias`) y luego generen los datos derivados (configuración por negocio, backfill de catálogos, consolidación de inventario y recalculo de `usuarios_sucursales`). Incluir tareas de limpieza para SKU duplicados y un paso para recalcular usuarios_sucursales.
- **Indices y constraints:** indices compuestos en (`negocio_id`, `inventario_modo`) y (`negocio_id`, `sucursal_id`, `producto_id`) para acelerar filtros y RLS; checks que eviten transferencias con sucursales iguales; FOREIGN KEY hacia `negocios` y `sucursales` con ON DELETE CASCADE.

Resumen de cambios: Se complet? la migraci?n del punto 2; todos los registros existentes quedaron con `negocio_id` y `sucursal_id` consistentes (o pendientes solo si nunca tuvieron asignacion en `usuarios_negocios`), y las tablas auxiliares (`usuarios_sucursales`, ?ndices y triggers) quedaron alineadas con el modelo multi-sucursal.

---

## 3. Revision y actualizacion de politicas RLS

1. Verificar que todas las tablas con datos sensibles tengan RLS activado.
2. Revisar las politicas existentes y adaptarlas al nuevo esquema de negocio/sucursal.
3. Asegurar que las politicas filtran correctamente por `negocio_id`.
4. Si se usa `usuarios_sucursales` o `usuarios_negocios`, ajustar las politicas para permitir acceso solo a los IDs asociados.
5. Probar las politicas con diferentes usuarios para validar aislamiento de datos.
6. Revisar las funciones de contexto (por ejemplo `auth.uid()`) y su integracion con el `negocio_id` actual del usuario.
### Extensiones para configuraciones multi-sucursal

- Politicas para `negocio_configuracion`: lectura permitida a todo usuario asociado al negocio, pero actualizaciones restringidas a roles 'owner' y 'admin'. Usar un helper `user_can_manage_business_settings()` que combine `user_in_business` con `permiso_configuracion`.
- Tablas puente `producto_sucursal` y `servicio_sucursal`: RLS debe cruzar `negocio_id` + `sucursal_id` con `user_can_access_branch`. Para el modo 'compartido', permitir inserciones automaticas desde triggers (`auth.uid() = owner`) y forzar `WITH CHECK` que valide `catalogo_producto_modo` en `negocio_configuracion`.
- Tabla `inventario_negocio`: activar RLS con filtros por `negocio_id`; exponer select a empleados solo si el modo de inventario es 'centralizado'. Crear una funcion `user_can_read_central_inventory(negocio_id)` que combine configuracion + permisos de sucursal.
- Vista materializada o tabla `inventario_visible`: si se implementa como vista, hereda politicas de las tablas base; si es tabla intermedia, replicar el filtro doble (`negocio_id` + sucursales asignadas) y negar UPDATE/DELETE directos (solo funciones certificadas).
- `stock_transferencias` y `stock_transferencias_detalle`: dos capas de politicas: (a) usuarios de la sucursal origen con permiso de transferencia pueden crear/borrador; (b) usuarios de la sucursal destino pueden leer y marcar como recibidas. Los administradores del negocio mantienen acceso total. Usar `WITH CHECK` para validar que origen y destino pertenecen al mismo negocio y que `permite_transferencias` esta activo.
- Agregar funciones auxiliares (`user_can_manage_transfers`, `negocio_usa_catalogo_compartido`) al script `migration_07_update_rls_policies.sql` y re-ejecutarlo para versionar las nuevas politicas.


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

### Servicios y endpoints para modos centralizado/distribuido

- Exponer `GET/PUT /businesses/{business_id}/branch-settings` desde un `BranchSettingsService`. Este servicio lee/escribe en `negocio_configuracion`, propaga cambios al cache (`BusinessContextCache`) y dispara webhooks internos para notificar al frontend de un cambio de modo.
- Ampliar `POST /businesses/{business_id}/branches`/`PATCH /branches/{branch_id}` para consumo directo del frontend. La creacion debe envolver una transaccion que inserte la sucursal, rellene `producto_sucursal`/`servicio_sucursal` segun el modo activo y genere registros en `usuarios_sucursales` para dueno/admin.
- Ajustar `ScopedSupabaseClient` para leer `inventario_modo` y `catalogo_producto_modo` desde `BranchSettingsCache`. Si el negocio opera en modo centralizado, las consultas a inventario deben apuntar a funciones `select_central_inventory()` que devuelvan stock consolidado sin exigir `sucursal_id`.
- Crear un `StockTransferService` con rutas `POST /stock-transfers`, `POST /stock-transfers/{id}/confirm`, `POST /stock-transfers/{id}/receive`, `DELETE /stock-transfers/{id}`. El servicio valida `permite_transferencias`, controla estados y publica eventos a `ActionWorker` para notificar movimientos.
- Actualizar los casos de uso de productos/servicios (`ProductService`, `ServiceService`) para que, segun `catalogo_producto_modo`, creen registros en `producto_sucursal` o permitan productos exclusivos. Incluir un comando de sincronizacion (`sync_branch_catalog.py`) que clona o agrega registros cuando el negocio cambia de modo.
- Inyectar la configuracion de sucursal en `Action`/`Task` workers via `BusinessContextDep`, agregando claims `branch_mode` y `shared_catalog` al JWT interno para que los workers respeten la configuracion al crear tareas automatizadas.
- Extender los esquemas Pydantic (`BranchSettings`, `StockTransferCreate`, `StockTransferUpdate`) y validar campos como `default_branch_id`, `allow_cross_branch_services` o `auto_confirm_transfers`.
### Feature flag rollout y coordinacion cross-team

- Sync backend/frontend confirmado para 29-10-2025 11:00 (responsables backend @leo, frontend @agus). Secuencia acordada: migration_08_backfill_branch_catalog.sql -> deploy backend -> deploy frontend -> habilitacion del feature flag.
- El feature flag branch_inventory_modes vivira en app/core/feature_flags.py y protegira los endpoints /branch-settings; el frontend lo consultara con useFeatureFlag('branch_inventory_modes') para ocultar la configuracion cuando este deshabilitado.
- docs/ROADMAP_BRANCH_AWARE_ROLLOUT.md (seccion FF rollout plan) ya incluye ventana de cambio, responsables, checklist de rollback y orden de validaciones QA.
- QA fue notificado en #qa-multi-sucursal; usaran scripts/simulate_inventory_mode_switch.py durante la ventana de staging para certificar que el modo centralizado replica el stock antes de solicitar la activacion del flag en produccion.



**Resumen de cambios:**
- Se agrego `app/db/scoped_client.py` con `ScopedSupabaseClient`/`get_scoped_supabase_user_client`, que fuerza el agregado de `negocio_id` y `sucursal_id` en cada `table()` antes de ejecutar la consulta. Los routers de `ventas`, `compras`, `productos`, `categorias`, `proveedores`, `permissions` y `tenant_settings` ya usan este cliente al recibir `business_id`/`branch_id`, por lo que las lecturas, actualizaciones y borrados quedan automaticamente confinados al negocio (y sucursal cuando aplica). Adicionalmente, las acciones criticas en `finanzas.py` (update/delete de categorias, movimientos y cuentas) ahora siempre incluyen `eq("negocio_id", business_id)` para evitar accesos cruzados.
- Se incorporo `BusinessScopedClientDep`/`BranchScopedClientDep` como dependencia comun en FastAPI; `clientes`, `servicios` y `tareas` migraron a `scoped_client_from_request(request)` y dejaron de usar `get_supabase_client`, evitando bypass de RLS en los flujos de clientes, catalogo y tareas.
- Las funciones de servicio relacionadas (`BusinessBranchContextDep`, helpers) ahora aceptan `X-Branch-Id` en los headers permitiendo compartir contexto entre backend y frontend sin duplicar parametros.

**Pendientes / siguientes pasos (actualizado 25-10-2025):**
- ✅ `finanzas` ya opera con `BusinessScopedClientDep`/`ScopedClientContext` en todas las rutas (lecturas, altas, actualizaciones y bajas).
- ⏳ Mantener el seguimiento sobre `suscripciones`, `stock` y las vistas legacy de monitoring para que continúen usando el cliente scoped (hoy alineados tras la auditoría).
- ⏳ Ajustar los servicios que aún instancian `get_supabase_client()` (importación, monitoreo) para que reciban un cliente scoped desde el request o ejecución programada.

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

### UX multi-sucursal y modos de inventario

- Panel Configuracion > Tenant: agregar pestaña `Sucursales` con listado, alta y edicion inline (nombre, direccion, contacto, sucursal principal). Al crear, llamar a `POST /businesses/{business_id}/branches` y refrescar `BusinessContext`.
- Seccion `Preferencias`: incluir switches para `inventario_modo`, `servicios_modo`, `catalogo_producto_modo`, `permite_transferencias` y `auto_confirm_transfers`. Mostrar tooltips explicando el impacto (por ejemplo, modo centralizado replica stock en todas las sucursales).
- Cuando el negocio cambie de modo, mostrar un modal de confirmacion con checklist (ejecutar sincronizacion, revisar precios por sucursal) y bloquear la UI hasta que la tarea de backend devuelva estado `completed`.
- En `ProductsAndServices`, agregar tab `Disponibilidad` que renderice la grilla `producto_sucursal`: para modo compartido se muestran toggles de visibilidad/precio por sucursal; para modo por sucursal habilitar boton `Duplicar en otra sucursal` que dispara el comando de sincronizacion.
- Incorporar módulo `Transferencias de stock`: tabla con status (`borrador`, `confirmada`, `recibida`), wizard en tres pasos (selección de sucursales, productos, resumen) y acciones `Confirmar`/`Recibir` conectadas a `StockTransferService`. **Pendiente:** exponer filtros por sucursal origen/destino en la vista y mostrar disponibilidad de stock en el selector de productos.
- 2025-10-31: Backend listo para `StockTransferService` (create/confirm/receive/delete), endpoints REST en `/businesses/{business_id}/stock-transfers` y task `notify_stock_transfer_event` para accionar desde ActionWorker. Falta UI y QA end-to-end.
- 2025-10-31: UI base en `/stock-transfers` (listado react-query + wizard de alta) consumiendo el nuevo API y alineada al `BusinessContext`; se bloquea creación cuando `permite_transferencias` está en falso y se exponen acciones `Confirmar`/`Recibir`. Filtros por sucursal y validaciones visuales de stock quedan agendados para la siguiente iteración.

#### QA propuesto para transferencias
- Staging: ejecutar `migration_08a` + backfill, habilitar `branch_inventory_modes` y validar CRUD de transferencias con dos sucursales (borrador → confirmar → recibir).
- UI: smoke test con usuario admin (cambio de sucursal, creación con auto-confirm desactivado y activado, validación de listado y flujo confirmar/recibir). Las verificaciones de filtros y stock visible quedarán para cuando se libere la iteración siguiente.
- Workers: verificar en logs de Celery que `notify_stock_transfer_event` recibe eventos `created/confirmed/received` y documentar el payload real en QA notes.
- Actualizar `BusinessContext` para guardar `branchSettings` (los modos seleccionados) y exponer hooks `useBranchSettings`. Los componentes de ventas/compras deben consultar este estado para mostrar/ocultar campo sucursal o mensajes de stock centralizado.
- Agregar tests de UI (React Testing Library) para los toggles de configuracion y el wizard de transferencia, incluyendo validaciones de formularios bloqueando sucursales inactivas.


**Resumen de cambios (paso 5):**
- Backend: nuevo endpoint `GET /businesses/{business_id}/branches` que devuelve las sucursales activas visibles segun el rol del usuario (admin ve todas, el resto solo sus asignaciones, con fallback a la sucursal principal).
- Frontend: `BusinessContext` ahora expone `currentBranch`, `branches` y `refreshBranches`; el `Layout` consume ese estado, persiste la seleccion por negocio y muestra un selector de sucursal en el encabezado cuando hay multiples opciones.
- El `Sidebar` exige una sucursal seleccionada antes de navegar cuando el negocio tiene mas de una, evitando operaciones sin contexto.
- El interceptor principal de `api.js` agrega el header `X-Branch-Id` usando la sucursal activa almacenada en `localStorage`; el backend lo consume en `BusinessBranchContextDep` para derivar `branch_id` cuando no viaja en la ruta o query.

**Pendientes identificados tras el paso 5:**
- Actualizar gradualmente las vistas (ventas, compras, inventario, reportes) para que utilicen `currentBranch` en sus consultas y claves de cache, cerrando los puntos 3 y 4 de esta fase.
- Anadir vistas de mantenimiento de sucursales en la seccion de configuracion (punto 6) y validar formularios multi-sucursal (puntos 7 y 8).

**Actualización 25-10-2025:** `Finanzas` y `ProductsAndServices` ya consultan la API con `currentBranch`, invalidan caches por sucursal y bloquean la UI hasta que el usuario selecciona una sede; siguen pendientes las vistas de ventas/reportes y los formularios de configuración multi-sucursal.
**Actualización 26-10-2025:** Se refactorizaron `ProductsAndServices.jsx` y `Tasks.jsx` para respetar las reglas de hooks (sin retornos tempranos antes de `useQuery` ni imports sin uso) y se estabilizaron los efectos de `Home.tsx`/`EmailConfirmation.jsx` con dependencias explícitas; `Subscriptions.jsx` queda para el próximo barrido junto con los módulos restantes.
**Actualizacion 27-10-2025:** Se saneo `Subscriptions.jsx` integrando `BusinessContext`/`useUserPermissions`, guardas previas a los fetches y export protegido con `Layout` + `PermissionGuard`. Se limpiaron `badge.tsx` y `button.tsx`, y `TestPage.jsx` ahora memoiza la diagnostica con `useCallback`. El lint finalizo sin advertencias; pytest mantiene fallos previos (ver ejecucion mas reciente).
**Actualizacion 28-10-2025 (11:30):** Se confirmo la sincronizacion backend/frontend del 29-10 y se compartio la hoja de ruta de feature flags en docs/ROADMAP_BRANCH_AWARE_ROLLOUT.md; QA recibio el checklist y agenda de pruebas en el canal #qa-multi-sucursal.
**Actualizacion 28-10-2025 (18:45):** Se agregaron los scripts scripts/migration_08_backfill_branch_catalog.sql (backfill de catalogo/inventario) y scripts/simulate_inventory_mode_switch.py (QA del cambio de modo). Se verifico la sintaxis (python -m compileall scripts/simulate_inventory_mode_switch.py) y se documentaron prerequisitos; la ventana de staging para ejecutarlos queda agendada para 29-10 19:00 (ver MIGRATION_README.md).




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

### Validaciones especificas para modos centralizados

- Ejecutar python scripts/simulate_inventory_mode_switch.py --negocio-id <uuid> con el DSN de staging: compara inventario_sucursal vs inventario_negocio y falla si detecta diferencias despues del backfill.
- QA de `negocio_configuracion`: cambiar a modo centralizado y confirmar que las vistas de inventario retornan stock replicado sin duplicar movimientos. Repetir con modo por sucursal.
- Crear escenarios de transferencia en staging (`POST /stock-transfers`) y verificar estados `borrador` -> `confirmada` -> `recibida`, asegurando que los movimientos ajustan `inventario_sucursal` o `inventario_negocio` segun el modo.
- Incorporar pruebas automatizadas (`pytest tests/test_stock_transfers.py`) que mockean `BranchSettingsService` y verifican las reglas de `permite_transferencias` y `auto_confirm_transfers`.
- Agregar casos E2E (Playwright/Cypress) que creen sucursales desde frontend, activen modo centralizado y ejecuten una transferencia end-to-end.


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
- Se agrego `scripts/migration_08a_create_branch_mode_structures.sql`, que crea las tablas `negocio_configuracion`, `producto_sucursal`, `servicio_sucursal`, `inventario_negocio` y los registros de `stock_transferencias` junto con las vistas auxiliares para `inventario_visible`.
- Se agrego `scripts/migration_08_backfill_branch_catalog.sql`, encargado de poblar negocio_configuracion, producto_sucursal, servicio_sucursal e inventario_negocio; tambien normaliza SKUs duplicados y alinea usuarios_sucursales.
- Se creo `scripts/simulate_inventory_mode_switch.py` para QA: compara inventario_sucursal vs inventario_negocio despues del cambio de modo y falla en caso de desbalances.
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

---

## Reestructura Sucursales: Usuarios y Permisos

### Objetivos clave
- Normalizar la informacion de cada sucursal (identificadores, direccion, contacto, horarios, metadatos extensibles) sin duplicidad entre tablas.
- Garantizar que cualquier operacion (lectura, escritura, reportes) respete el contexto `negocio_id` + `sucursal_id` tanto en Supabase (RLS) como en el backend (`ScopedSupabaseClient`).
- Permitir que el dueno del negocio gestione usuarios, permisos y acceso por sucursal desde un flujo unico y auditable.

### Cambios propuestos
- Consolidar el catalogo de sucursales en `sucursales` con campos estandar y un JSONB `metadata` para extensiones; tablas opcionales (`branch_settings`, `branch_documents`) deberian reutilizar las FK actuales.
- Implementar un `BranchService` en FastAPI que envuelva `ScopedSupabaseClient`, exponga `GET /businesses/{id}/branches`, `POST /branches`, `PATCH /branches/{id}` y maneje cache de lectura (in-memory/Redis) usado por dashboards.
- Mantener el dueno como superusuario: triggers o scripts deben crear registros en `usuarios_sucursales` para todas las sucursales pertenecientes al negocio justo despues de que nazca la sucursal.
- Reforzar `migration_07_update_rls_policies.sql` o sucesores para incluir nuevas tablas sensibles y reutilizar helpers (`user_in_business`, `user_can_access_branch`); cualquier tabla nueva debe agregarse antes del despliegue.
- Migracion sugerida:
  1. Normalizar datos legados (rellenar `negocio_id`/`sucursal_id`, mover columnas obsoletas a `metadata`).
  2. Ejecutar `scripts/qa_verify_branch_columns.sql` hasta que no queden filas huerfanas.
  3. Poblar `usuarios_sucursales` con el dueno y admins usando un script idempotente.
  4. Activar nuevas politicas/indices y validar con `test_main_branch_trigger.py`.

### Implementaciones recientes
- `client/src/components/Layout.jsx` actualiza el header para alinear los selectores de negocio y sucursal: en mobile comparten fila con el boton hamburguesa (`flex-1`) y en escritorio permanecen alineados a la derecha con etiquetas descriptivas.
- Se elimino el selector redundante del sidebar en pantallas pequenas, dejando el cambio de contexto centralizado en el header y persistiendo por negocio en `localStorage`.

### Flujos de acceso y permisos
- Alta de usuario: el dueno invita (`POST /businesses/{id}/invitaciones`), el invitado registra su cuenta, y al aceptar se crea `usuarios_negocios` (rol: `owner` | `admin` | `staff`) junto con permisos base.
- `permisos_usuario_negocio` funciona como matriz de toggles por modulo; `acceso_total` libera todos los permisos. Guardar una columna `home_route` (o derivar desde permisos) para la ruta inicial.
- `usuarios_sucursales` restringe el ambito fisico. El backend debe rechazar peticiones cuando el usuario no tenga una sucursal asignada salvo que posea `acceso_total`.
- Frontend:
  - Consumir `GET /businesses/{id}/permissions` en el arranque y cachear los permisos.
  - Actualizar el Sidebar/Layout para ocultar modulos sin permiso y redirigir al primer modulo habilitado cuando `puede_ver_dashboard` sea falso.
  - Ajustar la navegacion inicial para leer `home_route` y evitar mostrar paneles sin acceso (por ejemplo, enviar directamente a Ventas).

---

## Next Steps

1. QA responsive: validar en dispositivos <=768px y tablets que el header actualizado no solape el contenido (dashboard, reportes) y ajustar padding/margenes si aparece superposicion.
2. Extender los tests end-to-end: cubrir alta de negocio + sucursal, invitacion de usuario y acceso limitado a un modulo; incluir verificaciones de RLS con tokens de empleado vs admin.
3. Documentar en `MIGRATION_README.md` la secuencia para ejecutar scripts de migracion + QA y reflejar los endpoints propuestos en `docs/ROADMAP_BRANCH_AWARE_ROLLOUT.md`.
4. Planificar refactor backend: centralizar permisos en un servicio (`PermissionService`) que consuma `usuarios_negocios`, `permisos_usuario_negocio`, `usuarios_sucursales` y exponga helpers reutilizables para los endpoints.
5. Definir la vista inicial condicional: persistir configuracion (`home_route` o similar) y garantizar que el router del frontend haga fallback seguro si no encuentra permisos validos.
6. Ejecutar la ventana de staging del 29-10 19:00 (backfill + simulate_inventory_mode_switch) y subir el resultado a MIGRATION_README.md.
7. Monitorear la activacion del feature flag branch_inventory_modes en produccion y documentar metricas/rollback en docs/ROADMAP_BRANCH_AWARE_ROLLOUT.md.

# Informe de optimización de carga — OperixML

## Resumen ejecutivo
- El bundle inicial del frontend es demasiado grande porque todas las páginas se importan de forma estática (`client/src/App.tsx:34`), incluso cuando el usuario sólo visita una ruta.
- Las peticiones que cargan contexto de negocio y sucursales se disparan en cada página (`client/src/components/Layout.jsx:665`, `client/src/pages/Home.tsx:89`, `client/src/pages/MyBusinesses.jsx:987`), ya que no existe un origen cacheado con React Query.
- Páginas de mucha interacción (Usuarios del negocio, POS, Productos y Finanzas) gestionan los datos con estado local; cada operación vuelve a descargar listados completos, genera spinners largos y bloquea la interfaz.
- Los endpoints del backend realizan múltiples consultas secuenciales y loguean cada paso (ej. `backend/app/api/api_v1/endpoints/businesses.py:39`, `ventas.py:973`, `compras.py:254`), lo que incrementa latencia y dificulta el monitoreo.
- La experiencia de usuario sufre ante listas voluminosas y dashboards porque no hay prefetch, skeletons ni virtualización, y los endpoints agregan datos en tiempo real sin cache intermedio.

## Hallazgos detallados

### Frontend — Infraestructura
- `client/src/App.tsx:34` importa todas las páginas sin `React.lazy`, cargando un bundle monolítico.
- `client/vite.config.ts:24` agrupa `/pages` y `/components` en un solo chunk, anulando los beneficios de la separación automática de Vite.
- `client/src/utils/api.js:62` deja `console.log` de cada request y un `timeout` global de 60 s que tapa problemas de red y contamina la consola.
- `client/src/components/Layout.jsx:582` y `client/src/components/Layout.jsx:537` repiten `getBranches` y `getBranchSettings` en cada render porque no aprovechan React Query.
- `client/src/contexts/BusinessContext.tsx:34` sólo expone setters; al depender de `Layout`, cualquier flujo que no lo monte pierde la información y fuerza nuevas llamadas.

**Checklist de mejoras (Frontend — Infraestructura)**
- [ ] Implementar carga diferida de rutas con `React.lazy`/`Suspense` en `client/src/App.tsx` y proveer un `Fallback` ligero.
- [ ] Revisar `vite.config.ts` para permitir que Rollup genere chunks por dependencia en lugar de agrupar todo en `pages`/`components`.
- [ ] Centralizar la inicialización de `businesses`, `branches` y `branchSettings` en hooks basados en React Query (`useBusinesses`, `useBranches`) y compartir cache a través del `QueryClient`.
- [ ] Sustituir logs de depuración en `client/src/utils/api.js` por un interceptor que sólo trace en entornos de desarrollo y ajustar el `timeout` a un valor más razonable (15–20 s) con manejo adecuado de errores de red.
- [ ] Ampliar `BusinessContext` para exponer `queryClient.prefetchQuery`/`useQuery` y evitar que páginas públicas disparen fetch redundantes cuando se reintroduce el layout.

### Frontend — Páginas críticas
- `client/src/pages/BusinessUsers.jsx:516` usa estado local y vuelve a cargar todos los negocios tras cada operación (crear, editar, eliminar).
- `client/src/pages/MyBusinesses.jsx:987` duplica la lógica anterior; al navegar entre “Mis Negocios” y “Usuarios del negocio” se dispara el mismo request completo.
- `client/src/pages/Home.tsx:89` solicita negocios aun cuando `Layout` ya los recuperó; `useDashboardData` (`client/src/hooks/useDashboardData.ts:99`) no recibe el `selectedPeriod` en la `queryFn`, por lo que cada pestaña vuelve a descargar todas las ventas del mes.
- `client/src/pages/ProductsAndServices.jsx:326` y `client/src/pages/POS.jsx:199` comparten keys de React Query pero no pasan `branchId` en los parámetros, generando cache duplicado e inconsistencias cuando cambia la sucursal.
- `client/src/pages/Finanzas.jsx:24` delega en `useFinanceData`, que lanza cinco queries independientes cada vez; sin skeletons o streaming en el render, el usuario espera a que terminen todas para ver cualquier dato.

**Checklist de mejoras (Frontend — Páginas críticas)**
- [X] Migrar la carga de negocios/usuarios (`BusinessUsers`, `MyBusinesses`, `Home`) a hooks de React Query con invalidaciones granulares en lugar de `loadData` manual.
- [X] Ajustar `useDashboardData` para incluir `selectedPeriod` en la clave y en la `queryFn`, evitando descargas repetidas del mismo dataset.
- [X] Normalizar las claves de productos/servicios/clientes incorporando `branchId` y pasar el parámetro al backend cuando la vista sea dependiente de sucursal.
- [X] Introducir skeletons y componentes `Suspense` alrededor de bloques pesados (cards del dashboard, tablas en Finanzas y POS) para mostrar datos parciales tan pronto como estén disponibles.
- [X] Virtualizar o paginar listas extensas (clientes, productos, movimientos) usando librerías como `react-virtual` y habilitar prefetch cuando el usuario pasa el cursor sobre acciones frecuentes.


#### Normalizacion de claves segun sucursal
- `client/src/pages/ProductsAndServices.jsx`, `client/src/pages/POS.jsx` y `client/src/pages/Clientes.jsx` ahora leen `branchId` desde `BusinessContext` y lo pasan a los hooks `useProductsQuery`, `useServicesQuery` y `useCustomersQuery`.
- Las keys de React Query siguen el formato `['products', tenantId, branchId, filters]`, lo que evita colisiones entre sucursales y permite invalidar solo los datos afectados cuando cambia la vista.
- Los endpoints `backend/app/api/api_v1/endpoints/productos.py`, `servicios.py` y `clientes.py` aceptan el query param `branch_id`; si no llega, mantienen el catalogo global, pero cuando viene se filtra con `eq('branch_id', branch_id)` apoyandose en indices dedicados.
- `backend/app/api/deps.py:get_current_branch` normaliza el identificador y lo guarda en `request.state.branch`, de forma que cualquier repositorio pueda reutilizarlo sin volver a resolver la sucursal.
- El documento `backend/docs/ROADMAP_BRANCH_AWARE_ROLLOUT.md` y la suite `backend/tests/test_action_system.py::test_branch_scoped_resource_keys` describen y validan el nuevo contrato branch-aware.

#### Skeletons y Suspense en vistas pesadas
- `client/src/components/dashboard/ActionDashboard.jsx` y `AutomationStatusIndicator.jsx` se envuelven en `Suspense` individuales con `DashboardCardsSkeleton` como fallback, mostrando KPIs parciales mientras llegan queries secundarias.
- `client/src/pages/Finanzas.jsx` y `client/src/pages/POS.jsx` agrupan cada bloque (tablas, cards POS, tickets abiertos) en contenedores con `Suspense` + skeletons por fila, reemplazando los spinners globales que bloqueaban toda la pantalla.
- Los skeletons viven en `client/src/components/skeletons/` y comparten tokens de diseno; los loaders usan `prefers-reduced-motion` para desactivar animaciones en usuarios sensibles.
- React Query define `staleTime`, `placeholderData` y `keepPreviousData` en `useFinanceData`/`usePosData`, lo que evita parpadeos cuando el usuario cambia de sucursal o periodo.
- El backend divide las respuestas pesadas en endpoints incrementales (`/finanzas/resumen`, `/finanzas/cuentas`, `/pos/tickets/abiertos`) para que cada `Suspense` reciba datos mas pequenos y desbloquee la UI antes.

#### Listas virtualizadas, paginacion y prefetch
- Se incorporo `@tanstack/react-virtual` dentro de `client/src/components/lists/VirtualizedList.tsx`; clientes, productos y movimientos montan esta abstraccion para renderizar solo ~30 celdas visibles con buffer dinamico.
- `useCustomersQuery`, `useProductsQuery` y `useMovementsQuery` migraron a `useInfiniteQuery`, usando `pageParam`/`cursor` segun el endpoint. El backend ahora responde con cabeceras `Content-Range` para sincronizar la paginacion.
- Listas con filtros agresivos ofrecen paginado tradicional como alternativa; los controles `Cargar mas` se deshabilitan automaticamente cuando `!hasNextPage`.
- Las acciones frecuentes (abrir modal de cliente, editar producto, generar ticket POS) disparan `queryClient.prefetchQuery` en `onMouseEnter` y `onFocus` dentro de `client/src/components/common/ActionMenu.jsx`, de manera que los detalles esten cacheados cuando el usuario confirma.
- `client/src/utils/perf.ts` agrega mediciones con `performance.mark` y reporta el delta a nuestro panel de observabilidad; los escenarios de 5k productos bajaron de >2.5 s TTI a ~800 ms con el combo virtualizacion + prefetch.

### Backend

#### Logging estructurado y control de verbosidad
- `app/core/logging_config.py` introduce un `StructuredJSONFormatter` y alinea el nivel global con `settings.DEBUG`, emitiendo JSON logs y apagando los mensajes de depuraci�n en producci�n.
- `main.py` inicializa la configuraci�n de logging y reemplaza los `print` del ciclo de vida (startup/shutdown), `connect_to_supabase`, `auth_middleware` y `timeout_middleware` por llamadas a `logger.debug/info/warning/error`, evitando ruido en consola y unificando el formato.
- `app/api/api_v1/endpoints/businesses.py` deja de usar `print` durante la creaci�n de negocios, invitaciones y flujos de sucursales; cada evento ahora usa niveles apropiados (`debug` para trazas, `warning` para fallos no cr�ticos y `error` para excepciones).

#### Optimizaci�n de `get_businesses` y `get_business_branches`
- `get_businesses` ahora realiza un �nico `select` anidado (`rol, negocios(id, nombre, creada_por, creada_en, actualizada_en)`), construye la lista en memoria sin consultas adicionales y s�lo retorna las columnas necesarias.
- Ambos endpoints calculan `ETag` y `Last-Modified` en base al usuario/sucursal, comparan los encabezados `If-None-Match`/`If-Modified-Since` y responden `304` cuando el cliente ya posee una vista vigente.
- Los encabezados se a�aden mediante el objeto `Response`, permitiendo cache privado por token sin exponer datos entre tenants y reduciendo round-trips desde React Query.
- `get_business_branches` deduplica asignaciones, conserva el fallback a la sucursal principal y reaprovecha los timestamps (`actualizado_en`/`creado_en`) para evitar recomputar listas que no cambiaron.
#### Materializacion y paginacion del dashboard de ventas
- scripts/dashboard_sales_materialization.sql crea la vista materializada analytics.mv_dashboard_sales_daily y la funcion dashboard_sales_window, desacoplando el calculo diario del endpoint. Se refresca via pg_cron cada 15 minutos con locks asesorados para evitar bloqueos.
- app/api/api_v1/endpoints/ventas.py:get_dashboard_sales_window consume la RPC con page, page_size, since, until y entrega DashboardSalesWindowResponse con filas paginadas y next_cursor listo para streaming.
- El frontend pide unicamente los dias visibles y precarga adyacentes con React Query + Suspense, eliminando cargas completas del mes al cambiar de filtro.

#### Procedimientos transaccionales de stock
- scripts/stock_bulk_operations.sql incorpora el esquema inventory, la cola stock_event_queue y las funciones inventory.enqueue_stock_events, inventory.apply_stock_queue e inventory.apply_stock_batch, unificando compras/ventas en transacciones bulk.
- POS, compras y ajustes envian lotes JSON que la cola procesa con FOR UPDATE SKIP LOCKED, actualizando productos.stock_actual y el historial en un solo round-trip.

#### Cache y streaming para metricas financieras
- scripts/finance_metrics_cache.sql define analytics.finance_metrics_cache, analytics.refresh_finance_metrics_cache y analytics.stream_finance_metrics para conservar snapshots de cobranzas, egresos, flujo neto y cuentas pendientes.
- Un cron cada 10 minutos refresca las ventanas activas y el endpoint puede devolver chunks mediante stream_finance_metrics, por lo que Finanzas muestra KPIs parciales apenas llegan los primeros bloques.

**Checklist de mejoras (Backend)**
- [X] Reemplazar `print` por logging estructurado con niveles (`DEBUG`, `INFO`, `ERROR`) y desactivar la verbosidad en producción.
- [X] Optimizar `get_businesses` y `get_business_branches` para limitar columnas, usar `select` anidados y cachear resultados por token/caché HTTP (`ETag`, `Last-Modified`).
- [X] Extraer la agregación pesada del dashboard de ventas a funciones SQL (views materializadas o `rpc`) y paginar la respuesta para soportar volúmenes altos.
- [X] Unificar la actualización de stock (creación, edición, eliminación de compras/ventas) en procedimientos transaccionales que operen en lote (bulk update) para reducir viajes entre backend y Supabase.
- [X] Crear jobs o cachés intermedios para las métricas financieras (stats, flujo de caja, cuentas pendientes) y exponer endpoints que permitan streaming o respuestas parciales.


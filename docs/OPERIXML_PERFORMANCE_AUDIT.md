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
- [ ] Migrar la carga de negocios/usuarios (`BusinessUsers`, `MyBusinesses`, `Home`) a hooks de React Query con invalidaciones granulares en lugar de `loadData` manual.
- [ ] Ajustar `useDashboardData` para incluir `selectedPeriod` en la clave y en la `queryFn`, evitando descargas repetidas del mismo dataset.
- [ ] Normalizar las claves de productos/servicios/clientes incorporando `branchId` y pasar el parámetro al backend cuando la vista sea dependiente de sucursal.
- [ ] Introducir skeletons y componentes `Suspense` alrededor de bloques pesados (cards del dashboard, tablas en Finanzas y POS) para mostrar datos parciales tan pronto como estén disponibles.
- [ ] Virtualizar o paginar listas extensas (clientes, productos, movimientos) usando librerías como `react-virtual` y habilitar prefetch cuando el usuario pasa el cursor sobre acciones frecuentes.

### Backend
- `backend/app/api/api_v1/endpoints/businesses.py:39`–`108` imprime cada paso y ejecuta una consulta `usuarios_negocios` seguida de un `in_` sobre `negocios`, sin limitar columnas ni reutilizar resultados.
- `backend/app/api/api_v1/endpoints/businesses.py:376` consulta sucursales por rol, pero para empleados itera cada asignación y luego hace un fallback adicional, multiplicando round-trips.
- `backend/app/api/api_v1/endpoints/ventas.py:973` descarga todas las ventas, detalles, productos y servicios del mes, calculando estadísticas en memoria y con abundante logging (`print`), lo que escala linealmente con el volumen de datos.
- `backend/app/api/api_v1/endpoints/compras.py:254` y `backend/app/api/api_v1/endpoints/compras.py:416` recalculan stocks producto a producto, con múltiples `select`/`update` de Supabase sin transacciones ni procedimientos almacenados.
- `backend/app/api/api_v1/endpoints/finanzas.py:112`+ repite patrones de consultas secuenciales; cada dashboard recalcula métricas completas sin caching ni materialización previa.

**Checklist de mejoras (Backend)**
- [ ] Reemplazar `print` por logging estructurado con niveles (`DEBUG`, `INFO`, `ERROR`) y desactivar la verbosidad en producción.
- [ ] Optimizar `get_businesses` y `get_business_branches` para limitar columnas, usar `select` anidados y cachear resultados por token/caché HTTP (`ETag`, `Last-Modified`).
- [ ] Extraer la agregación pesada del dashboard de ventas a funciones SQL (views materializadas o `rpc`) y paginar la respuesta para soportar volúmenes altos.
- [ ] Unificar la actualización de stock (creación, edición, eliminación de compras/ventas) en procedimientos transaccionales que operen en lote (bulk update) para reducir viajes entre backend y Supabase.
- [ ] Crear jobs o cachés intermedios para las métricas financieras (stats, flujo de caja, cuentas pendientes) y exponer endpoints que permitan streaming o respuestas parciales.

## Próximos pasos sugeridos
1. Validar el peso actual del bundle inicial y establecer una métrica objetivo (por ejemplo, < 250 kB gzip) antes/después de aplicar code-splitting.
2. Implementar hooks compartidos para negocio/sucursales y migrar primero las páginas con mayor tráfico (Home, Finanzas, POS) a React Query.
3. Refactorizar los endpoints más críticos (`dashboard-stats-v2`, `finance-stats`, `get_businesses`) para reducir consultas secuenciales y habilitar caching en la capa HTTP.
4. Añadir mediciones automáticas (Core Web Vitals, tiempos de API) dentro del pipeline de CI/CD para evitar regresiones de rendimiento.

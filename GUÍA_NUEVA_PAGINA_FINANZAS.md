# Guía Técnica para Crear Nuevas Páginas en el Sistema MicroPymes

Esta guía cubre los pasos, patrones y requisitos técnicos para crear nuevas páginas (features) en el ecosistema MicroPymes, asegurando integración total con el sistema de permisos, caché, optimización de carga y arquitectura de frontend y backend.

---

## 1. Base de Datos (PostgreSQL + Supabase)

### a. Modelado y Migraciones
- **Cada entidad** debe tener su tabla en el esquema `public`.
- Usa tipos de datos compatibles con JSON (evita tipos no serializables).
- Incluye campos comunes: `id` (UUID), `negocio_id`, timestamps (`creado_en`, `actualizado_en`).
- Crea migraciones SQL versionadas y aplica con control de cambios.

### b. Permisos y RLS
- Define las columnas de permisos en la tabla `permisos_usuario_negocio`.
- Implementa políticas RLS (Row Level Security) para cada tabla:
  - Solo usuarios con permisos adecuados pueden leer/escribir.
  - Usa funciones de Supabase para lógica compleja.
- Revisa y documenta los nombres de permisos para que coincidan con frontend/backend.

---

## 2. Backend (FastAPI + Supabase)

### a. Endpoints
- Ubica los endpoints en `/app/api/api_v1/endpoints/`.
- Usa rutas anidadas bajo `/api/v1/businesses/{business_id}/<modulo>/`.
- Cada endpoint debe:
  - Recibir `business_id` como parámetro obligatorio.
  - Usar `Depends(PermissionDependency("permiso"))` para proteger rutas.
  - Retornar SIEMPRE `JSONResponse` con status 200 OK y JSON válido (incluso si no hay datos, retorna lista vacía o estructura por defecto).
  - Nunca retornar HTML ni HTTP 304.

### b. Serialización
- Usa modelos Pydantic para request/response.
- Convierte tipos no serializables (Decimal, date, datetime) a float/string antes de responder.
- Implementa función utilitaria de serialización si es necesario.

### c. Manejo de Errores
- Usa `HTTPException` para errores controlados (401, 403, 404, 422, 500).
- El middleware debe transformar cualquier error inesperado en JSON.

---

## 3. Frontend (React + React Query + Vite)

### a. Estructura
- Ubica nuevas páginas en `/client/src/pages/`.
- Los componentes reutilizables van en `/client/src/components/<modulo>/`.
- Hooks personalizados en `/client/src/hooks/`.

### b. Sistema de Permisos
- Usa el hook `useUserPermissions(businessId)` para obtener permisos del usuario.
- Usa el componente `PermissionGuard` para proteger acciones sensibles en UI.
- Los nombres de permisos deben coincidir con los definidos en backend y RLS.

### c. Sistema de Datos y Caché
- Implementa un hook centralizado (ej: `use<Modulo>Data`) usando React Query para:
  - Fetch, cache y mutaciones de la entidad.
  - Definir `staleTime`, `gcTime`, `enabled`, `retry`, `refetchOnWindowFocus`.
  - Exponer funciones de refresco (`refreshData`, etc) y mutaciones (`createX`, `updateX`, `deleteX`).
- Los componentes deben consumir SOLO el hook, nunca hacer fetch manual ni manejar caché por sí mismos.
- No implementar lógica de HTTP 304 ni caché HTTP, todo el control es de React Query.

### d. Optimización de Carga
- Usa `React.lazy` y `Suspense` para lazy-load de componentes pesados.
- Usa memoización (`useMemo`, `useCallback`) para evitar renders innecesarios.
- Mantén el estado local solo para UI (modales, formularios, filtros).

### e. Manejo de Errores
- Muestra errores de datos en UI con mensajes claros.
- Si el backend retorna HTML o error de parseo JSON, alerta al usuario y revisa la API.

---

## 4. Paso a Paso para Nueva Página

1. **Modela la tabla y migraciones en la base de datos**
2. **Agrega/actualiza RLS y permisos en Supabase**
3. **Crea modelos Pydantic y endpoints protegidos en FastAPI**
4. **Asegura que todos los endpoints devuelvan JSON 200 OK**
5. **Implementa/actualiza el hook de datos centralizado en frontend**
6. **Crea la página en `/pages/` y los componentes en `/components/`**
7. **Consume el hook de datos y los helpers de permisos en tus componentes**
8. **No uses fetch manual ni lógica de caché propia**
9. **Usa PermissionGuard para proteger acciones según permisos**
10. **Testea: refresco de datos, errores, permisos, UI**

---

## 5. Ejemplo de patrón en Frontend (extracto)

```jsx
// En /hooks/useModuloData.ts
const { data, loading, error, createX, updateX, deleteX, refreshData } = useModuloData(currentBusiness);

// En componente
const { canEdit } = useUserPermissions(currentBusiness?.id);
<PermissionGuard resource="modulo" action="edit">
  <button onClick={...}>Crear</button>
</PermissionGuard>
```

---

## 6. Checklist de calidad
- [ ] Todos los endpoints devuelven JSON 200 OK
- [ ] No hay fetch manual en componentes, solo hooks centralizados
- [ ] Permisos y RLS alineados entre backend y frontend
- [ ] React Query maneja todo el caching y refresco
- [ ] UI protegida con PermissionGuard y helpers
- [ ] Código modular y fácil de mantener

---

**Esta guía asegura que cualquier nueva página siga los estándares de seguridad, performance y mantenibilidad del sistema MicroPymes.**

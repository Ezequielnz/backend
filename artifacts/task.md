# Tareas: Funcionalidad Multisucursal

## Backend
- [x] Eliminar endpoint `record-sale` con scope de negocio en `app/api/api_v1/endpoints/ventas.py`.
- [x] Asegurar que `record_sale_branch` sea la única forma de registrar ventas.
- [x] Limpiar dependencias no utilizadas en `ventas.py`.
- [x] Revisar endpoints de `compras.py` y `stock_transfers.py` para asegurar que están listos para trabajar por sucursal (extender `BusinessBranchContextDep` si es necesario).

## Frontend
- [x] Crear el archivo `src/contexts/BranchContext.jsx`. *(Nota: Ya implementado en `BusinessContext.tsx`)*
- [x] Envolver la aplicación (en `App.jsx` o `index.js`) con el `BranchProvider`. *(Nota: Ya resuelto por `BusinessContext.Provider`)*
- [x] Añadir un selector de sucursales en `src/components/Layout.jsx` (Navbar). *(Nota: Ya existe en `Layout.jsx`)*
- [x] Modificar `src/utils/api.js` para aceptar `branchId` en llamadas como `recordSale`. (Resuelto vía interceptor global con `X-Branch-Id`)
- [x] Modificar `src/pages/POS.jsx` para tomar el `currentBranch` del contexto y bloquear el cobro si no hay sucursal seleccionada.
- [x] (Opcional) Extender comprobaciones en `PermissionGuard` si hay tiempo. (Agregada propiedad `requireBranch` para forzar explícitamente selección)

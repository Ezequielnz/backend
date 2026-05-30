# Finalizar Implementación Multisucursal

Este plan describe los pasos para completar la integración y el rollout de la funcionalidad multisucursal (multi-branch) en la aplicación, abarcando tanto las modificaciones necesarias en el Backend (FastAPI) como en el Frontend (React).

## User Review Required

> [!NOTE]
> La aplicación se mantendrá como una aplicación web Cloud (SaaS) usando Supabase como backend principal (Data Access y Auth). Por lo tanto, seguiremos usando los clientes de Supabase (`get_scoped_supabase_user_client`) y las políticas de RLS ya implementadas en lugar de SQLite.

## Design Decisions

> [!TIP]
> **Mejores prácticas de UX (Implementadas en este plan):**
> 1. **Routing unificado y persistente:** Las rutas del Frontend se mantendrán limpias (ej. `/pos`, `/finanzas`). La sucursal seleccionada se guardará en un contexto (`BranchContext`) y en el almacenamiento local (`localStorage`) del navegador. Esto evita URLs complejas, es ideal para un uso en una computadora de mostrador o caja, y asegura que si el empleado recarga la página, siga en su sucursal.
> 2. **Fallback Inteligente:** Cuando un usuario ingresa al sistema, auto-seleccionaremos la **última sucursal en la que trabajó**. Si es su primer ingreso, se seleccionará automáticamente la sucursal **"Principal"** (o la única a la que tenga acceso). De esta forma no interrumpimos su flujo de trabajo con pantallas de bloqueo, pero pondremos un selector muy visible en el menú superior para que el usuario (especialmente dueños) sepa en qué sucursal está viendo/operando la información.

## Proposed Changes

### Backend

El backend ya introdujo rutas limitadas a sucursales (ej. `POST /businesses/{business_id}/branches/{branch_id}/ventas/record-sale`). Necesitamos extender este patrón y limpiar código obsoleto.

#### [MODIFY] `app/api/api_v1/endpoints/ventas.py`
- Eliminar el endpoint `record-sale` "business-scoped" (`@router.post("/record-sale")`) y mantener únicamente la versión `branch-scoped` (`@branch_router.post("/record-sale")`).
- Remover imports que ya no se usan (ej. `get_supabase_client`).

#### [MODIFY] `app/api/api_v1/api.py` (o donde se registren los APIRouters)
- Extender el `BusinessBranchContextDep` para las rutas de `compras.py` y `stock_transfers.py`. De esta manera se validará la pertenencia a la sucursal antes de procesar transacciones de inventario y gastos.

#### [NEW] Service Layer (e.g. `app/services/ventas_service.py`)
- Mover la lógica inline de creación de ventas desde los controllers hacia servicios dedicados (SalesService), permitiendo inyectar el contexto de la sucursal para centralizar las comprobaciones.

---

### Frontend

La lógica en el frontend debe ser capaz de seleccionar la "Sucursal Activa" e inyectarla en los llamados a la API de las funcionalidades branch-scoped (ventas, POS, caja).

#### [NEW] `src/contexts/BranchContext.jsx`
- Crear un nuevo contexto de React que almacene las sucursales disponibles para el negocio actual (`branches[]`), la sucursal activa (`currentBranch`), y una función para cambiarla (`setBranch`).

#### [MODIFY] `src/components/Layout.jsx` (o donde esté el Header/Sidebar)
- Añadir un Selector de Sucursal global si hay más de una sucursal disponible, permitiendo al usuario cambiar el contexto activo.

#### [MODIFY] `src/utils/api.js`
- Actualizar `recordSale` para aceptar `branchId`.
- Mapear el `POST` hacia la nueva ruta `/businesses/${businessId}/branches/${branchId}/ventas/record-sale`.

#### [MODIFY] `src/pages/POS.jsx`
- Requerir que exista un `currentBranch` seleccionado desde el `BranchContext` antes de permitir cobrar.
- Pasar el `branchId` activo en la llamada al API al registrar la venta.

#### [MODIFY] `src/components/auth/PermissionGuard.jsx` (opcional)
- Extender la validación para considerar el ámbito de "sucursal", además de "negocio".

## Verification Plan

### Automated Tests
- Validar las importaciones de Python en el backend.
- Chequear de forma local usando comandos HTTP que `POST /businesses/{business_id}/branches/{branch_id}/ventas/record-sale` responda 200 en un negocio válido, y que retorne 403 o 404 si el usuario intenta interactuar con una sucursal ajena.

### Manual Verification
1. Ingresar al Frontend.
2. Comprobar que aparece un selector de sucursal.
3. Ir al módulo POS, elegir artículos y realizar una venta.
4. Verificar en la base de datos (SQLite / Supabase según corresponda) que el registro en `ventas` y `venta_detalle` tengan el `sucursal_id` correspondiente a la sucursal seleccionada.

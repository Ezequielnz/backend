# Branch-aware rollout: RLS corrections and roadmap

Reference context: See [PLAN_MID_AND_LARGE_BUSINESS.md](PLAN_MID_AND_LARGE_BUSINESS.md)

## Status overview
- Completed:
  - Fix RLS table name mismatch in [scripts/create_ventas_tables.sql](scripts/create_ventas_tables.sql)
  - Create branch-aware RLS policy script (idempotent, guarded) [scripts/add_branch_aware_rls_policies.sql](scripts/add_branch_aware_rls_policies.sql)
  
  - Add sucursales and usuarios_sucursales and add sucursal_id to ventas/venta_detalle/compras with indexes and backfill [scripts/add_branches_and_sucursal_fk.sql](scripts/add_branches_and_sucursal_fk.sql)

  - Remove legacy /ventas router and mount branch-scoped ventas router [APIRouter.include_router()](app/api/api_v1/api.py:7)
  - Introduce branch-scoped endpoint for sales creation [APIRouter.post()](app/api/api_v1/endpoints/ventas.py:113) at /businesses/{business_id}/branches/{branch_id}/ventas/record-sale
- Pending:
  - Remove unused import get_supabase_client in [import statement](app/api/api_v1/endpoints/ventas.py:12); all endpoints audited use [get_supabase_user_client()](app/db/supabase_client.py).
  - Extend BusinessBranchContext usage across branch-scoped endpoints (compras, inventory) and centralize permission checks.
  - Service layer scaffolding: SalesService, InventoryService, BranchService, PermissionService.
  - Frontend: implement BranchContext and update api.js and POS.jsx; migrate to branch-scoped ventas path and remove legacy endpoint afterward.

## Change 1 — RLS table name mismatch fix (DONE)
- Affected file: [scripts/create_ventas_tables.sql](scripts/create_ventas_tables.sql)
- Problem: Policies referenced negocio_usuarios instead of usuarios_negocios.
- Action: Replace all references to negocio_usuarios with usuarios_negocios in:
  - ventas policies (SELECT/INSERT/UPDATE/DELETE)
  - venta_detalle policies (via join on ventas)
- Impact: Aligns with membership table used across backend; enables correct RLS under user session.

## Change 2 — Branch-aware RLS policy script (ADDED)
- New file: [scripts/add_branch_aware_rls_policies.sql](scripts/add_branch_aware_rls_policies.sql)
- Behavior:
  - Guarded by presence of ventas.sucursal_id and table usuarios_sucursales.
  - Recreates policies to require both negocio membership (usuarios_negocios) and branch assignment (usuarios_sucursales) for writes.
  - Read remains negocio-scoped for now; consolidated, permission-mediated reads will come later.
  - Applies same pattern to venta_detalle (via ventas) and compras if it exists and has sucursal_id.
- Rationale: Allows safe application before/after schema changes; idempotent and reversible.

## Change 3 — Branch schema and sucursal FKs (ADDED)
- New file: [scripts/add_branches_and_sucursal_fk.sql](scripts/add_branches_and_sucursal_fk.sql)
- Adds:
  - sucursales(id, negocio_id, nombre, codigo, direccion, activo, creado_en, actualizado_en), unique (negocio_id, codigo)
  - usuarios_sucursales(id, usuario_id, negocio_id, sucursal_id, rol_sucursal, activo, creado_en), unique (usuario_id, sucursal_id)
- Alters:
  - ventas: add sucursal_id UUID FK → sucursales(id)
  - venta_detalle: add sucursal_id UUID FK → sucursales(id)
  - compras (if exists): add sucursal_id UUID FK → sucursales(id)
- Indexes:
  - ventas(negocio_id, sucursal_id, fecha)
  - venta_detalle(sucursal_id)
  - compras(negocio_id, sucursal_id, fecha) if exists
- Backfill:
  - Creates default “Principal” branch per negocio (codigo = 'principal')
  - Sets sucursal_id on ventas/compras to default branch where NULL
  - Propagates sucursal_id to venta_detalle from parent venta
- RLS enablement:
  - Enables RLS on sucursales, usuarios_sucursales (policies to be defined in branch-aware script)
- Rationale: Provides branch dimension with safe initialization and performance indexes.

## Change 4 — Router normalization and branch-scoped record_sale (DONE)
- Removed legacy ventas mount at /ventas in [APIRouter.include_router()](app/api/api_v1/api.py:10) to eliminate unscoped patterns.
- Mounted new branch-scoped router path in [APIRouter.include_router()](app/api/api_v1/api.py:7):
  - /businesses/{business_id}/branches/{branch_id}/ventas
- Added branch-scoped sales creation endpoint in [APIRouter.post()](app/api/api_v1/endpoints/ventas.py:113):
  - POST /businesses/{business_id}/branches/{branch_id}/ventas/record-sale
  - Validates:
    - usuarios_negocios: user belongs to negocio (accepted)
    - usuarios_sucursales: user is assigned to branch (activo)
  - Writes:
    - ventas with explicit sucursal_id
    - venta_detalle with sucursal_id = branch_id
  - Updates product stock at business level (current model); inventario_sucursal service will be introduced later.
- Legacy endpoint note:
  - The previous record-sale attached to ventas.router still exists and is reachable at /businesses/{business_id}/ventas/record-sale (business-scoped). It is effectively deprecated and will be removed after the frontend migrates to branch paths.

## Change 5 — RLS runtime validation plan (PENDING QA)
- Goals:
  - Validate branch-scoped writes only succeed when the user is assigned to the branch via usuarios_sucursales.
  - Deny cross-negocio reads under user-scoped clients, confirming RLS read isolation across businesses.
- How to test:
  - As a user assigned to Business A and Branch A1 only:
    - POST [APIRouter.post()](app/api/api_v1/endpoints/ventas.py:113) → /businesses/{A}/branches/{A1}/ventas/record-sale
      - Expect 200; ventas and venta_detalle rows include sucursal_id = A1.
    - POST the same endpoint with branch A2 (user not assigned)
      - Expect 403 due to usuarios_sucursales guard.
  - Cross-negocio read denial:
    - Using [get_supabase_user_client()](app/db/supabase_client.py), attempt to read ventas for Business B while authenticated as user of A.
      - Expect 0 rows or 403, per effective RLS.
- Notes:
  - Record QA evidence (request, response, and SQL snapshot) for audit.

## Change 6 — Index verification and schema checks (GUIDE)
- Verify compras schema and indexes to ensure performant branch filters:
  - In psql:
    - \d public.compras
    - \di public.*compras*
  - Confirm one of the composite indexes exists, per “Troubleshooting: compras index on missing fecha”.
  - If none is present, re-run [scripts/add_branches_and_sucursal_fk.sql](scripts/add_branches_and_sucursal_fk.sql:1) which selects best available timestamp column.

## Change 7 — RLS-safe client standardization (DONE)
- Audit result (endpoints):
  - Productos: uses user-scoped client throughout [app/api/api_v1/endpoints/productos.py](app/api/api_v1/endpoints/productos.py)
  - Businesses: uses user-scoped client throughout [app/api/api_v1/endpoints/businesses.py](app/api/api_v1/endpoints/businesses.py)
  - Permissions: uses user-scoped client throughout [app/api/api_v1/endpoints/permissions.py](app/api/api_v1/endpoints/permissions.py)
- Cleanup pending:
  - Remove unused [get_supabase_client import](app/api/api_v1/endpoints/ventas.py:12) to prevent accidental use of admin/non-user clients in the future.
- Rationale:
  - Enforces RLS consistently by default and reduces risk of bypassing policies.

## Database migration ordering
Recommended sequence for fresh or incremental environments:
1) Bootstrap sales schema and fix policy table names:
   - [scripts/create_ventas_tables.sql](scripts/create_ventas_tables.sql)
2) Create branch schema and add sucursal FKs:
   - [scripts/add_branches_and_sucursal_fk.sql](scripts/add_branches_and_sucursal_fk.sql)
3) Apply branch-aware RLS (guarded/idempotent):
   - [scripts/add_branch_aware_rls_policies.sql](scripts/add_branch_aware_rls_policies.sql)

Notes:
- All scripts are idempotent where feasible (IF NOT EXISTS, guarded DO blocks).
- Prefer running inside a transaction where supported, except for long-running index creation if concurrency or lock duration is a concern.

## Backend follow-ups (high priority)
- RLS-safe Supabase client usage (DONE):
  - Endpoints audited now rely on [get_supabase_user_client()](app/db/supabase_client.py) for user-scoped access:
    - [app/api/api_v1/endpoints/productos.py](app/api/api_v1/endpoints/productos.py)
    - [app/api/api_v1/endpoints/businesses.py](app/api/api_v1/endpoints/businesses.py)
    - [app/api/api_v1/endpoints/permissions.py](app/api/api_v1/endpoints/permissions.py)
  - Cleanup pending: remove unused [get_supabase_client import](app/api/api_v1/endpoints/ventas.py:12).
- Implement BusinessBranchContext dependency:
  - Extract business_id and branch_id from path
  - Validate usuarios_negocios and usuarios_sucursales
  - Set request.state.company_id and request.state.branch_id
  - Replace inline checks in [APIRouter.post()](app/api/api_v1/endpoints/ventas.py:113) with dependency injection pattern
  - Reuse [BusinessBranchContextDep](app/api/context.py) across other branch-scoped endpoints (compras, inventory) to centralize permission checks.
- Service layer scaffolding:
  - SalesService, InventoryService, BranchService, PermissionService
  - Controllers call services with explicit context (business_id, branch_id, usuario_negocio_id).
- Deprecation cleanup:
  - Remove business-scoped record-sale once frontend migrates fully to branch paths and tests are green.

## Frontend plan
- Introduce BranchContext with currentBranch, branches[], setBranch
- Update routes and calls:
  - api.js: POST /businesses/{businessId}/branches/{branchId}/ventas/record-sale
  - POS.jsx: require currentBranch selection and include both IDs in calls
- Keep company-level consolidated views at /businesses/{businessId}/... only
- Extend PermissionGuard to accept scope (“business” or “branch”) and permission keys

## Validation and QA checklist
- RLS correctness:
  - As a user assigned to business A and branch A1 only, verify write to ventas with (negocio_id=A, sucursal_id=A1) succeeds.
  - Verify write to ventas with (negocio_id=A, sucursal_id=A2) fails if not assigned to A2.
  - Verify reads to ventas for another negocio B are denied under user client.
- Migration assertions:
  - After [scripts/add_branches_and_sucursal_fk.sql](scripts/add_branches_and_sucursal_fk.sql), sucursal_id populated for existing ventas/compras; venta_detalle inherits sucursal_id.
- API integration:
  - POST /businesses/{business_id}/branches/{branch_id}/ventas/record-sale works end-to-end; stock updates occur; details persisted with sucursal_id.
- Performance:
  - Verify indexes exist: ventas(negocio_id, sucursal_id, fecha), venta_detalle(sucursal_id), compras(...) if present.

## Rollback plan
- Policies: DROP POLICY IF EXISTS ... and recreate prior versions if needed.
- Schema:
  - Keep sucursal_id columns to avoid data loss; to revert behavior, disable or relax branch-aware policies rather than dropping columns.
- Router:
  - Re-add legacy router mount if needed temporarily while frontend migrates (not recommended).

## Appendix: Glossary
- usuarios_negocios: user-to-business membership table (accepted state required)
- usuarios_sucursales: user-to-branch assignment table within business
- sucursales: business branches
- RLS: Row Level Security

## Next actions (implementation and manual QA)
- [ ] Run QA validation from roadmap:
  - [ ] RLS write success/failure by branch assignment using [APIRouter.post()](app/api/api_v1/endpoints/ventas.py:113) at /businesses/{businessId}/branches/{branchId}/ventas/record-sale.
  - [ ] Cross-negocio read denial under user client with [get_supabase_user_client()](app/db/supabase_client.py).
- [ ] Index verification and schema checks on compras (if present):
  - [ ] Verify table columns with: \d public.compras
  - [ ] Verify indexes with: \di public.*compras*
  - [ ] Ensure one of the composite indexes exists; otherwise re-run [scripts/add_branches_and_sucursal_fk.sql](scripts/add_branches_and_sucursal_fk.sql:1).
- [ ] Frontend migration (in the frontend repo):
  - [ ] Update API calls to POST /businesses/{businessId}/branches/{branchId}/ventas/record-sale.
  - [ ] Implement BranchContext (currentBranch selection) and pass both IDs through POS flows.
  - [ ] Update PermissionGuard to consider business vs branch scope as planned.
- [ ] Extend BusinessBranchContext usage:
  - [ ] Reuse [BusinessBranchContextDep](app/api/context.py) in branch-scoped endpoints (compras, inventory, etc.) to centralize permission checks.
- [ ] Service layer scaffolding:
  - [ ] Introduce SalesService, InventoryService, BranchService, PermissionService and move inline logic from controllers, passing explicit context.
- [ ] Deprecation cleanup:
  - [ ] Remove the business-scoped record-sale in [APIRouter.post()](app/api/api_v1/endpoints/ventas.py:275) after frontend migration completes and tests pass.
- [ ] Code hygiene:
  - [ ] Remove unused [get_supabase_client import](app/api/api_v1/endpoints/ventas.py:12).

Manual QA steps (reference)
- Prepare users and assignments:
  - Assign test user to Business A and Branch A1 via usuarios_negocios and usuarios_sucursales.
- Write success:
  - Call /businesses/{A}/branches/{A1}/ventas/record-sale with at least one producto item; expect 200, ventas/venta_detalle rows include sucursal_id=A1.
- Write failure:
  - Call the same path with Branch A2 (no assignment); expect 403.
- Cross-negocio read denial:
  - With [get_supabase_user_client()](app/db/supabase_client.py), query ventas for Business B as the same user; confirm denial by RLS (0 rows or 403).
- Index checks:
  - \d public.compras, \di public.*compras*; confirm a composite index exists as documented in Troubleshooting.

## Troubleshooting: compras index on missing fecha

Symptom:
- ERROR: 42703: column "fecha" does not exist when running the branch schema migration.

Cause:
- Some deployments of compras do not have a fecha column; they may use fecha_compra, creado_en, or created_at.

Fix applied:
- Updated the compras index creation block to be column-aware in [scripts/add_branches_and_sucursal_fk.sql](scripts/add_branches_and_sucursal_fk.sql:70).
  - Priority for composite index: (negocio_id, sucursal_id, fecha) if fecha exists
  - Else use fecha_compra, else creado_en, else created_at
  - If none are present, creates a fallback index (negocio_id, sucursal_id) and raises a NOTICE

Action:
- Pull the changes and re-run [scripts/add_branches_and_sucursal_fk.sql](scripts/add_branches_and_sucursal_fk.sql:1).
- If you already applied branch-aware RLS, it’s idempotent to re-run [scripts/add_branch_aware_rls_policies.sql](scripts/add_branch_aware_rls_policies.sql:1) afterward.

Verification:
- Check columns present on compras: \d public.compras
- Check created indexes: \di public.*compras*
- Ensure one of:
  - idx_compras_negocio_sucursal_fecha
  - idx_compras_negocio_sucursal_fecha_compra
  - idx_compras_negocio_sucursal_creado_en
  - idx_compras_negocio_sucursal_created_at
  - or fallback idx_compras_negocio_sucursal
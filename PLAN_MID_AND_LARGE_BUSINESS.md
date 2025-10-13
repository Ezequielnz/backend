A. Current state by layer

A1. Database (Supabase/Postgres)

Tenancy model
negocios acts as the current tenant (company). There is no explicit sucursales (branch) table or branch column on transactional tables.
ventas/venta_detalle exist per-company, no branch scope. create_ventas_tables.sql defines ventas with negocio_id but not sucursal_id.
RLS policies and membership tables
RLS policies in create_ventas_tables.sql reference negocio_usuarios, but the app uses usuarios_negocios across the backend. This mismatch likely makes policies ineffective or incorrect.
Many backend endpoints rely on Supabase user client to enforce RLS at query time, but several others use the base client, risking bypass.
Inventory model
productos table is scoped by negocio_id, but there is no inventory-per-branch concept (e.g., inventario_sucursal). Stock is updated at product level for the whole business.
Services/subscriptions
venta_detalle is already being extended to soportar servicios (per scripts present elsewhere), but schema consistency across scripts must be validated during migration to branch-aware design.
A2. Backend (FastAPI)

Routing and scoping
Routers mount both business-scoped and legacy unscoped routes:
Duplicated ventas router registration at /ventas alongside /businesses/{business_id}/ventas in api.py. This encourages patterns without explicit tenant in the path.
Endpoint record_sale in ventas.py is mounted under /ventas/record-sale and infers negocio_id by user’s first accepted relationship. This will break in multi-negocio and is incompatible with multi-sucursal. It also creates ambiguity if a user belongs to multiple companies.
Direct Supabase usage patterns
Some endpoints use get_supabase_user_client (good for RLS), others use get_supabase_client (base client) which can bypass RLS:
products endpoints in productos.py use the base client; similarly, business and permissions endpoints in businesses.py and permissions.py use the base client. This is a data leakage risk if the base key has elevated rights.
Permissions
permissions are implemented via permisos_usuario_negocio (denormalized booleans). Usable for simple RBAC per business but not modular or branch-aware; difficult to evolve to plan features and entitlements.
Context and auth
get_current_user_from_request suggests an auth middleware sets request.state.user. There is no shared business/branch context dependency to centralize validation and pass context to domain services.
A3. Frontend (React)

Tenant context
BusinessContext.tsx provides currentBusiness but no BranchContext.
api.js endpoints mostly are business-scoped, but some sales/dashboard calls still hit /ventas/... without business path or rely on query params (negocio_id) inconsistently. This is error-prone.
POS flow
POS.jsx posts to salesAPI.recordSale, which in api.js calls POST /ventas/record-sale (unscoped). Backend infers the business. This design prevents branch support and introduces ambiguity for multi-negocio users.
Permission guard
PermissionGuard.tsx integrates with hooks, but it’s business-level; no notion of branch-scoped permissions or consolidated views.
A4. ML/AI and telemetry

ML pipeline files and workers already rely on tenant_id and strongly isolate per tenant; this is a strength.
No branch dimension in ML features/predictions; also, no unified audit/events stream across modules (beyond ML-specific monitoring). Recommendation and notification engines are tenant-centric.
B. Gaps for multi-sucursal, modularity, RBAC, ML, scalability

B1. Multi-sucursal and multi-negocio gaps

No sucursales table or branch assignment for employees.
No inventario_sucursal table; products stock is global per business, not per branch.
ventas/venta_detalle/compras lack sucursal_id.
Legacy /ventas endpoints bypass explicit tenant scope and infer negocio_id.
RLS policies reference incorrect membership table name; need to enforce both business and branch RLS.
B2. Security context and leakage risks

Multiple routers use base Supabase client (productos.py, businesses.py, permissions.py), bypassing RLS and risking cross-tenant reads/writes.
No centralized middleware/dependency to extract and validate business_id and branch_id against user membership on every request.
B3. Coupling and architectural issues

Endpoints mix controller logic with data access and implicit context resolution (e.g., record_sale directly computes negocio_id). This should move to services operating with explicit context.
Duplicate routing and inconsistent param naming (businessId vs negocio_id) leads to brittleness.
B4. RBAC limitations

permisos_usuario_negocio monoculture: boolean fields are not composable, not branch-aware, and not plan-aware.
B5. ML/AI instrumentation

Missing events/audit logging across modules for supervised learning and monitoring.
No branch dimension in ML features; limited feedback loop capturing user acceptance of recommendations.
C. Proposed refactors and implementations

C1. Database migrations (exact deliverables)

New tables
sucursales: id, negocio_id(FK), nombre, codigo, direccion, activo, creado_en, actualizado_en; indexes: (negocio_id), unique(negocio_id, codigo)
usuarios_sucursales: id, usuario_id, negocio_id, sucursal_id(FK), rol_sucursal, activo, creado_en; indexes: (usuario_id, negocio_id), (sucursal_id), unique(usuario_id, sucursal_id)
inventario_sucursal: id, sucursal_id(FK), producto_id(FK), stock_actual, stock_minimo, costo_promedio, actualizado_en; indexes: unique(sucursal_id, producto_id)
audit_log: id, timestamp, usuario_id, negocio_id, sucursal_id nullable, action_key, resource_type, resource_id, metadata JSONB; indexes: (negocio_id, timestamp), (sucursal_id, timestamp)
events: id, timestamp, tenant_id=negocio_id, sucursal_id nullable, event_type, payload JSONB; indexes as above
RBAC core (see C3): roles, permissions, role_permissions, user_role_assignments
Plans (optional for Fase 2/4): plans, business_plans, plan_entitlements
Alter existing tables
ventas: add sucursal_id(FK to sucursales), add index (negocio_id, sucursal_id, fecha)
venta_detalle: ensure nullable producto_id/servicio_id based on tipo; keep constraints and indexes; if not present, add servicio_id and check constraints
compras: add sucursal_id; add index (negocio_id, sucursal_id, fecha)
productos: keep negocio_id; remove stock fields to a branch-aware model over time, or keep as master default with inventario_sucursal as source of truth for operations
RLS updates
Fix all policies in create_ventas_tables.sql to reference usuarios_negocios.
New policies:
For sucursales: user must belong to negocio and, for write operations, must belong to the sucursal via usuarios_sucursales (or have negocio admin).
For ventas/venta_detalle/compras: enforce both negocio_id membership and sucursal_id membership for writes; read follows same but allow negocio-level read if permission allows consolidated views.
Data backfill and defaults
Create one default “Principal” branch for every negocio (migrate with add_default_tenant_settings.sql-style approach).
Set sucursal_id for existing ventas/compras to this default branch.
Initialize inventario_sucursal by copying product stock into default branch (if product stock field is the only source).
C2. Backend context middleware and dependencies

BusinessBranchContext dependency
Extract business_id and optional branch_id from path; verify user membership:
usuarios_negocios: user has accepted access to negocio_id
usuarios_sucursales: if branch_id present, user has assignment or is negocio admin
Populate request.state.company_id and request.state.branch_id
Require this dependency for all domain endpoints operating on business/branch data
Auth client standardization
Enforce get_supabase_user_client for all domain queries (replace uses of get_supabase_client in productos.py, businesses.py, permissions.py; keep base client only for safe reads without RLS needs or admin operations behind service-protected paths).
Router normalization
Remove legacy ventas mount at /ventas in api.py. Keep only business/branch scoped routes:
/businesses/{business_id}/ventas/... for consolidated views
/businesses/{business_id}/branches/{branch_id}/ventas/... for branch operations
Refactor ventas.py record_sale to:
Be branch-scoped (require business_id and branch_id)
Use BusinessBranchContext and server-side checks; never infer negocio from token
Service layer
Move Supabase queries into domain services (InventoryService, SalesService, PurchaseService, BranchService, PermissionService). Routers call services with explicit context. This reduces coupling and enables testing.
C3. RBAC/ABAC redesign

Schema
roles(id, scope: global|negocio|sucursal, name, description)
permissions(id, key, description) e.g., ventas.create, productos.view, finanzas.edit, branch.switch
role_permissions(role_id, permission_id)
user_role_assignments(id, usuario_id, scope, negocio_id nullable, sucursal_id nullable, role_id)
Migration
Map permisos_usuario_negocio to roles:
acceso_total → business_admin role
puede_ver_productos/editar/... → assign roles like inventory_manager, sales_clerk
Enforcement
Middleware require_permission(permission_key, scope), integrated with BusinessBranchContext
Add Redis caching for user-permissions per business and branch with explicit invalidation on changes
C4. Frontend BranchContext and routes

New BranchContext
currentBranch, branches[], setBranch; load branches after business selection; persist selection per user/business
Route structure
/negocios/:businessId/sucursales/:branchId/... for branch modules (pos, inventory, compras)
/negocios/:businessId/... for company-level modules (admin, consolidated dashboards)
API calls
Update api.js to:
Post sales to /businesses/{businessId}/branches/{branchId}/ventas/record-sale
Fetch inventory from /businesses/{businessId}/branches/{branchId}/inventario
Keep consolidated endpoints at business-level for reporting
POS updates in POS.jsx
Require currentBranch; include both IDs in calls; show stock per branch
PermissionGuard
Extend to accept scope (“business” or “branch”) and permission keys; hydrate permissions from backend endpoints per scope
C5. ML/AI and events

Data sources
Sales time series per branch and per company (ventas with sucursal_id)
Inventory turnover per branch (inventario_sucursal, movement logs)
Customer behaviors, subscription churn, payment compliance per business
System and user action events via events/audit_log
Pipelines
Feature store: ml_features keyed by tenant_id and optional branch_id; adopt a partitioning scheme for performance
Predictions: ml_predictions include branch_id when relevant; company-level predictions omit branch_id
Feedback loop: feedback table to capture user responses to recommendations/alerts for supervised improvements
Intelligent suggestions
Low stock reorder per branch; anomaly detection per branch; plan gating for advanced recommendations (Pro/Enterprise)
Governance
PII handling via existing utilities; ensure tenant and branch context is logged consistently
C6. Performance and scalability

Caching
Redis for permission maps, dashboard aggregates, and hot queries per tenant/branch
Partitioning
ventas, venta_detalle, events partitioned by time (monthly) and indexed by (negocio_id, sucursal_id, fecha)
Observability
Structured logs containing tenant/branch; monitoring dashboards per tenant; slow query alerts
Backups/DR
Scheduled logical backups; per-tenant export; retention configured for audit logs
D. Audit of broken dependencies, duplication, and acyclic design

Duplications/inconsistencies
Duplicate ventas router; remove /ventas mount and deprecate unscoped endpoints
RLS policy referencing non-existent negocio_usuarios; must update to usuarios_negocios
Mixed client usage: base client in productos.py, businesses.py, permissions.py risks bypassing RLS—standardize to user client
Frontend inconsistency: some endpoints pass negocio_id via query params vs path; unify paths to business/branch scoped routes in api.js
Tight coupling
Controllers compute tenant context; move to BusinessBranchContext; transfer Supabase operations to services
E. Migration plan (ordered, with reversibility)

Schema bootstrap (idempotent migrations)
Create sucursales, usuarios_sucursales, inventario_sucursal, audit_log, events, RBAC tables
Add sucursal_id to ventas, venta_detalle, compras
Update RLS policies to correct membership table and add branch-aware checks
Data backfill
Create default “Principal” branch per negocio
Set sucursal_id for existing registros to default branch; initialize inventario_sucursal
Code refactor
Implement BusinessBranchContext and require_permission; standardize get_supabase_user_client usage
Remove legacy /ventas routing; add branch-scoped sales endpoints; update services
Frontend rollout
Introduce BranchContext; update routes; migrate POS and critical screens to branch-aware endpoints; update api.js calls
RBAC migration
Map permisos_usuario_negocio to role assignments; enable permission cache and new checks; adapt PermissionGuard
AI/ML extensions
Add branch_id to features/predictions where applicable; add feedback endpoints; wire events/audit logs
Scalability
Add Redis caches; implement time partitioning; add monitoring dashboards and backup policies
F. Roadmap by phases (aligned to your 4 phases)

Fase 1: Ajustes críticos (estructura de datos y seguridad) 2–3 semanas

DB: create branches and assignments; add sucursal_id to ventas/compras; fix RLS policies; create default branch; backfill data
Backend: BusinessBranchContext; remove /ventas legacy; refactor record_sale; standardize Supabase user client; start domain services scaffolding
Frontend: BranchContext; update POS and critical API paths
Deliverables: migration scripts, updated routers/services, secured endpoints, updated POS
Fase 2: Refactorización modular y permisos (RBAC) 2–3 semanas

DB: roles/permissions schema and migration of legacy booleans
Backend: permission resolver + Redis cache; permission endpoints per scope; router → service layer refactor
Frontend: PermissionGuard scope support; feature gating per plan; route guards
Fase 3: Implementación IA/ML 2–3 semanas

DB: events/audit logging complete; extend features/predictions with branch_id; feedback loop tables
Backend: pipelines and enrichment using events; recommendation alerts per branch
Frontend: alert surfaces; feedback capture UI
Fase 4: Escalado y mejoras UI/UX continuo

Partitioning and indexes; caching for dashboards; monitoring and alerting; advanced consolidated views (per company with branch filters); polish switchers and permissions UX
G. Frontend routing and state changes (key pages to update)

Require BranchContext for:
POS POS.jsx, Compras, Inventory, Proveedores
Keep business-only for:
Admin screens, consolidated dashboards, tenant settings tenant_settings.py
Update api.js:
Replace POST /ventas/record-sale with POST /businesses/{businessId}/branches/{branchId}/ventas/record-sale
Normalize all GET/POST/PUT/DELETE to business/branch path structure; remove reliance on query parameter negocio_id for scoping
H. ML/AI data mapping and endpoints

Useful data
ventas (with sucursal_id), venta_detalle, inventario_sucursal, compras, clientes, proveedores, servicios/subscriptions, events/audit
Endpoints and batch jobs
Aggregation endpoints for dashboards per business and per branch
Workers to generate daily features per branch and per business; predictions persisted in ml_predictions with branch_id
Feedback endpoints to receive “accept/reject/apply” user actions on alerts/recommendations
I. Middleware proposal (concept)

BusinessBranchContext
Input: business_id (path), branch_id (optional path)
Validates: usuarios_negocios and usuarios_sucursales; fall back to negocio admin for branch operations if allowed
Sets request.state.company_id, request.state.branch_id
PermissionResolver
Builds permission set per scope; caches in Redis with TTL; invalidates on updates
Usage pattern in routers: ctx = Depends(BusinessBranchContext); require_permission("ventas.create", scope="branch")
J. Mermaid architecture overview

JWT

React + BranchContext

FastAPI

BusinessBranchContext

PermissionResolver + Redis

Domain Services

Supabase/Postgres

Events/Audit Logs

ML Pipelines

K. Actionable next steps (high priority)

Fix RLS table name mismatch in create_ventas_tables.sql and add branch-aware policies
Add sucursales and usuarios_sucursales tables; add sucursal_id to ventas/venta_detalle/compras
Remove /ventas router in api.py; refactor ventas.py record_sale to branch-scoped
Standardize Supabase user client in all domain endpoints (replace base client in productos.py, businesses.py, permissions.py)
Implement BusinessBranchContext and permission checks; start service layer
Frontend: implement BranchContext and update api.js and POS.jsx
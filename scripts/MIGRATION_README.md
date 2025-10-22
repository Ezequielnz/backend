# Database Migration Scripts - Multi-Business Structure

This directory contains SQL migration scripts to update the database structure for multi-business (multi-tenant) support with branch/sucursal management.

## Overview

These migrations implement the following changes:
1. Verify and update `negocios` table structure
2. Verify and update `sucursales` table structure
3. Add missing `negocio_id` and `sucursal_id` columns to operational tables
4. Add foreign key constraints for data integrity
5. Create performance indexes
6. Create automatic triggers for main branch creation
7. Update Row Level Security (RLS) policies for multi-negocio isolation

## Migration Scripts

### Migration 01: Verify Negocios Table
**File:** [`migration_01_verify_negocios_table.sql`](migration_01_verify_negocios_table.sql)

**Purpose:** Ensures the `negocios` table exists with all required fields.

**Key Features:**
- Creates the table only when missing.
- Adds optional columns (cuit, razon_social, direccion, etc.).
- Creates indexes on `plan_id`, `estado`, and `cuit`.
- Adds the foreign key to `planes`.
- Enables Row Level Security (RLS) and the `updated_at` trigger.

**Safe to run:** Yes (idempotent; guarded with existence checks).

---

### Migration 02: Verify Sucursales Table
**File:** [`migration_02_verify_sucursales_table.sql`](migration_02_verify_sucursales_table.sql)

**Purpose:** Ensures the `sucursales` table exists with all required fields.

**Key Features:**
- Creates the table only when missing.
- Adds expected columns (`negocio_id`, `nombre`, `codigo`, `is_main`, etc.).
- Adds the foreign key to `negocios`.
- Creates useful indexes and a uniqueness check on `(negocio_id, codigo)`.
- Provides triggers to enforce a single main branch.
- Enables RLS.

**Safe to run:** Yes (idempotent).

---

### Migration 03: Add Missing Foreign Keys
**File:** [`migration_03_add_missing_foreign_keys.sql`](migration_03_add_missing_foreign_keys.sql)

**Purpose:** Adds `negocio_id` and `sucursal_id` columns to operational tables.

**Tables Modified:**
- `usuarios` (negocio_id, sucursal_id)
- `productos` (negocio_id)
- `clientes` (negocio_id)
- `proveedores` (negocio_id)
- `ventas` (negocio_id, sucursal_id)
- `compras` (negocio_id, sucursal_id)
- `inventario_sucursal` (negocio_id, sucursal_id)
- `audit_log` (negocio_id, sucursal_id)
- `eventos` (negocio_id, sucursal_id)
- `notificaciones` (negocio_id, sucursal_id)
- `transferencias_stock` (negocio_id)
- `venta_detalle` (negocio_id, sucursal_id)
- `compras_detalle` (negocio_id, sucursal_id)

**Key Features:**
- Adds columns only when they are missing.
- Backfills detail tables from their parent headers.
- Provides triggers to keep the detail tables in sync.

**Safe to run:** Yes (idempotent).

**Important:** Existing data can still contain NULL values if the backfill steps have not been executed. Run `scripts/qa_verify_branch_columns.sql` (via `python scripts/execute_sql_file.py ...`) to detect pending rows and apply the remediation snippets provided in that script.

---

### Migration 04: Add Foreign Key Constraints
**File:** [`migration_04_add_foreign_key_constraints.sql`](migration_04_add_foreign_key_constraints.sql)

**Purpose:** Adds all foreign key constraints for data integrity.

**Key Features:**
- Creates FK constraints for `negocio_id -> negocios.id`.
- Creates FK constraints for `sucursal_id -> sucursales.id`.
- Handles special cases (`transferencias_stock` origin/destination FKs).
- Covers the `usuarios_sucursales` junction table.

**Safe to run:** Yes (idempotent).

**Warning:** This script fails if NULL or invalid references remain. Ensure data is clean (see Migration 03 notes) before executing.

---

### Migration 05: Create Performance Indexes
**File:** [`migration_05_create_performance_indexes.sql`](migration_05_create_performance_indexes.sql)

**Purpose:** Creates guarded indexes for optimal query performance without assuming optional tables or columns exist.

**Key Features:**
- Uses a helper (`ensure_index_columns`) that checks for tables/columns and logs actions with `NOTICE`.
- Ensures core indexes for `usuarios`, `productos`, `clientes`, `proveedores`, `ventas`, `compras`, `venta_detalle`, `compras_detalle`, and `usuarios_sucursales`.
- Adds optional indexes (for `estado` filters, etc.) only when the column is present.
- Runs `ANALYZE` on observed tables and drops the helper function afterward.

**Safe to run:** Yes (idempotent and fully guarded).

**Performance Impact:** Index creation can take time on large tables. Review the `NOTICE` output to confirm what was created versus skipped.

---

### Migration 06: Create Auto Main Branch Trigger
**File:** [`migration_06_create_auto_main_branch_trigger.sql`](migration_06_create_auto_main_branch_trigger.sql)

**Purpose:** Creates triggers to automatically manage main branches.

**Key Features:**
- Automatically creates a "Principal" branch when a negocio is inserted.
- Ensures the creator is assigned to the main branch through `usuarios_sucursales`.
- Updates `usuarios.sucursal_id` to keep the default branch in sync.

**Safe to run:** Yes (idempotent).

---

### Migration 07: Update RLS Policies
**File:** [`migration_07_update_rls_policies.sql`](migration_07_update_rls_policies.sql)

**Purpose:** Consolidates and hardens all RLS policies so that every sensitive table enforces isolation by `negocio_id` (and `sucursal_id` when applicable).

**Key Features:**
- Defines helper functions (`jwt_claim_negocio_id`, `user_in_business`, `user_can_access_branch`, etc.) that encapsulate membership checks and JWT validation.
- Replaces legacy policies for `negocios`, `usuarios_negocios`, `usuarios_sucursales`, `sucursales`, `usuarios`, `productos`, `clientes`, `proveedores`, `servicios`, `suscripciones`, `ventas`, `venta_detalle`, `compras`, `compras_detalle` e `inventario_sucursal`.
- Enforces branch-level access through `usuarios_sucursales` while preserving full visibility for business admins.
- Idempotent by design: drops existing policies before recreating the standardized ones.

**Safe to run:** Yes (idempotent; only affects RLS definitions).

**Follow-up:** Validate isolation by executing `scripts/qa_verify_branch_columns.sql` and the manual RLS checks described in `Reestructura_multi_empresa.md`.

---

## Execution Order

**IMPORTANT:** Execute the scripts in the following order:

```bash
python scripts/execute_sql_file.py scripts/migration_01_verify_negocios_table.sql
python scripts/execute_sql_file.py scripts/migration_02_verify_sucursales_table.sql
python scripts/execute_sql_file.py scripts/migration_03_add_missing_foreign_keys.sql
python scripts/execute_sql_file.py scripts/migration_04_add_foreign_key_constraints.sql
python scripts/execute_sql_file.py scripts/migration_05_create_performance_indexes.sql
python scripts/execute_sql_file.py scripts/migration_06_create_auto_main_branch_trigger.sql
python scripts/execute_sql_file.py scripts/migration_07_update_rls_policies.sql
```

---

## Utility & QA Scripts

- `scripts/execute_sql_file.py`: Helper to run SQL files against Supabase, with environment selection (`.env`, `.env.qa`, etc.).
- `scripts/qa_verify_branch_columns.sql`: QA script that checks column presence/null counts across the main branch-aware tables and includes remediation snippets for backfilling.
- `scripts/test_main_branch_trigger.py`: Regression test for the automatic main-branch trigger; run it against staging after deploying migrations.

Run the QA script after migrations:

```bash
python scripts/execute_sql_file.py scripts/qa_verify_branch_columns.sql
```

---

## Testing Queries

After migration, test with these queries:

```sql
-- Check negocios and their sucursales
SELECT 
    n.id as negocio_id,
    n.nombre as negocio,
    s.id as sucursal_id,
    s.nombre as sucursal,
    s.is_main
FROM negocios n
LEFT JOIN sucursales s ON s.negocio_id = n.id
ORDER BY n.nombre, s.is_main DESC, s.nombre;

-- Check for records without negocio_id
SELECT 'usuarios' as tabla, COUNT(*) as sin_negocio
FROM usuarios WHERE negocio_id IS NULL
UNION ALL
SELECT 'productos', COUNT(*) FROM productos WHERE negocio_id IS NULL
UNION ALL
SELECT 'ventas', COUNT(*) FROM ventas WHERE negocio_id IS NULL;

-- Check for records without sucursal_id (where required)
SELECT 'ventas' as tabla, COUNT(*) as sin_sucursal
FROM ventas WHERE sucursal_id IS NULL
UNION ALL
SELECT 'compras', COUNT(*) FROM compras WHERE sucursal_id IS NULL
UNION ALL
SELECT 'inventario_sucursal', COUNT(*) FROM inventario_sucursal WHERE sucursal_id IS NULL;

-- Verify indexes were created
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
AND (indexname LIKE '%negocio%' OR indexname LIKE '%sucursal%')
ORDER BY tablename, indexname;

-- Check triggers
SELECT 
    trigger_name,
    event_object_table,
    action_statement
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table, trigger_name;
```

---

## Rollback Strategy

If you need to rollback:

1. **Restore from backup** (recommended)
2. Or manually:
   ```sql
   -- Drop triggers
   DROP TRIGGER IF EXISTS trigger_create_main_sucursal ON public.negocios;
   DROP TRIGGER IF EXISTS trigger_validate_main_sucursal ON public.sucursales;
   -- etc.
   
   -- Drop foreign keys
   ALTER TABLE public.usuarios DROP CONSTRAINT IF EXISTS fk_usuarios_negocio_id;
   -- etc.
   
   -- Drop indexes
   DROP INDEX IF EXISTS idx_usuarios_negocio_id;
   -- etc.
   
   -- Drop columns (CAUTION: This will delete data!)
   ALTER TABLE public.usuarios DROP COLUMN IF EXISTS negocio_id;
   -- etc.
   ```

---

## Troubleshooting

### Common Issues

**Issue:** Foreign key constraint fails
```
ERROR: insert or update on table "X" violates foreign key constraint "fk_X_negocio_id"
```
**Solution:** Ensure all negocio_id values reference existing records in negocios table.

---

**Issue:** Cannot delete main branch
```
ERROR: Cannot remove the last main branch
```
**Solution:** This is expected behavior. Create another main branch first, or delete the entire negocio.

---

**Issue:** Duplicate key violation on sucursal codigo
```
ERROR: duplicate key value violates unique constraint "unique_sucursal_codigo_per_negocio"
```
**Solution:** Ensure codigo is unique within each negocio, or set codigo to NULL.

---

## Support

For issues or questions:
1. Review the technical report: `Informe_tecnico_base_de_datos.md`
2. Review the restructuring plan: `Reestructura_multi_empresa.md`
3. Check the backend code for context usage
4. Consult the Supabase documentation for RLS policies

---

**Remember:** Always test in a non-production environment first!

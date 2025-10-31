-- =====================================================
-- MASTER MIGRATION SCRIPT - Multi-Business Structure
-- =====================================================
-- Description: Executes all migration scripts in the correct order
-- Author: Database Migration Script
-- Date: 2025-01-20
-- 
-- IMPORTANT: 
-- - Make sure you have a BACKUP before running this script!
-- - Review each migration script individually first
-- - Test in a staging environment before production
-- - This script is idempotent and safe to re-run
-- =====================================================

\echo '======================================================'
\echo 'Starting Multi-Business Database Migration'
\echo 'Date: ' `date`
\echo '======================================================'
\echo ''

-- Set client encoding and timezone
SET client_encoding = 'UTF8';
SET timezone = 'UTC';

-- Enable timing to see how long each step takes
\timing on

\echo ''
\echo '======================================================'
\echo 'STEP 1/10: Verifying NEGOCIOS table structure'
\echo '======================================================'
\echo ''
\i migration_01_verify_negocios_table.sql

\echo ''
\echo '======================================================'
\echo 'STEP 2/10: Verifying SUCURSALES table structure'
\echo '======================================================'
\echo ''
\i migration_02_verify_sucursales_table.sql

\echo ''
\echo '======================================================'
\echo 'STEP 3/10: Adding missing negocio_id and sucursal_id columns'
\echo '======================================================'
\echo ''
\i migration_03_add_missing_foreign_keys.sql

\echo ''
\echo '======================================================'
\echo 'STEP 4/10: Adding foreign key constraints'
\echo 'WARNING: This will fail if there are invalid references!'
\echo '======================================================'
\echo ''
\i migration_04_add_foreign_key_constraints.sql

\echo ''
\echo '======================================================'
\echo 'STEP 5/10: Creating performance indexes'
\echo 'NOTE: This may take time on large tables'
\echo '======================================================'
\echo ''
\i migration_05_create_performance_indexes.sql

\echo ''
\echo '======================================================'
\echo 'STEP 6/10: Creating automatic main branch triggers'
\echo '======================================================'
\echo ''
\i migration_06_create_auto_main_branch_trigger.sql

\echo ''
\echo '======================================================'
\echo 'STEP 7/10: Updating RLS policies'
\echo '======================================================'
\echo ''
\i migration_07_update_rls_policies.sql

\echo ''
\echo '======================================================'
\echo 'STEP 8/10: Creating branch mode structures'
\echo '======================================================'
\echo ''
\i migration_08a_create_branch_mode_structures.sql

\echo ''
\echo '======================================================'
\echo 'STEP 9/10: Backfilling branch catalog'
\echo '======================================================'
\echo ''
\i migration_08_backfill_branch_catalog.sql

\echo ''
\echo '======================================================'
\echo 'STEP 10/10: Creating reporting views'
\echo '======================================================'
\echo ''
\i migration_08_create_reporting_views.sql

\echo ''
\echo '======================================================'
\echo 'MIGRATION COMPLETED SUCCESSFULLY!'
\echo '======================================================'
\echo ''
\echo 'Next steps:'
\echo '1. Verify all negocios have at least one sucursal'
\echo '2. Populate NULL negocio_id and sucursal_id values'
\echo '3. Ejecutar scripts de QA (qa_verify_branch_columns + simulate_inventory_mode_switch)'
\echo '4. Validar endpoints backend y workers con los nuevos modos de inventario'
\echo '5. Actualizar frontend para reflejar configuraciones y transferencias'
\echo ''
\echo 'Run validation queries from MIGRATION_README.md to verify'
\echo '======================================================'

-- Disable timing
\timing off

-- Show summary statistics
\echo ''
\echo 'Database Statistics:'
\echo '===================='

SELECT 
    'Negocios' as tabla,
    COUNT(*) as total
FROM public.negocios
UNION ALL
SELECT 
    'Sucursales',
    COUNT(*)
FROM public.sucursales
UNION ALL
SELECT 
    'Main Branches',
    COUNT(*)
FROM public.sucursales
WHERE is_main = TRUE;

\echo ''
\echo 'Tables with negocio_id:'
\echo '======================='

SELECT 
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
AND column_name = 'negocio_id'
ORDER BY table_name;

\echo ''
\echo 'Tables with sucursal_id:'
\echo '========================'

SELECT 
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
AND column_name = 'sucursal_id'
ORDER BY table_name;

\echo ''
\echo 'Foreign Key Constraints:'
\echo '========================'

SELECT 
    tc.table_name,
    tc.constraint_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
    AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
AND tc.table_schema = 'public'
AND (kcu.column_name = 'negocio_id' OR kcu.column_name = 'sucursal_id')
ORDER BY tc.table_name, kcu.column_name;

\echo ''
\echo 'Indexes Created:'
\echo '================'

SELECT 
    tablename,
    indexname
FROM pg_indexes
WHERE schemaname = 'public'
AND (indexname LIKE '%negocio%' OR indexname LIKE '%sucursal%')
ORDER BY tablename, indexname;

\echo ''
\echo 'Triggers Created:'
\echo '================='

SELECT 
    trigger_name,
    event_object_table as table_name,
    action_timing,
    event_manipulation
FROM information_schema.triggers
WHERE trigger_schema = 'public'
AND (trigger_name LIKE '%negocio%' OR trigger_name LIKE '%sucursal%')
ORDER BY event_object_table, trigger_name;

\echo ''
\echo '======================================================'
\echo 'Migration execution completed!'
\echo 'Review the output above for any errors or warnings'
\echo '======================================================'

# Snapshot multi negocio (octubre 2025)

Este directorio guarda copias congeladas de los artefactos finales de la reestructuracion multi negocio/sucursal.

- `migration_final_snapshot.sql`: version final ejecutada de `scripts/migration_07_update_rls_policies.sql`.
- `qa_snapshot.sql`: script QA utilizado para validar columnas negocio/sucursal (`scripts/qa_verify_branch_columns.sql`).
- `rollback_snapshot.sql`: plan de rollback entregado junto con la migracion (`scripts/rollback_plan.sql`).

Mantener estas copias facilita auditorias futuras y evita que cambios posteriores en `scripts/` afecten la documentacion del proyecto.

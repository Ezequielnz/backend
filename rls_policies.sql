-- Enable RLS for all tables
ALTER TABLE clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE tareas ENABLE ROW LEVEL SECURITY;
ALTER TABLE productos ENABLE ROW LEVEL SECURITY;
ALTER TABLE categorias ENABLE ROW LEVEL SECURITY;
ALTER TABLE ventas ENABLE ROW LEVEL SECURITY;
ALTER TABLE venta_detalle ENABLE ROW LEVEL SECURITY;
ALTER TABLE configuracion_area ENABLE ROW LEVEL SECURITY;

-- Force RLS for table owners (recommended by Supabase)
ALTER TABLE clientes FORCE ROW LEVEL SECURITY;
ALTER TABLE usuarios FORCE ROW LEVEL SECURITY;
ALTER TABLE tareas FORCE ROW LEVEL SECURITY;
ALTER TABLE productos FORCE ROW LEVEL SECURITY;
ALTER TABLE categorias FORCE ROW LEVEL SECURITY;
ALTER TABLE ventas FORCE ROW LEVEL SECURITY;
ALTER TABLE venta_detalle FORCE ROW LEVEL SECURITY;
ALTER TABLE configuracion_area FORCE ROW LEVEL SECURITY;

-- Policies for 'usuarios' table
-- Users can view their own record. Assuming 'usuarios.id' is the UUID from auth.users.
CREATE POLICY "Allow individual user select access"
ON usuarios
FOR SELECT
USING (auth.uid() = id);

-- Users can update their own record.
CREATE POLICY "Allow individual user update access"
ON usuarios
FOR UPDATE
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id);

-- Policies for 'clientes' table
-- WARNING: This table lacks a direct user ownership column (e.g., user_id or empleado_id).
-- The following policy allows any authenticated user to VIEW clients.
-- ALL OTHER OPERATIONS (INSERT, UPDATE, DELETE) ARE DISALLOWED by default for safety.
-- A proper ownership mechanism (e.g., an 'owner_id' column) is STRONGLY recommended for this table.
CREATE POLICY "Allow authenticated users to select clientes"
ON clientes
FOR SELECT
USING (auth.role() = 'authenticated');

-- Policies for 'tareas' table
-- Users can select tasks assigned to them or created by them.
-- Assuming 'asignado_id' and 'creado_por' store UUIDs corresponding to auth.uid().
CREATE POLICY "Allow select access to assigned or created tasks"
ON tareas
FOR SELECT
USING (auth.uid() = asignado_id OR auth.uid() = creado_por);

-- Users can insert new tasks, 'creado_por' will be their ID.
CREATE POLICY "Allow insert access for tasks"
ON tareas
FOR INSERT
WITH CHECK (auth.uid() = creado_por);

-- Users can update tasks assigned to them or created by them.
CREATE POLICY "Allow update access to assigned or created tasks"
ON tareas
FOR UPDATE
USING (auth.uid() = asignado_id OR auth.uid() = creado_por)
WITH CHECK (auth.uid() = asignado_id OR auth.uid() = creado_por);

-- Users can delete tasks created by them.
CREATE POLICY "Allow delete access to created tasks"
ON tareas
FOR DELETE
USING (auth.uid() = creado_por);


-- Policies for 'productos' table
-- Authenticated users can select products.
CREATE POLICY "Allow select access to products for authenticated users"
ON productos
FOR SELECT
USING (auth.role() = 'authenticated');

-- Policies for 'categorias' table
-- Authenticated users can select categories.
CREATE POLICY "Allow select access to categories for authenticated users"
ON categorias
FOR SELECT
USING (auth.role() = 'authenticated');


-- Policies for 'ventas' table
-- Users can select their own sales. Assuming 'empleado_id' stores UUIDs corresponding to auth.uid().
CREATE POLICY "Allow select access to own sales"
ON ventas
FOR SELECT
USING (auth.uid() = empleado_id);

-- Users can insert their own sales.
CREATE POLICY "Allow insert access to own sales"
ON ventas
FOR INSERT
WITH CHECK (auth.uid() = empleado_id);

-- Users can update their own sales.
CREATE POLICY "Allow update access to own sales"
ON ventas
FOR UPDATE
USING (auth.uid() = empleado_id)
WITH CHECK (auth.uid() = empleado_id);

-- Optional: Users can delete their own sales. Uncomment if needed.
-- CREATE POLICY "Allow delete access to own sales"
-- ON ventas
-- FOR DELETE
-- USING (auth.uid() = empleado_id);


-- Policies for 'venta_detalle' table
-- Users can select sale details if they can access the parent sale.
CREATE POLICY "Allow select access to sale details based on parent sale"
ON venta_detalle
FOR SELECT
USING (
  EXISTS (
    SELECT 1
    FROM ventas
    WHERE ventas.id = venta_detalle.venta_id
    AND ventas.empleado_id = auth.uid() -- Assumes ventas.empleado_id is the user's auth UUID
  )
);

-- Users can insert sale details if they are creating it for their own sale.
CREATE POLICY "Allow insert access to sale details for own sales"
ON venta_detalle
FOR INSERT
WITH CHECK (
  EXISTS (
    SELECT 1
    FROM ventas
    WHERE ventas.id = venta_detalle.venta_id
    AND ventas.empleado_id = auth.uid()
  )
);

-- Users can update sale details if they belong to their own sale.
CREATE POLICY "Allow update access to sale details for own sales"
ON venta_detalle
FOR UPDATE
USING (
  EXISTS (
    SELECT 1
    FROM ventas
    WHERE ventas.id = venta_detalle.venta_id
    AND ventas.empleado_id = auth.uid()
  )
)
WITH CHECK ( -- Redundant if USING is correct, but good for safety
  EXISTS (
    SELECT 1
    FROM ventas
    WHERE ventas.id = venta_detalle.venta_id
    AND ventas.empleado_id = auth.uid()
  )
);

-- Users can delete sale details if they belong to their own sale.
CREATE POLICY "Allow delete access to sale details for own sales"
ON venta_detalle
FOR DELETE
USING (
  EXISTS (
    SELECT 1
    FROM ventas
    WHERE ventas.id = venta_detalle.venta_id
    AND ventas.empleado_id = auth.uid()
  )
);

-- Policies for 'configuracion_area' table
-- No explicit policies grant access. After RLS is enabled and forced,
-- only roles that bypass RLS (e.g., service_role) or superusers can access this table.
-- This is generally appropriate for sensitive configuration data.
-- If specific admin users need access, define policies for their roles.
-- Example for admin access (uncomment and adapt if needed):
-- CREATE POLICY "Allow admin full access to configuracion_area"
-- ON configuracion_area
-- FOR ALL
-- USING (get_my_claim('user_role') = 'admin'::text) -- Example using a custom JWT claim
-- WITH CHECK (get_my_claim('user_role') = 'admin'::text);

/*
IMPORTANT NOTES AND ASSUMPTIONS:

1.  User ID Fields:
    These policies assume that `usuarios.id`, `tareas.asignado_id`, `tareas.creado_por`,
    and `ventas.empleado_id` are UUID columns that directly reference `auth.users.id`.
    If your primary keys for users in these tables are, for example, auto-incrementing integers,
    and you have a *separate* column (e.g., `user_auth_id UUID`) that stores the `auth.uid()`,
    YOU MUST MODIFY THE POLICIES to use that correct column for checks against `auth.uid()`.
    Example: `USING (auth.uid() = user_auth_id)`.

2.  `clientes` Table:
    As highlighted by the WARNING in its policy section, the `clientes` table lacks a clear
    ownership link to users in the provided model. The current policy makes it read-only for
    all authenticated users and disallows INSERT/UPDATE/DELETE for safety.
    This is a temporary, restrictive measure. For proper functionality, you should:
    a. Add an `owner_id` (or `empleado_id`, etc.) column to `clientes` that links to a user.
    b. Update the RLS policies for `clientes` to use this new column for row ownership.

3.  `venta_detalle` Operations:
    Policies for `venta_detalle` are defined for SELECT, INSERT, UPDATE, and DELETE,
    all ensuring that operations are tied to the user's ownership of the parent `venta` record.

4.  Admin Access / `service_role`:
    Users with the `service_role` (typically used with the Supabase Admin API key for backend operations)
    will bypass these RLS policies by default. This is expected.
    If you have non-superuser admin roles that need broader access, create specific policies for them.

5.  Testing:
    Thoroughly test all policies from the perspective of different user accounts and roles.
    Use Supabase's SQL Editor (or client libraries) to verify:
    - Users can only see/modify their own data in `usuarios`, `tareas`, `ventas`, `venta_detalle`.
    - Users can only view `productos`, `categorias`, and `clientes`.
    - `configuracion_area` is inaccessible to normal users.
    - INSERT, UPDATE, and DELETE operations respect the defined checks.

6.  `FORCE ROW LEVEL SECURITY`:
    This ensures that table owners are also subject to RLS policies, which is crucial for effective security.

7.  No Deletion Policy for `ventas`:
    The policy to allow users to delete their own `ventas` is commented out. This is often a business
    decision, as sales records might need to be archived or marked inactive rather than deleted.
    Uncomment and use if direct deletion by users is required.
*/

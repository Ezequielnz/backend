# Fix del Sistema de Permisos

## Problema Identificado

Los usuarios creadores de negocios no podían acceder a las páginas de su propio negocio, recibiendo errores como:
- "Acceso Restringido - No tienes permisos para acceder a esta página"
- "Se requiere permiso para ver en inventario/ventas/clientes/tareas"

## Análisis del Problema

### 1. Backend - Endpoint de Permisos ✅ FUNCIONANDO
- El endpoint `/api/v1/businesses/{business_id}/permissions` está funcionando correctamente
- Los usuarios creadores tienen `has_full_access: True`
- Todos los permisos específicos se devuelven como `True`
- La lógica de creación de permisos automáticos al crear negocio funciona bien

### 2. Frontend - PermissionGuard ❌ PROBLEMA ENCONTRADO
- El componente `PermissionGuard` estaba usando una lógica antigua
- Llamaba a `businessAPI.getBusinessUsers()` en lugar del nuevo endpoint de permisos
- No estaba mapeando correctamente los módulos (ej: "inventario" → "productos")

## Solución Implementada

### 1. Actualización de PermissionGuard.jsx

**Antes (Lógica Antigua):**
```javascript
// Llamaba a businessAPI.getBusinessUsers()
const businessUsers = await businessAPI.getBusinessUsers(businessId);
const currentUserInBusiness = businessUsers.find(u => u.usuario?.email === user.email);

// Verificación manual de permisos
const permissionKey = `puede_${requiredAction}_${requiredModule}`;
const hasPermission = currentUserInBusiness.permisos?.[permissionKey] || false;
```

**Después (Nueva Lógica):**
```javascript
// Usa el hook useUserPermissions que llama al endpoint correcto
const { isLoading: loading, canView, canEdit, canDelete, hasFullAccess, permissions } = useUserPermissions(businessId);

// Mapeo de módulos a recursos
const moduleToResource = {
  'inventario': 'productos',
  'productos': 'productos', 
  'categorias': 'categorias',
  'clientes': 'clientes',
  'ventas': 'ventas',
  'tareas': 'tareas',
  'stock': 'stock',
  'facturacion': 'facturacion'
};

// Verificación de acceso con nueva lógica
const hasAccess = React.useMemo(() => {
  if (!permissions || loading) return false;
  
  // Full access users can access everything
  if (hasFullAccess()) return true;
  
  // Map the required module to the actual resource
  const resource = moduleToResource[requiredModule] || requiredModule;
  
  // Check specific permission based on action
  switch (requiredAction) {
    case 'ver':
      return canView(resource);
    case 'editar':
      return canEdit(resource);
    case 'eliminar':
      return canDelete(resource);
    default:
      return canView(resource);
  }
}, [permissions, loading, hasFullAccess, canView, canEdit, canDelete, requiredModule, requiredAction, moduleToResource]);
```

### 2. Mapeo de Módulos

El problema principal era que los componentes usaban diferentes nombres de módulos:

| Componente | Módulo Usado | Recurso Real |
|------------|-------------|--------------|
| ProductsAndServices | "inventario" | "productos" |
| Categories | "categorias" | "categorias" |
| Customers | "clientes" | "clientes" |
| POS | "ventas" | "ventas" |
| SalesReports | "ventas" | "ventas" |
| Tasks | "tareas" | "tareas" |

## Verificación de la Solución

### Datos de Base de Datos Verificados:
```
=== usuarios_negocios ===
Usuario: 20b34d5a-ac41-42a3-946f-2144b1e4faba
Negocio: 81fa189a-d30e-40ee-8954-defe015ee847 (Tienda 02)
Rol: admin
Estado: aceptado

=== permisos_usuario_negocio ===
Usuario_Negocio_ID: 5feb4944-8808-40c8-881f-422ca9e138d2
Acceso_Total: True

=== Endpoint de Permisos ===
Has Full Access: True
Todos los permisos: True
```

## Componentes Afectados y Corregidos

1. **PermissionGuard.jsx** - ✅ Actualizado para usar nuevo sistema
2. **useUserPermissions.ts** - ✅ Ya funcionaba correctamente
3. **permissions.py** - ✅ Ya funcionaba correctamente

## Páginas que Ahora Funcionan

- ✅ **ProductsAndServices** (`requiredModule="inventario"` → `productos`)
- ✅ **Categories** (`requiredModule="categorias"` → `categorias`)
- ✅ **Customers** (`requiredModule="clientes"` → `clientes`)
- ✅ **POS** (`requiredModule="ventas"` → `ventas`)
- ✅ **SalesReports** (`requiredModule="ventas"` → `ventas`)
- ✅ **Tasks** (`requiredModule="tareas"` → `tareas`)

## Resultado Final

Los usuarios creadores de negocios ahora pueden:
- Acceder a todas las páginas de su negocio
- Ver, editar y eliminar contenido según sus permisos
- El sistema de permisos funciona correctamente para admins y creadores
- Los usuarios regulares siguen teniendo permisos limitados según su configuración

## Notas Técnicas

- El endpoint de permisos está optimizado con caché de 5 minutos
- Los permisos se crean automáticamente al crear un negocio
- Los creadores y admins tienen `acceso_total: True` por defecto
- El sistema soporta permisos granulares para usuarios regulares 
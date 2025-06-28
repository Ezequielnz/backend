# Sistema de Invitaciones de Negocio

## Cambios Realizados

### 1. Frontend (Registro)
- **Eliminado**: Funcionalidad de búsqueda y vinculación a negocios existentes durante el registro
- **Nuevo**: Cada usuario que se registra automáticamente crea su propio negocio
- **Información**: Se muestra un mensaje informativo sobre cómo unirse a negocios existentes mediante invitaciones

### 2. Backend (Lógica de Registro)
- **Eliminado**: Campos `negocio_id` y `nuevo_negocio_nombre` del esquema `UserSignUp`
- **Nuevo**: Registro simple sin crear negocio automáticamente
- **Flexibilidad**: Usuario puede crear negocio manualmente o ser invitado a uno existente

### 3. Base de Datos (Políticas RLS)
- **Script**: `backend/scripts/update_business_invitation_logic.sql`
- **Cambio**: Solo administradores pueden invitar usuarios (no al revés)
- **Política INSERT**: Reemplazada para permitir solo invitaciones por admin
- **Política UPDATE**: Actualizada para permitir solo cambios por admin

### 4. Nuevos Endpoints de Invitación

#### POST `/api/v1/businesses/{business_id}/invitaciones`
- **Función**: Invitar usuario a negocio (solo admin)
- **Esquema**: `InvitacionCreate`
- **Respuesta**: `InvitacionResponse`
- **Estado actual**: Crea invitación en BD, no envía email aún

#### PUT `/api/v1/businesses/{business_id}/usuarios/{usuario_negocio_id}/estado`
- **Función**: Aceptar/rechazar invitación o cambiar estado de usuario
- **Esquema**: `UsuarioNegocioUpdate`
- **Permisos**: Usuario propio o admin del negocio

## Flujo Actual vs Futuro

### Flujo Actual (Implementado)
1. Usuario se registra → Cuenta creada sin negocio
2. Usuario puede crear su propio negocio O ser invitado a uno existente
3. Admin de negocio invita usuario existente → Se crea relación pendiente
4. Usuario invitado acepta/rechaza desde su dashboard
5. Admin puede gestionar usuarios y permisos

### Flujo Futuro (Por Implementar)
1. Admin invita usuario por email → Se envía email con link de invitación
2. Usuario hace clic en link → Si no existe, se registra; si existe, acepta invitación
3. Sistema de notificaciones por email (Resend/SendGrid)
4. Tokens de invitación con expiración

## Estructura de Permisos Mantenida

La estructura de permisos existente se mantiene intacta:
- Tabla `usuarios_negocios`: relación usuario-negocio con rol y estado
- Tabla `permisos_usuario_negocio`: permisos granulares por usuario
- Roles: `admin`, `empleado`
- Estados: `pendiente`, `aceptado`, `rechazado`

## Endpoints Existentes que Siguen Funcionando

- Gestión de usuarios del negocio
- Actualización de permisos
- Aprobación/rechazo de solicitudes pendientes
- Listado de usuarios y notificaciones

## Para Ejecutar los Cambios

1. **Frontend**: Los cambios ya están aplicados
2. **Backend**: Los cambios ya están aplicados
3. **Base de Datos**: Ejecutar manualmente el script:
   ```sql
   -- Copiar y ejecutar el contenido de:
   backend/scripts/update_business_invitation_logic.sql
   ```

## Próximos Pasos

1. **Implementar envío de emails**: Integrar Resend o SendGrid
2. **Crear página de aceptación de invitaciones**: Frontend para links de invitación
3. **Sistema de tokens**: Generar y validar tokens de invitación
4. **Notificaciones**: Sistema de notificaciones en tiempo real
5. **UI de invitaciones**: Interfaz para que admins gestionen invitaciones 
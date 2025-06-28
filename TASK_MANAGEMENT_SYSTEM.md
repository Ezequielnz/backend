# Sistema de Gestión de Tareas

## 📋 Descripción General

El sistema de gestión de tareas permite a los negocios crear, asignar y hacer seguimiento de tareas para sus empleados. Incluye un sistema completo de permisos, filtros avanzados, estadísticas y vista de calendario.

## 🗄️ Estructura de Base de Datos

### Tabla: `tareas`
```sql
- id (uuid, PK)
- titulo (text, NOT NULL)
- descripcion (text, nullable)
- fecha_inicio (timestamptz, nullable)
- fecha_fin (timestamptz, nullable)
- asignada_a_id (uuid, nullable) → FK a usuarios_negocios.id
- creada_por_id (uuid, nullable) → FK a usuarios_negocios.id
- estado (text, nullable) → pendiente, en_progreso, completada, cancelada, pausada
- prioridad (text, nullable) → baja, media, alta, urgente
- creado_en (timestamptz, nullable)
- actualizado_en (timestamptz, nullable)
- negocio_id (uuid, nullable) → FK a negocios.id
```

### Políticas RLS
- **SELECT**: Usuarios pueden ver tareas asignadas a ellos, creadas por ellos, o con permiso `puede_ver_tareas`
- **INSERT**: Solo usuarios con permiso `puede_asignar_tareas`
- **UPDATE**: Solo creador de la tarea o usuarios con permiso `puede_editar_tareas`
- **DELETE**: Solo creador de la tarea o usuarios con permiso `puede_editar_tareas`

## 🔧 API Endpoints

### Base URL: `/businesses/{business_id}/tareas`

#### 1. Listar Tareas
```http
GET /businesses/{business_id}/tareas
```
**Parámetros de Query:**
- `pagina` (int): Número de página (default: 1)
- `por_pagina` (int): Tareas por página (default: 20, max: 100)
- `estado` (enum): Filtrar por estado
- `prioridad` (enum): Filtrar por prioridad
- `asignada_a_id` (uuid): Filtrar por usuario asignado
- `creada_por_id` (uuid): Filtrar por creador
- `fecha_inicio_desde` (datetime): Fecha inicio desde
- `fecha_inicio_hasta` (datetime): Fecha inicio hasta
- `busqueda` (string): Búsqueda en título/descripción

**Respuesta:**
```json
{
  "tareas": [...],
  "total": 50,
  "pagina": 1,
  "por_pagina": 20,
  "total_paginas": 3
}
```

#### 2. Crear Tarea
```http
POST /businesses/{business_id}/tareas
```
**Body:**
```json
{
  "titulo": "Revisar inventario",
  "descripcion": "Revisar stock de productos críticos",
  "fecha_inicio": "2024-01-15T09:00:00",
  "fecha_fin": "2024-01-15T17:00:00",
  "estado": "pendiente",
  "prioridad": "alta",
  "asignada_a_id": "uuid-del-empleado"
}
```

#### 3. Obtener Tarea
```http
GET /businesses/{business_id}/tareas/{tarea_id}
```

#### 4. Actualizar Tarea
```http
PUT /businesses/{business_id}/tareas/{tarea_id}
```

#### 5. Eliminar Tarea
```http
DELETE /businesses/{business_id}/tareas/{tarea_id}
```

#### 6. Vista Calendario
```http
GET /businesses/{business_id}/tareas/calendario
```
**Parámetros:**
- `fecha_inicio` (datetime): Inicio del rango
- `fecha_fin` (datetime): Fin del rango

#### 7. Estadísticas
```http
GET /businesses/{business_id}/tareas/estadisticas
```
**Respuesta:**
```json
{
  "total_tareas": 25,
  "pendientes": 8,
  "en_progreso": 5,
  "completadas": 10,
  "vencidas": 2,
  "por_prioridad": {
    "baja": 5,
    "media": 10,
    "alta": 7,
    "urgente": 3
  },
  "por_empleado": [
    {
      "id": "uuid",
      "nombre": "Juan Pérez",
      "total": 5,
      "pendientes": 2,
      "en_progreso": 1,
      "completadas": 2
    }
  ]
}
```

#### 8. Listar Empleados
```http
GET /businesses/{business_id}/tareas/empleados
```

## 🔒 Sistema de Permisos

### Permisos Requeridos:
- **`puede_ver_tareas`**: Ver listado y detalles de tareas
- **`puede_asignar_tareas`**: Crear tareas y asignar a empleados
- **`puede_editar_tareas`**: Editar y eliminar tareas

### Lógica de Permisos:
1. **Creadores de negocio**: Tienen todos los permisos automáticamente
2. **Administradores**: Tienen todos los permisos automáticamente
3. **Empleados**: Solo los permisos específicamente otorgados

## 🎨 Frontend

### Componente Principal: `Tasks.jsx`

#### Funcionalidades:
- ✅ Lista de tareas con paginación
- ✅ Dashboard con estadísticas
- ✅ Filtros avanzados (estado, prioridad, empleado, búsqueda)
- ✅ Formulario modal para crear/editar
- ✅ Asignación a empleados del negocio
- ✅ Cambio rápido de estado
- ✅ Vista placeholder para calendario
- ✅ **Integración en dashboard del negocio**
- ✅ **Notificaciones de tareas asignadas**
- ✅ **Vista personal de tareas del usuario**

#### Estados y Prioridades:
```javascript
const ESTADOS = {
  pendiente: { label: 'Pendiente', color: 'bg-yellow-100 text-yellow-800' },
  en_progreso: { label: 'En Progreso', color: 'bg-blue-100 text-blue-800' },
  completada: { label: 'Completada', color: 'bg-green-100 text-green-800' },
  cancelada: { label: 'Cancelada', color: 'bg-red-100 text-red-800' },
  pausada: { label: 'Pausada', color: 'bg-gray-100 text-gray-800' }
};

const PRIORIDADES = {
  baja: { label: 'Baja', color: 'bg-gray-100 text-gray-800' },
  media: { label: 'Media', color: 'bg-blue-100 text-blue-800' },
  alta: { label: 'Alta', color: 'bg-orange-100 text-orange-800' },
  urgente: { label: 'Urgente', color: 'bg-red-100 text-red-800' }
};
```

## 🚀 Cómo Usar

### 1. Activar Backend
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Activar Frontend
```bash
cd client
npm run dev
```

### 3. Acceder al Sistema
1. **Iniciar sesión** en la aplicación
2. **Seleccionar un negocio** desde "Mis Negocios"
3. **Acceder a Tareas** de múltiples formas:
   - **Dashboard del negocio**: Botón "Tareas" en accesos directos
   - **URL directa**: `/business/{businessId}/tasks`
   - **Notificaciones**: Click en "Ver" en alertas de tareas asignadas

### 4. Navegación y Notificaciones

#### 📍 **Ubicación de Tareas:**
- **Panel de Control del Negocio**: Botón prominente en accesos directos
- **Ruta**: `/business/{businessId}/tasks`

#### 🔔 **Sistema de Notificaciones:**
- **Panel de Alertas**: Tareas asignadas al usuario aparecen en el dashboard
- **Mis Tareas Pendientes**: Sección dedicada mostrando hasta 3 tareas del usuario
- **Notificaciones en tiempo real**: Se actualizan al cargar el dashboard

#### 👤 **Vista Personal del Usuario:**
- **Dashboard personal**: Muestra solo tareas asignadas al usuario actual
- **Estados visibles**: Pendiente, En Progreso
- **Información mostrada**: Título, descripción, prioridad, fecha límite
- **Acceso rápido**: Botón "Ver todas" para ir a la vista completa

#### 🗺️ **Flujo de Navegación:**
```
🏠 Dashboard del Negocio
├── 📋 Botón "Tareas" (Accesos Directos) → 📄 Página de Tareas
├── 🔔 Panel de Alertas (Notificaciones) → 📄 Página de Tareas  
└── 👤 "Mis Tareas Pendientes" → 📄 Página de Tareas

📄 Página de Tareas (/business/{id}/tasks)
├── ✅ CRUD Completo de Tareas
├── 📊 Dashboard con Estadísticas
└── 🔍 Filtros y Búsqueda Avanzada
```

## 📊 Flujo de Trabajo Recomendado

### Para Administradores:
1. **Crear tareas** con título, descripción y fechas
2. **Asignar a empleados** específicos del negocio
3. **Establecer prioridad** según urgencia
4. **Monitorear progreso** mediante estadísticas
5. **Revisar tareas vencidas** regularmente

### Para Empleados:
1. **Ver tareas asignadas** en su dashboard
2. **Actualizar estado** conforme avanzan
3. **Marcar como completadas** al finalizar
4. **Comunicar problemas** al administrador

## 🔮 Funcionalidades Futuras

### Próximas Implementaciones:
- [ ] **Vista calendario completa** con librería de calendario
- [ ] **Notificaciones push** para tareas vencidas
- [ ] **Comentarios en tareas** para comunicación
- [ ] **Archivos adjuntos** en tareas
- [ ] **Plantillas de tareas** recurrentes
- [ ] **Reportes avanzados** en PDF/Excel
- [ ] **Integración con email** para notificaciones
- [ ] **Subtareas** y dependencias entre tareas

### Mejoras Técnicas:
- [ ] **Optimización de consultas** para grandes volúmenes
- [ ] **Cache de estadísticas** para mejor performance
- [ ] **Sincronización en tiempo real** con WebSockets
- [ ] **Búsqueda full-text** avanzada
- [ ] **API de webhooks** para integraciones externas

## 🐛 Troubleshooting

### Problemas Comunes:

#### 1. Error de Permisos
**Síntoma**: "No tienes permisos para ver/crear/editar tareas"
**Solución**: Verificar que el usuario tenga los permisos correspondientes en la tabla `permisos_usuario_negocio`

#### 2. Usuario No Encontrado al Asignar
**Síntoma**: "El usuario asignado no pertenece a este negocio"
**Solución**: Verificar que el empleado esté en estado "aceptado" en `usuarios_negocios`

#### 3. Tareas No Se Cargan
**Síntoma**: Lista vacía o error al cargar
**Solución**: 
- Verificar `currentBusinessId` en localStorage
- Comprobar conexión a la API
- Revisar logs del servidor

#### 4. Filtros No Funcionan
**Síntoma**: Filtros no afectan la lista
**Solución**: Verificar que los parámetros se envíen correctamente en la URL

## 📝 Notas de Desarrollo

### Consideraciones Técnicas:
1. **IDs de Usuario vs Usuario_Negocio**: Las tareas usan `usuario_negocio_id` para mantener contexto del negocio
2. **Fechas en UTC**: Todas las fechas se manejan en UTC en el backend
3. **Paginación**: Implementada para manejar grandes volúmenes de tareas
4. **Validaciones**: Tanto en frontend como backend para consistencia
5. **Transacciones**: Operaciones críticas envueltas en transacciones DB

### Patrones Utilizados:
- **Repository Pattern**: Para acceso a datos
- **Dependency Injection**: Para permisos y autenticación
- **Response Models**: Para tipado consistente
- **Error Handling**: Centralizado con mensajes amigables
- **State Management**: Local con React hooks 
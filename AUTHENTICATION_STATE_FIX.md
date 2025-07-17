# Fix de Gestión de Estado de Autenticación

## Problema Identificado

El error `ReferenceError: setUser is not defined` ocurrió después de modificar la lógica de permisos. El problema raíz era que múltiples componentes estaban gestionando el estado del usuario de forma independiente, en lugar de usar el `AuthContext` centralizado.

## Componentes Afectados

### 1. Layout.jsx
**Problema**: Intentaba llamar `setUser(userData)` pero la función no estaba disponible en su scope.

**Solución**: 
- Eliminó la llamada a `authAPI.getCurrentUser()` 
- Eliminó `setUser(userData)`
- Ahora usa solo el usuario del `AuthContext` mediante `const { user } = useAuth()`

```javascript
// ANTES
const [userData, businessesData] = await Promise.all([
  authAPI.getCurrentUser(),
  businessAPI.getBusinesses()
]);
setUser(userData);

// DESPUÉS  
const businessesData = await businessAPI.getBusinesses();
// El usuario ya está disponible en AuthContext
```

### 2. PermissionGuard.jsx
**Problema**: Gestionaba su propio estado de usuario independientemente.

**Soluciones aplicadas**:
- Agregó `import { useAuth } from '../contexts/AuthContext'`
- Cambió `const [user, setUser] = useState(null)` por `const { user } = useAuth()`
- Eliminó `const userData = await authAPI.getCurrentUser(); setUser(userData);`
- Cambió `userData.email` por `user.email`

### 3. MyBusinesses.jsx
**Problema**: Duplicaba la gestión de estado de usuario.

**Soluciones aplicadas**:
- Agregó `import { useAuth } from '../contexts/AuthContext'`
- Cambió `const [user, setUser] = useState(null)` por `const { user } = useAuth()`
- Eliminó la carga redundante de datos de usuario
- Agregó validación de usuario antes de cargar businesses

### 4. Profile.jsx
**Problema**: Gestionaba estado de usuario local y usaba `setUser` para actualizaciones.

**Soluciones aplicadas**:
- Agregó `import { useAuth } from '../contexts/AuthContext'`
- Cambió `const [user, setUser] = useState(null)` por `const { user, login } = useAuth()`
- Eliminó `const userData = await authAPI.getCurrentUser(); setUser(userData);`
- Cambió `setUser(prev => ({ ...prev, ...updatedUser }))` por `login({ ...user, ...updatedUser }, user.access_token)`
- Actualizó el `useEffect` para depender del usuario: `}, [user])`

## Principios de la Solución

### Gestión Centralizada de Estado
- **Un solo punto de verdad**: El `AuthContext` es la única fuente de datos del usuario
- **Eliminación de duplicación**: Los componentes ya no mantienen su propio estado de usuario
- **Consistencia**: Todos los componentes usan la misma instancia de datos de usuario

### Patrón de Uso Correcto
```javascript
// ✅ CORRECTO
import { useAuth } from '../contexts/AuthContext';

function MyComponent() {
  const { user, login, logout } = useAuth();
  
  // Usar user directamente, no cargar datos adicionales
  useEffect(() => {
    if (user) {
      // Lógica que depende del usuario
    }
  }, [user]);
}

// ❌ INCORRECTO
function MyComponent() {
  const [user, setUser] = useState(null);
  
  useEffect(() => {
    const loadUser = async () => {
      const userData = await authAPI.getCurrentUser();
      setUser(userData); // Esto causa inconsistencias
    };
    loadUser();
  }, []);
}
```

## Beneficios de la Solución

1. **Eliminación de errores**: Ya no hay referencias a `setUser` undefined
2. **Mejor rendimiento**: Menos llamadas redundantes a la API
3. **Consistencia de datos**: Un solo estado de usuario en toda la aplicación
4. **Mantenibilidad**: Más fácil de debuggear y mantener
5. **Sincronización automática**: Cambios en el usuario se propagan automáticamente

## Verificación

Para verificar que la solución funciona:

1. **Login**: El usuario debe poder iniciar sesión sin errores
2. **Navigation**: La navegación entre páginas debe mantener el estado del usuario
3. **Permissions**: Los permisos deben cargarse correctamente
4. **Profile Updates**: Las actualizaciones de perfil deben sincronizarse

## Endpoint de Permisos

El endpoint de permisos está correctamente registrado en `api.py`:
```python
api_router.include_router(permissions.router, prefix="", tags=["permissions"])
```

Y está disponible en: `GET /api/v1/businesses/{business_id}/permissions`

### 5. PageHeader.jsx
**Problema**: Cargaba datos de usuario independientemente usando useEffect.

**Soluciones aplicadas**:
- Agregó `import { useAuth } from '../contexts/AuthContext'`
- Eliminó `const [userInfo, setUserInfo] = useState(...)`
- Eliminó el `useEffect` para cargar datos de usuario
- Cambió a calcular `userInfo` directamente desde `user` del AuthContext

### 6. Tasks.jsx
**Problema**: Usaba React Query para cargar usuario independientemente.

**Soluciones aplicadas**:
- Agregó `import { useAuth } from '../contexts/AuthContext'`
- Cambió `const { data: user } = useQuery({...})` por `const { user } = useAuth()`
- Eliminó la query de React Query para getCurrentUser

### 7. BusinessUsers.jsx
**Problema**: Gestionaba estado de usuario local con setCurrentUser.

**Soluciones aplicadas**:
- Agregó `import { useAuth } from '../contexts/AuthContext'`
- Cambió `const [currentUser, setCurrentUser] = useState(null)` por `const { user: currentUser } = useAuth()`
- Eliminó `const userData = await authAPI.getCurrentUser(); setCurrentUser(userData);`
- Agregó validación de usuario antes de cargar datos

## Estado Final

Todos los componentes ahora usan el patrón correcto de gestión de estado:
- ✅ Layout.jsx - Corregido
- ✅ PermissionGuard.jsx - Corregido  
- ✅ MyBusinesses.jsx - Corregido
- ✅ Profile.jsx - Corregido
- ✅ PageHeader.jsx - Corregido
- ✅ Tasks.jsx - Corregido
- ✅ BusinessUsers.jsx - Corregido

**Resultado**: El error `setUser is not defined` ha sido completamente resuelto y ya no hay llamadas redundantes a `authAPI.getCurrentUser()`. 
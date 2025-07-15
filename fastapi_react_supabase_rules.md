# Reglas de Optimización para FastAPI + React + Supabase

## 🚀 FastAPI Backend

### Consultas a Base de Datos
- **SIEMPRE** usa `.select()` específico en lugar de `select("*")` - solo trae los campos necesarios
- **IMPLEMENTA** paginación en todas las consultas que puedan retornar múltiples registros
- **USA** índices compuestos para consultas con múltiples filtros
- **APLICA** `.limit()` por defecto (máximo 100 registros) si no se especifica
- **AGRUPA** consultas relacionadas usando `.select("*, tabla_relacionada(*)")` en lugar de múltiples queries

### Caching y Performance
- **IMPLEMENTA** cache con Redis o memoria para consultas frecuentes
- **USA** `@lru_cache` para funciones puras y cálculos repetitivos
- **APLICA** cache de 5-15 minutos para datos que no cambian frecuentemente
- **EVITA** consultas N+1 usando joins o consultas agrupadas

### Endpoints
- **ESTRUCTURA** endpoints RESTful con verbos HTTP correctos
- **IMPLEMENTA** compresión gzip para responses > 1KB
- **USA** response models de Pydantic para validar y optimizar el JSON de salida
- **APLICA** async/await en todas las operaciones de I/O

### Código Ejemplo FastAPI:
```python
from fastapi import FastAPI, Query, Depends
from functools import lru_cache
import asyncio

# ❌ MAL
@app.get("/users")
async def get_users():
    users = supabase.table("users").select("*").execute()
    return users.data

# ✅ BIEN
@app.get("/users")
async def get_users(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0)
):
    users = supabase.table("users").select(
        "id, name, email, created_at"
    ).range(offset, offset + limit - 1).execute()
    return users.data
```

## ⚛️ React Frontend

### Gestión de Estado
- **USA** React Query/TanStack Query para cache automático de API calls
- **IMPLEMENTA** optimistic updates para mejorar UX
- **APLICA** debouncing (300ms) en inputs de búsqueda
- **EVITA** re-renders innecesarios con React.memo y useMemo

### Carga de Datos
- **IMPLEMENTA** lazy loading para componentes pesados
- **USA** suspense boundaries para loading states
- **APLICA** infinite scroll en lugar de paginación tradicional
- **PRECARGAR** datos críticos en el route principal

### Optimizaciones de Rendering
- **DIVIDE** componentes grandes en componentes más pequeños
- **USA** keys estables en listas (nunca index como key)
- **APLICA** virtualization para listas > 100 items
- **EVITA** inline functions en props cuando sea posible

### Código Ejemplo React:
```jsx
// ❌ MAL
function UserList() {
  const [users, setUsers] = useState([]);
  
  useEffect(() => {
    fetch('/api/users').then(res => res.json()).then(setUsers);
  }, []);
  
  return users.map((user, index) => <UserCard key={index} user={user} />);
}

// ✅ BIEN
import { useQuery } from '@tanstack/react-query';

const UserList = memo(() => {
  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => fetch('/api/users').then(res => res.json()),
    staleTime: 5 * 60 * 1000, // 5 minutos
  });

  if (isLoading) return <Skeleton />;
  
  return users?.map(user => <UserCard key={user.id} user={user} />);
});
```

## 🗄️ Supabase Database

### Diseño de Esquema
- **CREA** índices para todas las columnas usadas en WHERE, ORDER BY, JOIN
- **USA** tipos de datos apropiados (no text para números)
- **IMPLEMENTA** RLS (Row Level Security) para seguridad automática
- **APLICA** foreign keys con ON DELETE CASCADE cuando corresponda

### Optimizaciones de Consultas
- **EVITA** consultas sin índices - siempre revisa el query plan
- **USA** prepared statements para consultas repetitivas
- **IMPLEMENTA** materialized views para consultas complejas frecuentes
- **APLICA** partitioning para tablas > 1M registros

### Políticas RLS Eficientes
- **CREA** políticas RLS que usen índices existentes
- **EVITA** subconsultas complejas en políticas RLS
- **USA** auth.uid() directamente en lugar de joins innecesarios

## 📊 Monitoreo y Métricas

### Métricas Clave a Monitorear
- **API Response Time**: < 200ms para endpoints críticos
- **Database Query Time**: < 100ms para consultas simples
- **React Component Render Time**: < 16ms para 60fps
- **Time to First Contentful Paint**: < 1.5s
- **Cache Hit Rate**: > 80% para datos frecuentes

### Herramientas de Debug
- **USA** React DevTools Profiler para identificar re-renders
- **IMPLEMENTA** logging de performance en producción
- **MONITOREA** slow queries en Supabase Dashboard
- **TRACKEA** Web Vitals en el frontend

## 🔧 Reglas Generales de Implementación

### Para el Agente de Cursor:
1. **SIEMPRE** pregunta si falta paginación antes de escribir un endpoint
2. **REVISA** que cada consulta tenga los índices necesarios
3. **VALIDA** que los componentes React usen memo cuando sea apropiado
4. **VERIFICA** que las consultas a Supabase sean específicas (no select *)
5. **ASEGURA** que existan loading states para toda operación async
6. **IMPLEMENTA** error boundaries para manejo de errores
7. **APLICA** TypeScript estricto en todo el código nuevo

### Checklist de Optimización:
- [ ] Endpoint tiene paginación
- [ ] Consulta usa select específico
- [ ] Existe índice para la consulta
- [ ] Componente usa React.memo si es necesario
- [ ] Hay loading state y error handling
- [ ] Cache implementado para datos frecuentes
- [ ] Response time < 200ms
- [ ] No hay console.logs en producción

## 🎯 Prioridades de Optimización

1. **CRÍTICO**: Consultas de base de datos lentas (> 100ms)
2. **ALTO**: Componentes que re-renderizan frecuentemente
3. **MEDIO**: Endpoints sin cache que se llaman repetitivamente
4. **BAJO**: Optimizaciones de bundle size

### Comandos de Análisis:
```bash
# Analizar bundle size
npm run build --analyze

# Profiling de Supabase
EXPLAIN ANALYZE SELECT ...

# React performance
// Usa React DevTools Profiler
```

**Regla de Oro**: Siempre mide antes de optimizar. Usa las herramientas de dev para identificar los verdaderos cuellos de botella.
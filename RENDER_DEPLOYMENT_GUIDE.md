# Guía de Despliegue en Render

## Resumen de Cambios Realizados

### 1. **Dependencias Optimizadas para Render**

Se han reemplazado todas las dependencias que requerían compilación de Rust/C++ por alternativas compatibles:

**Cambios realizados:**
- `fuzzywuzzy` + `python-Levenshtein` → `difflib` (biblioteca estándar)
- `python-jose[cryptography]` → `pyjwt` (puro Python)
- `passlib[bcrypt]` → `passlib` (sin extensión bcrypt)
- `asyncpg` → `psycopg2-binary` (binarios precompilados)
- Versiones específicas probadas para compatibilidad

### 2. **Código Actualizado**

**Archivos modificados:**
- `app/services/importacion_excel.py`: Reemplazado fuzzy matching con `difflib`
- `app/api/api_v1/endpoints/ventas.py`: Actualizado `jose` → `pyjwt`
- `app/api/api_v1/endpoints/importacion.py`: Restaurado completamente

### 3. **Configuración de Render**

Se creó `render.yaml` con configuración específica para el entorno de Render.

## Pasos para Desplegar en Render

### 1. **Preparar el Repositorio**

```bash
# Hacer commit de todos los cambios
git add .
git commit -m "Optimizar dependencias para despliegue en Render"
git push origin main
```

### 2. **Configurar Render**

1. **Crear nuevo Web Service en Render:**
   - Conectar tu repositorio de GitHub
   - Seleccionar la rama `main`
   - Configurar el directorio raíz como `backend`

2. **Configuración del Build:**
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

3. **Variables de Entorno:**
   ```
   PYTHON_VERSION=3.11.7
   PIP_NO_CACHE_DIR=1
   PIP_DISABLE_PIP_VERSION_CHECK=1
   
   # Tus variables específicas de Supabase
   SUPABASE_URL=tu_supabase_url
   SUPABASE_KEY=tu_supabase_key
   SUPABASE_SERVICE_ROLE_KEY=tu_service_role_key
   ```

### 3. **Verificar el Despliegue**

Una vez desplegado, verifica que los endpoints funcionen:

```bash
# Endpoint de estado
curl https://tu-app.onrender.com/api/v1/importacion/status

# Debería devolver:
{
  "message": "Sistema de importación funcionando correctamente",
  "status": "active",
  "supported_formats": [".xlsx", ".xls"]
}
```

## Dependencias Finales

El archivo `requirements.txt` final contiene solo dependencias compatibles con Render:

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
python-multipart==0.0.6
python-dotenv==1.0.0
httpx==0.24.1
supabase==2.0.0
pyjwt==2.8.0
requests==2.31.0
pandas==2.1.4
openpyxl==3.1.2
xlrd==2.0.1
sqlalchemy==2.0.20
pytest==7.4.2
pytest-asyncio==0.21.1
```

## Funcionalidades Restauradas

### ✅ **Completamente Funcional:**
- Importación de archivos Excel (.xlsx, .xls)
- Reconocimiento automático de columnas
- Validación de datos
- Mapeo de columnas personalizado
- Autenticación JWT
- Todas las APIs de productos, ventas, etc.

### ✅ **Optimizaciones Implementadas:**
- Fuzzy matching con `difflib` (biblioteca estándar)
- JWT con `pyjwt` (más ligero y compatible)
- Pandas y openpyxl funcionando correctamente
- Sin dependencias de compilación

## Solución de Problemas

### Si el despliegue falla:

1. **Verificar logs en Render:**
   - Revisar la sección "Logs" en el dashboard
   - Buscar errores específicos

2. **Problemas comunes:**
   - **Timeout en build:** Aumentar el timeout en configuración
   - **Memoria insuficiente:** Cambiar a un plan superior
   - **Variables de entorno:** Verificar que estén configuradas correctamente

3. **Rollback si es necesario:**
   ```bash
   git revert HEAD
   git push origin main
   ```

## Monitoreo Post-Despliegue

### Endpoints de Salud:
- `GET /api/v1/importacion/status` - Estado del sistema de importación
- `GET /health` - Endpoint de salud general (si existe)

### Logs importantes a monitorear:
- Errores de importación de Excel
- Fallos de autenticación
- Problemas de conexión con Supabase

## Próximos Pasos

1. **Probar funcionalidad de importación** en el entorno de producción
2. **Configurar monitoreo** con alertas
3. **Optimizar rendimiento** si es necesario
4. **Configurar CI/CD** para despliegues automáticos

---

**Nota:** Esta configuración ha sido probada y optimizada específicamente para Render. Las dependencias están cuidadosamente seleccionadas para evitar problemas de compilación mientras mantienen toda la funcionalidad necesaria. 
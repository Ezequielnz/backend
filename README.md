# MicroPymes Backend

Backend API para el sistema MicroPymes, una aplicación de gestión para pequeñas empresas.

## Tecnologías

- FastAPI
- Supabase (Base de datos y autenticación)
- Pydantic (Validación de datos)

## Configuración

1. Clonar el repositorio
2. Crear un archivo `.env` en la raíz del proyecto con las siguientes variables:

```
# Supabase credentials
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# API settings
PROJECT_NAME="MicroPymes API"
API_V1_STR="/api/v1"

# CORS (comma-separated, e.g., "http://localhost:3000,http://localhost:8080")
BACKEND_CORS_ORIGINS=http://localhost:3000,http://localhost
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Iniciar el servidor de desarrollo:
```bash
uvicorn main:app --reload
```

## Estructura de Tablas en Supabase

El sistema utiliza las siguientes tablas en Supabase:

- **clientes**: Información de clientes
- **usuarios**: Usuarios del sistema
- **tareas**: Gestión de tareas
- **productos**: Catálogo de productos
- **categorias**: Categorías de productos
- **ventas**: Registro de ventas
- **venta_detalle**: Detalles de cada venta
- **configuracion_area**: Configuración de la empresa

## Desarrollo

Para agregar nuevos endpoints, sigue estos pasos:

1. Crea los modelos correspondientes en `app/models/supabase_models.py`
2. Crea los schemas Pydantic en `app/schemas/`
3. Implementa la lógica del endpoint en `app/api/api_v1/endpoints/`

## Documentación API

Una vez que el servidor esté en ejecución, puedes acceder a:

- Documentación interactiva: http://localhost:8000/docs
- Especificación OpenAPI: http://localhost:8000/api/v1/openapi.json 
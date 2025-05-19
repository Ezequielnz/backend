# MicroPymes Backend

Backend para la aplicación MicroPymes desarrollado con FastAPI.

## Instalación

1. Clonar el repositorio
2. Crear entorno virtual: `python -m venv venv`
3. Activar entorno virtual:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`
4. Instalar dependencias: `pip install -r requirements.txt`
5. Crear archivo `.env` con las variables de entorno necesarias

## Ejecución

```bash
uvicorn main:app --reload
```

La API estará disponible en http://localhost:8000

La documentación Swagger estará disponible en http://localhost:8000/docs

## Estructura del proyecto

- `app/api`: Endpoints de la API
- `app/core`: Configuración central
- `app/db`: Configuración de la base de datos
- `app/models`: Modelos ORM de SQLAlchemy
- `app/schemas`: Esquemas de Pydantic para validación 
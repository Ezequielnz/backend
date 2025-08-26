# Guía de Configuración Celery - Sistema de Notificaciones ML

## ✅ Estado Actual

### Dependencias Instaladas
- ✅ **scikit-learn==1.7.1** - Machine Learning
- ✅ **prophet==1.1.7** - Predicciones de series temporales
- ✅ **pandas==2.2.3** - Manipulación de datos
- ✅ **numpy==2.2.6** - Computación numérica
- ✅ **joblib==1.5.1** - Serialización de modelos ML
- ✅ **celery[redis]==5.5.3** - Procesamiento asíncrono
- ✅ **redis==5.2.1** - Broker y backend
- ✅ **APScheduler==3.11.0** - Tareas programadas
- ✅ **flower==2.0.1** - Monitoreo de Celery

### Archivos Creados
- ✅ `docker-compose.yml` - Orquestación de servicios
- ✅ `Dockerfile` - Imagen del backend
- ✅ `app/celery_app.py` - Configuración de Celery con tareas programadas
- ✅ `app/workers/maintenance_worker.py` - Worker de mantenimiento
- ✅ `test_celery_local.py` - Script de pruebas locales
- ✅ `start_celery.bat` - Script de inicio para Windows

### Configuración Celery Beat
```python
# Tareas programadas configuradas:
"daily-notifications": {
    "task": "app.workers.notification_worker.send_daily_notifications",
    "schedule": crontab(hour=8, minute=0),  # 8 AM diario
},
"weekly-ml-retrain": {
    "task": "app.workers.ml_worker.retrain_all_models", 
    "schedule": crontab(hour=2, minute=0, day_of_week=1),  # Lunes 2 AM
},
"check-notification-rules": {
    "task": "app.workers.notification_worker.check_notification_rules",
    "schedule": 300.0,  # Cada 5 minutos
},
```

## 🔧 Opciones de Ejecución

### Opción 1: Docker Compose (Recomendado)
```bash
# Instalar Docker Desktop primero
# Luego ejecutar:
docker compose up -d redis
docker compose up -d celery-worker
docker compose up -d celery-beat  
docker compose up -d flower
```

### Opción 2: Local con Redis en Docker
```bash
# 1. Iniciar Redis
docker run -d --name micropymes_redis -p 6379:6379 redis:7-alpine

# 2. Ejecutar script de inicio
start_celery.bat
```

### Opción 3: Redis Local (Windows)
1. Descargar Redis para Windows: https://github.com/microsoftarchive/redis/releases
2. Instalar y ejecutar Redis
3. Ejecutar: `python test_celery_local.py`

## 📊 Monitoreo

### Flower Dashboard
- **URL**: http://localhost:5555
- **Usuario**: admin
- **Contraseña**: micropymes2025

### Verificación de Salud
```bash
# Verificar workers activos
celery -A app.celery_app inspect active

# Verificar tareas programadas
celery -A app.celery_app inspect scheduled

# Estado de workers
celery -A app.celery_app status
```

## 🚀 Próximos Pasos

### Semana 2 - Desarrollo ML
1. **BusinessMLEngine** - Motor de predicciones con Prophet
2. **Celery Workers** - Procesamiento asíncrono de ML
3. **NotificationRuleEngine** - Motor híbrido de reglas

### Validación Requerida
- [ ] Instalar Docker Desktop o Redis local
- [ ] Ejecutar workers y verificar en Flower
- [ ] Confirmar tareas programadas funcionando
- [ ] Validar conexión con Supabase desde workers

## 🔍 Troubleshooting

### Error: Redis no disponible
```bash
# Solución 1: Docker
docker run -d -p 6379:6379 redis:7-alpine

# Solución 2: Verificar Redis local
redis-cli ping
```

### Error: Workers no aparecen en Flower
1. Verificar variables de entorno en `.env`
2. Confirmar que Redis está corriendo
3. Revisar logs de workers para errores

### Error: Tareas no se ejecutan
1. Verificar Celery Beat está corriendo
2. Confirmar timezone en configuración
3. Revisar permisos de Supabase en workers

@echo off
echo === Iniciando Celery Workers ===

REM Verificar si Redis está corriendo
echo Verificando Redis...
python -c "import redis; r=redis.Redis(); r.ping(); print('Redis OK')" 2>nul
if errorlevel 1 (
    echo Redis no está disponible. Iniciando Redis con Docker...
    docker run -d --name micropymes_redis -p 6379:6379 redis:7-alpine
    timeout /t 3 >nul
)

REM Iniciar Celery Worker en una nueva ventana
echo Iniciando Celery Worker...
start "Celery Worker" cmd /k "python -m celery -A app.celery_app worker --loglevel=info --concurrency=2"

REM Esperar un poco
timeout /t 2 >nul

REM Iniciar Celery Beat en una nueva ventana
echo Iniciando Celery Beat...
start "Celery Beat" cmd /k "python -m celery -A app.celery_app beat --loglevel=info"

REM Esperar un poco
timeout /t 2 >nul

REM Iniciar Flower en una nueva ventana
echo Iniciando Flower...
start "Flower Monitor" cmd /k "python -m celery -A app.celery_app flower --port=5555"

echo.
echo === Celery iniciado ===
echo Worker: Procesamiento de tareas
echo Beat: Tareas programadas
echo Flower: http://localhost:5555
echo.
echo Presiona cualquier tecla para continuar...
pause >nul

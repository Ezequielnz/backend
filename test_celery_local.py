"""
Script para probar Celery workers localmente sin Docker
"""
import os
import sys
import subprocess
import time
from pathlib import Path

def setup_environment():
    """Configurar variables de entorno para pruebas locales"""
    os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
    os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    
    # Variables de Supabase (usar las del .env si existen)
    env_file = Path(".env")
    if env_file.exists():
        print("OK Archivo .env encontrado")
        with open(env_file) as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ.setdefault(key, value)
    else:
        print("⚠ Archivo .env no encontrado, usando valores por defecto")

def check_redis():
    """Verificar si Redis está disponible"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("OK Redis está disponible")
        return True
    except Exception as e:
        print(f"ERROR Redis no disponible: {e}")
        print("  Instala Redis localmente o usa Docker:")
        print("  - Windows: https://github.com/microsoftarchive/redis/releases")
        print("  - O ejecuta: docker run -d -p 6379:6379 redis:7-alpine")
        return False

def test_celery_worker():
    """Probar Celery worker"""
    print("\n=== Probando Celery Worker ===")
    try:
        # Ejecutar worker en background
        worker_process = subprocess.Popen([
            sys.executable, "-m", "celery", 
            "-A", "app.celery_app", 
            "worker", 
            "--loglevel=info",
            "--concurrency=2"
        ])
        
        print("OK Celery worker iniciado (PID: {})".format(worker_process.pid))
        print("  Presiona Ctrl+C para detener")
        
        # Esperar un poco y verificar que sigue corriendo
        time.sleep(3)
        if worker_process.poll() is None:
            print("OK Worker está corriendo correctamente")
        else:
            print("ERROR Worker se detuvo inesperadamente")
            
        return worker_process
        
    except Exception as e:
        print(f"ERROR iniciando worker: {e}")
        return None

def test_celery_beat():
    """Probar Celery Beat"""
    print("\n=== Probando Celery Beat ===")
    try:
        beat_process = subprocess.Popen([
            sys.executable, "-m", "celery",
            "-A", "app.celery_app",
            "beat",
            "--loglevel=info"
        ])
        
        print("OK Celery beat iniciado (PID: {})".format(beat_process.pid))
        
        time.sleep(3)
        if beat_process.poll() is None:
            print("OK Beat está corriendo correctamente")
        else:
            print("ERROR Beat se detuvo inesperadamente")
            
        return beat_process
        
    except Exception as e:
        print(f"ERROR iniciando beat: {e}")
        return None

def test_flower():
    """Probar Flower para monitoreo"""
    print("\n=== Probando Flower ===")
    try:
        flower_process = subprocess.Popen([
            sys.executable, "-m", "celery",
            "-A", "app.celery_app",
            "flower",
            "--port=5555"
        ])
        
        print("OK Flower iniciado (PID: {})".format(flower_process.pid))
        print("  Accede a http://localhost:5555 para ver el dashboard")
        
        time.sleep(3)
        if flower_process.poll() is None:
            print("OK Flower está corriendo correctamente")
        else:
            print("ERROR Flower se detuvo inesperadamente")
            
        return flower_process
        
    except Exception as e:
        print(f"ERROR iniciando flower: {e}")
        return None

def main():
    """Función principal"""
    print("=== Test Celery Local ===")
    
    # Setup
    setup_environment()
    
    # Verificar Redis
    if not check_redis():
        return
    
    processes = []
    
    try:
        # Iniciar worker
        worker = test_celery_worker()
        if worker:
            processes.append(worker)
        
        # Iniciar beat
        beat = test_celery_beat()
        if beat:
            processes.append(beat)
            
        # Iniciar flower
        flower = test_flower()
        if flower:
            processes.append(flower)
        
        if processes:
            print(f"\nOK {len(processes)} procesos iniciados correctamente")
            print("Presiona Ctrl+C para detener todos los procesos")
            
            # Esperar hasta que el usuario presione Ctrl+C
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n\nDeteniendo procesos...")
                
    except KeyboardInterrupt:
        print("\n\nDeteniendo procesos...")
    
    finally:
        # Limpiar procesos
        for process in processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"OK Proceso {process.pid} terminado")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"OK Proceso {process.pid} forzado a terminar")
            except Exception as e:
                print(f"WARNING Error terminando proceso {process.pid}: {e}")

if __name__ == "__main__":
    main()

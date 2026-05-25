"""Check integral Fase 1 — Pasos 1-6"""
import sys, os

PASS = "  [OK] "
FAIL = "  [FAIL]"
results = []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as e:
        results.append((name, False, str(e)))


# ── PASO 1: requirements.txt ───────────────────────────────────
def paso1():
    lines = [l for l in open("requirements.txt").readlines() if not l.strip().startswith("#")]
    txt = "".join(lines).lower()
    bad = ["supabase", "celery", "redis", "torch", "prophet", "statsmodels", "langchain"]
    for pkg in bad:
        assert pkg not in txt, f"{pkg!r} todavia en requirements.txt (lineas de codigo, no comentarios)"
    must = ["fastapi", "sqlalchemy", "alembic", "pyjwt", "openai"]
    for pkg in must:
        assert pkg in txt, f"{pkg!r} falta en requirements.txt"


check("Paso 1: requirements.txt", paso1)


# ── PASO 2: orm_models.py ──────────────────────────────────────
def paso2():
    from app.models.orm_models import (
        Negocio, Usuario, Producto, Servicio, Cliente, Proveedor,
        Categoria, MetodoPago, Venta, VentaDetalle,
        Compra, CompraDetalle, StockTransfer,
        Tarea, MovimientoFinanciero, CuentaPendiente, CategoriaFinanciera,
    )
    # Verificar que todas son clases SQLAlchemy válidas
    from sqlalchemy import inspect as sa_inspect
    for cls in [Negocio, Usuario, Producto, Venta, Compra, StockTransfer]:
        mapper = sa_inspect(cls)
        assert mapper is not None


check("Paso 2: orm_models.py (16 modelos SQLAlchemy)", paso2)


# ── PASO 3: Alembic ────────────────────────────────────────────
def paso3():
    assert os.path.isdir("alembic"), "directorio alembic/ no existe"
    assert os.path.isfile("alembic.ini"), "alembic.ini no existe"
    assert os.path.isfile("alembic/env.py"), "alembic/env.py no existe"
    versions = [f for f in os.listdir("alembic/versions") if f.endswith(".py")]
    assert len(versions) > 0, "No hay migraciones en alembic/versions/"
    assert os.path.isfile("micropymes.db"), "micropymes.db no fue creado"


check("Paso 3: Alembic + micropymes.db existe", paso3)


# ── PASO 4: local_db.py ────────────────────────────────────────
def paso4():
    from app.db.local_db import engine, SessionLocal, get_db, check_db_connection
    from app.db.session import get_db as get_db2, SessionLocal as SL2
    ok = check_db_connection()
    assert ok, "check_db_connection() retorna False — SQLite no responde"


check("Paso 4: local_db.py + session.py + health check", paso4)


# ── PASO 5: Workers/ML eliminados ─────────────────────────────
def paso5():
    deleted = [
        "app/workers",
        "app/tasks",
        "app/celery_app.py",
        "app/services/ml",
        "app/config/ml_settings.py",
        "app/db/scoped_client.py",
        "app/services/notification_service.py",
        "app/services/rubro_strategies.py",
        "app/api/api_v1/endpoints/notifications.py",
        "app/api/api_v1/endpoints/monitoring.py",
        "app/api/api_v1/endpoints/action.py",
        "app/api/api_v1/endpoints/suscripciones.py",
    ]
    for path in deleted:
        assert not os.path.exists(path), f"{path!r} deberia estar eliminado"
    # Shims deben existir
    shims = ["app/db/supabase_client.py", "app/core/supabase_admin.py"]
    for path in shims:
        assert os.path.isfile(path), f"{path!r} deberia existir como shim"
    # cache_manager memory-only (sin redis/supabase)
    cm_src = open("app/core/cache_manager.py").read()
    assert "import redis" not in cm_src, "cache_manager.py todavia importa redis"
    assert "create_client" not in cm_src, "cache_manager.py todavia importa supabase"


check("Paso 5: Workers/ML eliminados + shims + cache memory-only", paso5)


# ── PASO 6: config.py simplificado ────────────────────────────
def paso6():
    from app.core.config import settings
    # Campos que deben existir
    assert hasattr(settings, "DATABASE_URL"), "DATABASE_URL falta en settings"
    assert hasattr(settings, "JWT_SECRET_KEY"), "JWT_SECRET_KEY falta en settings"
    assert hasattr(settings, "BACKEND_CORS_ORIGINS"), "BACKEND_CORS_ORIGINS falta en settings"
    assert hasattr(settings, "OPENAI_API_KEY"), "OPENAI_API_KEY falta en settings"
    # Campos que NO deben existir
    removed = ["SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_ANON_KEY",
               "CELERY_BROKER_URL", "REDIS_URL", "ML_MODEL_PATH",
               "LLM_DEFAULT_MODEL", "DB_USER", "DB_HOST"]
    for attr in removed:
        assert not hasattr(settings, attr), f"settings.{attr} sigue existiendo — no fue eliminado"
    # DATABASE_URL apunta a SQLite
    assert "sqlite" in settings.DATABASE_URL, "DATABASE_URL no es SQLite"


check("Paso 6: config.py simplificado (sin cloud, solo SQLite+JWT)", paso6)


# ── Import completo ────────────────────────────────────────────
def full_import():
    import main  # noqa: F401 — solo testear que no lanza excepcion


check("Full import: main.py sin errores de importacion", full_import)


# ── RESULTADO ──────────────────────────────────────────────────
print()
print("=" * 62)
print("  CHECK INTEGRAL FASE 1 — Pasos 1 al 6")
print("=" * 62)
for name, ok, err in results:
    icon = PASS if ok else FAIL
    print(f"{icon}  {name}")
    if not ok:
        print(f"          >>> {err}")
print()
fails = [r for r in results if not r[1]]
if fails:
    print(f"RESULTADO: {len(fails)} fallo(s). Revisar errores arriba.")
    sys.exit(1)
else:
    print("RESULTADO: TODOS LOS CHECKS OK. Fase 1 completada correctamente.")

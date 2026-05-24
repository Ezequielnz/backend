"""
session.py — Re-exporta engine y sesión desde local_db.py
===========================================================
Mantenido por compatibilidad con código existente que importa desde aquí.
La implementación real vive en app.db.local_db.
"""

from app.db.local_db import engine, SessionLocal, get_db  # noqa: F401

# Alias legacy que algunos módulos internos esperan
SQLALCHEMY_DATABASE_URL = str(engine.url)
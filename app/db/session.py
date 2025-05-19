from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Usar la URL de la base de datos de la configuración
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Configuración del motor de base de datos
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Sólo para SQLite, necesitamos este argumento
    connect_args = {"check_same_thread": False}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 
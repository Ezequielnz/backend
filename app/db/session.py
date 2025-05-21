from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import ssl

from app.core.config import settings

# Get the database URL from settings
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Configure database engine
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Only for SQLite, we need this argument
    connect_args = {"check_same_thread": False}
elif SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    # For PostgreSQL with Supabase Session Pooler, configure SSL
    connect_args = {
        "sslmode": "require",
        "ssl_context": ssl.create_default_context()
    }

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args=connect_args,
    pool_size=5,  # Connection pool size
    max_overflow=10,  # Maximum overflow connections
    pool_timeout=30,  # Timeout for getting a connection from the pool
    pool_recycle=1800  # Recycle connections after 30 minutes
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 
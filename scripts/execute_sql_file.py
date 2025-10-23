import os
import sys
from pathlib import Path
from typing import Optional

import psycopg2


def _resolve_dsn() -> Optional[str]:
    """
    Return a DSN string if one is configured via environment variables.
    Preference order:
    - DB_DSN
    - DATABASE_URL
    - STAGING_DATABASE_URL (useful for staging runs)
    """
    for key in ("DB_DSN", "DATABASE_URL", "STAGING_DATABASE_URL"):
        value = os.getenv(key)
        if value:
            return value
    return None


def get_connection(*, autocommit: bool = True) -> psycopg2.extensions.connection:
    """
    Build a psycopg2 connection using either a DSN or discrete connection params.
    Defaults mirror the legacy hard-coded credentials so existing workflows keep working,
    but callers can now provide staging credentials via environment variables.
    """
    dsn = _resolve_dsn()
    if dsn:
        conn = psycopg2.connect(dsn)
    else:
        host = os.getenv("DB_HOST", "aws-0-us-west-1.pooler.supabase.com")
        port = int(os.getenv("DB_PORT", "5432"))
        dbname = os.getenv("DB_NAME", "postgres")
        user = os.getenv("DB_USER", "postgres.aupmnxxauxasetwnqkma")
        password = os.getenv("DB_PASSWORD", "kJAupLuJOgZdrIUy")
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )

    conn.autocommit = autocommit
    return conn


def main(path: str) -> None:
    sql_path = Path(path)
    sql = sql_path.read_text(encoding="utf-8")

    conn = get_connection(autocommit=True)
    cur = conn.cursor()
    try:
        cur.execute(sql)
        print(f"Executed {sql_path.name}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/execute_sql_file.py <path>")
    main(sys.argv[1])

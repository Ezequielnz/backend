import psycopg2
from pathlib import Path
import sys


def main(path: str) -> None:
    sql_path = Path(path)
    sql = sql_path.read_text(encoding="utf-8")

    conn = psycopg2.connect(
        host="aws-0-us-west-1.pooler.supabase.com",
        port=5432,
        dbname="postgres",
        user="postgres.aupmnxxauxasetwnqkma",
        password="kJAupLuJOgZdrIUy",
    )
    conn.autocommit = True
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

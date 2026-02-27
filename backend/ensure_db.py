"""Create the application database if it does not exist. Uses app.config settings."""

from __future__ import annotations

import sys

try:
    from app.config import settings
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError as e:
    print(f"ensure_db: skip ({e})", file=sys.stderr)
    sys.exit(0)

def main() -> int:
    if settings.database_url:
        # Parse URL to get db name and build URL to 'postgres'
        from sqlalchemy.engine import make_url
        url = make_url(settings.database_url)
        db_name = url.database or "supply_chain"
        url = url.set(database="postgres")
        conn_params = {
            "host": url.hostname or "localhost",
            "port": url.port or 5432,
            "user": url.username or "postgres",
            "password": url.password or "postgres",
        }
    else:
        db_name = settings.db_name
        conn_params = {
            "host": settings.db_host,
            "port": settings.db_port,
            "user": settings.db_username,
            "password": settings.db_password,
        }

    try:
        conn = psycopg2.connect(database="postgres", **conn_params)
    except Exception as e:
        print(f"ensure_db: cannot connect to PostgreSQL: {e}", file=sys.stderr)
        return 0  # non-fatal so app can still start

    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,),
        )
        if cur.fetchone():
            return 0
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        print(f"ensure_db: created database '{db_name}'")
    except Exception as e:
        print(f"ensure_db: failed to create database: {e}", file=sys.stderr)
        return 1
    finally:
        cur.close()
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())

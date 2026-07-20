"""Block until MySQL accepts connections (used by the container entrypoint)."""

from __future__ import annotations

import sys
import time

import pymysql

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    deadline = time.time() + 120
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            conn = pymysql.connect(
                host=settings.mysql_host,
                port=settings.mysql_port,
                user=settings.mysql_user,
                password=settings.mysql_password,
                database=settings.mysql_database,
                connect_timeout=3,
            )
            conn.close()
            print("MySQL is ready.")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Waiting for MySQL... ({exc})")
            time.sleep(2)
    print(f"Timed out waiting for MySQL: {last_error}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

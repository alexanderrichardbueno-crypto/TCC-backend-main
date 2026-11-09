"""Gera uma copia do banco atual em um arquivo SQLite, para usar sem o Firebase.

Uso, a partir da pasta do backend:
    python -m app.copy_postgres_to_sqlite banca.db

O banco de origem (DATABASE_URL do .env) e apenas lido.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select

from app import models, station_models  # noqa: F401
from app.config import get_settings
from app.database import Base


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: python -m app.copy_postgres_to_sqlite banca.db")
        return 2
    path = Path(sys.argv[1]).resolve()
    if path.exists():
        print(f"O arquivo {path} ja existe. Apague-o ou escolha outro nome.")
        return 1

    target_url = f"sqlite:///{path.as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env={**os.environ, "DATABASE_URL": target_url},
    )

    source = create_engine(get_settings().database_url)
    target = create_engine(target_url)
    tables = Base.metadata.sorted_tables
    differences = 0
    with source.connect() as src, target.begin() as dst:
        for table in reversed(tables):
            dst.execute(table.delete())
        for table in tables:
            rows = [dict(row._mapping) for row in src.execute(select(table))]
            if rows:
                dst.execute(table.insert(), rows)
            copied = dst.execute(select(func.count()).select_from(table)).scalar_one()
            differences += copied != len(rows)
            print(f"{table.name}: {copied} de {len(rows)}")

    print("Copia concluida." if not differences else f"{differences} tabela(s) com diferenca.")
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())

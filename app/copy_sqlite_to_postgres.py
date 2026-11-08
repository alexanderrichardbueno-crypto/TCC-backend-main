"""Copia todos os dados do banco SQLite para um PostgreSQL já migrado.

O SQLite é aberto somente para leitura. A cópia é feita em uma única transação: se algo
falhar, o PostgreSQL volta ao estado anterior. O destino vem da variável TARGET_DATABASE_URL,
para que a senha não apareça no histórico do terminal.

    python -m alembic upgrade head       (com DATABASE_URL apontando para o PostgreSQL)
    python -m app.copy_sqlite_to_postgres prevclima.db
"""

import argparse
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, Engine, Table, create_engine, func, select, text

from app import models, station_models  # noqa: F401
from app.database import Base

BATCH_SIZE = 500


def open_source(path: Path) -> Engine:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))


def schema_version(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def with_utc(table: Table, row: dict) -> dict:
    """O SQLite perde o fuso das datas, que o sistema sempre grava em UTC."""
    converted = dict(row)
    for column in table.columns:
        value = converted[column.name]
        if isinstance(column.type, DateTime) and isinstance(value, datetime) and not value.tzinfo:
            converted[column.name] = value.replace(tzinfo=UTC)
    return converted


def copy_table(source, target, table: Table) -> int:
    rows = [with_utc(table, dict(row)) for row in source.execute(select(table)).mappings()]
    for start in range(0, len(rows), BATCH_SIZE):
        target.execute(table.insert(), rows[start : start + BATCH_SIZE])
    column = table.autoincrement_column
    if rows and column is not None:
        target.execute(
            text("SELECT setval(pg_get_serial_sequence(:table, :column), :value)"),
            {
                "table": table.name,
                "column": column.name,
                "value": max(row[column.name] for row in rows),
            },
        )
    copied = target.execute(select(func.count()).select_from(table)).scalar_one()
    if copied != len(rows):
        raise RuntimeError(f"{table.name}: {len(rows)} linhas na origem, {copied} no destino")
    return copied


def copy_database(source_engine: Engine, target_engine: Engine) -> dict[str, int]:
    if target_engine.dialect.name != "postgresql":
        raise SystemExit("O destino precisa ser um banco PostgreSQL.")
    source_version = schema_version(source_engine)
    target_version = schema_version(target_engine)
    if source_version != target_version:
        raise SystemExit(
            f"Versões diferentes: origem {source_version}, destino {target_version}. "
            "Rode as migrações nos dois bancos."
        )
    tables = Base.metadata.sorted_tables
    with source_engine.connect() as source, target_engine.begin() as target:
        users = Base.metadata.tables["users"]
        if target.execute(select(func.count()).select_from(users)).scalar_one():
            raise SystemExit("O destino já tem usuários. Nada foi copiado.")
        # As migrações criam linhas iniciais, como os perfis, que também vêm da origem.
        for table in reversed(tables):
            target.execute(table.delete())
        return {table.name: copy_table(source, target, table) for table in tables}


def main() -> None:
    parser = argparse.ArgumentParser(description="Copia o SQLite para o PostgreSQL")
    parser.add_argument("source", type=Path, help="Arquivo SQLite de origem")
    arguments = parser.parse_args()
    if not arguments.source.is_file():
        raise SystemExit(f"Arquivo não encontrado: {arguments.source}")
    target_url = os.environ.get("TARGET_DATABASE_URL")
    if not target_url:
        raise SystemExit("Defina a variável TARGET_DATABASE_URL.")
    counts = copy_database(open_source(arguments.source), create_engine(target_url))
    for name, count in counts.items():
        print(f"{name}: {count}")
    print(f"Total: {sum(counts.values())} linhas copiadas.")


if __name__ == "__main__":
    main()

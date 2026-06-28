from collections.abc import Generator
from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import get_settings


engine = create_engine(
    get_settings().database_url,
    connect_args={"check_same_thread": False}
    if get_settings().database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    import backend.core.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()


def _migrate_sqlite_columns() -> None:
    if not engine.dialect.name == "sqlite":
        return
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = column.type.compile(dialect=engine.dialect)
            nullable = "" if column.nullable else " NOT NULL"
            default_sql = ""
            if column.default is not None and getattr(column.default, "arg", None) is not None:
                default_value = column.default.arg
                if callable(default_value):
                    # Python callables such as datetime.utcnow are application-side defaults,
                    # not valid SQLite ALTER TABLE DEFAULT expressions.
                    default_value = None
                if isinstance(default_value, str):
                    escaped = default_value.replace("'", "''")
                    default_sql = f" DEFAULT '{escaped}'"
                elif default_value is not None:
                    default_sql = f" DEFAULT {default_value}"
            with engine.begin() as conn:
                try:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}{nullable}{default_sql}'))
                except OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

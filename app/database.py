from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _engine_kwargs(database_url: str) -> dict:
    if not database_url.startswith("sqlite"):
        return {}

    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in database_url or "mode=memory" in database_url:
        # A plain in-memory SQLite database lives and dies with its connection.
        # StaticPool keeps a single connection alive so every request — and every
        # thread FastAPI hands work to — sees the same data for the process's lifetime.
        kwargs["poolclass"] = StaticPool
    return kwargs


settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    **_engine_kwargs(settings.database_url),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    """Create tables. Called on startup; safe to call repeatedly."""
    from app import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _migrate_legacy_addresses(engine)


_LEGACY_ADDRESS_COLUMNS = {"address", "city", "state", "postal_code", "country"}
_MISSING_LEGACY_STREET = "(street not provided in legacy data)"
_ADDRESS_MIGRATION = "normalize_contact_addresses_v1"


def _migrate_legacy_addresses(target_engine: Engine) -> None:
    """Copy pre-normalization contact addresses into owned address rows.

    The migration is intentionally additive: legacy columns remain in place, and
    a contact is backfilled only while it has no normalized addresses. A unique,
    transactional migration claim ensures concurrent application processes cannot
    both perform the backfill.
    """
    inspector = inspect(target_engine)
    if not {"contacts", "addresses"}.issubset(inspector.get_table_names()):
        return

    contact_columns = {column["name"] for column in inspector.get_columns("contacts")}
    if not _LEGACY_ADDRESS_COLUMNS.issubset(contact_columns):
        return

    backfill = text(
        """
        INSERT INTO addresses
            (contact_id, type, address, city, state, postal_code, country)
        SELECT
            contacts.id,
            'OTHER',
            CASE
                WHEN TRIM(COALESCE(contacts.address, '')) = '' THEN :missing_street
                ELSE contacts.address
            END,
            contacts.city,
            contacts.state,
            contacts.postal_code,
            contacts.country
        FROM contacts
        WHERE (
            TRIM(COALESCE(contacts.address, '')) <> ''
            OR TRIM(COALESCE(contacts.city, '')) <> ''
            OR TRIM(COALESCE(contacts.state, '')) <> ''
            OR TRIM(COALESCE(contacts.postal_code, '')) <> ''
            OR TRIM(COALESCE(contacts.country, '')) <> ''
        )
        AND NOT EXISTS (
            SELECT 1 FROM addresses WHERE addresses.contact_id = contacts.id
        )
        """
    )
    with target_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS contacts_schema_migrations (
                    name VARCHAR(255) PRIMARY KEY
                )
                """
            )
        )

    with target_engine.begin() as connection:
        claim = connection.execute(
            text(
                """
                INSERT INTO contacts_schema_migrations (name)
                VALUES (:name)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": _ADDRESS_MIGRATION},
        )
        if claim.rowcount != 1:
            return
        connection.execute(backfill, {"missing_street": _MISSING_LEGACY_STREET})


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

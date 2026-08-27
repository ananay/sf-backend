from sqlalchemy import create_engine, inspect, text

from app.database import (
    _ensure_linkedin_column,
    _ensure_photo_column,
    _migrate_legacy_addresses,
)
from app.models import Address


def test_photo_column_is_added_to_an_existing_contacts_table():
    legacy_engine = create_engine("sqlite+pysqlite:///:memory:")
    with legacy_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE contacts (id INTEGER PRIMARY KEY, email VARCHAR(320))")
        )

    _ensure_photo_column(legacy_engine)
    _ensure_photo_column(legacy_engine)  # The migration is safe on every startup.

    columns = {column["name"] for column in inspect(legacy_engine).get_columns("contacts")}
    assert columns == {"id", "email", "photo"}


def test_legacy_addresses_are_backfilled_once() -> None:
    """Startup preserves complete and partial legacy addresses without duplicates."""
    legacy_engine = create_engine("sqlite+pysqlite:///:memory:")
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY,
                    address VARCHAR(300),
                    city VARCHAR(120),
                    state VARCHAR(120),
                    postal_code VARCHAR(20),
                    country VARCHAR(120)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO contacts
                    (id, address, city, state, postal_code, country)
                VALUES
                    (1, '1 Market St', 'San Francisco', 'CA', '94105', 'USA'),
                    (2, NULL, 'London', NULL, NULL, 'UK'),
                    (3, NULL, NULL, NULL, NULL, NULL)
                """
            )
        )
    Address.__table__.create(bind=legacy_engine)

    _migrate_legacy_addresses(legacy_engine)
    _migrate_legacy_addresses(legacy_engine)

    with legacy_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT contact_id, type, address, city, country
                FROM addresses
                ORDER BY contact_id
                """
            )
        ).mappings().all()
        migration_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM contacts_schema_migrations
                WHERE name = 'normalize_contact_addresses_v1'
                """
            )
        ).scalar_one()

    assert [dict(row) for row in rows] == [
        {
            "contact_id": 1,
            "type": "OTHER",
            "address": "1 Market St",
            "city": "San Francisco",
            "country": "USA",
        },
        {
            "contact_id": 2,
            "type": "OTHER",
            "address": "(street not provided in legacy data)",
            "city": "London",
            "country": "UK",
        },
    ]
    assert migration_count == 1


def test_ensure_linkedin_column_migrates_existing_contacts_table():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE contacts ("
                "id INTEGER PRIMARY KEY, first_name VARCHAR(100) NOT NULL"
                ")"
            )
        )

    _ensure_linkedin_column(engine)
    _ensure_linkedin_column(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("contacts")}
    assert "linkedin_url" in columns

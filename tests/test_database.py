from sqlalchemy import create_engine, inspect, text

from app.database import _ensure_photo_column


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

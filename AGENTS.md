# Contacts backend

This repository contains the FastAPI service for the Contacts application. It uses
Pydantic for request and response contracts, SQLAlchemy for persistence, and pytest for
API coverage. The default in-memory SQLite database makes the service self-contained;
`CONTACTS_DATABASE_URL` can point to file-backed SQLite or Postgres when persistence is
needed. Install the `postgres` extra before using a `postgresql+psycopg://` URL.

## Working locally

- Use Python 3.11 or newer.
- Create an environment and install the project with `python -m pip install -e ".[dev]"`.
- For Postgres support, install with `python -m pip install -e ".[dev,postgres]"`.
- Start the API with `python -m app.main` or `uvicorn app.main:app --reload`.
- Run the complete suite with `python -m pytest` before handing off a change.
- Use the generated OpenAPI document at `/openapi.json` as the source of truth for the
  frontend contract.

## Architecture

- `app/main.py` configures the FastAPI application, lifespan, metadata, and health
  routes.
- `app/routers/contacts.py` owns the HTTP interface for contact operations.
- `app/schemas.py` defines validated request and response models.
- `app/models.py` defines SQLAlchemy persistence models.
- `app/crud.py` contains database queries and mutations.
- `app/database.py` owns engine, session, and schema initialization behavior.
- `app/config.py` is the only place that reads `CONTACTS_*` settings.
- Tests live in `tests/` and exercise the API through FastAPI's `TestClient`.

## Conventions

- Keep route handlers thin. Put validation in Pydantic schemas and persistence behavior
  in the CRUD or database layer.
- Use a request-scoped SQLAlchemy session from `get_db`; do not create ad hoc engines or
  global sessions.
- Preserve the documented status codes and FastAPI validation error shape.
- Keep email uniqueness case-insensitive and return `409` for conflicts.
- Add regression tests for success paths, validation failures, missing records, and
  persistence semantics affected by a change.
- Keep startup behavior safe for both the default in-memory database and configured
  persistent databases.

## Delivery

`.github/workflows/ci.yml` installs the package with its development dependencies and
runs the full pytest suite on pull requests and pushes to `trunk`.

import os
from collections.abc import Iterator

# Tests get their own empty in-memory database — no seed rows.
os.environ["CONTACTS_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["CONTACTS_SEED_DATA"] = "false"

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def payload() -> dict:
    return {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
        "phone": "+1-415-555-0101",
        "company": "Analytical Engines",
        "job_title": "Mathematician",
        "addresses": [
            {
                "type": "Work",
                "address": "1 Market St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94105",
                "country": "USA",
            }
        ],
        "notes": "First programmer.",
    }


@pytest.fixture(autouse=True)
def linkedin_verifier(monkeypatch) -> AsyncMock:
    """Avoid real LinkedIn requests in API tests while exposing call assertions."""
    verifier = AsyncMock(return_value=None)
    monkeypatch.setattr("app.routers.contacts.verify_linkedin_profile", verifier)
    return verifier

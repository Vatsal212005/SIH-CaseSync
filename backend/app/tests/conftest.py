import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_casesync.db"
os.environ["DEMO_MODE"] = "true"
os.environ["DEMO_PASSWORD"] = "CaseSync@2026"

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.ml import engine as ml_engine
from app.seed import seed


@pytest.fixture(scope="session", autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    ml_engine._model.cache_clear()
    ml_engine._model = lambda: None
    ml_engine.MODEL_STATUS.update(backend="feature-hash-fallback", error="disabled in unit tests")
    seed()
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    Path("test_casesync.db").unlink(missing_ok=True)


@pytest.fixture()
def client():
    # Unit tests exercise jobs directly; avoid starting the hourly production scheduler.
    yield TestClient(app)


def login(client, email="central@casesync.demo"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "CaseSync@2026"})
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("casesync_csrf")
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def central(client):
    return login(client)


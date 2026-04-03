import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["MODEL_ROUTER_PROVIDER"] = "heuristic"
os.environ["MODEL_ROUTER_SIMPLE_MODEL"] = "qwen3:4b"
os.environ["MODEL_ROUTER_STANDARD_MODEL"] = "qwen3:8b"
os.environ["MODEL_ROUTER_COMPLEX_MODEL"] = "qwen3:8b"
os.environ["BROWSER_AGENT_PROVIDER"] = "ollama"
os.environ["BROWSER_AGENT_MODEL"] = "qwen3-vl:4b"
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11439"
os.environ["GOOGLE_API_FREE_TIER_ONLY"] = "true"
os.environ["GOOGLE_API_FREE_TIER_FALLBACK_MODEL"] = "gemini-3-flash-preview"
os.environ["GOOGLE_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["BROWSER_USE_SYSTEM_CHROME"] = "false"
os.environ["BROWSER_CHROME_PROFILE_DIRECTORY"] = "Default"
os.environ["BROWSER_PERSISTENT_PROFILE_DIR"] = "artifacts/browser/browser-use-user-data-dir-gradeagent-test"
os.environ["BROWSER_CLEANUP_STALE_AFTER_SECONDS"] = "3600"
os.environ["BROWSER_MAX_SAVED_SCREENSHOTS"] = "3"

from app.db import get_session
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

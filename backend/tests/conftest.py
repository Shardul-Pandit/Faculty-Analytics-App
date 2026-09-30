"""
Shared test setup.

Settings are read when the app is imported, so the environment is pinned here,
before any `app` import. Environment variables take precedence over backend/.env,
which means the tests never use a real API key, the real database or the real
upload folders, even when run from a machine that has a configured .env.
"""

import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="faculty-analytics-tests-"))

os.environ.update({
    "SECRET_KEY":      "test-secret-key-not-for-production",
    "DATABASE_URL":    f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "UPLOADS_DIR":     str(_TMP / "uploads"),
    "OUTPUTS_DIR":     str(_TMP / "outputs"),
    "AI_PROVIDER":     "basic",
    "GEMINI_API_KEY":  "",
    "OPENAI_API_KEY":  "",
})

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
from app.engine.io import normalize_dataframe  # noqa: E402
from app.engine.mapping import auto_detect_mapping  # noqa: E402
from app.main import app  # noqa: E402

from helpers import AFTER_CSV, BEFORE_CSV, signup, upload  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    shutil.rmtree(_TMP, ignore_errors=True)


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_mapping():
    return auto_detect_mapping(list(pd.read_csv(BEFORE_CSV, nrows=0).columns))


@pytest.fixture
def before_df(sample_mapping):
    return normalize_dataframe(pd.read_csv(BEFORE_CSV), sample_mapping, "Before")


@pytest.fixture
def after_df(sample_mapping):
    return normalize_dataframe(pd.read_csv(AFTER_CSV), sample_mapping, "After")


# ---------------------------------------------------------------------------
# API fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """A TestClient on a fresh, empty database and empty storage folders."""
    Base.metadata.drop_all(bind=engine)
    for folder in (settings.uploads_dir, settings.outputs_dir):
        shutil.rmtree(folder, ignore_errors=True)
    with TestClient(app) as c:  # runs the app lifespan, which recreates tables
        yield c


@pytest.fixture
def auth(client):
    return signup(client)


@pytest.fixture
def two_files(client, auth, sample_mapping):
    """Upload both sample files for the default user; return (headers, ids, mapping)."""
    ids = [
        upload(client, auth, BEFORE_CSV, "Before").json()["file_id"],
        upload(client, auth, AFTER_CSV, "After").json()["file_id"],
    ]
    return auth, ids, sample_mapping

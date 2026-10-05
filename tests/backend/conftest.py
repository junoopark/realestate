import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.db.session import get_engine
from app.services.content_store import initialize_storage


@pytest.fixture
def local_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    get_engine.cache_clear()
    initialize_storage()
    yield
    get_engine().dispose()
    get_engine.cache_clear()

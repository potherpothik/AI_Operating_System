import os

# Only default to SQLite if the caller hasn't already set DATABASE_URL —
# unconditionally overwriting it here would silently run every test
# against SQLite even when a real Postgres URL was passed in, which is
# exactly what happened once already while verifying this project.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_governance.db")

import pytest

from governance.db import engine, Base


@pytest.fixture(autouse=True)
def clean_db():
    """
    Truncates tables through the same live connection rather than deleting
    the SQLite file — StaticPool (governance/db.py) holds one persistent
    connection for the whole test session, and removing the file out from
    under that open connection is what was producing "readonly database"
    errors, not a real permissions problem.
    """
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield

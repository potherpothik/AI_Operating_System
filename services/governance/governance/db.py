import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# Local dev/test default: SQLite, zero external setup required.
# Production target (Phase 19): set DATABASE_URL to the Postgres instance, e.g.
#   postgresql://user:pass@postgres:5432/governance
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./governance.db")

if DATABASE_URL.startswith("sqlite"):
    # StaticPool: all "connections" share one real underlying connection,
    # which avoids SQLite file-locking issues under a threaded test client.
    # Not used for Postgres, which handles real concurrent connections natively.
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

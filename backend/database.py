"""
database.py
SQLAlchemy engine, session factory, and dependency.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Import Base here so all models register against it
from models import Base  # noqa: E402  (after engine so no circular import)


def get_db():
    """FastAPI dependency — yields a DB session, closes on exit."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

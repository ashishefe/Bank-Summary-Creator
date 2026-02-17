"""SQLAlchemy database setup for session persistence."""

import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class ClientSessionDB(Base):
    __tablename__ = "client_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    client_name = Column(String(200), default="")
    assessment_year = Column(String(20), default="2025-2026")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # JSON blob storing parsed accounts and categorization state
    data_json = Column(Text, default="{}")


class UploadedFileDB(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    filepath = Column(String(1000), nullable=False)
    bank_name = Column(String(100), default="")
    status = Column(String(50), default="pending")  # pending, parsed, error, skipped
    error_message = Column(Text, default="")
    uploaded_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Create database tables."""
    Base.metadata.create_all(engine)


def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

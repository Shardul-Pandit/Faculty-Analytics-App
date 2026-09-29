from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship
from ..core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    file_records = relationship("FileRecord", back_populates="owner", cascade="all, delete-orphan")
    column_mappings = relationship("ColumnMapping", back_populates="owner", cascade="all, delete-orphan")

    # SSO extension point: add sso_provider / sso_subject columns here later

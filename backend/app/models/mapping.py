from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from ..core.database import Base


class ColumnMapping(Base):
    """
    Stores a user's saved column mapping for a specific CSV schema.
    The columns_fingerprint is a short hash of the sorted column names,
    used to auto-match the same schema on future uploads.
    """

    __tablename__ = "column_mappings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Stable hash of the CSV's column names — enables reuse across uploads
    columns_fingerprint = Column(String, index=True, nullable=False)

    # e.g. {"major": "Department", "grade": "Score", "student_name": "Name", ...}
    mapping = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="column_mappings")

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from ..core.database import Base


class FileRecord(Base):
    __tablename__ = "file_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Original name the user gave; stored_filename is the UUID-prefixed disk name
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False, unique=True)

    # Faculty can manually assign a term label if the CSV has no semester column
    term_label = Column(String, nullable=True)

    detected_columns = Column(JSON, nullable=True)   # list of column names as detected on upload
    row_count = Column(Integer, nullable=True)
    upload_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="file_records")

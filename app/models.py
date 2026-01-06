# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from datetime import datetime
from app.database import Base


# -------------------- User --------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    secret_key = Column(String, nullable=False, unique=False)      # رمز شخصی (NOT unique - multiple users can have same password)
    preferred_language = Column(String, default="en", nullable=False)  # زبان انتخابی کاربر (NOT nullable - always has default)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, server_default=None)  # زمان ثبت‌نام (NOT nullable - always has default)


# -------------------- Memory --------------------
class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_message = Column(String, nullable=False)
    sedi_response = Column(String, nullable=True)
    language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.utcnow)


# -------------------- HealthData --------------------
class HealthData(Base):
    __tablename__ = "health_data"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # CASCADE delete when user deleted
    heart_rate = Column(String, nullable=True)
    temperature = Column(String, nullable=True)
    spo2 = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


# -------------------- Notification --------------------
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # CASCADE delete when user deleted
    type = Column(String, nullable=False, default="info")  # Contract: type enum
    priority = Column(String, nullable=False, default="normal")  # Contract: priority enum
    title = Column(String, nullable=True)  # Contract: optional title
    message = Column(String, nullable=False)  # Contract: required message
    actions = Column(String, nullable=True)  # JSON string of actions array
    metadata_json = Column("metadata", String, nullable=True)  # JSON string of metadata object (column name is 'metadata' in DB)
    is_read = Column(Boolean, default=False, nullable=True)  # Contract: is_read
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)  # Contract: created_at

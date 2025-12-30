# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from datetime import datetime
from app.database import Base


# -------------------- User --------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)              # نام کاربر
    secret_key = Column(String, nullable=False)                     # رمز شخصی
    preferred_language = Column(String, default="en")               # زبان انتخابی کاربر
    created_at = Column(DateTime, default=datetime.utcnow)          # زمان ثبت‌نام


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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    heart_rate = Column(String, nullable=True)
    temperature = Column(String, nullable=True)
    spo2 = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# -------------------- Notification --------------------
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False, default="info")  # Contract: type enum
    priority = Column(String, nullable=False, default="normal")  # Contract: priority enum
    title = Column(String, nullable=True)  # Contract: optional title
    message = Column(String, nullable=False)  # Contract: required message
    actions = Column(String, nullable=True)  # JSON string of actions array
    metadata_json = Column("metadata", String, nullable=True)  # JSON string of metadata object (column name is 'metadata' in DB)
    is_read = Column(Boolean, default=False)  # Contract: is_read
    created_at = Column(DateTime, default=datetime.utcnow)  # Contract: created_at

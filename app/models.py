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


# -------------------- Notification --------------------
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(String, nullable=False)
    sound_id = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

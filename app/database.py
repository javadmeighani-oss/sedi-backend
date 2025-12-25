# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی
load_dotenv()

# دریافت DATABASE_URL از environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://sedi_user:sedi_password@localhost:5432/sedi_db"
)

# ایجاد engine برای PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # بررسی اتصال قبل از استفاده
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

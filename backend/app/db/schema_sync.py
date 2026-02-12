"""Idempotent schema sync: add missing notification columns at startup."""
from sqlalchemy import text

from backend.app.db.session import engine


def ensure_notifications_columns():
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS channel VARCHAR(50);
        """))
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS language VARCHAR(10);
        """))
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS actions_json JSONB;
        """))
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS deeplink_url TEXT;
        """))
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS provider VARCHAR(50);
        """))
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS provider_message_id TEXT;
        """))
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS status VARCHAR(50);
        """))
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS last_error TEXT;
        """))
        conn.execute(text("""
            ALTER TABLE notifications ADD COLUMN IF NOT EXISTS ttl_seconds INTEGER;
        """))

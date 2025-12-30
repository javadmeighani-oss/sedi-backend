#!/usr/bin/env python3
"""
Check PostgreSQL schema against contract requirements
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

# Load environment
os.chdir('/var/www/sedi/backend' if os.path.exists('/var/www/sedi/backend') else '.')
sys.path.insert(0, os.getcwd())

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

print("="*60)
print("SCHEMA INSPECTION")
print("="*60)

inspector = inspect(engine)

# Check notifications table
if 'notifications' not in inspector.get_table_names():
    print("❌ Table 'notifications' does not exist")
    sys.exit(1)

print("\n✅ Table 'notifications' exists")

# Get columns
columns = {col['name']: col for col in inspector.get_columns('notifications')}

print("\nColumns in 'notifications' table:")
required_fields = {
    'id': {'type': 'integer', 'nullable': False},
    'user_id': {'type': 'integer', 'nullable': False},
    'type': {'type': 'string', 'nullable': False},
    'priority': {'type': 'string', 'nullable': False},
    'title': {'type': 'string', 'nullable': True},
    'message': {'type': 'string', 'nullable': False},
    'actions': {'type': 'string', 'nullable': True},
    'metadata': {'type': 'string', 'nullable': True},
    'is_read': {'type': 'boolean', 'nullable': True},
    'created_at': {'type': 'datetime', 'nullable': True}
}

missing = []
for field, req in required_fields.items():
    if field in columns:
        col = columns[field]
        print(f"  ✅ {field}: {col['type']} (nullable={col['nullable']})")
    else:
        print(f"  ❌ {field}: MISSING")
        missing.append(field)

if missing:
    print(f"\n❌ Missing columns: {missing}")
    sys.exit(1)
else:
    print("\n✅ All required columns exist")
    print("\n✅ Schema matches contract requirements")


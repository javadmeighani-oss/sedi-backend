#!/usr/bin/env python3
"""
Script to check current database schema vs model definition
"""

import sys
from sqlalchemy import inspect, text
from app.database import engine
from app.models import User

def check_schema():
    """Check if database schema matches model"""
    print("=" * 60)
    print("CHECKING DATABASE SCHEMA")
    print("=" * 60)
    
    inspector = inspect(engine)
    
    # Check if users table exists
    if 'users' not in inspector.get_table_names():
        print("❌ ERROR: 'users' table does not exist!")
        print("Run: python fix_schema.py to create it")
        return False
    
    print("\n✅ 'users' table exists")
    
    # Get columns from database
    db_columns = {col['name']: col for col in inspector.get_columns('users')}
    
    print("\n" + "=" * 60)
    print("DATABASE SCHEMA (current):")
    print("=" * 60)
    for col_name, col_info in db_columns.items():
        nullable = "NULL" if col_info['nullable'] else "NOT NULL"
        default = f"DEFAULT {col_info.get('default')}" if col_info.get('default') else ""
        print(f"  {col_name}: {col_info['type']} {nullable} {default}")
    
    # Get expected columns from model
    print("\n" + "=" * 60)
    print("MODEL DEFINITION (expected):")
    print("=" * 60)
    for col in User.__table__.columns:
        nullable = "NULL" if col.nullable else "NOT NULL"
        default = f"DEFAULT {col.default.arg}" if col.default else ""
        print(f"  {col.name}: {col.type} {nullable} {default}")
    
    # Compare
    print("\n" + "=" * 60)
    print("COMPARISON:")
    print("=" * 60)
    
    issues = []
    
    # Check all model columns exist in DB
    for col in User.__table__.columns:
        if col.name not in db_columns:
            issues.append(f"❌ Column '{col.name}' missing in database")
        else:
            db_col = db_columns[col.name]
            # Check nullable
            if col.nullable != db_col['nullable']:
                issues.append(
                    f"⚠️  Column '{col.name}': nullable mismatch - "
                    f"Model: {col.nullable}, DB: {db_col['nullable']}"
                )
    
    # Check for extra columns in DB
    model_col_names = {col.name for col in User.__table__.columns}
    for db_col_name in db_columns:
        if db_col_name not in model_col_names:
            issues.append(f"⚠️  Extra column '{db_col_name}' in database (not in model)")
    
    if issues:
        print("\n❌ SCHEMA MISMATCH DETECTED:")
        for issue in issues:
            print(f"  {issue}")
        print("\n💡 SOLUTION: Run 'python fix_schema.py' to fix schema")
        return False
    else:
        print("\n✅ Schema matches model perfectly!")
        return True

if __name__ == "__main__":
    try:
        success = check_schema()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)

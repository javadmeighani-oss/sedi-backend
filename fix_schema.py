#!/usr/bin/env python3
"""
Temporary script to fix database schema mismatch.
This will drop and recreate the users table to match the current model.
USE WITH CAUTION - This will delete all existing users!
"""

import sys
import os
from sqlalchemy import text
from app.database import engine, Base
from app.models import User

def fix_schema():
    """Drop and recreate users table to match current model"""
    print("=" * 60)
    print("WARNING: This will DELETE ALL EXISTING USERS!")
    print("=" * 60)
    
    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()
        try:
            # Drop existing users table
            print("\n[1/3] Dropping existing users table...")
            conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
            print("✅ Users table dropped")
            
            # Recreate table from model
            print("\n[2/3] Creating users table from model...")
            Base.metadata.create_all(bind=engine, tables=[User.__table__])
            print("✅ Users table created")
            
            # Commit transaction
            trans.commit()
            print("\n[3/3] ✅ Schema fixed successfully!")
            print("\n" + "=" * 60)
            print("Users table has been recreated with correct schema.")
            print("=" * 60)
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ ERROR: {e}")
            import traceback
            print(traceback.format_exc())
            sys.exit(1)

if __name__ == "__main__":
    fix_schema()


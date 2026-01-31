#!/usr/bin/env python3
"""
Migration script to remove UNIQUE constraint from users.name column.
This is safe to run multiple times - it uses IF EXISTS.
"""

import sys
from sqlalchemy import text
from app.database import engine

def remove_name_unique_constraint():
    """Remove UNIQUE constraint from users.name if it exists"""
    print("=" * 60)
    print("Removing UNIQUE constraint from users.name column")
    print("=" * 60)
    
    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()
        try:
            # Drop the constraint if it exists (PostgreSQL syntax)
            print("\n[1/2] Dropping constraint 'users_name_key' if it exists...")
            conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_name_key"))
            conn.commit()
            print("✅ Constraint dropped (or did not exist)")
            
            # Also try alternative constraint names that might exist
            print("\n[2/2] Checking for other possible constraint names...")
            # Try common PostgreSQL unique constraint naming patterns
            alternative_names = [
                "users_name_unique",
                "users_name_uk",
                "users_name_key",
            ]
            
            for constraint_name in alternative_names:
                try:
                    conn.execute(text(f"ALTER TABLE users DROP CONSTRAINT IF EXISTS {constraint_name}"))
                    conn.commit()
                    print(f"✅ Checked {constraint_name}")
                except Exception as e:
                    # Ignore errors - constraint might not exist with this name
                    pass
            
            print("\n" + "=" * 60)
            print("✅ Migration completed successfully!")
            print("users.name column is now non-unique - multiple users can have the same name")
            print("=" * 60)
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ ERROR: {e}")
            import traceback
            print(traceback.format_exc())
            sys.exit(1)

if __name__ == "__main__":
    remove_name_unique_constraint()

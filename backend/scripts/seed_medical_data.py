#!/usr/bin/env python3
"""
Medical Data Seed Script

This script seeds the medical_conditions and medications tables with initial data.
It is idempotent - safe to run multiple times.

Usage:
    python scripts/seed_medical_data.py
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import MedicalCondition, Medication, Base

# Ensure tables exist
Base.metadata.create_all(bind=engine)


def load_seed_data():
    """Load seed data from JSON file"""
    script_dir = Path(__file__).parent
    json_path = script_dir / "seed_medical_data.json"
    
    if not json_path.exists():
        print(f"ERROR: Seed data file not found: {json_path}")
        sys.exit(1)
    
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_conditions(db: Session, conditions_data: list):
    """Seed medical conditions into database"""
    inserted = 0
    skipped = 0
    
    for cond_data in conditions_data:
        code = cond_data.get("code")
        name = cond_data.get("name")
        
        if not code or not name:
            print(f"WARNING: Skipping condition with missing code or name: {cond_data}")
            skipped += 1
            continue
        
        # Check if condition already exists (by code or name)
        existing = db.query(MedicalCondition).filter(
            (MedicalCondition.code == code) | (MedicalCondition.name == name)
        ).first()
        
        if existing:
            # Update existing condition if code matches
            if existing.code != code:
                existing.code = code
            if existing.name != name:
                existing.name = name
            if cond_data.get("description"):
                existing.description = cond_data.get("description")
            if cond_data.get("category"):
                existing.category = cond_data.get("category")
            print(f"  Updated existing condition: {code} - {name}")
            skipped += 1
            continue
        
        # Store metadata (chronic, severity_level, keywords) in description as JSON string
        metadata = {
            "chronic": cond_data.get("chronic", False),
            "severity_level": cond_data.get("severity_level", "medium"),
            "keywords": cond_data.get("keywords", [])
        }
        description_with_metadata = cond_data.get("description", "")
        if description_with_metadata:
            description_with_metadata += f" | Metadata: {json.dumps(metadata)}"
        else:
            description_with_metadata = f"Metadata: {json.dumps(metadata)}"
        
        # Create new condition
        new_condition = MedicalCondition(
            code=code,
            name=name,
            description=description_with_metadata,
            category=cond_data.get("category"),
            embedding_id=None  # RAG-ready, not active
        )
        
        db.add(new_condition)
        inserted += 1
        print(f"  ✓ Inserted condition: {code} - {name}")
    
    db.commit()
    return inserted, skipped


def seed_medications(db: Session, medications_data: list, conditions_map: dict):
    """Seed medications into database"""
    inserted = 0
    skipped = 0
    
    for med_data in medications_data:
        name = med_data.get("name")
        condition_code = med_data.get("condition_code")
        
        if not name:
            print(f"WARNING: Skipping medication with missing name: {med_data}")
            skipped += 1
            continue
        
        # Resolve condition_id from condition_code
        condition_id = None
        if condition_code:
            condition = conditions_map.get(condition_code)
            if condition:
                condition_id = condition.id
            else:
                print(f"WARNING: Condition code '{condition_code}' not found for medication '{name}'")
        
        # Check if medication already exists (by name)
        existing = db.query(Medication).filter(Medication.name == name).first()
        
        if existing:
            # Update existing medication
            if med_data.get("generic_name"):
                existing.generic_name = med_data.get("generic_name")
            if med_data.get("dosage_form"):
                existing.dosage_form = med_data.get("dosage_form")
            if med_data.get("default_dosage"):
                existing.default_dosage = med_data.get("default_dosage")
            if condition_id:
                existing.condition_id = condition_id
            print(f"  Updated existing medication: {name}")
            skipped += 1
            continue
        
        # Store keywords in default_dosage field (or create a combined field)
        dosage_info = med_data.get("default_dosage", "")
        keywords = med_data.get("keywords", [])
        if keywords:
            dosage_info = f"{dosage_info} | Keywords: {', '.join(keywords)}" if dosage_info else f"Keywords: {', '.join(keywords)}"
        
        # Create new medication
        new_medication = Medication(
            name=name,
            generic_name=med_data.get("generic_name"),
            dosage_form=med_data.get("dosage_form"),
            default_dosage=dosage_info,
            condition_id=condition_id,
            embedding_id=None  # RAG-ready, not active
        )
        
        db.add(new_medication)
        inserted += 1
        print(f"  ✓ Inserted medication: {name} → {condition_code or 'N/A'}")
    
    db.commit()
    return inserted, skipped


def main():
    """Main seed function"""
    print("=" * 60)
    print("Medical Data Seed Script")
    print("=" * 60)
    print()
    
    # Load seed data
    print("Loading seed data from JSON...")
    seed_data = load_seed_data()
    conditions_data = seed_data.get("conditions", [])
    medications_data = seed_data.get("medications", [])
    
    print(f"Found {len(conditions_data)} conditions and {len(medications_data)} medications")
    print()
    
    # Create database session
    db: Session = SessionLocal()
    
    try:
        # Seed conditions
        print("Seeding medical conditions...")
        cond_inserted, cond_skipped = seed_conditions(db, conditions_data)
        print()
        
        # Build conditions map for medication lookup
        print("Building conditions lookup map...")
        all_conditions = db.query(MedicalCondition).all()
        conditions_map = {cond.code: cond for cond in all_conditions if cond.code}
        print(f"  Mapped {len(conditions_map)} conditions by code")
        print()
        
        # Seed medications
        print("Seeding medications...")
        med_inserted, med_skipped = seed_medications(db, medications_data, conditions_map)
        print()
        
        # Summary
        print("=" * 60)
        print("SEED SUMMARY")
        print("=" * 60)
        print(f"Conditions: Inserted {cond_inserted}, Skipped {cond_skipped}")
        print(f"Medications: Inserted {med_inserted}, Skipped {med_skipped}")
        print()
        print("✅ Seed script completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

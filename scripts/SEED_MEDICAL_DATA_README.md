# Medical Data Seed Script

## Overview

This script seeds the `medical_conditions` and `medications` tables with initial medical data. The script is **idempotent** - safe to run multiple times without creating duplicates.

## Files

- `seed_medical_data.json` - JSON data file containing conditions and medications
- `seed_medical_data.py` - Python script to seed the database

## Usage

From the `backend` directory:

```bash
python scripts/seed_medical_data.py
```

Or from the project root:

```bash
cd backend
python scripts/seed_medical_data.py
```

## What Gets Seeded

### Medical Conditions (13 total)

**Mandatory Conditions:**
- **ALS** (Amyotrophic Lateral Sclerosis) - High severity, chronic
- **MS** (Multiple Sclerosis) - High severity, chronic

**Additional Conditions:**
- DIABETES_T2 (Type 2 Diabetes)
- HYPERTENSION
- ARRHYTHMIA
- HEART_FAILURE
- ASTHMA_COPD
- CHRONIC_BACK_PAIN
- KNEE_OSTEOARTHRITIS
- MIGRAINE
- INSOMNIA
- ANXIETY
- DEPRESSION_MILD

### Medications (8 total)

- Riluzole → ALS
- Interferon Beta → MS
- Metformin → DIABETES_T2
- Insulin (Generic) → DIABETES_T2
- Amlodipine → HYPERTENSION
- Losartan → HYPERTENSION
- Atorvastatin → HEART_FAILURE
- Sertraline → ANXIETY

## Features

- ✅ **Idempotent**: Safe to run multiple times
- ✅ **Checks existence**: Skips existing records
- ✅ **Updates existing**: Updates records if they exist
- ✅ **RAG-ready**: All `embedding_id` fields set to NULL
- ✅ **Clear output**: Shows inserted and skipped counts

## Output Example

```
============================================================
Medical Data Seed Script
============================================================

Loading seed data from JSON...
Found 13 conditions and 8 medications

Seeding medical conditions...
  ✓ Inserted condition: ALS - Amyotrophic Lateral Sclerosis
  ✓ Inserted condition: MS - Multiple Sclerosis
  ...

Building conditions lookup map...
  Mapped 13 conditions by code

Seeding medications...
  ✓ Inserted medication: Riluzole → ALS
  ✓ Inserted medication: Interferon Beta → MS
  ...

============================================================
SEED SUMMARY
============================================================
Conditions: Inserted 13, Skipped 0
Medications: Inserted 8, Skipped 0

✅ Seed script completed successfully!
```

## Data Structure

### Condition Metadata

Each condition includes:
- `code` - Unique uppercase code (e.g., "ALS", "MS")
- `name` - Full condition name
- `description` - Description + metadata (chronic, severity_level, keywords as JSON)
- `category` - Category (chronic, cardiovascular, respiratory, etc.)
- `embedding_id` - NULL (RAG-ready)

### Medication Structure

Each medication includes:
- `name` - Medication name
- `generic_name` - Generic name
- `condition_id` - Foreign key to medical_conditions (resolved from condition_code)
- `dosage_form` - Form (tablet, injection, etc.)
- `default_dosage` - Dosage info + keywords
- `embedding_id` - NULL (RAG-ready)

## Notes

- The script uses existing SQLAlchemy models and database configuration
- Metadata (chronic, severity_level, keywords) is stored in the `description` field as JSON
- Medications are linked to conditions via `condition_code` in JSON, which is resolved to `condition_id` in the database
- All `embedding_id` fields remain NULL (RAG-ready, not active)

## Troubleshooting

If you encounter errors:

1. **Database connection**: Ensure your database is running and `DATABASE_URL` is set correctly
2. **Import errors**: Make sure you're running from the `backend` directory or have the correct Python path
3. **Duplicate errors**: The script should handle duplicates automatically, but if you see unique constraint errors, check existing data

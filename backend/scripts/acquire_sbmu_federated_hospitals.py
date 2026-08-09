"""Acquire CAP25 SBMU federated hospital seed payload (facts-only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args(argv)

    from backend.app.services.i5.iran_directory_federation import acquire_sbmu_affiliated_hospitals
    from backend.app.services.i5.iran_directory_normalization import normalize_records

    fetched = acquire_sbmu_affiliated_hospitals()
    valid, rejected = normalize_records(fetched.records)
    payload = {
        "source": fetched.source_url,
        "final_url": fetched.final_url,
        "coverage_class": fetched.coverage_class,
        "nationwide_complete": False,
        "records": valid,
        "rejected_normalize": rejected,
        "rejected_verify": fetched.rejected,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "valid": len(valid),
                "rejected_normalize": len(rejected),
                "rejected_verify": len(fetched.rejected),
                "out": str(out),
            },
            ensure_ascii=False,
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())

"""Bounded rolling crawl of the Paziresh24 public directory → normalized payload JSON.

Stateless rotation: the window start is derived from the week number, so successive weekly runs
cover successive slices of the sorted doctor URL list and wrap around. No DB access here; feed
the payload to `iran_directory_prod_apply.py dry-run|apply --payload <file>`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


def window(urls: list[str], budget: int, week_index: int) -> list[str]:
    ordered = sorted(urls)
    if not ordered or budget <= 0:
        return []
    start = (week_index * budget) % len(ordered)
    doubled = ordered + ordered
    return doubled[start : start + min(budget, len(ordered))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paziresh24 rolling directory crawl")
    parser.add_argument("--budget", type=int, default=2000, help="max doctor pages this run")
    parser.add_argument("--week-index", type=int, default=date.today().toordinal() // 7)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    from backend.app.services.i5.iran_directory_normalization import normalize_records
    from backend.app.services.i5.iran_directory_p24 import crawl_doctors, list_doctor_urls

    urls = window(list_doctor_urls(), args.budget, args.week_index)
    result = crawl_doctors(urls, budget=args.budget, interval=args.interval)
    valid, rejected = normalize_records(result["records"])
    Path(args.out).write_text(json.dumps({"records": valid}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"stats": result["stats"], "valid": len(valid), "rejected": len(rejected),
                      "window": len(urls)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Controlled P1-L1 legacy companion seed entry point (dry-run default).

No import-time execution of seed logic beyond argparse definition.
Apply requires --apply plus environment, allowlist, digest, and confirmation.

Usage (planning only — this Gate never applies):
    python backend/scripts/seed_i5b2_p1_l1_legacy_companions.py
    python backend/scripts/seed_i5b2_p1_l1_legacy_companions.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# Ensure repository root is importable when invoked as a script.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="I5-B2-P1-L1 controlled legacy companion seed (dry-run default)"
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Plan only; zero writes (default)",
    )
    parser.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Authorize writes (still requires environment/allowlist/digest/confirm)",
    )
    parser.add_argument(
        "--environment",
        default="",
        help="Explicit target environment (required for apply)",
    )
    parser.add_argument(
        "--allowlist",
        default="",
        help="Comma-separated source_key allowlist (required for apply)",
    )
    parser.add_argument(
        "--expect-digest",
        default="",
        help="Expected plan digest (required for apply)",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help="Operator confirmation token (required for apply)",
    )
    parser.add_argument(
        "--evidence-json",
        default="",
        help="Optional JSON file mapping source_key -> governance_evidence object",
    )
    parser.add_argument(
        "--use-catalog-inventory",
        action="store_true",
        default=True,
        help="Include Gate3h catalog inventory keys (default true)",
    )
    parser.add_argument(
        "--no-catalog-inventory",
        dest="use_catalog_inventory",
        action="store_false",
        help="Do not include Gate3h catalog inventory",
    )
    return parser.parse_args(argv)


def _load_evidence_registry(path: str) -> Mapping[str, Mapping[str, Any]]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("evidence-json must be an object keyed by source_key")
    out: dict[str, Mapping[str, Any]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            raise SystemExit(f"evidence for {key!r} must be an object")
        out[str(key)] = value
    return out


def _build_candidates(evidence: Mapping[str, Mapping[str, Any]], use_catalog: bool):
    from backend.app.services.governance.kb_b2_legacy_companion_seed import (
        GATE3H_CATALOG_SOURCE_KEYS,
        LegacyCompanionSeedCandidate,
        catalog_inventory_candidates,
    )

    if use_catalog:
        base = list(catalog_inventory_candidates())
    else:
        base = []
    # Overlay explicit evidence without inventing defaults for unmapped keys.
    merged: dict[str, LegacyCompanionSeedCandidate] = {
        c.source_key: c for c in base
    }
    for key, ev in evidence.items():
        prior = merged.get(key)
        merged[key] = LegacyCompanionSeedCandidate(
            source_key=key,
            display_name=prior.display_name if prior else key,
            locator=prior.locator if prior else None,
            locator_kind=prior.locator_kind if prior else None,
            legacy_knowledge_source_id=(
                prior.legacy_knowledge_source_id if prior else None
            ),
            governance_evidence=ev,
            product_legal_hold=prior.product_legal_hold if prior else False,
        )
    # Preserve catalog order then any extra evidence-only keys.
    ordered_keys = list(GATE3H_CATALOG_SOURCE_KEYS) if use_catalog else []
    for key in evidence:
        if key not in ordered_keys:
            ordered_keys.append(key)
    return [merged[k] for k in ordered_keys if k in merged]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    evidence = _load_evidence_registry(args.evidence_json)
    candidates = _build_candidates(evidence, args.use_catalog_inventory)

    from backend.app.services.governance.kb_b2_legacy_companion_seed import (
        apply_plan,
        build_plan,
    )

    if args.dry_run:
        plan = build_plan(None, candidates, dry_run=True)
        report = {
            "dry_run": True,
            "plan_digest": plan.plan_digest,
            "total_scanned": plan.total_scanned,
            "eligible": plan.eligible,
            "already_present": plan.already_present,
            "would_create": plan.would_create,
            "would_append": plan.would_append,
            "ineligible": plan.ineligible,
            "conflicted": plan.conflicted,
            "blocked": plan.blocked,
            "errors": plan.errors,
            "decisions": [
                {
                    "legacy_identifier": d.legacy_identifier,
                    "canonical_key": d.canonical_key,
                    "decision": d.decision.value,
                    "reason": d.reason,
                    "eligibility": d.eligibility.value,
                    "missing_evidence": list(d.missing_evidence),
                    "proposed_operational_status": d.proposed_operational_status,
                }
                for d in plan.decisions
            ],
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    # Apply path requires an explicit DB session factory — still not invoked by this Gate.
    allowlist = [p.strip() for p in str(args.allowlist).split(",") if p.strip()]
    try:
        from backend.app.database import SessionFactory
    except Exception as exc:  # pragma: no cover - environment specific
        print(json.dumps({"error": "session_factory_unavailable", "detail": str(exc)}))
        return 2

    session = SessionFactory()
    try:
        result = apply_plan(
            session,
            candidates,
            dry_run=False,
            target_environment=args.environment,
            candidate_allowlist=allowlist,
            expected_plan_digest=args.expect_digest,
            operator_confirmation=args.confirm,
        )
        session.commit()
        print(
            json.dumps(
                {
                    "applied": result.applied,
                    "plan_digest": result.plan_digest,
                    "environment": result.environment,
                    "committed": list(result.committed),
                    "failed": list(result.failed),
                    "notes": list(result.notes),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if not result.failed else 1
    except Exception as exc:
        session.rollback()
        print(json.dumps({"error": getattr(exc, "reason", str(exc))}))
        return 2
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())

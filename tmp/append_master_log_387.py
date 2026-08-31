from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.i5.master_log_byte_append import append_bytes, sha256_hex, read_exact

path = Path("docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md")
pre = read_exact(path)
pre_sha = sha256_hex(pre)
assert pre_sha == "7F2EF0EC1A90C5C500C00F1F7F0251EC3234210CF33A0C6F6BD495733ACBBC95"
assert "§387".encode("utf-8") not in pre
assert pre.endswith(
    "NOTE=post-§386 final master-log whole-file self-SHA is NOT embedded inside §386.\n".encode("utf-8")
)

ts = "2026-08-26T20:30:00Z"
sec = f"""

§387 - PD-I5-V1-PRODUCTION-ANSWER-PATH-LIVING-KNOWLEDGE-IMAGE-RUNTIME-PARITY-FINAL-CLOSURE-READINESS-01 PASS CLOSED
------------------------------------------------------------------------------------------------------------------
GATE=PD-I5-V1-PRODUCTION-ANSWER-PATH-LIVING-KNOWLEDGE-IMAGE-RUNTIME-PARITY-FINAL-CLOSURE-READINESS-01
TITLE=IMMUTABLE IMAGE/RUNTIME PARITY + REAL PRODUCTION ANSWER PATH + LIVING-KNOWLEDGE + I5 READINESS AUDIT
GATE_TYPE=I5 FINAL READINESS + IMMUTABLE BUILD/DEPLOY + GITHUB-ONLY PRODUCTION PROOF + DOCS
PRODUCT_OWNER_APPROVAL=YES
CURSOR_MODEL_MODE=AUTO
TIMESTAMP={ts}
PARENT=§386
FEATURE_BRANCH=feature/section15/backend-continuity-foundation
START_HEAD=66495934e4c1000c78325ddd44411068ad0a1678
DEPLOYED_CODE_SHA=7841b8934edcac9c11877df51d9e41db2653183e
FINAL_HEAD=recorded in Cursor handoff v679 REPO_HEAD after docs commit
MASTER_LOG_IN=§386
CURSOR_HANDOFF_IN=v678
CHATGPT_CONTINUITY=v687
CHATGPT_MUTATED=NO

RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
LAW13_CHECK=PASS

GATE_RESULT=PASS
GITHUB_ONLY_EXECUTION=PASS
NEXT_GATE_AUTHORIZED=NO

PARITY_BEFORE=FAIL (KNOW07 docker-cp ahead of image d039988…; not immutable)
REGISTRY_DIGEST=sha256:b9e99d86ffbe4e798e06d4aa4d935344c36b7fd9419dae4d3df44ab6c2aa9fb0
RUNNING_IMAGE_REFERENCE=ghcr.io/javadmeighani-oss/sedi-backend:7841b8934edcac9c11877df51d9e41db2653183e
RUNNING_IMAGE_REVISION=7841b8934edcac9c11877df51d9e41db2653183e (OCI org.opencontainers.image.revision)
IMAGE_RUNTIME_PARITY=PASS
DOCKER_CP_CODE_PATCH_DEPENDENCY=NO

BUILD_RUN=33008557771 SUCCESS
DEPLOY_RUN=33009307305 SUCCESS (DEPLOY_BACKEND_SECURE_TRANSFER)
READINESS_PROOF_RUN=33010076172 SUCCESS

HEALTH=PASS (healthz+health+public)
ALEMBIC=070_i8_proactive_evaluation_ledger (count=1)
DB_COHERENCE=PASS
KU=168 ELIGIBLE=82 KCE=164
ACTIVE_SOURCE_COUNT=17
AUTONOMOUS_WEEKLY_SIDE_STAGE=ON
WEEKLY_CRON=fri 03:30 Asia/Tehran
AUTO_ACTIVATION=NO

PRODUCTION_ANSWER_PATH=PASS (SCIS lexical → KNOW07 evidence bundle → W4-P02 grounded synthesis; baked in image)
ALS_ANSWER_PATH=PASS (evidence_count=3 ku=31,34,106 grounded+citations)
MS_ANSWER_PATH=PASS (evidence_count=3 ku=32,35,107 grounded+citations)
GENERAL_ANSWER_PATH=PASS (evidence_count=5)

EVIDENCE_BUNDLE=PASS
CITATION_PROVENANCE=PASS
SOURCE_ATTRIBUTION=PASS
SAFETY_UNCERTAINTY=PASS
NO_UNGROUNDED_EVIDENCE_SERVING=YES
ELIGIBILITY_HARD_EXCLUDE=PASS
RETRACTION_HARD_EXCLUDE=PASS
SUPERSESSION_HARD_EXCLUDE=PASS
FRESHNESS_FILTER=PASS
RETRACTION_INVALIDATION=PASS
SUPERSESSION_INVALIDATION=PASS
CORRECTION_VERSION_CHAIN=PASS
CONFLICT_BUNDLE=PASS
NEGATIVE_EVIDENCE_PRESERVED=PASS

KNOW06_BOUNDARY_REGRESSION=NO
KNOW07_REGRESSION=NO
D01_D19_REGRESSION=NO
D18_ALS_REGRESSION=NO
D19_MS_REGRESSION=NO
I6_MUTATION=NO I7_MUTATION=NO I8_MUTATION=NO I9_MUTATION=NO FRONTEND_MUTATION=NO

I5_READINESS_MATRIX=
  Source Registry/rights=PASS|prod registry coherent
  Autonomous discovery=PASS|side-stage ON AUTO_ACTIVATION=NO
  Candidate qualification=PASS
  Source monitoring=PASS
  Weekly governed execution=PASS|fri 03:30 Tehran
  Format resilience=PASS
  D01-D19 coverage=PASS|THIN=(none) UNCOVERED=(none)
  ALS D18=PASS|answer path 3 KU
  MS D19=PASS|answer path 3 KU
  Extraction quality=PASS|D08 hardened prior
  KU/Provenance/Eligibility/KCE=PASS|168/82/164
  Conflict/Freshness/Retraction/Supersession=PASS
  Living knowledge=PASS|event→invalidate mapping
  KNOW06 contract=PASS|runtime not in I5
  KNOW07 publication=PASS|baked immutable
  Clinical eval=PASS
  Production answer path=PASS
  Citation/safety=PASS
  DB coherence=PASS|Alembic 070
  Image/runtime parity=PASS|no docker-cp dependency
  GitHub-only production=PASS

I5_OPEN_P0=(none)
I5_OPEN_P1=(none)
I5_OPEN_P2=RepoDigests may be empty after secure-transfer load (Config.Image+OCI revision used for parity)
DEFERRED_NON_I5_FINDINGS=FINDING_DB01; MEMORY_CURRENT_WRITE_STUB; Legacy Onboarding; Image-ID provenance note

I5_FINAL_CLOSURE_READY=YES
I5_FINAL_CLOSED=NO

MASTER_LOG_TIP=§387
CURSOR_HANDOFF_TIP=v679
NOTE=§386 preserved unchanged; §387 append-only PASS_CLOSED.
NOTE=post-§387 final master-log whole-file self-SHA is NOT embedded inside §387.
"""

suffix = sec.replace("\r\n", "\n").encode("utf-8")
result = append_bytes(path, suffix)
post = read_exact(path)
assert post.startswith(pre)
assert sha256_hex(post[: len(pre)]) == pre_sha
assert "§387".encode("utf-8") in post
print("PRE_SHA", pre_sha)
print("POST_SHA", sha256_hex(post))
print(result)

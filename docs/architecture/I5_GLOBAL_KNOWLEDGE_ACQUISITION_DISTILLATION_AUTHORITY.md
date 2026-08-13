# SEDI-V1 I5 GLOBAL KNOWLEDGE ACQUISITION & DISTILLATION AUTHORITY

Status: **AUTHORITATIVE GOVERNANCE ADDENDUM**  
Approved by: **Javad Meighani**  
Recorded: 2026-08-13  
Scope: Sedi V1 / I5 international medical-scientific knowledge acquisition, evidence cataloging, text/data processing, provenance, rights, retention, and controlled activation.

## 1. Product objective

Sedi I5 must build the broadest credible international medical, healthcare, disease, psychology, lifestyle, nutrition, exercise, daily-routine, and scientific-evidence knowledge base reasonably possible while remaining lawful, medically governed, provenance-preserving, scalable, and operationally low-noise.

The objective is **knowledge acquisition and evidence distillation**, not the creation of an unauthorized archive of publisher expression.

## 2. Superseding clarification — publisher permission is not a universal prerequisite

Direct publisher approval is **NOT** a universal prerequisite for Sedi to learn from a trusted source.

Where Sedi has a lawful automated access route, Sedi may process credible scientific/medical material to extract and persist its own structured knowledge representation, including facts, claims, findings, study characteristics, effect estimates, recommendations, warnings, contraindications, limitations, evidence strength, conflicts, taxonomies, guideline statements, and other factual or analytical knowledge.

A source's raw/full-text retention rights and Sedi's ability to derive knowledge are separate decisions.

`PUBLICLY_ACCESSIBLE` does not automatically mean `UNRESTRICTED_RAW_REUSE`, but lack of raw-retention permission must not automatically exclude an otherwise lawfully accessible credible source from Sedi's evidence catalog or derived-knowledge pipeline.

## 3. Core legal/rights distinction

Sedi must distinguish at least these questions:

1. **May Sedi lawfully access this source by the chosen automated route?**
2. **May Sedi transiently process the returned material for knowledge extraction?**
3. **May Sedi retain the raw/full expression?**
4. **May Sedi redistribute/display that raw expression?**
5. **May Sedi persist derived structured knowledge, facts, claims, evidence metadata, and provenance?**

A `NO` or `UNKNOWN` for raw retention or redistribution does not automatically mean a `NO` for lawful transient processing or derived knowledge. Conversely, if the provider's access terms prohibit the required automated/text-mining route, Sedi must not bypass those restrictions.

## 4. Knowledge-over-expression storage model

For materials whose raw/full-text retention or redistribution is not established, Sedi should prefer:

- stable source identifier (PMID / PMCID / DOI / canonical URL where applicable),
- publisher/journal/source identity,
- publication/version/date metadata,
- study type and evidence class,
- population,
- intervention/exposure,
- comparator,
- outcomes,
- effect estimates and numerical findings,
- limitations,
- warnings and contraindications,
- recommendations/guideline statements represented in Sedi's own structured form,
- evidence strength/confidence,
- conflicts and supersession state,
- taxonomy/entity mappings,
- source/version/provenance chain,
- rights/licence/access-route state,
- hashes and retrieval/version metadata where appropriate,
- Sedi-authored structured synthesis.

Default behavior for restricted or uncertain raw expression:

```text
PROCESS_VIA_LAWFUL_AUTOMATED_ROUTE=YES
DERIVE_STRUCTURED_KNOWLEDGE=YES
STORE_PROVENANCE=YES
STORE_EVIDENCE_METADATA=YES
STORE_RAW_FULL_TEXT=NO unless explicitly permitted
REPUBLISH_SOURCE_EXPRESSION=NO unless explicitly permitted
```

Do not reconstruct a protected work through large or overlapping verbatim excerpts.

## 5. Copyright principle

Copyright protects original expression, while individual facts, ideas, systems, and methods are generally treated differently. Sedi must therefore persist its own normalized knowledge/evidence representation rather than assume permission to retain or redistribute publisher prose.

This governance rule does not claim that every form of text/data mining is automatically lawful in every jurisdiction or under every provider contract. Access terms, database rights, licences, and applicable jurisdiction must still be evaluated source-by-source.

## 6. Source access priority

Use the least invasive and most provider-supported machine route available:

1. official API,
2. official feed,
3. official baseline/update/export dataset,
4. official bulk/text-mining service,
5. documented machine-readable endpoint,
6. public-web fetch only when the provider's terms/access rules permit that automation.

HTML crawling must not be preferred when a supported official dataset/API provides the required information.

## 7. PubMed / NCBI strategy

For Sedi V1:

```text
SEDI_NCBI_TOOL=sedi
SEDI_NCBI_EMAIL=info@sedi-ai.com
SEDI_NCBI_API_KEY=OPTIONAL
OUTBOUND_EMAIL_TO_NCBI_REQUIRED_FOR_CURRENT_PHASE=NO
```

`info@sedi-ai.com` is the approved real operational Sedi mailbox for NCBI identity configuration.

Sedi does not need to send an outbound registration email to NCBI in the current phase merely to proceed with a low-rate canary. Registration status must not be falsely reported as complete.

For targeted E-utilities canaries/lookup, include the configured `tool` and `email`, keep the request rate deliberately low, batch where possible, and remain below provider limits.

For broad PubMed-scale coverage, prefer the official PubMed annual baseline plus daily update files over millions of request-by-request page/API fetches. The baseline/update path must preserve NLM/PubMed terms, update/revision/deletion semantics, checksums, and provenance.

PubMed citation/abstract data should be processed according to the applicable PubMed dataset terms. Abstract text must not be assumed to be freely redistributable publisher expression; Sedi may distill factual/evidence knowledge through a lawful route while minimizing persistent verbatim retention when rights are not established.

## 8. PMC strategy

Systematic/bulk retrieval of PMC material must use PMC-supported machine-access services/datasets, not scraping of the ordinary PMC website.

For every PMC article used for raw/full-text retention or reuse, evaluate its specific licence/rights statement. Not every article in PMC has the same reuse rights.

Preferred model:

```text
PMC_MACHINE_ROUTE=OFFICIAL_ONLY
ARTICLE_LICENSE_CHECK=REQUIRED
RAW_RETENTION=LICENSE_DEPENDENT
DERIVED_KNOWLEDGE=ALLOWED_ONLY_WHEN_ACCESS/PROCESSING_ROUTE_IS_LAWFUL
```

## 9. No evasion / no access-control bypass

The following are forbidden:

- paywall bypass,
- authentication/access-control circumvention,
- CAPTCHA bypass,
- robots bypass where the chosen route is governed by it,
- rate-limit evasion,
- proxy/IP rotation intended to evade restrictions,
- identity deception,
- spoofing another service to conceal automation,
- ignoring Retry-After or provider stop signals,
- systematic retrieval through a route that the provider explicitly disallows.

If a source denies or throttles Sedi, Sedi must stop/back off/classify/review rather than evade.

## 10. Meaning of “unobtrusive / نامحسوس”

For Sedi, unobtrusive acquisition means:

- background execution,
- no user-facing interruption,
- bounded network load,
- batching,
- caching where permitted,
- low request rate,
- off-peak execution where useful,
- resource isolation from user traffic,
- minimal operational noise.

It **does not** mean hiding Sedi's identity from a provider or bypassing provider controls.

## 11. Evidence catalog coverage

Sedi should strive to know that credible evidence exists even when it cannot retain the original full text.

The evidence catalog may retain lawful bibliographic/source identifiers, metadata, evidence classification, provenance, rights state, and Sedi-derived structured knowledge. A paper should not disappear from Sedi's knowledge universe solely because raw full-text retention is restricted.

## 12. Medical-safety boundary

Acquisition success is not clinical approval.

Every derived candidate must continue through Sedi's existing evidence-strength, provenance, conflict, medical-safety, governance, review, publication, and runtime-eligibility controls.

An individual study is not automatically a guideline or medical consensus. No external source may directly modify patient-specific advice without the established safety/recommendation layer.

## 13. Iran/local-source boundary

International credible medical/scientific sources remain primary for clinical/scientific knowledge.

Iranian sources remain primarily for local provider/facility/service/referral/availability information unless an Iranian source independently qualifies as a high-quality scientific/clinical authority under the same evidence-governance framework.

## 14. Scheduler / activation safety correction

Current Production evidence at Master Log §300 found:

```text
SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=true
SEDI_I5_SOURCE_ACTIVATION_ENABLED=true
SEDI_I5_MULTISOURCE_ENABLED=true
SEDI_DISABLE_SCHEDULER=false
```

The application starts its in-process APScheduler when `SEDI_DISABLE_SCHEDULER=false`, and the I5 weekly job is registered by current code. Therefore the absence of a separate `sedi-scheduler` container is not sufficient proof that I5 scheduling is off.

Before any NCBI or other live one-shot canary, the next Gate must:

1. read-only audit historical I5 weekly runs/network/write evidence,
2. fail-close only the I5 weekly flags,
3. preserve unrelated Sedi notification/medication/device scheduler behavior,
4. prove `DORMANT_NO_OP`, `network_executed=false`, `production_write=false`,
5. only then install/validate NCBI identity and proceed to a one-shot controlled canary.

Do not globally disable the shared scheduler merely to disable I5 unless a separate justified decision requires it.

## 15. One-shot before unattended operation

After NF16 identity becomes Green, the first live I5 proof must remain one-shot and bounded.

Preferred sequence:

```text
I5 fail-close
→ NCBI low-rate metadata connectivity canary
→ legal/rights preflight
→ one-shot bounded source acquisition
→ structured knowledge distillation
→ provenance/governance persistence
→ idempotent rerun
→ failure/retry proof
→ user-capacity regression check
→ only then unattended weekly scheduler decision
```

Scaled RAG remains off. ANN/HNSW/IVFFlat remain outside this authority and require the already-recorded evidence-based performance decision when KCE growth warrants it.

## 16. Rights fail-closed semantics

`RIGHTS_FAIL_CLOSED=YES` means Sedi must fail closed for the **specific action whose permission is not established**.

Examples:

- unknown raw-storage permission → do not retain raw full text;
- unknown redistribution permission → do not display/redistribute source expression;
- prohibited automated access route → do not use/bypass that route;
- lawful metadata route available → catalog metadata/provenance may continue;
- lawful processing route available but raw retention restricted → derived knowledge may continue while raw expression is discarded/minimized.

Do not incorrectly interpret `RIGHTS_FAIL_CLOSED` as “discard the source and learn nothing.”

## 17. Legal review and jurisdiction

This engineering authority is designed to reduce copyright, database-rights, contract, operational, and medical-safety risk; it is not a guarantee that no legal issue can arise in every jurisdiction.

Material new source families, unusual commercial restrictions, uncertain text/data-mining terms, or new jurisdictions may require human legal review. Such review should be source/risk-specific rather than a universal publisher-approval prerequisite.

## 18. Permanent invariants

```text
DIRECT_PUBLISHER_APPROVAL_UNIVERSAL_PREREQUISITE=NO
LAWFUL_AUTOMATED_ACCESS_REQUIRED=YES
DERIVED_KNOWLEDGE_DISTILLATION=YES
RAW_FULL_TEXT_RETENTION=LICENSE/RIGHTS_DEPENDENT
UNKNOWN_RAW_RETENTION_RIGHTS_DO_NOT_ERASE_SOURCE_FROM_EVIDENCE_UNIVERSE=YES
OFFICIAL_API_FEED_DATASET_FIRST=YES
PUBMED_BASELINE_UPDATES_PREFERRED_FOR_SCALE=YES
PMC_SYSTEMATIC_RETRIEVAL_OFFICIAL_MACHINE_ROUTES_ONLY=YES
OUTBOUND_EMAIL_TO_NCBI_REQUIRED_FOR_CURRENT_PHASE=NO
SEDI_NCBI_TOOL=sedi
SEDI_NCBI_EMAIL=info@sedi-ai.com
PAYWALL_BYPASS=NO
CAPTCHA_BYPASS=NO
ROBOTS_BYPASS=NO
RATE_LIMIT_EVASION=NO
IDENTITY_DECEPTION=NO
UNOBTRUSIVE_MEANS_LOW_NOISE_NOT_DECEPTIVE=YES
MEDICAL_GOVERNANCE_BYPASS=NO
PRODUCTION_RAG=NO_UNTIL_SEPARATELY_AUTHORIZED
ANN_REVIEW_REQUIRED_BEFORE_SCALED_RAG=YES
SEDI_V1_MINIMUM_TARGET_USERS=5000
```

## 19. Official-source verification basis

This authority was normalized against current official materials on 2026-08-13, including:

- NCBI E-utilities usage guidance: low request rates, batching, `tool`/`email`, and API-key rate behavior.
- NLM PubMed download documentation: annual baseline + daily updates and associated terms.
- PMC copyright / Article Dataset documentation: systematic retrieval through supported machine services and article-specific licence responsibility.
- U.S. Copyright Office guidance distinguishing facts/ideas/systems/methods from protected expression.

Future Gates must re-check source-specific current terms when material automation/retention behavior changes.

## 20. Continuity requirement

This document is a permanent authority addendum and must be cited/reconstructed by subsequent I5 Gates.

The next execution Gate must also append this decision to the Master Log and update the canonical Cursor handoff plus the independent ChatGPT/Dropbox continuity chain. If a later authority intentionally supersedes any rule here, it must name the superseded clause explicitly rather than silently drifting.

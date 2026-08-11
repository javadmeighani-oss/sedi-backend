# 08 — Evidence-Aware RAG / SCIS Contract (FROZEN)

```text
PURE_VECTOR_ONLY_RAG = NOT_ACCEPTABLE for high-risk clinical evidence
SCIS_01 = global hybrid substrate (already GREEN in CI)
I8_IS_RAG = NO (Section 39)
```

## Target pipeline

```text
user query
→ intent / disease / concept extraction
→ structured clinical filters
→ patient applicability filter
→ safety filter
→ freshness / current-version filter
→ structured SQL retrieval (studies/effects/recs/trials)
→ semantic/vector retrieval (SCIS KCE)
→ evidence-aware fusion / rerank (rerank still deferred-optional)
→ evidence bundle construction (labeled)
→ grounded synthesis
→ citations
→ uncertainty / safety wording
```

## Contract surfaces

| Producer | Consumer | Payload |
|---|---|---|
| I5 KU + evidence links + studies | SCIS indexer | eligible chunk text + structured metadata filters |
| I5 eligibility/retraction | SCIS retrieval | hard exclude |
| user_clinical_feature_index | applicability filter | features + lineage |
| SCIS evidence bundle | I8 / chat | GLOBAL_GOVERNED_KNOWLEDGE labeled items |
| I6/I7 (future) | fusion | personal/longitudinal — separate plane |

## Conflict / negative evidence

Support SUPPORTS/CONTRADICTS/REFUTES/INCONCLUSIVE; group conflicts by disease+population+intervention+comparator+outcome+time horizon.

## Living knowledge events

Reuse freshness/supersession; EXTEND for: new publication, guideline edition, correction, expression of concern, retraction, drug approval/safety change, trial status change, guideline supersession → eligibility + index invalidation.

## Connectors (design)

- ClinicalTrials.gov API v2 structured (primary)
- PubMed via NCBI E-utilities → metadata → DOI/PMCID → OA/rights resolution → authorized fulltext route (not HTML scrape primary)

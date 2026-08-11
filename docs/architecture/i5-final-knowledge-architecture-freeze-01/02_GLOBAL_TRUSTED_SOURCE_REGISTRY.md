# 02 — Global Trusted Source Registry (FROZEN)

```text
REGISTRY_NAME = Sedi Global Trusted Source Registry
STORAGE_STRATEGY = EXTEND GovernedSourceProfile (+ versioned registry overlay)
REGISTRY != AUTOMATIC AUTHORIZATION
DESIGN_ONLY YAML = design_only_yaml/trusted_source_registry_seed_v1.yaml
```

## Source families (registry candidates — not activated)

WHO, NICE, NHS, NIH/NLM, PubMed, PMC, LitArch OA, ClinicalTrials.gov, FDA/openFDA, CDC, NIMH, MedlinePlus, Cochrane, EAN, ECTRIMS, AAN, ADA, specialty societies, government guideline repos, systematic-review repos, peer-reviewed journals, open/commercial reference books, approved datasets.

## Required fields (logical; map to GSP columns or additive registry columns in future impl Gate)

```text
publisher_identity, authority_tier, source_family, source_type, specialty, knowledge_domains, jurisdiction, language
canonical_endpoint, api_endpoint, rss_atom_endpoint, sitemap, oai_pmh_endpoint, ftp_bulk_endpoint
supported_formats[]
rights_state, automation_state, tdm_state, storage_permission, transformation_permission, redistribution_permission, attribution_requirement
robots_access_state, rate_limits
freshness_policy, update_frequency
crawler_adapter_type
last_rights_review, last_source_verification, last_successful_retrieval, last_observed_change
registry_state, runtime_eligibility, human_review_state
```

## Preferred acquisition order

```text
official API → bulk/FTP → OAI-PMH → structured XML/JSON/RDF → RSS/Atom → sitemap → public HTML
```

## Research-backed primary routes (examples)

| Source | Primary route | Evidence |
|---|---|---|
| ClinicalTrials.gov | REST API v2 `https://clinicaltrials.gov/api/v2` | clinicaltrials.gov/data-api/api; NLM TB 2024 |
| PubMed / Entrez | NCBI E-utilities | ncbi.nlm.nih.gov/books/NBK25497 |
| Current V1 allowlist | PUBLIC_WEB_FETCH NHS/MedlinePlus/CDC/NIMH | multisource_activation_allowlist_v1.yaml |

HTML scraping is **fallback**, never primary for PubMed/CT.gov.

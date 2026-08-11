# 04 — Multi-Format Acquisition Design (FROZEN)

```text
DESIGN_ONLY = YES
EXTENDS = W3 adapters (PUBLIC_WEB_FETCH, OFFICIAL_API, RSS)
```

## Formats

| Format | Detection | Parser class (future) | OCR | Notes |
|---|---|---|---|---|
| HTML | MIME/content-type | HtmlAdapter (exists) | N | Injection scrub |
| PDF_TEXT | magic/%PDF + text layer | PdfTextAdapter | N | size/page caps |
| PDF_SCANNED | PDF without text | PdfOcrAdapter | Y | high cost; rights-gated |
| XML / JATS_XML / BITS_XML | schema/ns | XmlScientificAdapter | N | preferred for journals/books |
| JSON / REST_API | content-type | OfficialApiAdapter (exists) | N | CT.gov, openFDA |
| RSS / ATOM | feed | RssFeedAdapter (exists) | N | |
| OAI_PMH | protocol | OaiPmhAdapter | N | bulk metadata |
| CSV / TSV | mime/ext | TabularAdapter | N | datasets |
| RDF | mime | RdfAdapter | N | |
| EPUB | zip+opf | EpubAdapter | N | books |
| DOCX | zip+xml | DocxAdapter | N | |
| ZIP_DATASET | zip | ZipDatasetAdapter | N | zip-bomb limits |
| IMAGE / TABLE / SUPPLEMENTARY | mime | MediaMetaAdapter | optional | store locator+hash; extract governed |

## Common pipeline controls (all formats)

```text
detection → security/MIME validation → rights enforcement → parser
→ normalization → section/page locator → table/figure extract
→ checksum → version detection → error handling
→ max size / resource limits → malformed fail-closed
→ prompt-injection handling → no durable store unless rights allow
```

## Security fail-closed set

source impersonation, domain takeover, redirect abuse, malicious PDF/XML, MIME spoof, zip bombs, oversized artifacts, parser bombs, prompt injection in docs, hidden text, adversarial citations, duplicate poisoning, citation laundering, fabricated PMID/DOI/NCT, malformed encoding, SSRF, private-network redirects.

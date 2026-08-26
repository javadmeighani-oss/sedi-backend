"""CSV/TSV + DOCX adapters — bounded extraction, no macros/execution, converge to FetchEnvelope."""
from __future__ import annotations

import csv
import io
import zipfile
from typing import Optional, Sequence
from xml.etree import ElementTree as ET

from backend.app.schemas.i5_adapters import AdapterMetadata, FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CONTENT_BYTES,
    AdapterFrameworkError,
    FixtureTransport,
    SourceAdapter,
    assert_source_governance_allows_controlled_use,
    build_fetch_envelope,
)
from backend.app.services.i5.adapters.live_fetch import fetch_live_envelope
from backend.app.services.i5.adapters.live_transport import HttpGet

CSV_ADAPTER_ID = "i5.csv_tsv"
CSV_ADAPTER_VERSION = "fmt-resilience-v1"
DOCX_ADAPTER_ID = "i5.docx"
DOCX_ADAPTER_VERSION = "fmt-resilience-v1"

MAX_CSV_ROWS = 5_000
MAX_CSV_COLS = 64
MAX_CSV_FIELD_CHARS = 4_096
MAX_DOCX_UNCOMPRESSED = 2_097_152
MAX_DOCX_FILES = 64
MAX_DOCX_TEXT_CHARS = 500_000

_CSV_TYPES = frozenset(
    {
        "text/csv",
        "application/csv",
        "text/tab-separated-values",
        "text/plain",
        "application/octet-stream",
    }
)
_DOCX_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/zip",
    }
)


def extract_csv_tsv_text(body: bytes, *, delimiter: Optional[str] = None) -> str:
    """Bounded CSV/TSV → inert plain text. Formula-looking cells stay text (never executed)."""
    if len(body) > MAX_CONTENT_BYTES:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", str(len(body)))
    if b"\x00" in body[:8192]:
        raise AdapterFrameworkError("PARSING_FAILED", "BINARY_CSV")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("latin-1", errors="replace")
    sample = text[:4096]
    if delimiter is None:
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    lines: list[str] = []
    for i, row in enumerate(reader):
        if i >= MAX_CSV_ROWS:
            raise AdapterFrameworkError("CONTENT_TOO_LARGE", "CSV_ROWS")
        if len(row) > MAX_CSV_COLS:
            raise AdapterFrameworkError("CONTENT_TOO_LARGE", "CSV_COLS")
        cleaned = []
        for cell in row:
            if len(cell) > MAX_CSV_FIELD_CHARS:
                raise AdapterFrameworkError("CONTENT_TOO_LARGE", "CSV_FIELD")
            # Treat spreadsheet formulas as inert text
            cleaned.append(cell)
        lines.append(" | ".join(cleaned))
    joined = "\n".join(lines).strip()
    if len(joined) < 8:
        raise AdapterFrameworkError("EXTRACTION_FAILED", "CSV_TOO_SHORT")
    return joined


def _assert_ooxml_docx(body: bytes) -> zipfile.ZipFile:
    if not body.startswith(b"PK"):
        raise AdapterFrameworkError("INVALID_CONTENT_TYPE", "NOT_ZIP")
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise AdapterFrameworkError("PARSING_FAILED", "BAD_DOCX_ZIP") from exc
    names = zf.namelist()
    if len(names) > MAX_DOCX_FILES:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", "DOCX_FILE_COUNT")
    total = 0
    for info in zf.infolist():
        # Reject nested archives / suspicious paths
        name = info.filename.replace("\\", "/")
        if name.endswith((".exe", ".dll", ".bat", ".cmd", ".js", ".vbs", ".docm")):
            raise AdapterFrameworkError("UNSUPPORTED_FORMAT", "DOCX_EXECUTABLE")
        if ".." in name or name.startswith("/") or ".jar" in name.lower():
            raise AdapterFrameworkError("UNSUPPORTED_FORMAT", "DOCX_PATH")
        if name.lower().endswith(".zip") or name.lower().endswith(".docx"):
            raise AdapterFrameworkError("UNSUPPORTED_FORMAT", "NESTED_ARCHIVE")
        total += int(info.file_size)
        if total > MAX_DOCX_UNCOMPRESSED:
            raise AdapterFrameworkError("CONTENT_TOO_LARGE", "DOCX_UNCOMPRESSED")
        # Zip-bomb ratio guard
        if info.compress_size > 0 and info.file_size // max(info.compress_size, 1) > 100:
            raise AdapterFrameworkError("CONTENT_TOO_LARGE", "DOCX_ZIP_BOMB")
    if "[Content_Types].xml" not in names and not any(n.startswith("word/") for n in names):
        raise AdapterFrameworkError("PARSING_FAILED", "NOT_OOXML_DOCX")
    if "word/document.xml" not in names:
        raise AdapterFrameworkError("PARSING_FAILED", "MISSING_DOCUMENT_XML")
    # Macros / vba
    if any(n.startswith("word/vba") or n.endswith("vbaProject.bin") for n in names):
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", "DOCX_MACROS")
    return zf


def extract_docx_text(body: bytes) -> str:
    """Extract text only from word/document.xml; ignore macros/embeds."""
    if len(body) > MAX_CONTENT_BYTES:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", str(len(body)))
    zf = _assert_ooxml_docx(body)
    try:
        raw = zf.read("word/document.xml")
    except KeyError as exc:
        raise AdapterFrameworkError("PARSING_FAILED", "MISSING_DOCUMENT_XML") from exc
    if len(raw) > MAX_DOCX_UNCOMPRESSED:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", "DOCUMENT_XML")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise AdapterFrameworkError("PARSING_FAILED", "MALFORMED_DOCUMENT_XML") from exc
    # WordprocessingML text nodes: w:t
    parts: list[str] = []
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "t" and el.text:
            parts.append(el.text)
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"p", "br"}:
            parts.append("\n")
    text = "".join(parts)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) > MAX_DOCX_TEXT_CHARS:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", "DOCX_TEXT")
    if len(text) < 8:
        raise AdapterFrameworkError("EXTRACTION_FAILED", "DOCX_TOO_SHORT")
    return text


class CsvTsvAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=CSV_ADAPTER_ID,
            adapter_version=CSV_ADAPTER_VERSION,
            mode="CSV_TSV",
            capabilities=("FETCH", "EXTRACTION", "CONTENT_TYPES"),
        )

    def fetch_fixture(
        self,
        *,
        request_id: str,
        url: str,
        transport: FixtureTransport,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
    ) -> FetchEnvelope:
        assert_source_governance_allows_controlled_use(governance)
        resp = transport(url)
        ctype = (resp.content_type or "").split(";", 1)[0].strip().lower()
        body = resp.body or b""
        if ctype not in _CSV_TYPES and not (b"," in body[:512] or b"\t" in body[:512]):
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", ctype or "missing")
        env = build_fetch_envelope(
            request_id=request_id,
            adapter_id=CSV_ADAPTER_ID,
            adapter_version=CSV_ADAPTER_VERSION,
            url=url,
            response=resp,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )
        if env.error_category:
            return env
        extract_csv_tsv_text(env.body)
        return env

    def fetch_live(
        self,
        *,
        request_id: str,
        url: str,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        allowed_url_patterns: Optional[Sequence[str]] = None,
        trust_level: str = "official",
        review_required: bool = True,
        http_get: Optional[HttpGet] = None,
    ) -> FetchEnvelope:
        env = fetch_live_envelope(
            request_id=request_id,
            url=url,
            governance=governance,
            adapter_id=CSV_ADAPTER_ID,
            adapter_version=CSV_ADAPTER_VERSION,
            max_bytes=max_bytes,
            timeout=timeout,
            allowed_url_patterns=allowed_url_patterns,
            trust_level=trust_level,
            review_required=review_required,
            http_get=http_get,
        )
        if env.error_category:
            return env
        if env.content_type not in _CSV_TYPES and not (
            b"," in env.body[:512] or b"\t" in env.body[:512]
        ):
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", env.content_type)
        extract_csv_tsv_text(env.body)
        return env


class DocxAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=DOCX_ADAPTER_ID,
            adapter_version=DOCX_ADAPTER_VERSION,
            mode="DOCX",
            capabilities=("FETCH", "EXTRACTION", "CONTENT_TYPES", "ATTACHMENT_HANDLING"),
        )

    def fetch_fixture(
        self,
        *,
        request_id: str,
        url: str,
        transport: FixtureTransport,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
    ) -> FetchEnvelope:
        assert_source_governance_allows_controlled_use(governance)
        resp = transport(url)
        ctype = (resp.content_type or "").split(";", 1)[0].strip().lower()
        body = resp.body or b""
        if ctype not in _DOCX_TYPES and not body.startswith(b"PK"):
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", ctype or "missing")
        env = build_fetch_envelope(
            request_id=request_id,
            adapter_id=DOCX_ADAPTER_ID,
            adapter_version=DOCX_ADAPTER_VERSION,
            url=url,
            response=resp,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )
        if env.error_category:
            return env
        extract_docx_text(env.body)
        return env

    def fetch_live(
        self,
        *,
        request_id: str,
        url: str,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        allowed_url_patterns: Optional[Sequence[str]] = None,
        trust_level: str = "official",
        review_required: bool = True,
        http_get: Optional[HttpGet] = None,
    ) -> FetchEnvelope:
        env = fetch_live_envelope(
            request_id=request_id,
            url=url,
            governance=governance,
            adapter_id=DOCX_ADAPTER_ID,
            adapter_version=DOCX_ADAPTER_VERSION,
            max_bytes=max_bytes,
            timeout=timeout,
            allowed_url_patterns=allowed_url_patterns,
            trust_level=trust_level,
            review_required=review_required,
            http_get=http_get,
        )
        if env.error_category:
            return env
        if env.content_type not in _DOCX_TYPES and not env.body.startswith(b"PK"):
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", env.content_type)
        extract_docx_text(env.body)
        return env

"""Future format adapter contracts (KNOW-01 insertion points; not full parsers)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping

from backend.app.services.i5.adapters.base import AdapterFrameworkError

FUTURE_FORMATS = (
    "BITS_XML",
    "PDF_SCANNED",
    "OCR",
    "OAI_PMH",
    "RSS",
    "ATOM",
    "CSV",
    "TSV",
    "RDF",
    "EPUB",
    "DOCX",
    "ZIP_DATASET",
    "SUPPLEMENTARY_FILE",
    "IMAGE",
    "TABLE",
)


class FutureFormatAdapter(ABC):
    format_id: str

    @abstractmethod
    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        raise NotImplementedError


def _unsupported(format_id: str) -> None:
    raise AdapterFrameworkError("UNSUPPORTED_FORMAT", format_id)


class BitsXmlAdapterContract(FutureFormatAdapter):
    format_id = "BITS_XML"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class PdfScannedAdapterContract(FutureFormatAdapter):
    format_id = "PDF_SCANNED"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class OcrAdapterContract(FutureFormatAdapter):
    format_id = "OCR"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class OaiPmhAdapterContract(FutureFormatAdapter):
    format_id = "OAI_PMH"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class RssContract(FutureFormatAdapter):
    format_id = "RSS"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class AtomContract(FutureFormatAdapter):
    format_id = "ATOM"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class CsvAdapterContract(FutureFormatAdapter):
    format_id = "CSV"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class TsvAdapterContract(FutureFormatAdapter):
    format_id = "TSV"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class RdfAdapterContract(FutureFormatAdapter):
    format_id = "RDF"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class EpubAdapterContract(FutureFormatAdapter):
    format_id = "EPUB"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class DocxAdapterContract(FutureFormatAdapter):
    format_id = "DOCX"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class ZipDatasetAdapterContract(FutureFormatAdapter):
    format_id = "ZIP_DATASET"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class SupplementaryFileAdapterContract(FutureFormatAdapter):
    format_id = "SUPPLEMENTARY_FILE"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class ImageAdapterContract(FutureFormatAdapter):
    format_id = "IMAGE"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


class TableAdapterContract(FutureFormatAdapter):
    format_id = "TABLE"

    def extract(self, body: bytes, *, meta: Mapping[str, str] | None = None) -> str:
        _unsupported(self.format_id)
        return ""


FUTURE_ADAPTER_CONTRACTS: Mapping[str, FutureFormatAdapter] = {
    c.format_id: c
    for c in (
        BitsXmlAdapterContract(),
        PdfScannedAdapterContract(),
        OcrAdapterContract(),
        OaiPmhAdapterContract(),
        RssContract(),
        AtomContract(),
        CsvAdapterContract(),
        TsvAdapterContract(),
        RdfAdapterContract(),
        EpubAdapterContract(),
        DocxAdapterContract(),
        ZipDatasetAdapterContract(),
        SupplementaryFileAdapterContract(),
        ImageAdapterContract(),
        TableAdapterContract(),
    )
}

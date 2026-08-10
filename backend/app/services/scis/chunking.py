"""KU + section-aware chunking (deterministic identity/hash)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from backend.app.services.scis import CHUNKER_VERSION

_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Za-z0-9 /-]{2,80}:)\s*$")
_WARN_RE = re.compile(
    r"(?i)^(contraindication|warning|caution|important|توجه|هشدار|تحذير)\b"
)


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    text: str
    section_path: str
    chunk_hash: str
    chunk_identity: str
    chunker_version: str
    language: str
    knowledge_unit_id: Optional[int]
    immutable_version_id: Optional[str]
    is_atomic_warning: bool = False


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_sections(text: str) -> List[tuple[str, str]]:
    """Return list of (section_path, body)."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    sections: List[tuple[str, list[str]]] = []
    current_path = "root"
    buf: list[str] = []
    for line in lines:
        if _HEADING_RE.match(line.strip()) and buf:
            sections.append((current_path, buf))
            buf = []
            current_path = line.strip().lstrip("#").strip().rstrip(":")
            continue
        if _HEADING_RE.match(line.strip()) and not buf:
            current_path = line.strip().lstrip("#").strip().rstrip(":")
            continue
        buf.append(line)
    if buf or not sections:
        sections.append((current_path, buf))
    out: List[tuple[str, str]] = []
    for path, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if body:
            out.append((path, body))
    return out or [("root", (text or "").strip())]


def _atomic_blocks(section_path: str, body: str) -> List[tuple[str, str, bool]]:
    """Keep warning/contraindication paragraphs atomic."""
    section_atomic = bool(
        _WARN_RE.match(section_path) or re.search(r"(?i)contraindication|warning|caution|هشدار|تحذير", section_path)
    )
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paras:
        return [(section_path, body, section_atomic)] if body.strip() else []
    blocks: List[tuple[str, str, bool]] = []
    for i, para in enumerate(paras):
        atomic = section_atomic or bool(_WARN_RE.match(para))
        path = f"{section_path}/warn-{i}" if atomic else f"{section_path}/p-{i}"
        blocks.append((path, para, atomic))
    return blocks


def chunk_knowledge_text(
    *,
    text: str,
    language: str = "en",
    knowledge_unit_id: Optional[int] = None,
    immutable_version_id: Optional[str] = None,
    canonical_unit_id: Optional[str] = None,
    max_chars: int = 1200,
) -> List[ChunkDraft]:
    """Deterministic KU/section-aware chunker.

    Short texts → single chunk. Long texts → section + paragraph blocks,
    splitting oversized non-atomic blocks by sentence-ish boundaries.
    """
    text = (text or "").strip()
    if not text:
        return []

    drafts: List[ChunkDraft] = []
    idx = 0
    for section_path, body in _split_sections(text):
        for path, block, atomic in _atomic_blocks(section_path, body):
            pieces = [block]
            if not atomic and len(block) > max_chars:
                pieces = _split_oversized(block, max_chars)
            for piece in pieces:
                chash = _sha256(
                    f"{CHUNKER_VERSION}|{canonical_unit_id or ''}|{immutable_version_id or ''}|"
                    f"{knowledge_unit_id or ''}|{path}|{piece}"
                )
                identity = _sha256(
                    f"{canonical_unit_id or knowledge_unit_id or 'ku'}|{immutable_version_id or 'v'}|{path}|{chash}"
                )
                drafts.append(
                    ChunkDraft(
                        chunk_index=idx,
                        text=piece,
                        section_path=path,
                        chunk_hash=chash,
                        chunk_identity=identity,
                        chunker_version=CHUNKER_VERSION,
                        language=language,
                        knowledge_unit_id=knowledge_unit_id,
                        immutable_version_id=immutable_version_id,
                        is_atomic_warning=atomic,
                    )
                )
                idx += 1
    return drafts


def _split_oversized(text: str, max_chars: int) -> List[str]:
    # Prefer sentence boundaries; fall back to hard wrap.
    parts = re.split(r"(?<=[.!?۔؟])\s+", text)
    out: List[str] = []
    buf = ""
    for part in parts:
        if not part:
            continue
        if len(buf) + len(part) + 1 <= max_chars:
            buf = f"{buf} {part}".strip()
        else:
            if buf:
                out.append(buf)
            if len(part) <= max_chars:
                buf = part
            else:
                for i in range(0, len(part), max_chars):
                    out.append(part[i : i + max_chars])
                buf = ""
    if buf:
        out.append(buf)
    return out or [text[:max_chars]]


def chunk_knowledge_unit(ku: object) -> List[ChunkDraft]:
    """Chunk from a KnowledgeUnit-like object."""
    statement = getattr(ku, "normalized_statement", "") or ""
    applicability = getattr(ku, "applicability", None) or ""
    exclusions = getattr(ku, "exclusions", None) or ""
    parts: List[str] = [statement]
    if applicability:
        parts.append(f"Applicability:\n{applicability}")
    if exclusions:
        parts.append(f"Contraindication:\n{exclusions}")
    text = "\n\n".join(parts)
    return chunk_knowledge_text(
        text=text,
        language=getattr(ku, "language", "en") or "en",
        knowledge_unit_id=getattr(ku, "id", None),
        immutable_version_id=getattr(ku, "immutable_version_id", None),
        canonical_unit_id=getattr(ku, "canonical_unit_id", None),
    )

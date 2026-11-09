"""R-082 phase 1 - page rights detector for the weekly crawler (what may Sedi do with THIS page?).

R-045 said "open licences only"; R-082a (Javad, 2026-11-08) widens it: copyrighted pages of approved IRANIAN sites may be
fetched and indexed, never served in full. This module reads the signals a page itself gives and returns a verdict in the
vocabulary of ``BookRightsClass`` (KNOW-01), plus how the content may be served:

- OPEN_AUTOMATION_ALLOWED  CC BY / CC0 / Open Government Licence      -> serve_mode ``passage``
- PUBLIC_DOMAIN            public-domain notice                          -> ``passage``
- OWNER_RIGHTS_INDEX_ONLY  all rights reserved on an approved Iranian host (R-082a) -> ``short_attributed_passage``
- OPEN_LICENSE_RESTRICTED  CC BY-SA (needs a decision), NC, ND         -> blocked
- FULLTEXT_TDM_PROHIBITED  explicit text-and-data-mining / AI reservation -> blocked (the stricter signal always wins)
- ALL_RIGHTS_RESERVED      reserved page on a non-approved host           -> blocked
- UNKNOWN_RIGHTS           the page says nothing -> allowed ONLY when ``strict`` is False (the source's manifest licence
  then stands), blocked when ``strict`` (new / non-manifest sources).

Deterministic, no I/O, fail-open at the call site. Enforcement is behind ``SEDI_I5_PAGE_RIGHTS_ENFORCE`` (default OFF = shadow:
the verdict is logged, nothing changes) so production can first measure what WOULD be blocked.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ENFORCE_ENV = "SEDI_I5_PAGE_RIGHTS_ENFORCE"
MAX_SCAN_BYTES = 400_000

OPEN_AUTOMATION_ALLOWED = "OPEN_AUTOMATION_ALLOWED"
PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
OWNER_RIGHTS_INDEX_ONLY = "OWNER_RIGHTS_INDEX_ONLY"
OPEN_LICENSE_RESTRICTED = "OPEN_LICENSE_RESTRICTED"
FULLTEXT_TDM_PROHIBITED = "FULLTEXT_TDM_PROHIBITED"
ALL_RIGHTS_RESERVED = "ALL_RIGHTS_RESERVED"
UNKNOWN_RIGHTS = "UNKNOWN_RIGHTS"

# R-082a: approved Iranian hosts whose copyrighted pages may be indexed (short attributed passages only).
IRANIAN_INDEX_SUFFIXES: tuple[str, ...] = (".ac.ir", ".gov.ir", ".sch.ir")
IRANIAN_INDEX_HOSTS: tuple[str, ...] = ("irimc.org", "behdasht.gov.ir", "fda.gov.ir", "salamat.gov.ir")

_CC_URL = re.compile(r"creativecommons\.org/(licenses|licences)/(by(?:-(?:nc|nd|sa))*)(?:/|\b)")
_CC_PD_URL = re.compile(r"creativecommons\.org/publicdomain/(zero|mark)")
_NC = re.compile(r"non-?commercial|\bby-nc\b|cc[- ]by-nc")
_ND = re.compile(r"no[- ]?derivs|no derivatives|\bby-nd\b|cc[- ]by-nd|noderiv")
_SA_TEXT = re.compile(r"attribution[- ]?share ?alike|\bcc[- ]by-sa\b")
# Permissive signals count only when the PAGE declares them (Codex P2): a link to a CC resource or a page ABOUT licences is not
# the page's own licence. Restrictive signals (NC / ND / SA / TDM) count wherever they appear: the stricter signal always wins.
_DECL = re.compile(r"(?:licen[cs]ed|released|published|available|distributed)\s+(?:freely\s+)?under|licen[cs]e\s*:")
_REL_LICENSE_TAG = re.compile(r"<(?:a|link)\b[^>]*\brel\s*=\s*[\"'][^\"']*\blicen[cs]e\b[^\"']*[\"'][^>]*>")
_BY_CORE = re.compile(r"creative commons attribution(?! ?-? ?(?:non|share|no))|\bcc[- ]by(?:[- ]4\.0|[- ]3\.0|[- ]2\.0)?\b(?![- ]?(?:nc|nd|sa))")
_BY_VERSIONED = re.compile(r"\bcc[- ]by[- ]\d\.\d\b(?![- ]?(?:nc|nd|sa))")  # a versioned label ("CC BY 4.0") is a declaration on its own
_OGL_CORE = re.compile(r"open[- ]government[- ]licen[cs]e|nationalarchives\.gov\.uk/doc/open-government-licence")
_PD_CORE = re.compile(r"\bcc0\b|public domain")
_PD_STATEMENT = re.compile(r"(?:is|are|was|were)\s+in the public domain|released into the public domain|dedicated to the public domain|works? of the united states government")
_META_TAG = re.compile(r"<meta\b[^>]*>")
_TDM_TEXT = re.compile(r"text and data mining[^.<]{0,80}(?:prohibit|not permitted|reserved|forbidden)|(?:prohibit|not permitted|reserved|forbidden)[^.<]{0,80}text and data mining|tdmrep")
_RESERVED = re.compile(r"all rights reserved|کلیه حقوق|تمامی حقوق|حقوق این (?:سایت|وب ?سایت|اثر) محفوظ|حقوق محفوظ")
_COPYRIGHT_MARK = re.compile(r"©|&copy;|\bcopyright\b|کپی ?رایت")  # a bare notice claims copyright but does not reserve everything


@dataclass(frozen=True)
class RightsVerdict:
    rights_class: str
    allowed: bool
    serve_mode: str  # "passage" | "short_attributed_passage" | "none"
    reason: str
    signals: tuple[str, ...] = ()

    def as_log(self, url: str) -> dict[str, Any]:
        host = (urlparse(url).hostname or "").lower()
        return {"host": host, "class": self.rights_class, "allowed": self.allowed, "mode": self.serve_mode, "signals": list(self.signals)}


def enforce_enabled() -> bool:
    return os.getenv(ENFORCE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def is_iranian_index_host(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    if not host:
        return False
    return any(host.endswith(s) for s in IRANIAN_INDEX_SUFFIXES) or any(host == h or host.endswith("." + h) for h in IRANIAN_INDEX_HOSTS)


def _text(body: Any, charset: str = "utf-8") -> str:
    if isinstance(body, bytes):
        return body[:MAX_SCAN_BYTES].decode(charset or "utf-8", errors="replace").lower()
    return str(body or "")[:MAX_SCAN_BYTES].lower()


def _attr(tag: str, name: str) -> str:
    m = re.search(r"\b" + re.escape(name) + r"\s*=\s*[\"']([^\"']*)[\"']", tag)
    return m.group(1).strip() if m else ""


def _tdm_meta(s: str) -> bool:
    """TDM / AI reservation in a meta tag, whatever the attribute order (Codex P2)."""
    for tag in _META_TAG.findall(s):
        name, content = _attr(tag, "name"), _attr(tag, "content")
        if name == "tdm-reservation" and content == "1":
            return True
        if name == "robots" and re.search(r"noai|noimageai", content):
            return True
    return False


def _meta_license_text(s: str) -> str:
    out = []
    for tag in _META_TAG.findall(s):
        if _attr(tag, "name") in {"license", "licence", "dc.rights", "dcterms.license", "dc.license"}:
            out.append(_attr(tag, "content"))
    return " ".join(out)


def _declared(s: str, core: "re.Pattern") -> bool:
    """The page DECLARES the licence: a declaration phrase ("licensed under ...", "License: ...") followed by it."""
    return any(core.search(s[m.end(): m.end() + 220]) for m in _DECL.finditer(s))


def classify_page_rights(body: Any, url: str = "", *, strict: bool = False, charset: str = "utf-8") -> RightsVerdict:
    """Read the page's own rights signals. The stricter signal always wins; see the module docstring."""
    s = _text(body, charset)
    signals: list[str] = []
    cc_kinds = {m.group(2) for m in _CC_URL.finditer(s)}  # anywhere on the page: only used for the STRICT checks
    declared = " ".join(_REL_LICENSE_TAG.findall(s)) + " " + _meta_license_text(s)
    declared_kinds = {m.group(2) for m in _CC_URL.finditer(declared)}
    nc = bool(_NC.search(s)) or any("nc" in k.split("-") for k in cc_kinds)
    nd = bool(_ND.search(s)) or any("nd" in k.split("-") for k in cc_kinds)
    sa = bool(_SA_TEXT.search(s)) or any("sa" in k.split("-") for k in cc_kinds)
    by = ("by" in declared_kinds) or _declared(s, _BY_CORE) or bool(_BY_VERSIONED.search(s))
    ogl = bool(_OGL_CORE.search(declared)) or _declared(s, _OGL_CORE)
    pd = bool(_CC_PD_URL.search(declared)) or bool(_PD_STATEMENT.search(s)) or _declared(s, _PD_CORE)
    tdm = _tdm_meta(s) or bool(_TDM_TEXT.search(s))
    reserved = bool(_RESERVED.search(s))
    notice = bool(_COPYRIGHT_MARK.search(s))
    for name, on in (("copyright_notice", notice),("tdm_reservation", tdm), ("nc", nc), ("nd", nd), ("sa", sa), ("cc_by", by), ("ogl", ogl), ("public_domain", pd), ("reserved", reserved)):
        if on:
            signals.append(name)
    sig = tuple(signals)

    if tdm:
        return RightsVerdict(FULLTEXT_TDM_PROHIBITED, False, "none", "text-and-data-mining / AI reservation on the page", sig)
    if nc or nd:
        return RightsVerdict(OPEN_LICENSE_RESTRICTED, False, "none", "non-commercial or no-derivatives licence", sig)
    if sa and not (ogl or pd):
        return RightsVerdict(OPEN_LICENSE_RESTRICTED, False, "none", "share-alike licence needs a decision", sig)
    if by or ogl:
        return RightsVerdict(OPEN_AUTOMATION_ALLOWED, True, "passage", "open licence (CC BY / OGL)", sig)
    if pd:
        return RightsVerdict(PUBLIC_DOMAIN, True, "passage", "public-domain notice", sig)
    if reserved or (notice and is_iranian_index_host(url)):
        if is_iranian_index_host(url):
            return RightsVerdict(OWNER_RIGHTS_INDEX_ONLY, True, "short_attributed_passage", "approved Iranian host, rights reserved (R-082a)", sig)
        return RightsVerdict(ALL_RIGHTS_RESERVED, False, "none", "rights reserved on a non-approved host", sig)
    if strict:
        return RightsVerdict(UNKNOWN_RIGHTS, False, "none", "no rights signal and strict mode", sig)
    return RightsVerdict(UNKNOWN_RIGHTS, True, "passage", "no rights signal; the source's manifest licence stands", sig)


def apply_page_rights_gate(envelope: Any, *, url: str, strict: bool = False) -> Optional[RightsVerdict]:
    """Call site for the fetch adapters. Shadow by default (log only); with the flag ON a blocked page raises.

    Fail-open: any problem in the detector itself never stops the weekly run."""
    try:
        body = getattr(envelope, "body", b"") or b""
        if not body:
            return None
        verdict = classify_page_rights(body, url, strict=strict, charset=getattr(envelope, "charset", "utf-8") or "utf-8")
    except Exception:  # noqa: BLE001
        return None
    logger.info("i5_page_rights enforce=%s %s", enforce_enabled(), verdict.as_log(url))
    if enforce_enabled() and not verdict.allowed:
        from backend.app.services.i5.adapters.base import AdapterFrameworkError

        raise AdapterFrameworkError("REVIEW_REQUIRED", f"RIGHTS_BLOCKED:{verdict.rights_class}:{verdict.reason}")
    return verdict

# backend.app.services.notification_runtime.i18n_resolver
"""
Multi-language notification text resolution.

Resolves a multilingual texts dict to a single {title, message, ...} dict
using user language with prefix matching and fallback order:
  user_language (exact/prefix) -> default -> "fa" -> "en" -> first available.
"""

from typing import Any, Dict, Optional


def _is_flat_content(texts: Dict[str, Any]) -> bool:
    """True if texts looks like a single locale block: {title, message} with string values."""
    if not texts or not isinstance(texts, dict):
        return False
    # If any value is a dict (nested block), it's multilingual
    for v in texts.values():
        if isinstance(v, dict):
            return False
    return True


def _lang_prefix(locale: str) -> str:
    """Return language prefix: 'fa-IR' -> 'fa', 'en' -> 'en'."""
    if not locale:
        return ""
    return locale.split("-")[0].split("_")[0].lower()


def _pick_lang_key(
    texts: Dict[str, Any],
    user_language: Optional[str],
    default: str,
) -> Optional[str]:
    """
    Pick best language key from texts.
    Order: exact match -> prefix match (user_lang) -> default -> 'fa' -> 'en' -> first key.
    """
    if not texts or not isinstance(texts, dict):
        return None
    keys = list(texts.keys())
    if not keys:
        return None
    # Only consider keys whose value looks like a content block (dict with string values)
    lang_keys = [k for k in keys if isinstance(texts.get(k), dict)]
    if not lang_keys:
        return None

    user_lang = (user_language or "").strip().lower()
    user_prefix = _lang_prefix(user_lang) if user_lang else ""

    # 1) Exact match
    if user_lang and user_lang in lang_keys:
        return user_lang
    # 2) Prefix match: e.g. user_language "fa-IR" -> prefer key starting with "fa"
    if user_prefix:
        for k in lang_keys:
            if _lang_prefix(k) == user_prefix:
                return k
    # 3) Default
    if default and default in lang_keys:
        return default
    # 4) "fa" then "en"
    for preferred in ("fa", "en"):
        for k in lang_keys:
            if _lang_prefix(k) == preferred:
                return k
    # 5) First available
    return lang_keys[0]


def resolve_text_by_user_language(
    texts: Optional[Dict[str, Any]],
    user_language: Optional[str] = None,
    default: str = "fa",
) -> Dict[str, str]:
    """
    Resolve multilingual notification texts to a single locale block.

    Args:
        texts: Either:
            - None -> return {}
            - Flat dict {"title": "...", "message": "..."} -> return as-is (pass-through)
            - Multilingual {"fa": {"title": "...", "message": "..."}, "en": {...}}
              Keys may be "fa", "fa-IR", "en-US"; matched by prefix (fa*, en*) then fallback.
        user_language: User locale, e.g. "fa", "fa-IR", "en", "en-US".
        default: Default language when user_language is None or no match ("fa").

    Returns:
        Dict with at least "title" and "message" (or "body") when possible.
        Extra keys from the chosen block are passed through.
        Empty dict on invalid/empty input.
    """
    if texts is None:
        return {}
    if not isinstance(texts, dict):
        return {}

    # Flat structure: only accept str values; otherwise return {}
    if _is_flat_content(texts):
        out: Dict[str, str] = {}
        for k, v in texts.items():
            if isinstance(k, str) and isinstance(v, str) and (v or "").strip():
                out[k] = v
        return out if out else {}

    # Multilingual: pick one block; strict: only str values, else return {}
    lang_key = _pick_lang_key(texts, user_language, default)
    if lang_key is None:
        return {}
    block = texts.get(lang_key)
    if not isinstance(block, dict):
        return {}
    result: Dict[str, str] = {}
    for k, v in block.items():
        if isinstance(k, str) and isinstance(v, str) and (v or "").strip():
            result[k] = v
    if not result:
        return {}
    # Ensure "message" for contract: use "message" or "body" from block
    if "message" not in result and "body" in result:
        result["message"] = result["body"]
    elif "body" not in result and "message" in result:
        result["body"] = result["message"]
    return result

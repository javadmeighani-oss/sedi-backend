"""Device credential verification abstraction (transport-neutral)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

from backend.app import models
from backend.app.core.device_token_crypto import hash_device_token


class CredentialStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUSPENDED = "suspended"
    INVALID = "invalid"


@dataclass(frozen=True)
class CredentialVerificationResult:
    verified: bool
    status: CredentialStatus
    credential_identity: Optional[str]
    credential_kind: Optional[str]
    reject_reason: Optional[str] = None


class DeviceCredentialVerifier(Protocol):
    def verify(self, device: models.Device, presented_proof: str) -> CredentialVerificationResult:
        ...


def credential_fingerprint_from_hash(token_hash: str) -> str:
    """Stable per-credential identity fingerprint (non-reversible)."""
    return hashlib.sha256(f"fp:{token_hash}".encode("utf-8")).hexdigest()[:16]


def is_pin_or_setup_code_proof(presented_proof: str) -> bool:
    """PIN/QR/setup codes are never runtime packet authentication."""
    normalized = (presented_proof or "").strip().lower()
    if not normalized:
        return False
    if normalized.startswith("pin:") or normalized.startswith("setup:") or normalized.startswith("qr:"):
        return True
    # Short numeric-only codes are treated as setup/PIN, not device credentials.
    if normalized.isdigit() and len(normalized) <= 8:
        return True
    return False


class PerDeviceSymmetricCredentialVerifier:
    """Per-device high-entropy symmetric credential via token_hash."""

    def verify(self, device: models.Device, presented_proof: str) -> CredentialVerificationResult:
        proof = (presented_proof or "").strip()
        if not proof:
            return CredentialVerificationResult(
                verified=False,
                status=CredentialStatus.INVALID,
                credential_identity=device.credential_fingerprint,
                credential_kind=device.credential_kind,
                reject_reason="MISSING_PROOF",
            )
        if is_pin_or_setup_code_proof(proof):
            return CredentialVerificationResult(
                verified=False,
                status=CredentialStatus.INVALID,
                credential_identity=device.credential_fingerprint,
                credential_kind=device.credential_kind,
                reject_reason="PIN_NOT_RUNTIME_AUTH",
            )
        if device.claim_lifecycle_status == "suspended":
            return CredentialVerificationResult(
                verified=False,
                status=CredentialStatus.SUSPENDED,
                credential_identity=device.credential_fingerprint,
                credential_kind=device.credential_kind,
                reject_reason="DEVICE_SUSPENDED",
            )
        if device.status == "revoked" or device.claim_lifecycle_status == "revoked":
            return CredentialVerificationResult(
                verified=False,
                status=CredentialStatus.REVOKED,
                credential_identity=device.credential_fingerprint,
                credential_kind=device.credential_kind,
                reject_reason="DEVICE_REVOKED",
            )
        if hash_device_token(proof) != device.token_hash:
            return CredentialVerificationResult(
                verified=False,
                status=CredentialStatus.INVALID,
                credential_identity=device.credential_fingerprint,
                credential_kind=device.credential_kind,
                reject_reason="CREDENTIAL_MISMATCH",
            )
        return CredentialVerificationResult(
            verified=True,
            status=CredentialStatus.ACTIVE,
            credential_identity=device.credential_fingerprint or credential_fingerprint_from_hash(device.token_hash),
            credential_kind=device.credential_kind,
        )


_default_verifier = PerDeviceSymmetricCredentialVerifier()


def get_device_credential_verifier() -> DeviceCredentialVerifier:
    return _default_verifier

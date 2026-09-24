from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

from .exceptions import BiometricProcessingError


def _fernet() -> MultiFernet:
    configured = [
        value.strip()
        for value in str(settings.BIOMETRIC_TEMPLATE_KEYS).split(",")
        if value.strip()
    ]
    if not configured:
        # Development-compatible encrypted storage. Production deployments
        # should provide an independent key so rotating SECRET_KEY does not
        # invalidate templates and a settings leak does not expose both keys.
        digest = hashlib.sha256(
            f"biometric-template:{settings.SECRET_KEY}".encode("utf-8")
        ).digest()
        configured = [base64.urlsafe_b64encode(digest).decode("ascii")]
    try:
        return MultiFernet([Fernet(value.encode("ascii")) for value in configured])
    except (TypeError, ValueError) as exc:
        raise BiometricProcessingError(
            "BIOMETRIC_TEMPLATE_KEYS contains an invalid Fernet key."
        ) from exc


def encrypt_template(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _fernet().encrypt(serialized).decode("ascii")


def decrypt_template(token: str) -> Any:
    if not token:
        raise BiometricProcessingError("The enrolled biometric template is missing.")
    try:
        serialized = _fernet().decrypt(token.encode("ascii"))
        return json.loads(serialized.decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BiometricProcessingError(
            "The enrolled biometric template could not be decrypted."
        ) from exc

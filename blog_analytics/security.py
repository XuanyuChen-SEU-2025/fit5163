from __future__ import annotations

import hmac
import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from flask import session


class EncryptionService:
    def __init__(self, key_file: str) -> None:
        key_path = Path(key_file)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if not key_path.exists():
            key_path.write_bytes(Fernet.generate_key())
        self._fernet = Fernet(key_path.read_bytes())

    def encrypt_text(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt_text(self, token: str) -> str:
        if not token:
            return ""
        return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")

    def encrypt_json(self, payload: dict) -> str:
        return self.encrypt_text(json.dumps(payload, ensure_ascii=False))

    def decrypt_json(self, token: str) -> dict:
        if not token:
            return {}
        return json.loads(self.decrypt_text(token))


def get_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        session["_csrf_token"] = token
    return token


def validate_csrf_token(token: str | None) -> bool:
    expected = session.get("_csrf_token", "")
    provided = token or ""
    return bool(expected) and hmac.compare_digest(expected, provided)

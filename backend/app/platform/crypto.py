from __future__ import annotations

import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _key() -> bytes:
    return hashlib.sha256(("nexus-private-state:" + settings.core_api_secret_key).encode()).digest()


def encrypt_json(payload: dict, *, aad: str) -> bytes:
    nonce = os.urandom(12)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext, aad.encode())


def decrypt_json(ciphertext: bytes, *, aad: str) -> dict:
    nonce, body = ciphertext[:12], ciphertext[12:]
    return json.loads(AESGCM(_key()).decrypt(nonce, body, aad.encode()))

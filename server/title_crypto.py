"""Authenticated encryption for foreground window titles."""

from __future__ import annotations

import os
from dataclasses import dataclass


class TitleEncryptionError(RuntimeError):
    """Raised when a title encryption key cannot be prepared."""


@dataclass(frozen=True)
class EncryptedTitle:
    ciphertext: bytes
    nonce: bytes


class TitleCipher:
    """Derive an AES-256-GCM key from an AYON Secret passphrase."""

    def __init__(self, passphrase: str, salt: bytes, key_name: str) -> None:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        except ImportError as exc:
            raise TitleEncryptionError(
                "AYON Server does not provide its required cryptography runtime"
            ) from exc
        if not passphrase:
            raise TitleEncryptionError("The selected AYON Secret is empty")
        if len(salt) < 16:
            raise TitleEncryptionError("The title encryption salt is invalid")
        key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(
            passphrase.encode("utf-8")
        )
        self._cipher = AESGCM(key)
        self._associated_data = key_name.encode("utf-8")

    def encrypt(self, title: str) -> EncryptedTitle:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(
            nonce, title.encode("utf-8"), self._associated_data
        )
        return EncryptedTitle(ciphertext=ciphertext, nonce=nonce)

    def decrypt(self, ciphertext: bytes, nonce: bytes) -> str:
        plaintext = self._cipher.decrypt(nonce, ciphertext, self._associated_data)
        return plaintext.decode("utf-8")

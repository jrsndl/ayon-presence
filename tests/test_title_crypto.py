from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


pytest.importorskip("cryptography")
SPEC = spec_from_file_location("presence_title_crypto", Path("server/title_crypto.py"))
title_crypto = module_from_spec(SPEC)
sys.modules[SPEC.name] = title_crypto
assert SPEC.loader is not None
SPEC.loader.exec_module(title_crypto)


def test_title_cipher_round_trip_and_random_nonce():
    cipher = title_crypto.TitleCipher(
        "five comfortable studio words", b"s" * 16, "key-v1"
    )
    first = cipher.encrypt("Browser tab title")
    second = cipher.encrypt("Browser tab title")

    assert first.ciphertext != second.ciphertext
    assert first.nonce != second.nonce
    assert cipher.decrypt(first.ciphertext, first.nonce) == "Browser tab title"


def test_title_cipher_rejects_tampering():
    cipher = title_crypto.TitleCipher(
        "five comfortable studio words", b"s" * 16, "key-v1"
    )
    encrypted = cipher.encrypt("Sensitive title")

    with pytest.raises(Exception):
        cipher.decrypt(encrypted.ciphertext[:-1] + b"x", encrypted.nonce)

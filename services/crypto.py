"""Fernet encryption helpers for face embeddings."""

from cryptography.fernet import Fernet
from config import FERNET_KEY_FILE


def _load_or_create_key() -> bytes:
    if FERNET_KEY_FILE.exists():
        return FERNET_KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    FERNET_KEY_FILE.write_bytes(key)
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt_embedding(raw_bytes: bytes) -> bytes:
    return _fernet.encrypt(raw_bytes)


def decrypt_embedding(enc_bytes: bytes) -> bytes:
    return _fernet.decrypt(enc_bytes)

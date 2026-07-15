"""Encrypted API-key storage using Windows DPAPI.

Keys are encrypted at rest with CryptProtectData (tied to the current Windows
user) and stored as base64 in the settings table - never plaintext, never in
config files. ctypes calls into crypt32 directly so this needs no extra
dependency and works in a frozen build.
"""

import base64
import ctypes
from ctypes import wintypes

from ..memory.repository import Repository

_KEY_PREFIX = "apikey:"  # settings key namespace, e.g. apikey:openai


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _blob_bytes(blob: _DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _dpapi_encrypt(plaintext: str) -> bytes:
    out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(_blob(plaintext.encode("utf-8"))),
        "Corvus API key", None, None, None, 0, ctypes.byref(out)
    ):
        raise OSError("CryptProtectData failed")
    try:
        return _blob_bytes(out)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _dpapi_decrypt(ciphertext: bytes) -> str:
    out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(_blob(ciphertext)), None, None, None, None, 0, ctypes.byref(out)
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return _blob_bytes(out).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class KeyVault:
    """Per-provider API keys, encrypted at rest via DPAPI."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def set_key(self, provider: str, key: str) -> None:
        if not key:
            self.clear_key(provider)
            return
        encrypted = base64.b64encode(_dpapi_encrypt(key)).decode("ascii")
        self.repo.set_setting(_KEY_PREFIX + provider, encrypted)

    def get_key(self, provider: str) -> str | None:
        stored = self.repo.get_setting(_KEY_PREFIX + provider)
        if not stored:
            return None
        try:
            return _dpapi_decrypt(base64.b64decode(stored))
        except Exception:
            return None

    def has_key(self, provider: str) -> bool:
        return self.repo.get_setting(_KEY_PREFIX + provider) is not None

    def clear_key(self, provider: str) -> None:
        # Overwrite with empty then leave a tombstone-free state.
        self.repo.set_setting(_KEY_PREFIX + provider, "")
        self.repo.set_setting(_KEY_PREFIX + provider, "")
        self.repo.conn.execute("DELETE FROM settings WHERE key = ?", (_KEY_PREFIX + provider,))
        self.repo.conn.commit()

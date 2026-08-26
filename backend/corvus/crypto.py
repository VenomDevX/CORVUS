"""Application-level encryption for sensitive database fields."""

import ctypes
from ctypes import wintypes
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

from .config import data_dir

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _encrypt_dpapi(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.c_char_p(data), ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    
    if crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    raise Exception("CryptProtectData failed")


def _decrypt_dpapi(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.c_char_p(data), ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    
    if crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    raise Exception("CryptUnprotectData failed")


def _get_fernet() -> Fernet:
    key_path = data_dir() / "corvus_key.bin"
    if key_path.exists():
        encrypted_key = key_path.read_bytes()
        try:
            key = _decrypt_dpapi(encrypted_key)
            return Fernet(key)
        except Exception:
            # If decryption fails (e.g., moved to a new PC without the profile), 
            # we must generate a new key and they will lose encrypted data.
            # In a real app we'd want to handle this gracefully, but for now we regenerate.
            pass

    # Generate new key
    key = Fernet.generate_key()
    encrypted_key = _encrypt_dpapi(key)
    key_path.write_bytes(encrypted_key)
    return Fernet(key)


_fernet_instance = None

def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        _fernet_instance = _get_fernet()
    return _fernet_instance


def encrypt(text: str) -> str:
    """Encrypt a string and return it as a string safe for SQLite."""
    if not text:
        return text
    f = get_fernet()
    # Return as base64 string
    return f.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt(text: str) -> str:
    """Decrypt a string. If decryption fails (e.g., unencrypted old data), return original."""
    if not text:
        return text
    try:
        f = get_fernet()
        return f.decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return text
    except Exception:
        # Fallback for old unencrypted text or corrupted data
        return text

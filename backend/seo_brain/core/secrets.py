"""SecretStore — API keys never touch the DB or logs.

Windows: values are encrypted with DPAPI (CryptProtectData, current-user scope) → data/secrets/<ref>.bin.
Other OS: Fernet (if `cryptography` is installed) with a key file at data/secrets/.key (0600); otherwise the store
refuses to save (raises) rather than writing plaintext. Reads return None when a ref is missing.
The API only ever exposes `key_hint` (last 4 chars).
"""
from __future__ import annotations

import base64
import ctypes
import os
import re
import sys
from pathlib import Path

from ..common.config import PROJECT_ROOT

_REF_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


class SecretStoreError(RuntimeError):
    pass


def _dpapi(data: bytes, protect: bool) -> bytes:
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), "seo-brain", None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise SecretStoreError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


class SecretStore:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or (PROJECT_ROOT / "data" / "secrets")
        self.backend = "dpapi" if sys.platform == "win32" else ("fernet" if self._fernet_available() else "none")

    @staticmethod
    def _fernet_available() -> bool:
        try:
            import cryptography  # noqa: F401
            return True
        except ImportError:
            return False

    def _path(self, ref: str) -> Path:
        if not _REF_RE.match(ref):
            raise SecretStoreError(f"invalid secret ref '{ref}'")
        return self.dir / f"{ref}.bin"

    def _fernet(self):
        from cryptography.fernet import Fernet
        keyfile = self.dir / ".key"
        if not keyfile.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            keyfile.write_bytes(Fernet.generate_key())
            try:
                os.chmod(keyfile, 0o600)
            except OSError:
                pass
        return Fernet(keyfile.read_bytes())

    def set(self, ref: str, value: str) -> str:
        p = self._path(ref)
        self.dir.mkdir(parents=True, exist_ok=True)
        raw = value.encode("utf-8")
        if self.backend == "dpapi":
            blob = _dpapi(raw, True)
        elif self.backend == "fernet":
            blob = self._fernet().encrypt(raw)
        else:
            raise SecretStoreError("no encryption backend available (install `cryptography`) — refusing to store plaintext")
        p.write_bytes(base64.b64encode(blob))
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return ref

    def get(self, ref: str | None) -> str | None:
        if not ref:
            return None
        p = self._path(ref)
        if not p.exists():
            return None
        blob = base64.b64decode(p.read_bytes())
        if self.backend == "dpapi":
            return _dpapi(blob, False).decode("utf-8")
        if self.backend == "fernet":
            return self._fernet().decrypt(blob).decode("utf-8")
        return None

    def delete(self, ref: str | None) -> bool:
        if not ref:
            return False
        p = self._path(ref)
        if p.exists():
            p.unlink()
            return True
        return False

    def exists(self, ref: str | None) -> bool:
        return bool(ref) and self._path(ref).exists()  # type: ignore[arg-type]

    @staticmethod
    def hint(value: str) -> str:
        return value[-4:] if len(value) >= 8 else "••••"


_default: SecretStore | None = None


def get_secret_store() -> SecretStore:
    global _default
    if _default is None:
        _default = SecretStore()
    return _default

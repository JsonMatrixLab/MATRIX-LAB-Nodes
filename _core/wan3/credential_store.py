"""Private, per-scope credentials outside workflows and the source checkout."""

from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from .private_storage import private_directory, private_file


def _store_dir() -> Path:
    import folder_paths

    return Path(folder_paths.get_user_directory()) / "matrix-wan3" / "credentials"


def _windows_owner_only(path: Path) -> None:
    import csv

    try:
        output = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True).stdout
        sid = next(csv.reader([output.strip()]))[1]
    except (subprocess.SubprocessError, IndexError, StopIteration) as exc:
        raise OSError("Cannot identify the Windows user for private credential storage.") from exc
    if not sid.startswith("S-1-"):
        raise OSError("Cannot identify the Windows user for private credential storage.")
    try:
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:F"], capture_output=True, check=True)
    except subprocess.SubprocessError as exc:
        raise OSError("Cannot restrict saved credential permissions.") from exc


def _crypt(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        return data
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    source = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    outgoing = Blob()
    operation = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not operation(ctypes.byref(incoming), None, None, None, None, 0, ctypes.byref(outgoing)):
        raise OSError("Windows could not protect or read the saved credential.")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(outgoing.data)


def _path(scope: str) -> Path:
    return _store_dir() / f"{hashlib.sha256(scope.encode('utf-8')).hexdigest()}.key"


def save(scope: str, key: str) -> None:
    directory = private_directory(_store_dir())
    if os.name == "nt":
        _windows_owner_only(directory)
    encoded = _crypt(key.encode("utf-8"), decrypt=False)
    descriptor, temporary = tempfile.mkstemp(prefix=".key-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        private_file(temporary)
        if os.name == "nt":
            _windows_owner_only(Path(temporary))
        if _crypt(Path(temporary).read_bytes(), decrypt=True).decode("utf-8") != key:
            raise OSError("Saved credential verification failed.")
        # A failed replacement leaves the prior credential intact.
        os.replace(temporary, _path(scope))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(scope: str) -> str | None:
    path = _path(scope)
    if not path.is_file():
        return None
    private_file(path)
    return _crypt(path.read_bytes(), decrypt=True).decode("utf-8")


def delete(scope: str) -> None:
    _path(scope).unlink(missing_ok=True)

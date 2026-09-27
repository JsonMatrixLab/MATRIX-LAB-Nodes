"""Owner-only permissions for node-owned persistent files on POSIX systems."""

from __future__ import annotations

import os
from pathlib import Path


def private_directory(path: str | Path) -> Path:
    """Create a node-owned directory and restrict it without changing ancestors."""
    directory = Path(path)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(directory, 0o700)
    return directory


def private_file(path: str | Path) -> Path:
    """Create a private file before a library opens it, or tighten our existing file."""
    file_path = Path(path)
    private_directory(file_path.parent)
    if os.name == "posix":
        try:
            descriptor = os.open(file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        os.chmod(file_path, 0o600)
    return file_path

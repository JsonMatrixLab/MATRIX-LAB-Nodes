import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from matrix_lab_nodes._core.wan3.journal import TaskJournal
from matrix_lab_nodes._core.wan3.private_storage import private_directory, private_file
from matrix_lab_nodes._core.wan3.uploads import UploadCache


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits are not available on this host")


def test_journal_upload_cache_and_results_are_private_without_chmodding_ancestors(tmp_path):
    package_data = tmp_path / "matrix-wan3"
    package_data.mkdir()
    os.chmod(tmp_path, 0o755)

    journal_path = package_data / "tasks.sqlite3"
    TaskJournal(journal_path).get_or_create("intent-id", "semantic-intent")

    cache_path = package_data / "uploads.sqlite3"
    asset = SimpleNamespace(sha256="content", size=5, content_type="image/png")
    UploadCache(cache_path).get_or_upload(asset, "account-scope", lambda: "https://assets.example.test/image")

    results = private_directory(package_data / "results")
    result_file = results / "fixture.mp4"
    result_file.write_bytes(b"fixture")
    private_file(result_file)
    assert package_data.stat().st_mode & 0o777 == 0o700
    assert journal_path.stat().st_mode & 0o777 == 0o600
    assert cache_path.stat().st_mode & 0o777 == 0o600
    assert results.stat().st_mode & 0o777 == 0o700
    assert result_file.stat().st_mode & 0o777 == 0o600
    assert tmp_path.stat().st_mode & 0o777 == 0o755
    for sidecar in package_data.glob("*.sqlite3-*"):
        assert sidecar.stat().st_mode & 0o077 == 0

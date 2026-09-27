from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import pytest

from matrix_lab_nodes._core.wan3.uploads import UploadCache


def asset():
    return SimpleNamespace(sha256="content-hash", size=10, content_type="image/png")


def test_reuse_survives_restart_but_not_key_change_expiry_or_clock_rollback(tmp_path):
    now = [100.0]
    calls = []
    def upload():
        calls.append(1)
        return "https://assets.example.test/" + str(len(calls))
    def cache():
        return UploadCache(tmp_path / "uploads.sqlite3", clock=lambda: now[0])
    assert cache().get_or_upload(asset(), "account-A", upload).endswith("/1")
    assert cache().get_or_upload(asset(), "account-A", upload).endswith("/1")
    assert cache().get_or_upload(asset(), "account-B", upload).endswith("/2")
    now[0] += UploadCache.MAX_AGE
    assert cache().get_or_upload(asset(), "account-A", upload).endswith("/3")
    now[0] = 50
    assert cache().get_or_upload(asset(), "account-A", upload).endswith("/4")


def test_cancelled_waiter_does_not_cancel_shared_uploader(tmp_path):
    started, release = Event(), Event()
    cache = UploadCache(tmp_path / "uploads.sqlite3")
    def upload():
        started.set()
        assert release.wait(5)
        return "https://assets.example.test/one"
    def cancelled():
        raise RuntimeError("cancelled fixture waiter")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cache.get_or_upload, asset(), "scope", upload)
        assert started.wait(5)
        try:
            with pytest.raises(RuntimeError, match="cancelled"):
                cache.get_or_upload(asset(), "scope", upload, check_cancelled=cancelled)
        finally:
            release.set()
        assert first.result().endswith("/one")
    assert cache.get_or_upload(asset(), "scope", lambda: pytest.fail("duplicate upload")).endswith("/one")


def test_failed_upload_releases_cache_lock_and_leaves_no_asset(tmp_path):
    cache = UploadCache(tmp_path / "uploads.sqlite3")
    def failed():
        raise OSError("injected transport failure")
    with pytest.raises(OSError):
        cache.get_or_upload(asset(), "scope", failed)
    assert cache.get_or_upload(asset(), "scope", lambda: "https://assets.example.test/recovered").endswith("/recovered")

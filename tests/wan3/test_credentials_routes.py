import asyncio
import os
import sys
import types
import threading

import pytest

from matrix_lab_nodes._core.wan3 import credentials, credential_store


def test_balance_verification_does_not_block_server_event_loop(handlers, monkeypatch):
    loop_thread = threading.get_ident()
    seen = []
    credentials.set_session_key("async-scope", "test-only-secret")

    class Client:
        def __init__(self, key):
            pass

        def verify_balance_access(self):
            seen.append(threading.get_ident())
            return {"verified": True}

    monkeypatch.setattr(credentials, "WaveSpeedClient", Client)
    response = asyncio.run(handlers[("POST", "/matrix-wan3/credentials/v1/verify")](
        Request(method="POST", origin="http://127.0.0.1:8188", body={"node_id": "async-scope"})))
    assert response["status"] == 200
    assert seen and seen[0] != loop_thread


class Routes:
    def __init__(self):
        self.handlers = {}

    def _decorator(self, method, path):
        def register(handler):
            self.handlers[(method, path)] = handler
            return handler
        return register

    def get(self, path):
        return self._decorator("GET", path)

    def post(self, path):
        return self._decorator("POST", path)


class Request:
    def __init__(self, *, method, origin=None, remote="127.0.0.1", host="127.0.0.1:8188", scheme="http", query=None, body=None):
        self.method = method
        self.headers = {"Origin": origin} if origin else {}
        self.remote = remote
        self.host = host
        self.scheme = scheme
        self.query = query or {}
        self._body = body or {}

    async def json(self):
        return self._body


@pytest.fixture
def handlers(monkeypatch, tmp_path):
    monkeypatch.setenv("MATRIX_WAN3_SINGLE_USER", "1")
    monkeypatch.setattr(credential_store, "_store_dir", lambda: tmp_path / "credentials")
    class Web:
        @staticmethod
        def json_response(data, *, status=200):
            return {"status": status, "data": data}

    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = Web
    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)
    routes = Routes()
    credentials.register_routes(types.SimpleNamespace(routes=routes))
    yield routes.handlers


def test_status_allows_originless_loopback_get_but_rejects_nonlocal_host(handlers):
    status = handlers[("GET", "/matrix-wan3/credentials/v1/status")]
    result = asyncio.run(status(Request(method="GET", query={"node_id": "scope-1"})))
    assert result["status"] == 200
    assert result["data"]["present"] is False

    remote = asyncio.run(status(Request(method="GET", host="example.test:8188", query={"node_id": "scope-1"})))
    assert remote["status"] == 403
    spoofed = asyncio.run(status(Request(method="GET", origin="http://127.0.0.1:8188", remote="192.0.2.10", query={"node_id": "scope-1"})))
    assert spoofed["status"] == 403


def test_network_listener_requires_explicit_single_user_opt_in(handlers, monkeypatch):
    monkeypatch.delenv("MATRIX_WAN3_SINGLE_USER")
    monkeypatch.setattr(sys, "argv", ["main.py", "--listen", "0.0.0.0"])
    status = handlers[("GET", "/matrix-wan3/credentials/v1/status")]
    response = asyncio.run(status(Request(method="GET", query={"node_id": "scope-1"})))
    assert response["status"] == 403
    with pytest.raises(ValueError, match="trusted local"):
        credentials.resolve_key("scope-1")


def test_post_requires_exact_local_origin_and_session_key_never_in_response(handlers):
    set_key = handlers[("POST", "/matrix-wan3/credentials/v1/set")]
    blocked = asyncio.run(set_key(Request(method="POST", body={"node_id": "scope-2", "key": "test-only-secret"})))
    assert blocked["status"] == 403

    saved = asyncio.run(set_key(Request(method="POST", origin="http://127.0.0.1:8188", body={"node_id": "scope-2", "key": "test-only-secret"})))
    assert saved == {"status": 200, "data": {"saved": True, "persistent": True}}
    assert "test-only-secret" not in repr(saved)
    status = handlers[("GET", "/matrix-wan3/credentials/v1/status")]
    present = asyncio.run(status(Request(method="GET", query={"node_id": "scope-2"})))
    assert present["data"] == {"present": True, "source": "saved", "verified": False}


def test_verify_uses_server_response_shape_and_never_returns_transport_exception_text(handlers, monkeypatch):
    scope = "scope-3"
    credentials.set_session_key(scope, "test-only-secret")
    verify = handlers[("POST", "/matrix-wan3/credentials/v1/verify")]

    class Client:
        def __init__(self, key):
            assert key == "test-only-secret"

        def verify_balance_access(self):
            raise RuntimeError("sensitive-provider-body")

    monkeypatch.setattr(credentials, "WaveSpeedClient", Client)
    response = asyncio.run(verify(Request(method="POST", origin="http://127.0.0.1:8188", body={"node_id": scope})))
    assert response == {"status": 502, "data": {"access": "unavailable", "generation_tested": False, "error": "RuntimeError"}}
    assert "sensitive-provider-body" not in repr(response)


def test_saved_key_survives_restart_and_disconnect_deletes_without_environment_fallback(handlers, monkeypatch):
    monkeypatch.setenv("WAVESPEED_API_KEY", "test-only-env-secret")
    scope = "scope-with-env"
    with pytest.raises(ValueError, match="No saved"):
        credentials.resolve_key(scope)
    credentials.set_session_key(scope, "test-only-saved-secret")
    assert credentials.resolve_key(scope) == ("test-only-saved-secret", "saved")
    stored_file = credential_store._path(scope)
    assert stored_file.is_file()
    if os.name == "nt":
        assert b"test-only-saved-secret" not in stored_file.read_bytes()
    assert credential_store.load(scope) == "test-only-saved-secret"
    credentials.disconnect_session_key(scope)
    assert credentials.key_status(scope) == {"present": False, "source": None, "verified": False}
    with pytest.raises(ValueError, match="No saved"):
        credentials.resolve_key(scope)
    credentials.set_session_key(scope, "test-only-session-secret")
    assert credentials.resolve_key(scope) == ("test-only-session-secret", "saved")


def test_failed_save_preserves_prior_key(handlers, monkeypatch):
    credentials.set_session_key("scope-no-env", "test-only-session-secret")
    original = credential_store.os.replace
    def fail(*_args):
        raise OSError("test failure")
    monkeypatch.setattr(credential_store.os, "replace", fail)
    with pytest.raises(OSError):
        credentials.set_session_key("scope-no-env", "replacement-secret")
    monkeypatch.setattr(credential_store.os, "replace", original)
    assert credentials.resolve_key("scope-no-env") == ("test-only-session-secret", "saved")


def test_windows_acl_failure_is_a_controlled_storage_error(monkeypatch, tmp_path):
    import subprocess
    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "whoami")
    monkeypatch.setattr(credential_store.subprocess, "run", fail)
    with pytest.raises(OSError, match="Cannot identify"):
        credential_store._windows_owner_only(tmp_path)


def test_route_registration_is_idempotent_and_collisions_fail(monkeypatch):
    class Web:
        @staticmethod
        def json_response(data, *, status=200):
            return {"status": status, "data": data}
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = Web
    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)

    routes = Routes()
    server = types.SimpleNamespace(routes=routes)
    credentials.register_routes(server)
    first = dict(routes.handlers)
    credentials.register_routes(server)
    assert routes.handlers == first

    collision = Routes()
    collision.handlers[("GET", "/matrix-wan3/credentials/v1/status")] = object()
    with pytest.raises(RuntimeError, match="route collision"):
        credentials.register_routes(types.SimpleNamespace(routes=collision))

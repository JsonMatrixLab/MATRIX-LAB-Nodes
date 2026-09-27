"""Saved local credentials behind a same-origin, loopback-only HTTP interface."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import sys
from threading import RLock

from . import credential_store
from .transport import WaveSpeedClient

_LOCK = RLock()
_NODE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_REGISTERED_ROUTE_TABLES: list[object] = []
_ROUTE_KEYS = {
    ("GET", "/matrix-wan3/credentials/v1/status"),
    ("POST", "/matrix-wan3/credentials/v1/set"),
    ("POST", "/matrix-wan3/credentials/v1/disconnect"),
    ("POST", "/matrix-wan3/credentials/v1/verify"),
}


def single_user_enabled() -> bool:
    """The ordinary local ComfyUI launch is usable; network listeners require opt-in."""
    if os.environ.get("MATRIX_WAN3_SINGLE_USER", "").strip() == "1":
        return True
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        if arg == "--listen":
            address = args[index + 1] if index + 1 < len(args) and not args[index + 1].startswith("-") else "0.0.0.0"
            return address in {"127.0.0.1", "localhost", "::1"}
        if arg.startswith("--listen="):
            return arg.split("=", 1)[1] in {"127.0.0.1", "localhost", "::1"}
    return True


def _node_id(value) -> str:
    if not isinstance(value, (str, int)) or not _NODE_ID.fullmatch(str(value)):
        raise ValueError("Invalid node identity.")
    return str(value)


def set_session_key(node_id, key: str) -> None:
    scope = _node_id(node_id)
    if not isinstance(key, str) or not key.strip() or len(key) > 4096:
        raise ValueError("Enter a non-empty WaveSpeed key.")
    with _LOCK:
        credential_store.save(scope, key.strip())


def disconnect_session_key(node_id) -> None:
    with _LOCK:
        credential_store.delete(_node_id(node_id))


def resolve_key(node_id) -> tuple[str, str]:
    if not single_user_enabled():
        raise ValueError("Live WaveSpeed mode requires a trusted local ComfyUI host or MATRIX_WAN3_SINGLE_USER=1.")
    with _LOCK:
        key = credential_store.load(_node_id(node_id))
    if not key:
        raise ValueError("No saved WaveSpeed key is available. Open this node and save an API key.")
    return key, "saved"


def key_status(node_id) -> dict:
    with _LOCK:
        present = credential_store.load(_node_id(node_id)) is not None
    return {"present": present, "source": "saved" if present else None, "verified": False}


def _is_local_same_origin(request) -> bool:
    origin = request.headers.get("Origin")
    host = request.host.rsplit(":", 1)[0].strip("[]").lower()
    if host not in ("localhost", "127.0.0.1", "::1"):
        return False
    try:
        peer = ipaddress.ip_address((request.remote or "").split("%", 1)[0])
        if not (peer.is_loopback or (getattr(peer, "ipv4_mapped", None) and peer.ipv4_mapped.is_loopback)):
            return False
    except ValueError:
        return False
    if origin:
        return origin == f"{request.scheme}://{request.host}"
    return request.method == "GET"


def register_routes(prompt_server) -> None:
    from aiohttp import web

    routes = prompt_server.routes
    if any(routes is registered for registered in _REGISTERED_ROUTE_TABLES):
        return
    existing_handlers = getattr(routes, "handlers", {})
    collisions = _ROUTE_KEYS.intersection(existing_handlers)
    if collisions:
        raise RuntimeError(f"MATRIX WAN 3.0 route collision: {sorted(collisions)!r}")

    def response(data, status=200):
        return web.json_response(data, status=status)

    def allowed(request):
        if not single_user_enabled():
            return response({"error": "Credentials and live requests require a trusted local ComfyUI host."}, status=403)
        if not _is_local_same_origin(request):
            return response({"error": "Local same-origin access required."}, status=403)
        return None

    @routes.get("/matrix-wan3/credentials/v1/status")
    async def status(request):
        denied = allowed(request)
        if denied:
            return denied
        try:
            return response(key_status(request.query.get("node_id")))
        except (ValueError, OSError):
            return response({"error": "Credential status unavailable."}, status=400)

    @routes.post("/matrix-wan3/credentials/v1/set")
    async def set_key(request):
        denied = allowed(request)
        if denied:
            return denied
        try:
            data = await request.json()
            set_session_key(data.get("node_id"), data.get("key"))
            return response({"saved": True, "persistent": True})
        except (ValueError, OSError, json.JSONDecodeError):
            return response({"error": "Could not save this API key."}, status=400)

    @routes.post("/matrix-wan3/credentials/v1/disconnect")
    async def disconnect(request):
        denied = allowed(request)
        if denied:
            return denied
        try:
            data = await request.json()
            disconnect_session_key(data.get("node_id"))
            return response({"disconnected": True})
        except (ValueError, OSError, json.JSONDecodeError):
            return response({"error": "Could not delete this API key."}, status=400)

    @routes.post("/matrix-wan3/credentials/v1/verify")
    async def verify(request):
        denied = allowed(request)
        if denied:
            return denied
        try:
            data = await request.json()
            key, source = resolve_key(data.get("node_id"))
            access = await asyncio.to_thread(WaveSpeedClient(key).verify_balance_access)
            return response({"access": "verified", "source": source, "generation_tested": False, **access})
        except Exception as exc:
            return response({"access": "unavailable", "generation_tested": False, "error": type(exc).__name__}, status=502)

    _REGISTERED_ROUTE_TABLES.append(routes)

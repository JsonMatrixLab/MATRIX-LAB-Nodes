from __future__ import annotations

from dataclasses import dataclass
import base64
import inspect
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any, Callable, Literal, Mapping
from urllib.parse import urlsplit


class MissingProviderKey(RuntimeError):
    pass


class CredentialStoreError(RuntimeError):
    pass


_REMOTE_DISABLED = (
    "Remote key entry is disabled. Set WAVESPEED_API_KEY on the ComfyUI server, "
    "or set MATRIX_ALLOW_REMOTE_KEY_INGEST=1 with secure remote pairing."
)
_ORIGIN_NOT_ALLOWED = (
    "Remote key entry is not enabled for this origin. Add this exact HTTPS origin to "
    "MATRIX_REMOTE_KEY_INGEST_ORIGINS, or set WAVESPEED_API_KEY on the server."
)
_PROXY_SIGNAL_HEADERS = frozenset({
    "forwarded", "via", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "x-forwarded-port", "x-real-ip", "cf-connecting-ip", "true-client-ip", "x-original-host",
})


@dataclass(frozen=True)
class CredentialIngressDecision:
    allowed: bool
    code: Literal[
        "ok", "remote_disabled", "origin_required", "origin_not_allowed",
        "https_required", "same_origin_required", "pairing_required",
        "pairing_invalid", "pairing_expired", "policy_unavailable",
    ]
    message: str
    mode: Literal["loopback", "remote_pairing", "none"]


def _decision(
    code: Literal[
        "ok", "remote_disabled", "origin_required", "origin_not_allowed",
        "https_required", "same_origin_required", "pairing_required",
        "pairing_invalid", "pairing_expired", "policy_unavailable",
    ],
    message: str,
    mode: Literal["loopback", "remote_pairing", "none"] = "none",
) -> CredentialIngressDecision:
    return CredentialIngressDecision(code == "ok", code, message, mode)


def _loopback(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value.lower() == "localhost"


def _loopback_listeners(value: object) -> bool | None:
    """Return whether every configured listen address is loopback-only."""
    if not isinstance(value, str):
        return None
    listeners = value.split(",")
    if not listeners or any(not listener or listener != listener.strip() for listener in listeners):
        return None
    return all(_loopback(listener) for listener in listeners)


def _canonical_https_origin(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.hostname is None
        ):
            return None
        host = parsed.hostname.lower()
        port = parsed.port
    except ValueError:
        return None
    if "*" in host:
        return None
    authority = f"[{host}]" if ":" in host else host
    if port is not None and port != 443:
        authority = f"{authority}:{port}"
    canonical = f"https://{authority}"
    return canonical if value == canonical else None


def _canonical_host(value: object) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    try:
        parsed = urlsplit(f"//{value}")
        if (
            not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.hostname is None
        ):
            return None
        host = parsed.hostname.lower()
        port = parsed.port
    except ValueError:
        return None
    authority = f"[{host}]" if ":" in host else host
    if port is not None and port != 443:
        authority = f"{authority}:{port}"
    return authority


def _origin_of(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.hostname is None
        ):
            return None
        host = parsed.hostname.lower()
        port = parsed.port
    except ValueError:
        return None
    authority = f"[{host}]" if ":" in host else host
    if port is not None and not (parsed.scheme == "https" and port == 443):
        authority = f"{authority}:{port}"
    return f"{parsed.scheme}://{authority}"


class CredentialIngressPolicy:
    """Fail-closed topology and pairing policy for one provider credential route."""

    pairing_header = "X-Matrix-Credential-Pairing"

    def __init__(
        self,
        *,
        intent_header: str,
        intent_value: str,
        remote_origins: frozenset[str] = frozenset(),
        pairing_token: str | None = None,
        pairing_expires_at: float | None = None,
        now: Callable[[], float] = time.time,
        listen_addresses: object = "127.0.0.1",
    ) -> None:
        if not intent_header or not intent_value:
            raise ValueError("credential intent header and value are required")
        if remote_origins and (not pairing_token or pairing_expires_at is None):
            raise ValueError("remote credential pairing requires a token and expiry")
        self.intent_header = intent_header
        self.intent_value = intent_value
        self.remote_origins = remote_origins
        self._pairing_token = pairing_token
        self._pairing_expires_at = pairing_expires_at
        self._now = now
        self._loopback_listeners = _loopback_listeners(listen_addresses)
        self._pairing_consumed = False
        self._pairing_lock = threading.Lock()

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str],
        logger: Any,
        now: Callable[[], float] = time.time,
        intent_header: str,
        intent_value: str,
        listen_addresses: object = "127.0.0.1",
    ) -> "CredentialIngressPolicy":
        enabled = environ.get("MATRIX_ALLOW_REMOTE_KEY_INGEST") == "1"
        if not enabled:
            return cls(intent_header=intent_header, intent_value=intent_value, now=now, listen_addresses=listen_addresses)
        raw_origins = environ.get("MATRIX_REMOTE_KEY_INGEST_ORIGINS")
        if raw_origins is None:
            raise ValueError("MATRIX_REMOTE_KEY_INGEST_ORIGINS is required when remote pairing is enabled")
        values = raw_origins.split(",")
        origins = frozenset(_canonical_https_origin(value) for value in values)
        if not values or None in origins or len(origins) != len(values):
            raise ValueError("MATRIX_REMOTE_KEY_INGEST_ORIGINS must be a non-empty comma-separated list of exact canonical HTTPS origins")
        token = secrets.token_urlsafe(32)
        expires_at = now() + 600
        logger.info(
            "Matrix remote credential pairing token (print once): %s; origins: %s; expires_at: %s",
            token,
            ",".join(sorted(origins)),
            expires_at,
        )
        return cls(
            intent_header=intent_header,
            intent_value=intent_value,
            remote_origins=origins,
            pairing_token=token,
            pairing_expires_at=expires_at,
            now=now,
            listen_addresses=listen_addresses,
        )

    @property
    def ingest_mode(self) -> Literal["loopback", "remote_pairing", "none"]:
        return "remote_pairing" if self.remote_origins else "loopback"

    def _headers(self, request: object) -> Mapping[str, str]:
        headers = getattr(request, "headers", {})
        return headers if isinstance(headers, Mapping) else {}

    def _local_sockname(self, request: object) -> object:
        transport = getattr(request, "transport", None)
        if transport is None:
            return None
        try:
            sockname = transport.get_extra_info("sockname")
        except Exception:
            return None
        return sockname[0] if isinstance(sockname, tuple) and sockname else sockname

    def _is_loopback_request(self, request: object) -> bool:
        if self._loopback_listeners is not True:
            return False
        headers = self._headers(request)
        # Any proxy marker makes the network path ambiguous. Never interpret
        # its value; force the strict remote policy instead.
        if any(isinstance(name, str) and name.lower() in _PROXY_SIGNAL_HEADERS for name in headers):
            return False
        host = _canonical_host(headers.get("Host", getattr(request, "host", "")))
        peer = getattr(request, "remote", None)
        local = self._local_sockname(request)
        host_name = urlsplit(f"//{host}").hostname if host else None
        return bool(host_name and _loopback(host_name) and _loopback(peer) and _loopback(local))

    def _intent_ok(self, request: object) -> bool:
        return self._headers(request).get(self.intent_header) == self.intent_value

    def _local_decision(self, request: object) -> CredentialIngressDecision:
        headers = self._headers(request)
        if not self._intent_ok(request):
            return _decision("same_origin_required", "Credential entry must be opened from the ComfyUI page.")
        host = _canonical_host(headers.get("Host", getattr(request, "host", "")))
        scheme = getattr(request, "scheme", "http")
        expected = f"{scheme}://{host}"
        origin = headers.get("Origin")
        referer = headers.get("Referer")
        if (origin and _origin_of(origin) != expected) or (referer and _origin_of(referer) != expected):
            return _decision("same_origin_required", "Credential entry must use the same ComfyUI origin.")
        site = headers.get("Sec-Fetch-Site")
        if site is not None and site != "same-origin":
            return _decision("same_origin_required", "Credential entry must use the same ComfyUI origin.")
        return _decision("ok", "Credential entry is available on this loopback ComfyUI server.", "loopback")

    def _remote_decision(self, request: object, presented_token: str | None, *, require_token: bool) -> CredentialIngressDecision:
        headers = self._headers(request)
        if not self.remote_origins:
            return _decision("remote_disabled", _REMOTE_DISABLED)
        if getattr(request, "scheme", None) != "https":
            return _decision("https_required", "Remote key entry requires an HTTPS transport. Set WAVESPEED_API_KEY on the ComfyUI server instead.")
        origin = headers.get("Origin")
        if not origin:
            return _decision("origin_required", "Remote key entry requires an exact HTTPS Origin. Set WAVESPEED_API_KEY on the server instead.")
        canonical_origin = _canonical_https_origin(origin)
        if canonical_origin is None:
            return _decision("https_required", "Remote key entry requires HTTPS. Set WAVESPEED_API_KEY on the ComfyUI server instead.")
        if canonical_origin not in self.remote_origins:
            return _decision("origin_not_allowed", _ORIGIN_NOT_ALLOWED)
        host = _canonical_host(headers.get("Host", getattr(request, "host", "")))
        if host is None or canonical_origin != f"https://{host}":
            return _decision("same_origin_required", "Origin and Host must exactly match the ComfyUI HTTPS origin.")
        if headers.get("Sec-Fetch-Site") != "same-origin":
            return _decision("same_origin_required", "Remote key entry requires a same-origin ComfyUI request.")
        referer = headers.get("Referer")
        if referer is not None and _origin_of(referer) != canonical_origin:
            return _decision("same_origin_required", "Remote key entry requires a same-origin ComfyUI request.")
        if not require_token:
            return _decision("ok", "Remote credential status is available.", "remote_pairing")
        if not isinstance(presented_token, str) or not presented_token:
            return _decision("pairing_required", "Read the one-time pairing token from the ComfyUI server log.", "remote_pairing")
        with self._pairing_lock:
            if self._pairing_expires_at is None or self._now() >= self._pairing_expires_at:
                return _decision("pairing_expired", "Pairing token expired; restart the ComfyUI backend to issue another.", "remote_pairing")
            if self._pairing_consumed or self._pairing_token is None:
                return _decision("pairing_invalid", "Pairing token is invalid or already used; restart the ComfyUI backend to issue another.", "remote_pairing")
            if not secrets.compare_digest(self._pairing_token, presented_token):
                return _decision("pairing_invalid", "Pairing token is invalid; restart the ComfyUI backend to issue another.", "remote_pairing")
        return _decision("ok", "Remote credential pairing is authorized.", "remote_pairing")

    def authorize_status(self, request: object) -> CredentialIngressDecision:
        try:
            if self._loopback_listeners is None:
                return _decision("policy_unavailable", "Credential policy is unavailable. Set WAVESPEED_API_KEY on the ComfyUI server.")
            if self._is_loopback_request(request):
                return self._local_decision(request)
            return self._remote_decision(request, None, require_token=False)
        except Exception:
            return _decision("policy_unavailable", "Credential policy is unavailable. Set WAVESPEED_API_KEY on the ComfyUI server.")

    def authorize_ingest(self, request: object, presented_token: str) -> CredentialIngressDecision:
        try:
            if self._loopback_listeners is None:
                return _decision("policy_unavailable", "Credential policy is unavailable. Set WAVESPEED_API_KEY on the ComfyUI server.")
            if self._is_loopback_request(request):
                return self._local_decision(request)
            return self._remote_decision(request, presented_token, require_token=True)
        except Exception:
            return _decision("policy_unavailable", "Credential policy is unavailable. Set WAVESPEED_API_KEY on the ComfyUI server.")

    def consume_pairing(self, presented_token: str) -> None:
        """Consume a currently valid remote token after synchronous store success only."""
        if not self.remote_origins:
            return
        with self._pairing_lock:
            if (
                self._pairing_consumed
                or self._pairing_token is None
                or self._pairing_expires_at is None
                or self._now() >= self._pairing_expires_at
                or not secrets.compare_digest(self._pairing_token, presented_token)
            ):
                raise RuntimeError("pairing token is no longer valid")
            self._pairing_consumed = True
            self._pairing_token = None


def default_credential_root() -> Path:
    import folder_paths

    return Path(folder_paths.get_user_directory()) / "credentials"


def provider_key_widget(provider: str) -> tuple[str, dict]:
    return ("STRING", {"default": "", "multiline": False, "tooltip": f"One-time {provider} key entry. Protected for the current Windows user with DPAPI; cleartext 0600 on single-user macOS/Linux. Never saved in the workflow."})


def _safe_tail(value: str) -> str:
    return value[-4:] if len(value) > 4 else ""


def _is_windows() -> bool:
    return os.name == "nt"


def _protect_for_current_user(value: str) -> str:
    """DPAPI-protect UTF-8 text without exposing it in any error message."""
    try:
        import ctypes
        from ctypes import wintypes

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        raw = value.encode("utf-8")
        buffer = ctypes.create_string_buffer(raw)
        input_blob = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        output_blob = DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        if not crypt32.CryptProtectData(ctypes.byref(input_blob), None, None, None, None, 1, ctypes.byref(output_blob)):
            raise OSError(ctypes.get_last_error(), "CryptProtectData failed")
        try:
            protected = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree.restype = ctypes.c_void_p
            kernel32.LocalFree(output_blob.pbData)
        return base64.b64encode(protected).decode("ascii")
    except Exception as exc:
        raise CredentialStoreError("The stored credential cannot be protected safely.") from exc


def _unprotect_for_current_user(encoded: object) -> str:
    """Decode a current-user DPAPI blob, failing closed on every malformed value."""
    try:
        if not isinstance(encoded, str):
            raise ValueError("invalid protected record")
        protected = base64.b64decode(encoded.encode("ascii"), validate=True)
        import ctypes
        from ctypes import wintypes

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        buffer = ctypes.create_string_buffer(protected)
        input_blob = DataBlob(len(protected), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        output_blob = DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        if not crypt32.CryptUnprotectData(ctypes.byref(input_blob), None, None, None, None, 1, ctypes.byref(output_blob)):
            raise OSError(ctypes.get_last_error(), "CryptUnprotectData failed")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
        finally:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree.restype = ctypes.c_void_p
            kernel32.LocalFree(output_blob.pbData)
    except Exception as exc:
        raise CredentialStoreError("The stored credential cannot be read safely.") from exc


class ProviderKeyStore:
    def __init__(self, provider: str, env_names: tuple[str, ...], *, profile: str = "default", root: Path | None = None) -> None:
        for label, value in (("provider", provider), ("profile", profile)):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
                raise ValueError(f"{label} must be a filesystem-safe identifier")
        self.provider, self.env_names = provider, env_names
        self.path = (Path(root) if root is not None else default_credential_root()) / provider / f"{profile}.json"

    def remember(self, value: str, *, verified: bool) -> None:
        key = value.strip()
        if not key:
            raise ValueError("refusing to store an empty provider key")
        record = {"key_dpapi": _protect_for_current_user(key), "verified": bool(verified)} if _is_windows() else {"key": key, "verified": bool(verified)}
        self._write_record(record)

    def _write_record(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
        os.chmod(self.path, 0o600)

    def _record(self) -> dict | None:
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CredentialStoreError(f"The stored {self.provider} credential cannot be read safely.") from exc
        if not isinstance(record, dict):
            raise CredentialStoreError(f"The stored {self.provider} credential has an invalid format.")
        return record

    def _stored_key(self, record: dict) -> str:
        if "key_dpapi" in record:
            if not _is_windows():
                raise CredentialStoreError(f"The stored {self.provider} credential cannot be read safely.")
            key = _unprotect_for_current_user(record["key_dpapi"])
        elif "key" in record:
            key = record["key"]
        else:
            return ""
        if not isinstance(key, str) or not key.strip():
            raise CredentialStoreError(f"The stored {self.provider} credential cannot be read safely.")
        key = key.strip()
        if "key" in record and _is_windows():
            # Upgrade only after a successful legacy read; write failures leave
            # no success path and therefore fail closed.
            self._write_record({"key_dpapi": _protect_for_current_user(key), "verified": bool(record.get("verified", False))})
        return key

    def resolve(self, transient: str = "") -> str:
        typed = transient.strip()
        if typed:
            return typed
        record = self._record()
        if record:
            key = self._stored_key(record)
            if key:
                return key
        for name in self.env_names:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        first_name = self.env_names[0] if self.env_names else "the provider environment variable"
        raise MissingProviderKey(f"No {self.provider} key is available. Use the provider key control once or set {first_name}.")

    def status(self) -> dict:
        record = self._record()
        if record:
            key = self._stored_key(record)
            if key:
                return {"stored": True, "source": "store", "tail": _safe_tail(key), "verified": bool(record.get("verified", False))}
        for name in self.env_names:
            key = os.environ.get(name, "").strip()
            if key:
                return {"stored": True, "source": "environment", "tail": _safe_tail(key), "verified": False}
        return {"stored": False, "source": "", "tail": "", "verified": False}


async def _await_if_needed(value: object) -> object:
    return await value if inspect.isawaitable(value) else value


def _error_response(web: Any, decision: CredentialIngressDecision):
    return web.json_response({"ok": False, "error_code": decision.code, "error": decision.message}, status=403)


def register_provider_key_routes(routes, web, path: str, store: ProviderKeyStore, *, verify, policy: CredentialIngressPolicy | None = None, authorize=None):
    if not path.startswith("/") or len([part for part in path.split("/") if part]) < 2:
        raise ValueError("credential route must be namespaced")
    if (policy is None) == (authorize is None):
        raise ValueError("provide exactly one of policy or authorize")

    async def decision_for(request: object, *, ingest: bool) -> CredentialIngressDecision:
        if policy is not None:
            token = policy._headers(request).get(policy.pairing_header, "")
            return policy.authorize_ingest(request, token) if ingest else policy.authorize_status(request)
        try:
            allowed = bool(await _await_if_needed(authorize(request)))
        except Exception:
            allowed = False
        return _decision("ok", "Credential entry authorized.", "loopback") if allowed else _decision("policy_unavailable", "Credential policy is unavailable. Set WAVESPEED_API_KEY on the ComfyUI server.")

    @routes.get(path)
    async def key_status(request):
        decision = await decision_for(request, ingest=False)
        if not decision.allowed:
            return _error_response(web, decision)
        body = store.status()
        if policy is not None:
            body["ingest_mode"] = decision.mode
        return web.json_response(body)

    @routes.post(path)
    async def key_ingest(request):
        decision = await decision_for(request, ingest=True)
        if not decision.allowed:
            return _error_response(web, decision)
        try:
            body = await request.json()
        except Exception:
            body = None
        value = body.get("key", "") if isinstance(body, dict) else ""
        key = value.strip() if isinstance(value, str) else ""
        if not key:
            return web.json_response({"ok": False, "error": "a non-empty string key is required"}, status=400)
        try:
            verified = await _await_if_needed(verify(key))
        except Exception:
            verified = None
        if verified is False:
            return web.json_response({"ok": False, "error": "credential rejected"}, status=401)
        # A verifier may await. Recheck immediately before the synchronous file replace so a
        # previously consumed remote token can never authorize a second write.
        decision = await decision_for(request, ingest=True)
        if not decision.allowed:
            return _error_response(web, decision)
        try:
            store.remember(key, verified=verified is True)
            if policy is not None and decision.mode == "remote_pairing":
                policy.consume_pairing(policy._headers(request).get(policy.pairing_header, ""))
        except Exception:
            return web.json_response({"ok": False, "error": "credential store unavailable"}, status=500)
        body = {"ok": True, **store.status()}
        if policy is not None:
            body["ingest_mode"] = decision.mode
        return web.json_response(body)

    return key_status, key_ingest

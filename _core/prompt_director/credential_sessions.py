"""Credential-scoped, secret-free browser sessions for Prompt Director."""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from dataclasses import dataclass

from ..auth_provider_key import ProviderKeyStore


class CredentialSessionError(RuntimeError):
    pass


def _tail(key: str) -> str:
    return "••••" + key[-4:] if len(key) >= 4 else "••••"


@dataclass(frozen=True)
class ResolvedCredential:
    key: str
    fingerprint: str
    status: dict


class CredentialSessions:
    """Keep Linux keys in memory and Windows keys in a DPAPI-backed profile."""

    def __init__(self, *, platform=None, store_factory=ProviderKeyStore):
        self.platform = platform or os.name
        self.store_factory = store_factory
        self._memory: dict[str, str] = {}
        self._opt_out: set[str] = set()
        self._invalid: set[str] = set()
        self._verified: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _fingerprint(key: str) -> str:
        return hashlib.sha256(("xai-grok\0" + key).encode()).hexdigest()

    def _store(self, session: str):
        return self.store_factory(
            "xai-grok", ("XAI_API_KEY", "MATRIX_GROK_KEY"), profile=session
        )

    def connect(self, key: str, *, prior_session="") -> ResolvedCredential:
        if not isinstance(key, str) or not key.strip() or len(key) > 4096:
            raise CredentialSessionError("key must be a bounded non-empty string")
        key = key.strip()
        if prior_session:
            try:
                if str(uuid.UUID(prior_session)) != prior_session:
                    raise ValueError
            except (ValueError, TypeError, AttributeError) as exc:
                raise CredentialSessionError("credential session is invalid") from exc
        session = str(uuid.uuid4())
        with self._lock:
            if self.platform == "nt":
                self._store(session).remember(key, verified=True)
                persistence = "dpapi"
                if prior_session:
                    prior_store = self._store(prior_session)
                    try:
                        prior_store._write_record({"revoked": True})
                    except OSError as exc:
                        # A post-replace permission failure can occur after revocation committed.
                        if prior_store._record() != {"revoked": True}:
                            raise CredentialSessionError("previous credential session could not be invalidated") from exc
            else:
                self._memory[session] = key
                persistence = "memory"
            if prior_session:
                self._invalid.add(prior_session)
                self._memory.pop(prior_session, None)
                self._opt_out.discard(prior_session)
            self._verified.add(self._fingerprint(key))
        return self._resolved(key, session=session, source="session", verified=True, persistence=persistence)

    def _resolved(self, key, *, session, source, verified, persistence):
        return ResolvedCredential(
            key=key,
            fingerprint=self._fingerprint(key),
            status={"configured": True, "source": source, "tail": _tail(key),
                    "verified": bool(verified), "session": session,
                    "persistence": persistence},
        )

    def resolve(self, session="") -> ResolvedCredential:
        if session:
            try:
                if str(uuid.UUID(session)) != session:
                    raise ValueError
            except (ValueError, TypeError, AttributeError) as exc:
                raise CredentialSessionError("credential session is invalid") from exc
        with self._lock:
            if session in self._invalid:
                raise CredentialSessionError("credential session is no longer valid")
            if session in self._opt_out:
                return self._disconnected(session, persistence="memory")
            key = self._memory.get(session) if session else None
        if key:
            return self._resolved(key, session=session, source="session", verified=True, persistence="memory")
        if session and self.platform == "nt":
            try:
                store = self._store(session)
                record = store._record()
                if record and record.get("opt_out") is True:
                    return self._disconnected(session, persistence="dpapi")
                key = store._stored_key(record) if record and not record.get("revoked") else ""
            except Exception as exc:
                raise CredentialSessionError("credential session is unavailable") from exc
            if not key:
                raise CredentialSessionError("credential session is unavailable")
            return self._resolved(key, session=session, source="store", verified=True, persistence="dpapi")
        if session:
            raise CredentialSessionError("credential session is unavailable")
        for name in ("XAI_API_KEY", "MATRIX_GROK_KEY"):
            key = os.environ.get(name, "").strip()
            if key:
                fingerprint = self._fingerprint(key)
                return self._resolved(key, session="", source="environment",
                                      verified=fingerprint in self._verified, persistence="environment")
        return ResolvedCredential("", "", {"configured": False, "source": "", "tail": "",
            "verified": False, "session": "", "persistence": "none"})

    @staticmethod
    def _disconnected(session: str, *, persistence: str) -> ResolvedCredential:
        return ResolvedCredential("", "", {"configured": False, "source": "", "tail": "",
            "verified": False, "session": session, "persistence": persistence})

    def disconnect(self, session="") -> ResolvedCredential:
        """Create a scoped opt-out without deleting or changing any global credential."""
        current = self.resolve(session)
        if session and not current.key:
            return current
        opt_out_session = session or str(uuid.uuid4())
        with self._lock:
            if self.platform == "nt":
                store = self._store(opt_out_session)
                record = {"revoked": True, "opt_out": True}
                try:
                    store._write_record(record)
                except OSError as exc:
                    # Preserve the prior usable session unless the durable replacement landed.
                    if store._record() != record:
                        raise CredentialSessionError("credential session could not be disconnected") from exc
                persistence = "dpapi"
            else:
                self._opt_out.add(opt_out_session)
                persistence = "memory"
            self._memory.pop(opt_out_session, None)
            self._invalid.discard(opt_out_session)
        return self._disconnected(opt_out_session, persistence=persistence)

    def status(self, session="") -> dict:
        return self.resolve(session).status

    def mark_verified(self, credential: ResolvedCredential) -> None:
        with self._lock:
            self._verified.add(credential.fingerprint)


__all__ = ["CredentialSessionError", "CredentialSessions", "ResolvedCredential"]

"""Durable, explicit xAI vision request service for the prompt director."""

from __future__ import annotations

import base64
import asyncio
import hashlib
import io
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from ..auth_provider_key import ProviderKeyStore
from ..io_image_collection import MAX_IMAGES, input_digest, load_ordered_records, parse_collection_state
from ..spend_tokens import TokenLedger, TokenPrices, TokenUsage
from ..text_refusal import finish_completion
from ..errors_taxonomy import failure_from_http
from .credential_sessions import CredentialSessionError, CredentialSessions


POST_PATH = "/matrixlab/prompt-director/v1/generate"
GET_PATH = "/matrixlab/prompt-director/v1/requests/{request_id}"
MODELS_PATH = "/matrixlab/prompt-director/v1/models"
CREDENTIAL_PATH = "/matrixlab/prompt-director/v1/credential"
CREDENTIAL_DISCONNECT_PATH = CREDENTIAL_PATH + "/disconnect"
MAX_TEXT_CHARS = 64_000
MAX_OUTPUT_TOKENS = 8_192
MAX_IMAGE_EDGE = 2_048
MAX_REQUEST_IMAGE_BYTES = 20 * 1024 * 1024
MAX_JSON_BYTES = 256 * 1024
INTENT_HEADER = "X-Matrix-Prompt-Intent"
INTENT_VALUE = "generate-v1"
CREDENTIAL_INTENT_HEADER = "X-Matrix-Credential-Intent"
SESSION_HEADER = "X-Matrix-Credential-Session"
_FIELDS = {
    "request_id", "collection", "instructions", "system_prompt", "model",
    "character_trigger", "allow_paid", "max_output_tokens", "temperature",
}


def _canonical_https_origin(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.netloc or parsed.username is not None
                or parsed.password is not None or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment or parsed.hostname is None):
            return None
        port = parsed.port
    except (TypeError, ValueError):
        return None
    host = parsed.hostname.casefold()
    authority = f"[{host}]" if ":" in host else host
    if port is not None and port != 443:
        authority += f":{port}"
    return "https://" + authority


def _trusted_external_origins(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    env = os.environ if environ is None else environ
    origins: set[str] = set()
    pod_id = env.get("RUNPOD_POD_ID", "").strip().casefold()
    if pod_id and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", pod_id):
        origins.add(f"https://{pod_id}-8188.proxy.runpod.net")
    configured = env.get("MATRIX_COMFYUI_EXTERNAL_ORIGINS", "")
    for raw in configured.split(",") if configured else ():
        canonical = _canonical_https_origin(raw.strip())
        if canonical is None:
            raise PromptDirectorError("configured external origin must be an exact HTTPS origin")
        origins.add(canonical)
    return frozenset(origins)


def _authorize_origin(request, *, credential: bool) -> None:
    origin = getattr(request, "headers", {}).get("Origin", "")
    if not origin:
        return
    parsed = urlsplit(origin)
    host = parsed.hostname.casefold() if parsed.hostname else ""
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    observed_same_origin = parsed.netloc.casefold() == str(request.host).casefold()
    if observed_same_origin and parsed.scheme in ({"http", "https"} if loopback else {"https"}):
        return
    canonical = _canonical_https_origin(origin)
    if canonical is not None and canonical in _trusted_external_origins():
        return
    label = "credential access" if credential else "prompt generation"
    raise PromptDirectorError(f"cross-origin {label} is refused")


class PromptDirectorError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelConfig:
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal | None
    pricing_version: str
    input_token_upper_bound: int
    max_output_tokens: int = MAX_OUTPUT_TOKENS


def load_model_configs(path: str | Path | None = None) -> dict[str, ModelConfig]:
    """Load only generated-fact models that prove image input and text output."""
    source = Path(path) if path is not None else Path(__file__).with_name("provider.json")
    try:
        fact = json.loads(source.read_text(encoding="utf-8"))
        fetched = str(fact["fetched"])
        models = fact["models"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise PromptDirectorError("compiled xAI provider catalogue is missing or malformed") from exc
    result: dict[str, ModelConfig] = {}
    for slug, model in models.items():
        try:
            inputs = model["input_modalities"]["value"]
            outputs = model["output_modalities"]["value"]
            if "image" not in inputs or "text" not in inputs or outputs != ["text"]:
                continue
            input_price = Decimal(str(model["input_token_price"]["value"]))
            output_price = Decimal(str(model["output_token_price"]["value"]))
            cached_value = model["cached_input_token_price"]["value"]
            cached_price = None if cached_value is None else Decimal(str(cached_value))
        except (KeyError, TypeError, ValueError) as exc:
            raise PromptDirectorError(f"generated model {slug!r} has incomplete pricing/modalities") from exc
        # This is a conservative engineering exposure bound, not a provider-exact
        # estimator: scale the prior 200k/five-image allowance to ten images.
        result[str(slug)] = ModelConfig(
            input_price, output_price, cached_price, fetched,
            input_token_upper_bound=400_000, max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    if not result:
        raise PromptDirectorError("compiled xAI catalogue contains no image-to-text model")
    return result


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _authorize(request) -> None:
    headers = getattr(request, "headers", {})
    if headers.get(INTENT_HEADER) != INTENT_VALUE:
        raise PromptDirectorError("explicit prompt-generation intent header is required")
    _authorize_origin(request, credential=False)
    if getattr(request, "content_length", None) is not None and request.content_length > MAX_JSON_BYTES:
        raise PromptDirectorError("prompt-generation request is too large")


def _authorize_credential(request, intent: str) -> None:
    headers = getattr(request, "headers", {})
    if headers.get(CREDENTIAL_INTENT_HEADER) != intent:
        raise PromptDirectorError("explicit credential intent header is required")
    _authorize_origin(request, credential=True)
    if getattr(request, "content_length", None) is not None and request.content_length > 8192:
        raise PromptDirectorError("credential request is too large")


def _validate_text(value: Any, name: str, *, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT_CHARS:
        raise PromptDirectorError(f"{name} must be a bounded string")
    if required and not value.strip():
        raise PromptDirectorError(f"{name} must not be empty")
    return value


def _request_payload(body: Any, models: Mapping[str, ModelConfig]) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) - _FIELDS:
        raise PromptDirectorError("request has unsupported fields")
    try:
        request_id = str(uuid.UUID(body.get("request_id", "")))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PromptDirectorError("request_id must be a canonical UUID") from exc
    if request_id != body.get("request_id"):
        raise PromptDirectorError("request_id must be a canonical UUID")
    if body.get("allow_paid") is not True or type(body.get("allow_paid")) is not bool:
        raise PromptDirectorError("allow_paid must be literal true")
    raw_collection = body.get("collection")
    if isinstance(raw_collection, dict):
        collection = _canonical(raw_collection)
    else:
        collection = _validate_text(raw_collection, "collection", required=True)
    state = parse_collection_state(collection)
    if not 1 <= len(state.items) <= MAX_IMAGES:
        raise PromptDirectorError(f"collection must contain 1 to {MAX_IMAGES} images")
    model = _validate_text(body.get("model"), "model", required=True)
    if model not in models:
        raise PromptDirectorError("model is not in the generated allowlist")
    config = models[model]
    maximum = body.get("max_output_tokens", min(2048, config.max_output_tokens))
    if type(maximum) is not int or not 1 <= maximum <= min(MAX_OUTPUT_TOKENS, config.max_output_tokens):
        raise PromptDirectorError("max_output_tokens is outside the generated model limit")
    temperature = body.get("temperature", 0.2)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= float(temperature) <= 2:
        raise PromptDirectorError("temperature must be between 0 and 2")
    return {
        "request_id": request_id,
        "collection": collection,
        "instructions": _validate_text(body.get("instructions", ""), "instructions"),
        "system_prompt": _validate_text(body.get("system_prompt", ""), "system_prompt"),
        "model": model,
        "character_trigger": _validate_text(body.get("character_trigger", ""), "character_trigger"),
        "max_output_tokens": maximum,
        "temperature": float(temperature),
    }


def _image_data_urls(collection: str) -> list[str]:
    from PIL import Image

    urls: list[str] = []
    total = 0
    for record in load_ordered_records(collection):
        tensor = record.image_tensor[0].detach().cpu().numpy()
        pixels = (tensor.clip(0, 1) * 255).round().astype("uint8")
        image = Image.fromarray(pixels, "RGB")
        image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
        encoded = output.getvalue()
        total += len(encoded)
        if total > MAX_REQUEST_IMAGE_BYTES:
            raise PromptDirectorError("encoded reference images exceed the request limit")
        urls.append("data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii"))
    return urls


def _prepare_image_snapshot(collection: str) -> tuple[str, list[str]]:
    before = input_digest(collection)
    urls = _image_data_urls(collection)
    after = input_digest(collection)
    if before != after:
        raise PromptDirectorError("reference images changed while preparing the request")
    return after, urls


def _normalize_trigger(text: str, trigger: str) -> str:
    """Place one trigger first, repairing glued identifier-style model output."""
    trigger = trigger.strip()
    if not trigger:
        return text.strip()
    escaped = re.escape(trigger)
    # Match explicit tokens only, plus the one known provider defect: <trigger>image.
    pattern = re.compile(rf"(?<!\w){escaped}(?=$|\W)|(?<!\w){escaped}(?=image(?:$|\W))")
    remainder = " ".join(pattern.sub(" ", text).split()).strip(" ,")
    return trigger + (", " + remainder if remainder else "")


class PromptDirectorService:
    def __init__(
        self, database_path, *, models: Mapping[str, ModelConfig], credential_store,
        transport=None, base_url="https://api.x.ai", deadline_seconds=180,
        request_timeout=180, credential_sessions=None,
    ):
        self.database_path = Path(database_path)
        self.models = dict(models)
        self.credential_store = credential_store
        self.credential_sessions = credential_sessions
        self._catalogues: dict[str, tuple[str, dict[str, ModelConfig]]] = {}
        if transport is None:
            from ..transport_http import request as transport
        self.transport = transport
        self.base_url = base_url.rstrip("/")
        self.deadline_seconds = float(deadline_seconds)
        self.request_timeout = float(request_timeout)
        self._lock = threading.Lock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prompt_requests(
                request_id TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL, state TEXT NOT NULL,
                result TEXT, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                credential_fingerprint TEXT NOT NULL DEFAULT '')""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(prompt_requests)")}
            if "credential_fingerprint" not in columns:
                db.execute("ALTER TABLE prompt_requests ADD COLUMN credential_fingerprint TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def status(self, request_id: str, credential_fingerprint: str | None = None) -> dict[str, Any] | None:
        try:
            canonical_id = str(uuid.UUID(request_id))
        except (ValueError, TypeError, AttributeError):
            return None
        with self._connect() as db:
            row = db.execute("SELECT * FROM prompt_requests WHERE request_id=?", (canonical_id,)).fetchone()
        if row is None:
            return None
        if credential_fingerprint is not None and row["credential_fingerprint"] != credential_fingerprint:
            return None
        result = {"request_id": canonical_id, "state": row["state"], "fingerprint": row["payload_sha256"]}
        if row["state"] == "completed":
            result["prompt"] = row["result"]
            result["final_prompt"] = row["result"]
        if row["state"] in {"uncertain", "failed"}:
            result["error"] = row["error"] or "request did not complete"
        return result

    def _credential(self, session=""):
        if self.credential_sessions is not None:
            resolved = self.credential_sessions.resolve(session)
            if not resolved.key:
                raise CredentialSessionError("No xAI credential is configured")
            return resolved
        key = self.credential_store.resolve("")
        fingerprint = hashlib.sha256(("xai-grok\0" + key).encode()).hexdigest()
        return type("Credential", (), {"key": key, "fingerprint": fingerprint,
            "status": {"configured": True, "source": "environment", "tail": "••••" + key[-4:],
                       "verified": False, "session": "", "persistence": "environment"}})()

    async def refresh_models(self, session="") -> dict[str, Any]:
        credential = self._credential(session)
        allowed, catalogue_fingerprint = await self._fetch_catalogue(credential.key)
        if self.credential_sessions is not None:
            self.credential_sessions.mark_verified(credential)
            credential = self._credential(session)
        self._catalogues[credential.fingerprint] = (catalogue_fingerprint, allowed)
        return {"models": [{"id": slug} for slug in sorted(allowed)],
                "catalogue_fingerprint": catalogue_fingerprint,
                "credential": credential.status}

    async def _fetch_catalogue(self, key: str) -> tuple[dict[str, ModelConfig], str]:
        response = await self.transport(
            "GET", self.base_url + "/v1/language-models",
            deadline=time.monotonic() + self.deadline_seconds,
            request_timeout=self.request_timeout,
            headers={"Authorization": "Bearer " + key},
        )
        if not isinstance(getattr(response, "status", None), int) or not isinstance(getattr(response, "body", None), bytes):
            raise PromptDirectorError("xAI returned no model catalogue")
        if not 200 <= response.status < 300:
            raise failure_from_http(response.status, response.body.decode("utf-8", "replace"))
        try:
            decoded = json.loads(response.body)
            records = decoded["models"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PromptDirectorError("xAI model catalogue is malformed") from exc
        allowed: dict[str, ModelConfig] = {}
        for record in records:
            try:
                slug = str(record["id"])
                if not {"text", "image"} <= set(record["input_modalities"]):
                    continue
                if set(record["output_modalities"]) != {"text"}:
                    continue
                generated = self.models[slug]
            except (KeyError, TypeError):
                continue
            allowed[slug] = generated
        ids = sorted(allowed)
        if not ids:
            raise PromptDirectorError("xAI returned no supported image-to-text models")
        catalogue_fingerprint = hashlib.sha256(_canonical(ids).encode()).hexdigest()
        return allowed, catalogue_fingerprint

    async def connect_credential(self, key: str, *, prior_session="") -> dict:
        if self.credential_sessions is None:
            raise CredentialSessionError("interactive credential sessions are unavailable")
        with self._lock:
            prior = self.credential_sessions.resolve(prior_session)
            if prior.fingerprint:
                self._refuse_unresolved_credential_change(prior.fingerprint)
        try:
            allowed, catalogue_fingerprint = await self._fetch_catalogue(key)
        except Exception as exc:
            raise CredentialSessionError("xAI rejected the credential")
        with self._lock:
            prior = self.credential_sessions.resolve(prior_session)
            if prior.fingerprint:
                self._refuse_unresolved_credential_change(prior.fingerprint)
            resolved = self.credential_sessions.connect(key, prior_session=prior_session)
            if prior_session:
                self._catalogues.pop(prior.fingerprint, None)
            self._catalogues[resolved.fingerprint] = (catalogue_fingerprint, allowed)
        return resolved.status

    def _refuse_unresolved_credential_change(self, fingerprint: str) -> None:
        with self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM prompt_requests WHERE credential_fingerprint=? "
                "AND state IN ('claimed','submitted','uncertain') LIMIT 1", (fingerprint,),
            ).fetchone()
        if row is not None:
            raise CredentialSessionError(
                "credential has an unresolved request; recover it before changing credentials"
            )

    def disconnect_credential(self, session="") -> dict:
        if self.credential_sessions is None:
            raise CredentialSessionError("interactive credential sessions are unavailable")
        with self._lock:
            current = self.credential_sessions.resolve(session)
            if current.fingerprint:
                self._refuse_unresolved_credential_change(current.fingerprint)
            disconnected = self.credential_sessions.disconnect(session)
            if current.fingerprint:
                self._catalogues.pop(current.fingerprint, None)
        return disconnected.status

    async def generate(self, body: Any, *, credential_session="") -> dict[str, Any]:
        credential = self._credential(credential_session)
        catalogue = self._catalogues.get(credential.fingerprint)
        if catalogue is None:
            await self.refresh_models(credential_session)
            catalogue = self._catalogues[credential.fingerprint]
        models = catalogue[1]
        payload = _request_payload(body, models)
        # Decode and hash away from the event loop, then claim the exact stable snapshot.
        collection_digest, images = await asyncio.to_thread(
            _prepare_image_snapshot, payload["collection"]
        )
        # Bind cache identity to the source bytes without putting bytes or paths in the database.
        digest_payload = dict(payload)
        digest_payload["collection_digest"] = collection_digest
        digest_payload.pop("collection")
        payload_sha = hashlib.sha256(_canonical(digest_payload).encode("utf-8")).hexdigest()
        now = time.time()
        with self._lock, self._connect() as db:
            if self.credential_sessions is not None:
                current = self.credential_sessions.resolve(credential_session)
                if current.fingerprint != credential.fingerprint:
                    raise CredentialSessionError("credential session changed while preparing the request")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM prompt_requests WHERE request_id=?", (payload["request_id"],)).fetchone()
            if row is not None:
                if row["credential_fingerprint"] != credential.fingerprint:
                    raise PromptDirectorError("request_id belongs to a different credential session")
                if row["payload_sha256"] != payload_sha:
                    raise PromptDirectorError("request_id is already bound to different content")
                db.commit()
                state = self.status(payload["request_id"])
                if state and state["state"] == "completed":
                    return state
                raise PromptDirectorError("request is already in flight or has uncertain billing; no resubmit")
            db.execute(
                "INSERT INTO prompt_requests(request_id,payload_sha256,state,result,error,created_at,updated_at,credential_fingerprint) VALUES(?,?, 'claimed', NULL, NULL, ?, ?, ?)",
                (payload["request_id"], payload_sha, now, now, credential.fingerprint),
            )
            db.commit()

        config = self.models[payload["model"]]
        prices = TokenPrices(
            provider="xai-grok", model=payload["model"], pricing_version=config.pricing_version,
            input_usd_per_million=config.input_usd_per_million,
            output_usd_per_million=config.output_usd_per_million,
            cached_input_usd_per_million=config.cached_input_usd_per_million,
        )
        exposure = (
            Decimal(config.input_token_upper_bound) * max(
                config.input_usd_per_million,
                config.cached_input_usd_per_million or config.input_usd_per_million,
            )
            + Decimal(payload["max_output_tokens"]) * config.output_usd_per_million
        ) / Decimal(1_000_000)
        ledger = TokenLedger(run_id=payload["request_id"], account="xai-grok", ceiling_usd=exposure)
        reservation = ledger.reserve(
            prices=prices, input_token_upper_bound=config.input_token_upper_bound,
            max_output_tokens=payload["max_output_tokens"],
        )
        try:
            request_text = (payload["instructions"] if payload["instructions"].strip()
                            else "Describe these references as one coherent image prompt.")
            with self._connect() as db:
                db.execute("UPDATE prompt_requests SET state='submitted',updated_at=? WHERE request_id=?", (time.time(), payload["request_id"]))
            response = await self.transport(
                "POST", self.base_url + "/v1/responses", deadline=time.monotonic() + self.deadline_seconds,
                request_timeout=self.request_timeout, headers={"Authorization": "Bearer " + credential.key},
                json={
                    "model": payload["model"], "store": False,
                    "input": [
                        *([{"role": "system", "content": [{"type": "input_text", "text": payload["system_prompt"]}]}] if payload["system_prompt"] else []),
                        {"role": "user", "content": [
                            {"type": "input_text", "text": request_text + ("\nUse this exact character trigger once in the final prompt: " + payload["character_trigger"] if payload["character_trigger"] else "")},
                            *({"type": "input_image", "image_url": url} for url in images),
                        ]},
                    ],
                    "max_output_tokens": payload["max_output_tokens"],
                },
                billable_submit=True,
            )
            if not isinstance(getattr(response, "status", None), int) or not isinstance(getattr(response, "body", None), bytes):
                raise PromptDirectorError("xAI returned no terminal HTTP response")
            if not 200 <= response.status < 300:
                raise failure_from_http(response.status, response.body.decode("utf-8", "replace"))
            decoded = json.loads(response.body)
            if decoded.get("status") != "completed":
                raise PromptDirectorError("xAI response did not complete")
            content = [item for output in decoded.get("output", []) if output.get("type") == "message" for item in output.get("content", [])]
            refusal = next((item.get("refusal") for item in content if item.get("type") == "refusal"), None)
            if refusal:
                finish_completion(text="", finish_state="refusal", model=payload["model"], detail=str(refusal))
            text = "".join(str(item.get("text", "")) for item in content if item.get("type") == "output_text")
            usage = decoded["usage"]
            if not isinstance(text, str) or not text.strip():
                raise PromptDirectorError("xAI returned an empty prompt")
            finish = "complete"
            terminal = finish_completion(
                text=text, finish_state=finish, model=payload["model"], model_limit=None,
                input_tokens=int(usage["input_tokens"]), output_allowance=payload["max_output_tokens"],
                truncation_policy="disabled",
            )
            if terminal.finish_state != "complete":
                raise PromptDirectorError("xAI truncated the generated prompt")
            input_tokens = int(usage["input_tokens"])
            raw_output_tokens = int(usage["output_tokens"])
            total_tokens = int(usage.get("total_tokens", input_tokens + raw_output_tokens))
            effective_output_tokens = max(raw_output_tokens, max(0, total_tokens - input_tokens))
            reservation.settle(TokenUsage(
                input_tokens=input_tokens, output_tokens=effective_output_tokens,
                cached_input_tokens=int(usage.get("input_tokens_details", {}).get("cached_tokens", 0)),
            ))
            final_prompt = terminal.text.strip()
            trigger = payload["character_trigger"].strip()
            if trigger:
                final_prompt = _normalize_trigger(final_prompt, trigger)
            with self._connect() as db:
                db.execute("UPDATE prompt_requests SET state='completed',result=?,updated_at=? WHERE request_id=?", (final_prompt, time.time(), payload["request_id"]))
            return {"request_id": payload["request_id"], "fingerprint": payload_sha, "state": "completed", "prompt": final_prompt, "final_prompt": final_prompt}
        except BaseException as exc:
            # Failures before the transport boundary are definitely not billed. Once the
            # POST begins, ambiguity is retained and the same UUID is never submitted again.
            with self._connect() as db:
                row = db.execute("SELECT state FROM prompt_requests WHERE request_id=?", (payload["request_id"],)).fetchone()
                failure_state = "uncertain" if row and row["state"] == "submitted" else "failed"
                db.execute("UPDATE prompt_requests SET state=?,error=?,updated_at=? WHERE request_id=?", (failure_state, type(exc).__name__, time.time(), payload["request_id"]))
            raise


def _default_service(models: Mapping[str, ModelConfig] | None = None) -> PromptDirectorService:
    import folder_paths

    root = Path(folder_paths.get_user_directory()) / "matrix-compiled" / "prompt-director" / "v1"
    store = ProviderKeyStore("xai-grok", ("XAI_API_KEY", "MATRIX_GROK_KEY"))
    return PromptDirectorService(
        root / "requests.sqlite3", models=models or load_model_configs(), credential_store=store,
        credential_sessions=CredentialSessions(),
    )


def register_routes(*, models: Mapping[str, ModelConfig] | None = None, service: PromptDirectorService | None = None) -> None:
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return
    prompt_server = getattr(PromptServer, "instance", None)
    routes = getattr(prompt_server, "routes", None)
    if routes is None:
        return

    backend = service or _default_service(models)

    @routes.post(POST_PATH)
    async def generate(request):
        try:
            _authorize(request)
            raw = await request.read()
            if len(raw) > MAX_JSON_BYTES:
                raise PromptDirectorError("prompt-generation request is too large")
            return web.json_response(await backend.generate(
                json.loads(raw), credential_session=request.headers.get(SESSION_HEADER, "")
            ))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return web.json_response({"error": "Request body must be valid JSON."}, status=400)
        except CredentialSessionError:
            return web.json_response({"error": "Credential session is unavailable."}, status=401)
        except PromptDirectorError as exc:
            return web.json_response({"error": str(exc)}, status=409)
        except Exception:
            return web.json_response({"error": "Prompt generation did not complete; check request status before retrying."}, status=502)

    @routes.get(GET_PATH)
    async def status(request):
        try:
            credential = backend._credential(request.headers.get(SESSION_HEADER, ""))
        except CredentialSessionError:
            return web.json_response({"error": "Credential session is unavailable."}, status=401)
        result = backend.status(request.match_info["request_id"], credential.fingerprint)
        if result is None:
            return web.json_response({"error": "Request not found."}, status=404)
        return web.json_response(result)

    @routes.get(MODELS_PATH)
    async def models_route(request):
        try:
            _authorize(request)
            return web.json_response(await backend.refresh_models(request.headers.get(SESSION_HEADER, "")))
        except CredentialSessionError:
            return web.json_response({"error": "Credential session is unavailable."}, status=401)
        except Exception:
            return web.json_response({"error": "Model catalogue refresh failed."}, status=502)

    @routes.get(CREDENTIAL_PATH)
    async def credential_status(request):
        try:
            _authorize_credential(request, "status-v1")
            return web.json_response(backend.credential_sessions.status(request.headers.get(SESSION_HEADER, "")))
        except Exception:
            return web.json_response({"configured": False, "source": "", "tail": "", "verified": False, "session": "", "persistence": "none"}, status=401)

    @routes.post(CREDENTIAL_PATH)
    async def credential_connect(request):
        try:
            _authorize_credential(request, "set-v1")
            raw = await request.read()
            if len(raw) > 8192:
                raise PromptDirectorError("credential request is too large")
            body = json.loads(raw)
            if not isinstance(body, dict) or set(body) != {"key"}:
                raise PromptDirectorError("credential request must contain exactly key")
            return web.json_response(await backend.connect_credential(
                body["key"], prior_session=request.headers.get(SESSION_HEADER, "")
            ))
        except Exception:
            return web.json_response({"error": "Credential verification failed."}, status=401)

    @routes.post(CREDENTIAL_DISCONNECT_PATH)
    async def credential_disconnect(request):
        try:
            _authorize_credential(request, "disconnect-v1")
            if await request.read():
                raise PromptDirectorError("credential disconnect request body must be empty")
            return web.json_response(backend.disconnect_credential(
                request.headers.get(SESSION_HEADER, "")
            ))
        except Exception:
            return web.json_response({"error": "Credential disconnect failed."}, status=409)


__all__ = ["CREDENTIAL_DISCONNECT_PATH", "CREDENTIAL_PATH", "GET_PATH", "MODELS_PATH", "ModelConfig", "POST_PATH", "PromptDirectorError", "PromptDirectorService", "load_model_configs", "register_routes"]

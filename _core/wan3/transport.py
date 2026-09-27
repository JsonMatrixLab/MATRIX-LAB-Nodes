"""WaveSpeed REST and signed-upload transport with pinned TLS and bounded streams."""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit

API_ROOT = "https://api.wavespeed.ai/api/v3"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024 * 1024
_ALLOWED_TICKET_HEADERS = {"content-type", "content-length", "content-md5", "if-none-match"}


class TransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: Mapping[str, str]
    body: bytes


def _validated_target(url: str, resolver: Callable = socket.getaddrinfo) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise TransportError("Remote media endpoints must be plain HTTPS URLs without user information or fragments.")
    if parsed.port not in (None, 443):
        raise TransportError("Remote media endpoints must use HTTPS port 443.")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    try:
        results = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise TransportError("The remote HTTPS hostname could not be resolved.") from exc
    addresses = {item[4][0] for item in results}
    if not addresses:
        raise TransportError("The remote HTTPS hostname returned no addresses.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as exc:
            raise TransportError("The remote HTTPS hostname returned an invalid address.") from exc
        if not ip.is_global:
            raise TransportError("Private, local, and non-global remote HTTPS addresses are refused.")
    # Resolve once and connect to that checked address; the TLS server name remains the hostname.
    ip = sorted(addresses)[0]
    target = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
    return host, ip, target


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, address: str, timeout: float):
        super().__init__(hostname, port=443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_address, 443), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class PinnedHTTPS:
    """No proxy inheritance, no redirects, global-DNS check and address-pinned TLS."""

    def __init__(self, *, resolver: Callable = socket.getaddrinfo, connection_factory: Callable | None = None, timeout: float = 30):
        self.resolver = resolver
        self.connection_factory = connection_factory or _PinnedHTTPSConnection
        self.timeout = timeout

    def request(self, method: str, url: str, *, headers: Mapping[str, str] | None = None, body: bytes | None = None,
                source_path: str | Path | None = None, max_bytes: int = MAX_JSON_BYTES,
                check_cancelled: Callable[[], None] | None = None) -> HTTPResult:
        host, address, target = _validated_target(url, self.resolver)
        parsed = urlsplit(url)
        outbound = {"host": ("Host", parsed.netloc), "connection": ("Connection", "close")}
        for name, value in (headers or {}).items():
            if not isinstance(name, str) or not name or not isinstance(value, str) or "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                raise TransportError("Invalid HTTP header name or value.")
            lowered = name.lower()
            if lowered in outbound:
                raise TransportError("Duplicate or overridden HTTP headers are refused.")
            outbound[lowered] = (name, value)
        size = len(body) if body is not None else (Path(source_path).stat().st_size if source_path is not None else 0)
        if body is not None or source_path is not None:
            declared = outbound.get("content-length")
            if declared is not None and declared[1] != str(size):
                raise TransportError("The prepared upload length differs from the upload ticket.")
            outbound.setdefault("content-length", ("Content-Length", str(size)))
        # All caller-controlled header and file-size checks precede connection creation.
        conn = self.connection_factory(host, address, self.timeout)
        try:
            if check_cancelled:
                check_cancelled()
            conn.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
            for name, value in outbound.values():
                conn.putheader(name, value)
            conn.endheaders()
            if body is not None:
                conn.send(body)
            elif source_path is not None:
                path = Path(source_path)
                before = path.stat()
                sent = 0
                with path.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        if check_cancelled:
                            check_cancelled()
                        sent += len(chunk)
                        if sent > size:
                            raise TransportError("The prepared upload changed while it was being sent.")
                        conn.send(chunk)
                after = path.stat()
                if sent != size or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                    raise TransportError("The prepared upload changed while it was being sent.")
            response = conn.getresponse()
            chunks = bytearray()
            while chunk := response.read(min(64 * 1024, max_bytes + 1 - len(chunks))):
                chunks.extend(chunk)
                if len(chunks) > max_bytes:
                    raise TransportError("The remote response exceeded its size limit.")
            return HTTPResult(response.status, dict(response.getheaders()), bytes(chunks))
        finally:
            conn.close()

    def download(self, url: str, destination: str | Path, *, max_bytes: int = MAX_RESULT_BYTES,
                 check_cancelled: Callable[[], None] | None = None) -> Path:
        host, address, target = _validated_target(url, self.resolver)
        parsed = urlsplit(url)
        conn = self.connection_factory(host, address, self.timeout)
        temp_path = None
        try:
            if check_cancelled:
                check_cancelled()
            conn.putrequest("GET", target, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", parsed.netloc)
            conn.putheader("Connection", "close")
            conn.endheaders()
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".matrix-wan3-", suffix=".partial", dir=destination.parent)
            temp_path = Path(temp_name)
            os.close(fd)
            response = conn.getresponse()
            if response.status != 200:
                qualifier = " (partial content)" if response.status == 206 else ""
                raise TransportError(f"Result download failed with HTTP {response.status}{qualifier}; the prediction will not be resubmitted.")
            content_range = response.getheader("Content-Range")
            if content_range is not None:
                raise TransportError("Partial or ranged result downloads are refused; the prediction will not be resubmitted.")
            length = response.getheader("Content-Length")
            declared_length = None
            if length is not None:
                if not isinstance(length, str) or not re.fullmatch(r"[0-9]+", length.strip()):
                    raise TransportError("The result Content-Length header is malformed.")
                declared_length = int(length.strip())
                if declared_length > max_bytes:
                    raise TransportError("The video result exceeds the configured download-size limit.")
            count = 0
            with temp_path.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    if check_cancelled:
                        check_cancelled()
                    count += len(chunk)
                    if count > max_bytes:
                        raise TransportError("The video result exceeded the configured download-size limit.")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if declared_length is not None and count != declared_length:
                raise TransportError("The downloaded byte count does not match Content-Length.")
            if count == 0:
                raise TransportError("The completed prediction returned an empty video file.")
            os.replace(temp_path, destination)
            return destination
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise
        finally:
            conn.close()


class WaveSpeedClient:
    def __init__(self, api_key: str, http: PinnedHTTPS | None = None):
        if not api_key or not isinstance(api_key, str):
            raise TransportError("WaveSpeed API key is not configured.")
        self._api_key = api_key
        self.http = http or PinnedHTTPS()

    def _json(self, method: str, path: str, *, body: Mapping | None = None) -> dict:
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        if raw is not None:
            headers["Content-Type"] = "application/json"
        result = self.http.request(method, API_ROOT + path, headers=headers, body=raw, max_bytes=MAX_JSON_BYTES)
        if not 200 <= result.status < 300:
            raise TransportError(f"WaveSpeed returned HTTP {result.status}; the request was not retried.")
        try:
            decoded = json.loads(result.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TransportError("WaveSpeed returned malformed JSON.") from exc
        if not isinstance(decoded, dict) or decoded.get("code", 200) not in (200, "200"):
            raise TransportError("WaveSpeed returned an unsuccessful API response.")
        return decoded.get("data", decoded)

    def verify_balance_access(self) -> dict:
        data = self._json("GET", "/balance")
        return {"verified": True, "generation_tested": False, "has_balance_field": "balance" in data}

    def upload(self, media, *, account_scope: str, check_cancelled: Callable[[], None] | None = None) -> str:
        ticket = self._json("POST", "/media/uploads", body={
            "filename": media.filename,
            "size": media.size,
            "content_type": media.content_type,
        })
        upload = ticket.get("upload") or ticket
        method = upload.get("method")
        url = upload.get("url")
        returned_headers = upload.get("headers", {})
        download_url = ticket.get("download_url") or upload.get("download_url")
        if method != "PUT" or not isinstance(url, str) or not isinstance(returned_headers, dict) or not isinstance(download_url, str):
            raise TransportError("WaveSpeed returned an unsupported upload ticket; generation was not submitted.")
        # Validate both endpoints before transmitting bytes or retaining the resulting URL.
        _validated_target(url, self.http.resolver)
        _validated_target(download_url, self.http.resolver)
        safe_headers = {}
        seen_headers = set()
        for name, value in returned_headers.items():
            lower = name.lower()
            if lower in seen_headers:
                raise TransportError("The upload ticket contains duplicate headers; generation was not submitted.")
            seen_headers.add(lower)
            if not isinstance(value, str) or "\r" in value or "\n" in value:
                raise TransportError("The upload ticket contains an invalid header; generation was not submitted.")
            if lower == "if-none-match" and value != "*":
                raise TransportError("The upload ticket If-None-Match header must be exactly the wildcard; generation was not submitted.")
            if lower not in _ALLOWED_TICKET_HEADERS and not lower.startswith(("x-amz-", "x-goog-")):
                raise TransportError("The upload ticket requested a credential-bearing or unreviewed header; generation was not submitted.")
            safe_headers[name] = value
        content_type = next((value for name, value in safe_headers.items() if name.lower() == "content-type"), media.content_type)
        if content_type != media.content_type:
            raise TransportError("The upload ticket content type does not match the prepared media.")
        if not any(name.lower() == "content-type" for name in safe_headers):
            safe_headers["Content-Type"] = media.content_type
        length = next((value for name, value in safe_headers.items() if name.lower() == "content-length"), str(media.size))
        if length != str(media.size):
            raise TransportError("The upload ticket content length does not match the prepared media.")
        if not any(name.lower() == "content-length" for name in safe_headers):
            safe_headers["Content-Length"] = length
        put = self.http.request("PUT", url, headers=safe_headers, source_path=media.path, max_bytes=1024 * 1024, check_cancelled=check_cancelled)
        if not 200 <= put.status < 300:
            # A lost/failed PUT is never retried in this client; caller must stop before paid submit.
            raise TransportError(f"Signed media upload returned HTTP {put.status}; no generation request was sent.")
        return download_url

    def submit(self, model_id: str, payload: Mapping) -> str:
        result = self._json("POST", "/" + model_id, body=payload)
        prediction_id = result.get("id") or result.get("prediction_id")
        if not isinstance(prediction_id, str) or not prediction_id:
            raise TransportError("WaveSpeed did not return a prediction ID; this submission is indeterminate and cannot be repeated.")
        return prediction_id

    def poll(self, prediction_id: str) -> dict:
        if not prediction_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in prediction_id):
            raise TransportError("The journaled prediction ID has an invalid format.")
        return self._json("GET", f"/predictions/{prediction_id}/result")

    def download_result(self, url: str, destination: str | Path, *, check_cancelled: Callable[[], None] | None = None) -> Path:
        return self.http.download(url, destination, check_cancelled=check_cancelled)

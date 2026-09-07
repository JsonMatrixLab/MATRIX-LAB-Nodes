"""Async HTTP transport shared by provider-backed nodes."""

import asyncio
from dataclasses import dataclass
import ipaddress
import socket
import time
from urllib.parse import urlsplit

import aiohttp

from ..errors_taxonomy import EmptyOrMalformedSuccessError
from ..errors_taxonomy import IndeterminateSubmitError
from ..errors_taxonomy import LocalValidationError
from ..errors_taxonomy import TimeoutOrInterruptedError, failure_from_http
from ..errors_taxonomy import TransientTransportOrServerError


READ_RETRY_DELAYS = (1.0, 2.0)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict
    body: bytes


@dataclass(frozen=True)
class HttpDownloadStream:
    headers: dict
    chunks: object


def _default_interrupt():
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError:
        return
    throw_exception_if_processing_interrupted()


async def _await_interruptibly(
    awaitable,
    *,
    deadline,
    request_deadline,
    interrupt,
    indeterminate_on_interrupt=False,
):
    task = asyncio.ensure_future(awaitable)
    try:
        while True:
            try:
                interrupt()
            except BaseException as exc:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                if indeterminate_on_interrupt:
                    raise IndeterminateSubmitError(
                        "billable submit was interrupted after its request started"
                    ) from exc
                raise
            now = time.monotonic()
            remaining = min(deadline, request_deadline) - now
            if remaining <= 0:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                reason = "operation_deadline" if deadline <= request_deadline else "request_timeout"
                raise TimeoutOrInterruptedError(
                    f"{reason.replace('_', ' ')} expired",
                    reason=reason,
                )
            done, _ = await asyncio.wait((task,), timeout=min(1.0, remaining))
            if done:
                return await task
    except asyncio.CancelledError:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        raise


async def _read_body(
    response,
    *,
    deadline,
    request_deadline,
    interrupt,
    indeterminate_on_interrupt=False,
):
    chunks = []
    iterator = response.content.iter_chunked(64 * 1024).__aiter__()
    while True:
        try:
            chunk = await _await_interruptibly(
                iterator.__anext__(),
                deadline=deadline,
                request_deadline=request_deadline,
                interrupt=interrupt,
                indeterminate_on_interrupt=indeterminate_on_interrupt,
            )
        except StopAsyncIteration:
            return b"".join(chunks)
        chunks.append(chunk)


async def _backoff(seconds, *, deadline, interrupt):
    await _await_interruptibly(
        asyncio.sleep(seconds),
        deadline=deadline,
        request_deadline=deadline,
        interrupt=interrupt,
    )


async def request(
    method,
    url,
    *,
    deadline,
    request_timeout,
    headers=None,
    json=None,
    data=None,
    interrupt=None,
    billable_submit=False,
):
    """Perform one asynchronous HTTP operation."""
    if time.monotonic() >= deadline:
        raise TimeoutOrInterruptedError(
            "operation deadline expired before the request",
            reason="operation_deadline",
        )
    interrupt = interrupt or _default_interrupt
    interrupt()
    timeout = aiohttp.ClientTimeout(total=float(request_timeout))
    method = str(method).upper()
    uncertain_post = bool(billable_submit and method == "POST")
    async with aiohttp.ClientSession() as session:
        retry_delays = iter(READ_RETRY_DELAYS if method == "GET" else ())
        while True:
            request_deadline = time.monotonic() + float(request_timeout)
            try:
                response = await _await_interruptibly(
                    session.request(
                        method,
                        url,
                        headers=headers,
                        json=json,
                        data=data,
                        timeout=timeout,
                    ),
                    deadline=deadline,
                    request_deadline=request_deadline,
                    interrupt=interrupt,
                    indeterminate_on_interrupt=uncertain_post,
                )
            except TimeoutOrInterruptedError as exc:
                if exc.reason != "request_timeout":
                    raise
                failure = (
                    IndeterminateSubmitError(
                        "billable submit timed out after its request started"
                    )
                    if uncertain_post
                    else exc
                )
            except asyncio.CancelledError as exc:
                if not uncertain_post:
                    raise
                failure = IndeterminateSubmitError(
                    "billable submit was cancelled after its request started"
                )
                failure.__cause__ = exc
            except aiohttp.InvalidURL as exc:
                failure = LocalValidationError(
                    f"request URL is invalid: {type(exc).__name__}"
                )
            except aiohttp.ClientConnectorError as exc:
                failure = TransientTransportOrServerError(
                    f"connection failed before request write: {type(exc).__name__}"
                )
            except (aiohttp.ClientError, OSError) as exc:
                failure = (
                    IndeterminateSubmitError(
                        "billable submit lost its response after request start"
                    )
                    if uncertain_post
                    else TransientTransportOrServerError(
                        f"transport failed: {type(exc).__name__}"
                    )
                )
            else:
                try:
                    try:
                        body = await _read_body(
                            response,
                            deadline=deadline,
                            request_deadline=request_deadline,
                            interrupt=interrupt,
                            indeterminate_on_interrupt=(
                                uncertain_post and response.status < 400
                            ),
                        )
                    except TimeoutOrInterruptedError as exc:
                        if exc.reason != "request_timeout":
                            raise
                        if response.status >= 400:
                            failure = failure_from_http(response.status)
                        elif uncertain_post:
                            failure = IndeterminateSubmitError(
                                "billable submit response body timed out"
                            )
                        else:
                            failure = exc
                    except asyncio.CancelledError as exc:
                        if not uncertain_post or response.status >= 400:
                            raise
                        failure = IndeterminateSubmitError(
                            "billable submit response body was cancelled"
                        )
                        failure.__cause__ = exc
                    except (aiohttp.ClientError, OSError) as exc:
                        if response.status >= 400:
                            failure = failure_from_http(response.status)
                        elif uncertain_post:
                            failure = IndeterminateSubmitError(
                                "billable submit response body was lost"
                            )
                        else:
                            failure = TransientTransportOrServerError(
                                f"transfer failed: {type(exc).__name__}"
                            )
                    else:
                        if response.status >= 400:
                            failure = failure_from_http(
                                response.status,
                                body[:300].decode("utf-8", errors="replace"),
                            )
                        else:
                            return HttpResponse(response.status, dict(response.headers), body)
                finally:
                    response.release()
            if method != "GET" or not failure.retryable:
                raise failure
            try:
                delay = next(retry_delays)
            except StopIteration:
                raise failure
            await _backoff(delay, deadline=deadline, interrupt=interrupt)


async def download(url, *, deadline, request_timeout, interrupt=None):
    """Download provider output without forwarding provider credentials."""
    response = await request(
        "GET",
        url,
        deadline=deadline,
        request_timeout=request_timeout,
        interrupt=interrupt,
    )
    if not response.body:
        raise EmptyOrMalformedSuccessError("provider output download was empty")
    return response.body


def _download_target(url):
    """Parse an output URL before its resolver is invoked."""
    parsed = urlsplit(str(url))
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise LocalValidationError("output download URL must be absolute HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise LocalValidationError("output download URL must not contain userinfo")

    return parsed


def _validated_download_records(records):
    """Retain only globally routable records from one DNS resolution."""
    try:
        records = tuple(records)
    except TypeError as exc:
        raise LocalValidationError("output download resolver returned invalid records") from exc
    addresses = []
    for record in records:
        try:
            address = ipaddress.ip_address(record[4][0])
        except (IndexError, TypeError, ValueError) as exc:
            raise LocalValidationError("output download resolver returned an invalid address") from exc
        if not address.is_global:
            raise LocalValidationError("output download host resolved to a non-global address")
        addresses.append(address)
    if not addresses:
        raise LocalValidationError("output download host resolved to no addresses")
    return records


def _validated_download_target(url, *, resolver):
    """Compatibility validator for synchronous custom download adapters."""
    parsed = _download_target(url)
    try:
        records = resolver(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise LocalValidationError("output download host could not be resolved") from exc
    records = _validated_download_records(records)
    return parsed, records


async def _resolved_download_target(
    url,
    *,
    resolver,
    deadline,
    request_deadline,
    interrupt,
):
    """Resolve output DNS without allowing it to block the event loop."""
    parsed = _download_target(url)
    try:
        loop = asyncio.get_running_loop()
        if resolver is socket.getaddrinfo:
            resolution = loop.getaddrinfo(
                parsed.hostname,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        else:
            resolution = asyncio.to_thread(
                resolver,
                parsed.hostname,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        records = await _await_interruptibly(
            resolution,
            deadline=deadline,
            request_deadline=request_deadline,
            interrupt=interrupt,
        )
    except (OSError, ValueError) as exc:
        raise LocalValidationError("output download host could not be resolved") from exc
    records = _validated_download_records(records)
    return parsed, records


def validate_download_url(url, *, resolver=socket.getaddrinfo):
    """Refuse SSRF targets before an unauthenticated output GET is opened."""
    parsed, _records = _validated_download_target(url, resolver=resolver)
    return parsed.geturl()


class _PinnedResolver:
    """aiohttp resolver that returns exactly the already-validated addresses."""

    def __init__(self, hostname, records):
        self.hostname = hostname
        self.records = tuple(records)

    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        if host != self.hostname:
            raise OSError("output connector attempted an unexpected hostname")
        return [
            {
                "hostname": self.hostname,
                "host": record[4][0],
                "port": port,
                "family": record[0],
                "proto": record[2],
                "flags": 0,
            }
            for record in self.records
        ]

    async def close(self):
        return None


async def download_stream(url, *, deadline, request_timeout, max_bytes, interrupt=None, resolver=socket.getaddrinfo):
    """Open one validated, no-redirect output stream with a transport-side byte cap."""
    limit = int(max_bytes)
    if limit < 1:
        raise LocalValidationError("output download size cap must be positive")
    if time.monotonic() >= deadline:
        raise TimeoutOrInterruptedError("operation deadline expired before the request", reason="operation_deadline")
    interrupt = interrupt or _default_interrupt
    interrupt()
    request_deadline = time.monotonic() + float(request_timeout)
    parsed, records = await _resolved_download_target(
        url,
        resolver=resolver,
        deadline=deadline,
        request_deadline=request_deadline,
        interrupt=interrupt,
    )
    url = parsed.geturl()
    timeout = aiohttp.ClientTimeout(total=float(request_timeout))
    response_headers = {}

    async def chunks():
        try:
            # Allocate the connector only when iteration starts. Returning and
            # abandoning this lazy stream therefore cannot leak a connector.
            connector = aiohttp.TCPConnector(
                resolver=_PinnedResolver(parsed.hostname, records), use_dns_cache=False
            )
            async with aiohttp.ClientSession(connector=connector) as session:
                response = await _await_interruptibly(
                    session.request("GET", url, headers=None, timeout=timeout, allow_redirects=False),
                    deadline=deadline,
                    request_deadline=request_deadline,
                    interrupt=interrupt,
                )
                try:
                    if 300 <= response.status < 400:
                        raise LocalValidationError("output download redirect is refused")
                    if response.status >= 400:
                        raise failure_from_http(response.status)
                    # Keep the exact response metadata on the stream object.  The
                    # mapping is populated before the zero-byte metadata barrier is
                    # yielded, so downstream validation can inspect headers without
                    # buffering any provider body bytes.
                    response_headers.update(dict(response.headers))
                    declared = response.headers.get("Content-Length")
                    if declared is not None:
                        try:
                            declared_size = int(declared)
                        except (TypeError, ValueError) as exc:
                            raise LocalValidationError("output download has invalid Content-Length") from exc
                        if declared_size < 0 or declared_size > limit:
                            raise LocalValidationError("declared output download exceeds size cap")
                    yield b""
                    total = 0
                    iterator = response.content.iter_chunked(64 * 1024).__aiter__()
                    while True:
                        try:
                            chunk = await _await_interruptibly(
                                iterator.__anext__(),
                                deadline=deadline,
                                request_deadline=request_deadline,
                                interrupt=interrupt,
                            )
                        except StopAsyncIteration:
                            return
                        total += len(chunk)
                        if total > limit:
                            raise LocalValidationError("output download exceeded size cap")
                        yield chunk
                finally:
                    response.release()
        except aiohttp.InvalidURL as exc:
            raise LocalValidationError(
                f"output download URL is invalid: {type(exc).__name__}"
            ) from exc
        except (aiohttp.ClientError, OSError) as exc:
            raise TransientTransportOrServerError(
                f"output download transport failed: {type(exc).__name__}"
            ) from exc

    return HttpDownloadStream(response_headers, chunks())

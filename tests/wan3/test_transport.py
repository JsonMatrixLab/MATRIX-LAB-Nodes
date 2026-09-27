import json
from pathlib import Path

import pytest

from matrix_lab_nodes._core.wan3.media import PreparedMedia
from matrix_lab_nodes._core.wan3.transport import HTTPResult, PinnedHTTPS, TransportError, WaveSpeedClient, _validated_target


def public_resolver(host, port, *, type):
    return [(None, None, None, None, ("8.8.8.8", port))]


class FakeResponse:
    def __init__(self, status=200, body=b"", headers=()):
        self.status = status
        self.body = body
        self.headers = list(headers)
        self._cursor = 0

    def read(self, amount=-1):
        if amount < 0:
            amount = len(self.body)
        part = self.body[self._cursor:self._cursor + amount]
        self._cursor += len(part)
        return part

    def getheaders(self):
        return self.headers

    def getheader(self, name):
        return next((value for key, value in self.headers if key.lower() == name.lower()), None)


class FakeConnection:
    def __init__(self, response=None, *, send_error=False):
        self.response = response or FakeResponse()
        self.send_error = send_error
        self.headers = []
        self.sent = bytearray()
        self.closed = False

    def putrequest(self, *args, **kwargs):
        self.request_line = args

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self):
        pass

    def send(self, data):
        if self.send_error:
            raise OSError("sentinel transport failure")
        self.sent.extend(data)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def test_connection_closes_when_request_send_fails():
    connection = FakeConnection(send_error=True)
    client = PinnedHTTPS(resolver=public_resolver, connection_factory=lambda *args: connection)
    with pytest.raises(OSError, match="sentinel"):
        client.request("POST", "https://api.example.test/path", body=b"body")
    assert connection.closed


def test_download_setup_failure_closes_connection(tmp_path):
    connection = FakeConnection()
    client = PinnedHTTPS(resolver=public_resolver, connection_factory=lambda *args: connection)
    blocker = tmp_path / "not-a-directory"
    blocker.write_bytes(b"fixture")
    with pytest.raises(OSError):
        client.download("https://cdn.example.test/result", blocker / "video.mp4")
    assert connection.closed


def download_client(response):
    connection = FakeConnection(response)
    client = PinnedHTTPS(resolver=public_resolver, connection_factory=lambda *args: connection)
    return client, connection


@pytest.mark.parametrize("response", [
    FakeResponse(206, b"partial", [("Content-Length", "7")]),
    FakeResponse(200, b"partial", [("Content-Length", "7"), ("Content-Range", "bytes 0-6/20")]),
])
def test_partial_or_ranged_download_refuses_replacement_and_cleans_temp(tmp_path, response):
    client, connection = download_client(response)
    destination = tmp_path / "result.mp4"
    destination.write_bytes(b"previous-result")
    with pytest.raises(TransportError, match="partial|range"):
        client.download("https://cdn.example.test/result", destination)
    assert destination.read_bytes() == b"previous-result"
    assert list(tmp_path.glob("*.partial")) == []
    assert connection.closed


@pytest.mark.parametrize("length", ["malformed", "-1", "5"])
def test_invalid_or_mismatched_content_length_refuses_replacement(tmp_path, length):
    client, connection = download_client(FakeResponse(200, b"1234", [("Content-Length", length)]))
    destination = tmp_path / "result.mp4"
    destination.write_bytes(b"previous-result")
    with pytest.raises(TransportError, match="Content-Length|length|size"):
        client.download("https://cdn.example.test/result", destination)
    assert destination.read_bytes() == b"previous-result"
    assert list(tmp_path.glob("*.partial")) == []
    assert connection.closed


def test_known_length_truncated_download_does_not_replace_destination(tmp_path):
    client, _ = download_client(FakeResponse(200, b"abc", [("Content-Length", "4")]))
    destination = tmp_path / "result.mp4"
    destination.write_bytes(b"original")
    with pytest.raises(TransportError, match="Content-Length"):
        client.download("https://cdn.example.test/result", destination)
    assert destination.read_bytes() == b"original"


def test_missing_content_length_is_allowed_but_response_cap_still_applies(tmp_path):
    client, _ = download_client(FakeResponse(200, b"1234"))
    destination = tmp_path / "result.mp4"
    assert client.download("https://cdn.example.test/result", destination, max_bytes=4) == destination
    assert destination.read_bytes() == b"1234"

    too_large, _ = download_client(FakeResponse(200, b"12345"))
    prior = tmp_path / "prior.mp4"
    prior.write_bytes(b"old")
    with pytest.raises(TransportError, match="size limit"):
        too_large.download("https://cdn.example.test/result", prior, max_bytes=4)
    assert prior.read_bytes() == b"old"
    assert list(tmp_path.glob("*.partial")) == []


def test_matching_content_length_replaces_destination_at_exact_cap(tmp_path):
    client, connection = download_client(FakeResponse(200, b"1234", [("Content-Length", "4")]))
    destination = tmp_path / "result.mp4"
    destination.write_bytes(b"previous-result")
    assert client.download("https://cdn.example.test/result", destination, max_bytes=4) == destination
    assert destination.read_bytes() == b"1234"
    assert list(tmp_path.glob("*.partial")) == []
    assert connection.closed


def test_cancelled_download_cleans_partial_and_preserves_destination(tmp_path):
    client, connection = download_client(FakeResponse(200, b"x" * (2 * 1024 * 1024)))
    destination = tmp_path / "result.mp4"
    destination.write_bytes(b"original")
    counter = {"n": 0}

    def cancel():
        counter["n"] += 1
        if counter["n"] == 2:
            raise InterruptedError("cancelled")

    with pytest.raises(InterruptedError, match="cancelled"):
        client.download("https://cdn.example.test/result", destination, check_cancelled=cancel)
    assert destination.read_bytes() == b"original"
    assert list(tmp_path.glob("*.partial")) == []
    assert connection.closed


def test_request_setup_validation_happens_before_connection_creation():
    created = []

    def make_connection(*args):
        created.append(FakeConnection())
        return created[-1]

    client = PinnedHTTPS(resolver=public_resolver, connection_factory=make_connection)
    with pytest.raises(TransportError, match="Duplicate or overridden"):
        client.request("GET", "https://api.example.test/path", headers={"Host": "wrong.example.test"})
    assert created == []


def test_private_dns_and_redirects_are_refused_without_following():
    with pytest.raises(TransportError, match="non-global"):
        _validated_target("https://storage.example.test/object", lambda *a, **k: [(None, None, None, None, ("127.0.0.1", 443))])
    connection = FakeConnection(FakeResponse(302, b""))
    client = PinnedHTTPS(resolver=public_resolver, connection_factory=lambda *args: connection)
    response = client.request("GET", "https://api.example.test/path")
    assert response.status == 302
    assert len(connection.headers) == 2
    assert connection.closed


class FakeHTTP:
    resolver = staticmethod(public_resolver)

    def __init__(self, *, ticket_headers=None, put_status=200):
        self.ticket_headers = ticket_headers if ticket_headers is not None else {"content-type": "image/png", "content-length": "4", "x-amz-meta-test": "ok"}
        self.put_status = put_status
        self.calls = []

    def request(self, method, url, *, headers=None, body=None, source_path=None, max_bytes, check_cancelled=None):
        self.calls.append((method, url, dict(headers or {}), body, source_path))
        if method == "POST" and url.endswith("/media/uploads"):
            return HTTPResult(200, {}, json.dumps({"code": 200, "data": {"upload": {"method": "PUT", "url": "https://store.example.test/opaque?sig=sentinel", "headers": self.ticket_headers}, "download_url": "https://asset.example.test/item"}}).encode())
        if method == "PUT":
            return HTTPResult(self.put_status, {}, b"")
        raise AssertionError(f"unexpected request {method} {url}")


def media_file(tmp_path, content=b"1234", mime="image/png"):
    path = tmp_path / "input.bin"
    path.write_bytes(content)
    return PreparedMedia(path, "input.png", mime, "digest", len(content))


def test_ticket_content_headers_are_canonical_single_and_preserved(tmp_path):
    http = FakeHTTP(ticket_headers={"content-type": "image/png", "content-length": "4", "x-amz-meta-test": "keep"})
    url = WaveSpeedClient("sentinel-api-key", http=http).upload(media_file(tmp_path), account_scope="scope")
    put = [call for call in http.calls if call[0] == "PUT"][0]
    headers = put[2]
    normalized = [name.lower() for name in headers]
    assert normalized.count("content-type") == 1
    assert normalized.count("content-length") == 1
    assert headers["content-type"] == "image/png"
    assert headers["content-length"] == "4"
    assert "authorization" not in normalized
    assert "cookie" not in normalized
    assert headers["x-amz-meta-test"] == "keep"
    assert url == "https://asset.example.test/item"


@pytest.mark.parametrize("ticket_headers", [
    {"Content-Type": "image/png", "content-type": "image/png"},
    {"content-type": "application/octet-stream", "content-length": "4"},
    {"content-type": "image/png", "content-length": "5"},
    {"Authorization": "Bearer sentinel", "content-length": "4"},
])
def test_bad_upload_ticket_headers_block_put_and_generation(tmp_path, ticket_headers):
    http = FakeHTTP(ticket_headers=ticket_headers)
    with pytest.raises(TransportError):
        WaveSpeedClient("sentinel-api-key", http=http).upload(media_file(tmp_path), account_scope="scope")
    assert not any(call[0] == "PUT" for call in http.calls)


def test_ticket_lowercase_content_type_is_not_overridden(tmp_path):
    http = FakeHTTP(ticket_headers={"content-type": "image/png", "content-length": "4"})
    WaveSpeedClient("sentinel-api-key", http=http).upload(media_file(tmp_path), account_scope="scope")
    put = [call for call in http.calls if call[0] == "PUT"][0]
    assert put[2]["content-type"] == "image/png"
    assert len([key for key in put[2] if key.lower() == "content-type"]) == 1


def test_ticket_if_none_match_wildcard_is_forwarded_without_authentication(tmp_path):
    http = FakeHTTP(ticket_headers={"content-type": "image/png", "content-length": "4", "If-None-Match": "*"})
    WaveSpeedClient("sentinel-api-key", http=http).upload(media_file(tmp_path), account_scope="scope")
    put = [call for call in http.calls if call[0] == "PUT"][0]
    assert put[2]["If-None-Match"] == "*"
    assert "authorization" not in {name.lower() for name in put[2]}


@pytest.mark.parametrize("value", ["foo", "W/\"tag\"", ""])
def test_ticket_if_none_match_non_wildcard_is_rejected_before_put(tmp_path, value):
    http = FakeHTTP(ticket_headers={"content-type": "image/png", "content-length": "4", "If-None-Match": value})
    with pytest.raises(TransportError, match="If-None-Match"):
        WaveSpeedClient("sentinel-api-key", http=http).upload(media_file(tmp_path), account_scope="scope")
    assert not any(call[0] == "PUT" for call in http.calls)


def test_upload_failure_never_reaches_generation_or_retries_put(tmp_path):
    http = FakeHTTP(put_status=500)
    with pytest.raises(TransportError, match="no generation request"):
        WaveSpeedClient("sentinel-api-key", http=http).upload(media_file(tmp_path), account_scope="scope")
    assert [call[0] for call in http.calls].count("PUT") == 1


def test_cancelled_stream_upload_closes_connection(tmp_path):
    path = tmp_path / "large.bin"
    path.write_bytes(b"x" * (2 * 1024 * 1024))
    connection = FakeConnection()
    client = PinnedHTTPS(resolver=public_resolver, connection_factory=lambda *args: connection)
    counter = {"n": 0}
    def cancel():
        counter["n"] += 1
        if counter["n"] == 2:
            raise InterruptedError("cancelled")
    with pytest.raises(InterruptedError):
        client.request("PUT", "https://storage.example.test/upload", source_path=path, check_cancelled=cancel)
    assert connection.closed

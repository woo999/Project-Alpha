import pytest

from project_alpha import official_source


class Headers:
    def __init__(self, content_type):
        self.content_type = content_type

    def get_content_type(self):
        return self.content_type


class Response:
    def __init__(self, content, url, content_type="application/json"):
        self.content = content
        self.url = url
        self.headers = Headers(content_type)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def geturl(self):
        return self.url

    def read(self, limit):
        return self.content[:limit]


def test_official_download_is_bounded_and_hashed(monkeypatch):
    payload = b'{"stat":"ok"}'
    monkeypatch.setattr(
        official_source,
        "urlopen",
        lambda request, timeout: Response(
            payload, "https://www.tpex.org.tw/openapi/v1/example"
        ),
    )
    result = official_source.fetch_official_source(
        "https://www.tpex.org.tw/openapi/v1/example"
    )
    assert result.content == payload
    assert len(result.sha256) == 64


def test_redirect_to_nonofficial_host_is_rejected(monkeypatch):
    monkeypatch.setattr(
        official_source,
        "urlopen",
        lambda request, timeout: Response(b"payload", "https://example.com/redirect"),
    )
    with pytest.raises(ValueError, match="approved official"):
        official_source.fetch_official_source(
            "https://www.tpex.org.tw/openapi/v1/example"
        )


def test_oversized_or_unexpected_response_is_rejected(monkeypatch):
    monkeypatch.setattr(
        official_source,
        "urlopen",
        lambda request, timeout: Response(b"12345", request.full_url),
    )
    with pytest.raises(ValueError, match="size limit"):
        official_source.fetch_official_source(
            "https://www.tpex.org.tw/openapi/v1/example", max_bytes=4
        )
    monkeypatch.setattr(
        official_source,
        "urlopen",
        lambda request, timeout: Response(
            b"binary", request.full_url, "application/octet-stream"
        ),
    )
    with pytest.raises(ValueError, match="unsupported"):
        official_source.fetch_official_source(
            "https://www.tpex.org.tw/openapi/v1/example"
        )


def test_transient_timeout_is_retried_within_bound(monkeypatch):
    calls = 0

    def flaky(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary timeout")
        return Response(b"[]", request.full_url)

    monkeypatch.setattr(official_source, "urlopen", flaky)
    monkeypatch.setattr(official_source.time, "sleep", lambda seconds: None)
    result = official_source.fetch_official_source(
        "https://www.tpex.org.tw/openapi/v1/example"
    )
    assert result.content == b"[]"
    assert calls == 2

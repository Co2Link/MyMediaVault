from email.message import Message
from urllib.error import HTTPError

import pytest

from app.torrents.provider import HttpTorrentMetadataProvider, TorrentMetadataProviderError


def test_http_provider_returns_parsed_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"d4:infod6:lengthi123e4:name9:video.mp4ee"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return payload

    monkeypatch.setattr("app.torrents.provider.urlopen", lambda request, timeout: FakeResponse())
    provider = HttpTorrentMetadataProvider(["https://resolver.example/{info_hash}"], 1.0)

    metadata = provider.fetch("0123456789ABCDEF0123456789ABCDEF01234567")

    assert metadata.name == "video.mp4"
    assert metadata.size_bytes == 123
    assert metadata.raw == payload


def test_http_provider_falls_back_between_resolvers(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"d4:infod6:lengthi5e4:name5:videoee"
    calls: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return payload

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 404, "missing", hdrs=Message(), fp=None)
        return FakeResponse()

    monkeypatch.setattr("app.torrents.provider.urlopen", fake_urlopen)
    provider = HttpTorrentMetadataProvider(
        ["https://resolver-one.example/{info_hash}", "https://resolver-two.example/{info_hash}"],
        1.0,
    )

    metadata = provider.fetch("0123456789abcdef0123456789abcdef01234567")

    assert len(calls) == 2
    assert metadata.name == "video"


def test_http_provider_raises_when_all_resolvers_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 404, "missing", hdrs=Message(), fp=None)

    monkeypatch.setattr("app.torrents.provider.urlopen", fake_urlopen)
    provider = HttpTorrentMetadataProvider(["https://resolver.example/{info_hash}"], 1.0)

    with pytest.raises(TorrentMetadataProviderError):
        provider.fetch("0123456789abcdef0123456789abcdef01234567")

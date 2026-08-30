from pathlib import Path

from utilities.wiki_sprites import WikiSpriteClient


class FakeResponse:
    content = b"\x89PNG\r\n\x1a\nrest"

    def raise_for_status(self):
        return None

    def json(self):
        return {"query": {"pages": {"1": {"imageinfo": [{"url": "https://example.test/logs.png"}]}}}}


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_download_resolves_and_writes_png(tmp_path: Path):
    session = FakeSession()
    output = WikiSpriteClient(session).download("Logs", tmp_path)
    assert output.name == "Logs.png"
    assert output.read_bytes().startswith(b"\x89PNG")
    assert output.with_suffix(".json").exists()
    assert len(session.calls) == 2


"""Download OSRS item sprites directly from the Old School Wiki."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import requests

WIKI_API = "https://oldschool.runescape.wiki/api.php"
FILE_PATH = "https://oldschool.runescape.wiki/w/Special:FilePath/"
USER_AGENT = "OS-Bot-COLOR/1.0 (local sprite tooling)"


def _filename(name: str) -> str:
    value = re.sub(r"\s+", "_", name.strip())
    return value if value.lower().endswith(".png") else value + ".png"


class WikiSpriteClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def image_url(self, item_name: str) -> str:
        """Resolve a Wiki file URL, falling back to Special:FilePath."""
        file_name = _filename(item_name)
        params = {"action": "query", "titles": f"File:{file_name}", "prop": "imageinfo", "iiprop": "url", "format": "json"}
        response = self.session.get(WIKI_API, params=params, timeout=20)
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo")
            if info:
                return info[0]["url"]
        return FILE_PATH + quote(file_name)

    def download(self, item_name: str, destination: str | Path, *, width: int | None = None, overwrite: bool = False) -> Path:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        stem = Path(_filename(item_name)).stem
        output = destination / f"{stem}.png"
        if output.exists() and not overwrite:
            return output
        url = self.image_url(item_name)
        if width:
            url += ("&" if "?" in url else "?") + f"width={int(width)}"
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"Wiki response for {item_name!r} was not a PNG")
        output.write_bytes(response.content)
        output.with_suffix(".json").write_text(json.dumps({"name": item_name, "url": url}, indent=2) + "\n", encoding="utf-8")
        return output


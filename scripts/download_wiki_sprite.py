"""Download item sprites: python scripts/download_wiki_sprite.py ""Logs""."""

from __future__ import annotations

import argparse
from pathlib import Path

from utilities.wiki_sprites import WikiSpriteClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Download OSRS Wiki item sprites as PNG templates")
    parser.add_argument("items", nargs="+", help="Item names, e.g. Logs or Dragon axe")
    parser.add_argument("--output", type=Path, default=Path("src/images/bot/items"))
    parser.add_argument("--width", type=int, default=None, help="Optional Wiki resize width")
    parser.add_argument("--force", action="store_true", help="Overwrite existing sprites")
    args = parser.parse_args()
    client = WikiSpriteClient()
    for item in args.items:
        print(client.download(item, args.output, width=args.width, overwrite=args.force))


if __name__ == "__main__":
    main()


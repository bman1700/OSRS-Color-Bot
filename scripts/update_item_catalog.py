"""Refresh the local item name/ID catalog from the Wiki-backed price API."""

from __future__ import annotations

import argparse
from pathlib import Path

import requests

from utilities.item_catalog import ItemCatalog

MAPPING_URL = "https://prices.runescape.wiki/api/v1/osrs/mapping"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the OSRS item name/ID catalog")
    parser.add_argument("--output", type=Path, default=Path("src/data/items.json"))
    args = parser.parse_args()
    response = requests.get(MAPPING_URL, headers={"User-Agent": "OS-Bot-COLOR/1.0"}, timeout=30)
    response.raise_for_status()
    path = ItemCatalog.from_wiki_mapping(response.json()).to_file(args.output)
    print(f"Wrote {len(ItemCatalog.from_file(path))} items to {path}")


if __name__ == "__main__":
    main()


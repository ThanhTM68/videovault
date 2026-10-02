"""Small synthetic metadata shared by deterministic downloader tests."""

import json
from pathlib import Path

URL = "https://www.youtube.com/watch?v=fixture-video"
FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/downloader/metadata.json").read_text(encoding="utf-8")
)

from copy import deepcopy

CHANNEL = "UC" + "a" * 22
SOURCE = "https://www.youtube.com/@research/videos"
IDS = ["clip0000001", "clip0000002", "clip0000003", "clip0000004"]


def entry(identity: str, duration: float | None = 30, **kwargs) -> dict[str, object]:
    return {
        "id": identity,
        "url": "https://www.youtube.com/watch?v=" + identity,
        "ie_key": "Youtube",
        "_type": "url",
        "channel_id": CHANNEL,
        "channel": "Research creator",
        "title": "Public fixture " + identity,
        "duration": duration,
        "view_count": 100,
        "upload_date": "20260901",
        **kwargs,
    }


DATA = {
    "_type": "playlist",
    "extractor_key": "YoutubeTab",
    "id": CHANNEL,
    "channel_id": CHANNEL,
    "channel": "Research channel",
    "webpage_url": SOURCE,
    "entries": [
        entry(IDS[0], 10),
        entry(IDS[1], 20),
        entry(IDS[2], None, view_count=None, upload_date=None),
        entry(IDS[0], 10),
        entry(IDS[3], 60),
    ],
}


class SourceCore:
    def __init__(self, data=None):
        self.data = deepcopy(DATA if data is None else data)
        self.calls = 0

    def list_channel(self, url):
        self.calls += 1
        return deepcopy(self.data)

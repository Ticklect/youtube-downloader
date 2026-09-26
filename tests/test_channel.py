import pytest

import helper.channel as channel


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.youtube.com/@creator", "https://www.youtube.com/@creator/videos"),
        ("https://youtube.com/channel/UC123", "https://www.youtube.com/channel/UC123/videos"),
        ("https://www.youtube.com/c/CreatorName/", "https://www.youtube.com/c/CreatorName/videos"),
        ("https://www.youtube.com/user/CreatorName", "https://www.youtube.com/user/CreatorName/videos"),
        ("https://www.youtube.com/@creator/videos", "https://www.youtube.com/@creator/videos"),
    ],
)
def test_normalize_channel_url_accepts_supported_channel_forms(raw, expected):
    assert channel.normalize_channel_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "youtube.com/@creator",
        "ftp://youtube.com/@creator",
        "https://example.com/@creator",
        "https://www.youtube.com/watch?v=abc123",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/",
    ],
)
def test_normalize_channel_url_rejects_non_channel_inputs(raw):
    with pytest.raises(ValueError):
        channel.normalize_channel_url(raw)


class FakeYDL:
    def __init__(self, options, payload):
        self.options = options
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        assert url.endswith("/videos")
        assert download is False
        assert self.options["extract_flat"] is True
        return self.payload


def test_load_channel_returns_normalized_video_info_and_skips_bad_entries(monkeypatch):
    payload = {
        "channel": "Test Creator",
        "entries": [
            {
                "id": "abc123",
                "title": "First video",
                "url": "abc123",
                "thumbnail": "https://img.example/1.jpg",
                "duration": 42,
            },
            None,
            {"id": None, "title": "Broken"},
            {
                "id": "def456",
                "title": "Second video",
                "webpage_url": "https://www.youtube.com/watch?v=def456",
                "thumbnails": [{"url": "https://img.example/2.jpg"}],
                "duration": None,
            },
        ],
    }
    monkeypatch.setattr(channel, "YoutubeDL", lambda options: FakeYDL(options, payload))

    result = channel.load_channel("https://www.youtube.com/@creator")

    assert result.channel_name == "Test Creator"
    assert [item.video_id for item in result.videos] == ["abc123", "def456"]
    assert result.videos[0].url == "https://www.youtube.com/watch?v=abc123"
    assert result.videos[1].thumbnail == "https://img.example/2.jpg"
    assert result.videos[1].duration is None

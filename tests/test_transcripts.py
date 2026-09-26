from helper.transcripts import vtt_to_text


def test_vtt_to_text_removes_metadata_tags_and_duplicate_adjacent_lines():
    vtt = """WEBVTT

1
00:00:00.000 --> 00:00:02.000 align:start
<c>Hello &amp; welcome</c>

2
00:00:02.000 --> 00:00:04.000
Hello &amp; welcome
Next line

NOTE ignored metadata
"""

    assert vtt_to_text(vtt) == "Hello & welcome\nNext line"

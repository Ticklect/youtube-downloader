from __future__ import annotations

import html
import re


TIMESTAMP = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s+-->")
TAG = re.compile(r"<[^>]+>")


def vtt_to_text(vtt: str) -> str:
    output: list[str] = []
    previous: str | None = None
    in_note = False
    for raw in vtt.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            in_note = False
            continue
        if line == "WEBVTT" or line.startswith(("Kind:", "Language:")):
            continue
        if line.startswith("NOTE"):
            in_note = True
            continue
        if in_note or TIMESTAMP.match(line) or line.isdigit():
            continue
        line = html.unescape(TAG.sub("", line)).strip()
        if not line or line == previous:
            continue
        output.append(line)
        previous = line
    return "\n".join(output)

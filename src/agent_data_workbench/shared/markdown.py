"""Escape supplied text and delimit literal blocks in Markdown reports."""

from __future__ import annotations

import re


def md(value: str) -> str:
    # Keep supplied text as text instead of turning trace content into HTML/links/images.
    return re.sub(r"([\\\x60*_{}\[\]()<>#!|])", r"\\\1", value).replace("\n", " ")


def fence(value: str, language: str = "") -> str:
    marker = chr(96) * max(
        3, max((len(m.group()) + 1 for m in re.finditer(r"`+", value)), default=3)
    )
    return marker + language + "\n" + value + "\n" + marker

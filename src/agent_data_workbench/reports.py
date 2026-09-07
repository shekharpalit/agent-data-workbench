"""Escape untrusted text in Markdown reports."""

import re


def md(value: str) -> str:
    # Keep supplied text as text instead of turning trace content into HTML/links/images.
    return re.sub(r"([\\\x60*_{}\[\]()<>#!|])", r"\\\1", value).replace("\n", " ")

"""Language-neutral lexical tokens from the values selected by a JSON pointer.

No stop words or field names are excluded. Negation, numeric tokens, identifiers
and one-character words can distinguish agent outcomes. This is lexical
preprocessing, not language understanding or semantic similarity.
"""

import re
from collections.abc import Iterator
from typing import Any

from agent_data_workbench.shared.json import json_text

# The explorer reports this preview budget and the IDs whose selected text exceeds it.
CLUSTER_TEXT_LIMIT = 20_000
_WORD = re.compile(r"\w+(?:['’]\w+)*")


def text_values(value: Any) -> Iterator[str]:
    """Visit every selected value, preserving order; field names are not content."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from text_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from text_values(item)
    else:
        yield json_text(value)


def words(value: Any) -> tuple[list[str], bool]:
    """Tokenize the preview prefix, omitting a word split by the character budget."""
    remaining, tokens = CLUSTER_TEXT_LIMIT, []
    for text in text_values(value):
        clipped = len(text) > remaining
        # Look ahead through a word character or an apostrophe plus its next character.
        prefix = text[: remaining + 2]
        for match in _WORD.finditer(prefix):
            if match.end() <= remaining:
                tokens.append(match.group().casefold())
        if clipped:
            return tokens, True
        remaining -= len(text)
    return tokens, False

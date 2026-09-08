"""Language-neutral lexical tokens from the values selected by a JSON pointer.

No stop words or field names are excluded. Negation, numeric tokens, identifiers
and one-character words can distinguish agent outcomes. This is lexical
preprocessing, not language understanding or semantic similarity.
"""

import re
from collections.abc import Iterator
from typing import Any

from agent_data_workbench.shared.json import json_text

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


def words(value: Any) -> Iterator[str]:
    """Tokenize every selected value without dropping the end of long runs."""
    for text in text_values(value):
        for match in _WORD.finditer(text):
            yield match.group().casefold()

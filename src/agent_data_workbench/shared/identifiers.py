"""UUID identities serialized as canonical strings at JSON and file boundaries."""

from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BeforeValidator, TypeAdapter, WithJsonSchema

_uuid = TypeAdapter(UUID)


def canonical_uuid(value: str | UUID) -> str:
    return str(_uuid.validate_python(value))


UUIDString = Annotated[
    str, BeforeValidator(canonical_uuid), WithJsonSchema({"type": "string", "format": "uuid"})
]


def new_id() -> str:
    return str(uuid4())


def stable_id(kind: str, content: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"agent-data-workbench:{kind}:{content}"))

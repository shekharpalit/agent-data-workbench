"""Stable UUIDs keep test relationships readable without legacy production IDs."""

from uuid import NAMESPACE_URL, UUID, uuid5


def uid(label: str) -> str:
    try:
        return str(UUID(label))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, "workbench-test:" + label))

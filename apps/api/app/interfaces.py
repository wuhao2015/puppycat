from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DataSource(Protocol):
    """Common contract every external data source implements.

    The concrete query methods differ per source (Places searches POIs,
    web search runs freshness queries, weather fetches forecasts), but the
    uniform surface lets the pipeline register, enable/disable, and report on
    sources consistently. Adding Reddit or another source later means
    implementing this protocol and nothing else changes.
    """

    name: str

    def is_configured(self) -> bool:
        """Whether the source has the credentials/config needed to run."""
        ...

from __future__ import annotations

from typing import Protocol, TypedDict


class SourceItem(TypedDict):
    """Normalized data item shared across all sources."""

    name: str       # marker label (e.g. "中山南路 外交部")
    address: str    # full address (e.g. "中正區中山南路 外交部")
    lat: float      # latitude
    lng: float      # longitude
    category: str   # e.g. "trash_bin", "toilet"
    note: str       # extra info


class DataSource(Protocol):
    """Interface that every data source must implement."""

    name: str

    async def check(self, state: dict) -> bool:
        """Lightweight probe. Return True if the source has new data.

        Args:
            state: Previously saved state dict (empty on first run).
        """
        ...

    async def fetch(self) -> tuple[list[SourceItem], dict]:
        """Download and normalize data.

        Returns:
            A tuple of (items, new_state) where new_state will be persisted
            for the next check() call.
        """
        ...

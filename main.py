from __future__ import annotations

import asyncio
import logging
from typing import Any

import yaml

from pipeline.diff import compute_diff
from pipeline.notify import notify_update
from pipeline.sheet import get_gspread_client, update_sheet
from pipeline.state import read_data, read_state, write_data, write_state
from settings import Settings
from sources.base import DataSource
from sources.toilets import ToiletSource
from sources.trash_bins import TrashBinSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SOURCE_REGISTRY: dict[str, type] = {
    "trash_bins": TrashBinSource,
    "toilets": ToiletSource,
}


async def run_source(
    source: DataSource, config: dict[str, Any], settings: Settings, gs_client: Any
) -> None:
    """Run the full pipeline for a single source."""
    logger.info(f"[{source.name}] Checking for updates...")

    state = read_state(source.name)

    if not await source.check(state):
        logger.info(f"[{source.name}] No updates found, skipping.")
        return

    logger.info(f"[{source.name}] Update detected, fetching...")
    items, new_state = await source.fetch()
    logger.info(f"[{source.name}] Fetched {len(items)} items.")

    old_data = read_data(source.name)
    diff = compute_diff(old_data, items)
    logger.info(f"[{source.name}] Diff: {diff.summary}")

    if not diff.has_changes and old_data:
        logger.info(f"[{source.name}] Data identical, skipping sheet update.")
        write_state(source.name, new_state)
        return

    # Update Google Sheet
    await asyncio.to_thread(
        update_sheet, gs_client, config["sheet_id"], config["sheet_name"], items
    )
    logger.info(f"[{source.name}] Google Sheet updated.")

    # Notify via GitHub Issue
    summary = diff.summary if old_data else f"初次匯入 {len(items)} 筆資料"
    await notify_update(
        source.name,
        summary,
        token=settings.github_token,
        repository=settings.github_repository,
    )

    # Persist state and data (last — so failures above cause retry)
    write_state(source.name, new_state)
    write_data(source.name, items)
    logger.info(f"[{source.name}] State saved.")


async def main() -> None:
    settings = Settings()

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    gs_client = get_gspread_client(settings.google_service_account_key)

    tasks = []
    source_names = []
    for name, source_config in config["sources"].items():
        if not source_config.get("enabled", False):
            logger.info(f"[{name}] Disabled, skipping.")
            continue
        if name not in SOURCE_REGISTRY:
            logger.warning(f"[{name}] Unknown source, skipping.")
            continue
        source = SOURCE_REGISTRY[name]()
        tasks.append(run_source(source, source_config, settings, gs_client))
        source_names.append(name)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for name, result in zip(source_names, results):
        if isinstance(result, Exception):
            logger.error(f"[{name}] Source failed: {result}", exc_info=result)


if __name__ == "__main__":
    asyncio.run(main())

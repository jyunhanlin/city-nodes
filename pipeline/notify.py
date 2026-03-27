from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


async def notify_update(
    source_name: str,
    summary: str,
    *,
    token: str,
    repository: str,
) -> None:
    """Open a GitHub Issue to notify the user of data updates.

    Silently skips if token or repository is not configured (local dev).
    """
    if not token or not repository:
        print(f"[{source_name}] {summary} (GitHub notification skipping — missing token or repo)")
        return

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{repository}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "title": f"[city-nodes] {source_name} 資料更新",
                "body": (
                    f"## 變更摘要\n\n"
                    f"{summary}\n\n"
                    f"請到 Google My Maps 點「重新匯入並合併」→「重新匯入」更新地圖。"
                ),
            },
        )
        resp.raise_for_status()
        logger.info(f"[{source_name}] GitHub Issue #{resp.json()['number']} created")

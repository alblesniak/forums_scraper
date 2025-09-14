from __future__ import annotations

import asyncio
from typing import Any, Dict

from forums_scraper.fs_core.config import AppConfig, load_config
from forums_scraper.fs_core.runner import AnalysisRunner


class AnalysisPipeline:
    def __init__(self, config_path: str | None = None):
        self.config_path = config_path
        self.app_config: AppConfig | None = None
        self.runner: AnalysisRunner | None = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("FS_CONFIG_PATH"))

    async def open_spider(self, spider):
        if not self.config_path:
            return
        self.app_config = load_config(self.config_path)
        if not self.app_config.analysis.enabled:
            return
        self.runner = AnalysisRunner(self.app_config.analysis)
        await self.runner.setup()

    async def close_spider(self, spider):
        if self.runner:
            await self.runner.close()

    async def process_item(self, item: Dict[str, Any], spider):
        if not self.runner:
            return item
        results = await self.runner.run_all(item)
        if results:
            # scal wyniki w polu analysis
            existing = item.get("analysis") or {}
            if isinstance(existing, dict):
                existing.update(results)
                item["analysis"] = existing
            else:
                item["analysis"] = results
        return item



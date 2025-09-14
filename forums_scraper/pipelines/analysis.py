from __future__ import annotations

import asyncio
from typing import Any, Dict

from core.config import AppConfig, load_config
from core.runner import AnalysisRunner


class AnalysisPipeline:
    def __init__(self, config_path: str | None = None):
        self.config_path = config_path
        self.app_config: AppConfig | None = None
        self.runner: AnalysisRunner | None = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("FS_CONFIG_PATH"))

    def open_spider(self, spider):
        spider.logger.info(f"🔬 AnalysisPipeline.open_spider: config_path={self.config_path}")
        if not self.config_path:
            spider.logger.warning("❌ AnalysisPipeline: Brak config_path - analiza wyłączona")
            return
        self.app_config = load_config(self.config_path)
        if not self.app_config.analysis.enabled:
            spider.logger.warning("❌ AnalysisPipeline: Analiza wyłączona w konfiguracji")
            return
        spider.logger.info("✅ AnalysisPipeline: Inicjalizacja runnera")
        self.runner = AnalysisRunner(self.app_config.analysis)
        # Uruchom setup asynchronicznie w istniejącym event loop
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Event loop już działa - użyj create_task
                task = asyncio.create_task(self.runner.setup())
                # Czekaj na zakończenie synchronicznie
                while not task.done():
                    import time
                    time.sleep(0.01)
                if task.exception():
                    raise task.exception()
                spider.logger.info("✅ AnalysisPipeline: Runner gotowy (async)")
            else:
                # Event loop nie działa - użyj run
                asyncio.run(self.runner.setup())
                spider.logger.info("✅ AnalysisPipeline: Runner gotowy (sync)")
        except Exception as e:
            spider.logger.error(f"❌ AnalysisPipeline: Błąd inicjalizacji: {e}")
            self.runner = None

    def close_spider(self, spider):
        if self.runner:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Event loop już działa - użyj create_task
                    task = asyncio.create_task(self.runner.close())
                    # Czekaj na zakończenie synchronicznie
                    while not task.done():
                        import time
                        time.sleep(0.01)
                    if task.exception():
                        spider.logger.error(f"❌ AnalysisPipeline: Błąd zamykania: {task.exception()}")
                else:
                    # Event loop nie działa - użyj run
                    asyncio.run(self.runner.close())
                spider.logger.info("✅ AnalysisPipeline: Runner zamknięty")
            except Exception as e:
                spider.logger.error(f"❌ AnalysisPipeline: Błąd zamykania: {e}")

    def process_item(self, item: Dict[str, Any], spider):
        if not self.runner:
            spider.logger.debug("❌ AnalysisPipeline.process_item: Brak runnera")
            return item
        
        # Analizuj tylko ForumPostItem (posty mają treść do analizy)
        if not hasattr(item, '__class__') or item.__class__.__name__ != 'ForumPostItem':
            spider.logger.debug(f"⏭️ AnalysisPipeline.process_item: Pomijam {type(item).__name__} - nie jest ForumPostItem")
            return item
            
        spider.logger.info(f"🔬 AnalysisPipeline.process_item: Analizuję {type(item).__name__} - {item.get('username', 'unknown')}")
        # Uruchom analizę asynchronicznie w istniejącym event loop
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Event loop już działa - użyj create_task
                task = asyncio.create_task(self.runner.run_all(item))
                # Czekaj na zakończenie synchronicznie
                while not task.done():
                    import time
                    time.sleep(0.01)
                if task.exception():
                    spider.logger.error(f"❌ AnalysisPipeline.process_item: Błąd analizy: {task.exception()}")
                    return item
                results = task.result()
            else:
                # Event loop nie działa - użyj run
                results = asyncio.run(self.runner.run_all(item))
            
            if results:
                spider.logger.info(f"✅ AnalysisPipeline.process_item: Wyniki analizy: {list(results.keys())}")
                # scal wyniki w polu analysis
                existing = item.get("analysis") or {}
                if isinstance(existing, dict):
                    existing.update(results)
                    item["analysis"] = existing
                else:
                    item["analysis"] = results
            else:
                spider.logger.warning("❌ AnalysisPipeline.process_item: Brak wyników analizy")
        except Exception as e:
            spider.logger.error(f"❌ AnalysisPipeline.process_item: Błąd analizy: {e}")
        return item



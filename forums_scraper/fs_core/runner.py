from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import AnalysisConfig, AnalyzerConfig
from .protocol import Analyzer
from .registry import load_analyzers


class AnalysisRunner:
    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(max(1, int(config.concurrency or 1)))
        self.analyzers: List[Analyzer] = []

    async def setup(self) -> None:
        if not self.config.enabled:
            return
        names = [a.name for a in self.config.analyzers]
        self.analyzers = load_analyzers(names)
        # Ustaw parametry konstruktorów jeśli definiowane w configu
        # Przyjmujemy, że klasy wspierają **params w __init__
        analyzers_with_params: List[Analyzer] = []
        name_to_params = {a.name: a.params for a in self.config.analyzers}
        for analyzer in self.analyzers:
            params = name_to_params.get(getattr(analyzer, "name", None), {})
            if params:
                # Próbujemy odtworzyć z parametrami
                cls = analyzer.__class__
                analyzer = cls(**params)
            analyzers_with_params.append(analyzer)
        self.analyzers = analyzers_with_params
        await asyncio.gather(*(a.setup() for a in self.analyzers))

    async def close(self) -> None:
        if not self.analyzers:
            return
        await asyncio.gather(*(a.close() for a in self.analyzers))

    async def run_all(self, item: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.config.enabled or not self.analyzers:
            return {}

        async def _run(analyzer: Analyzer) -> Dict[str, Any]:
            async with self.semaphore:
                try:
                    return await analyzer.analyze(item, context)
                except Exception:
                    return {analyzer.name: {"error": True}}

        results = await asyncio.gather(*(_run(a) for a in self.analyzers))
        merged: Dict[str, Any] = {}
        for part in results:
            # part może być {"token_count": 123} albo {"analyzer_name": {...}}
            if not isinstance(part, dict):
                continue
            for k, v in part.items():
                merged[k] = v
        return merged



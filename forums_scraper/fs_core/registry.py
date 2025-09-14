from __future__ import annotations

from importlib.metadata import entry_points
from typing import Iterable, List

from .protocol import Analyzer


def load_analyzers(selected_names: Iterable[str]) -> List[Analyzer]:
    eps = entry_points(group="forums_scraper.analyzers")
    available = {ep.name: ep for ep in eps}
    analyzers: List[Analyzer] = []
    for name in selected_names:
        ep = available.get(name)
        if not ep:
            continue
        cls = ep.load()
        analyzers.append(cls())
    return analyzers



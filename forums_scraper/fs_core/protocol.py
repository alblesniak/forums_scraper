from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class Analyzer(Protocol):
    name: str

    async def setup(self) -> None:
        ...

    async def analyze(self, item: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ...

    async def close(self) -> None:
        ...



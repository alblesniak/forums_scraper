from __future__ import annotations

from typing import Any, Dict, Optional


class TokenCountAnalyzer:
    name = "token_count"

    def __init__(self, model: str = "cl100k_base") -> None:
        self.model = model
        self._enc = None

    async def setup(self) -> None:
        try:
            import tiktoken  # type: ignore
        except Exception as exc:
            raise RuntimeError("Zainstaluj optional dependency: tiktoken") from exc
        self._enc = tiktoken.get_encoding(self.model)

    async def analyze(self, item: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        text = (item.get("content") or item.get("text") or "").strip()
        if not text:
            return {self.name: 0}
        assert self._enc is not None
        tokens = self._enc.encode(text)
        return {self.name: len(tokens)}

    async def close(self) -> None:
        self._enc = None



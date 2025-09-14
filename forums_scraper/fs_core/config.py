from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_yaml(text: str) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("Aby używać konfiguracji YAML zainstaluj pyyaml") from exc
    return yaml.safe_load(text) or {}


def _load_toml(text: str) -> Dict[str, Any]:
    try:
        import tomllib  # py311+
        return tomllib.loads(text)
    except Exception:
        try:
            import tomli  # type: ignore
            return tomli.loads(text)
        except Exception as exc:
            raise RuntimeError("Aby używać konfiguracji TOML zainstaluj tomli (py<3.11)") from exc


@dataclass
class AnalyzerConfig:
    name: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisConfig:
    enabled: bool = False
    analyzers: List[AnalyzerConfig] = field(default_factory=list)
    concurrency: int = 4


@dataclass
class OutputConfig:
    db: Optional[str] = None
    format: Optional[str] = None


@dataclass
class ScrapyConfig:
    concurrent_requests: Optional[int] = None
    autothrottle: Optional[bool] = None


@dataclass
class AppConfig:
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    scrapy: ScrapyConfig = field(default_factory=ScrapyConfig)

    @staticmethod
    def from_mapping(data: Dict[str, Any]) -> "AppConfig":
        analysis_data = data.get("analysis", {}) or {}
        analyzers = [
            AnalyzerConfig(name=a.get("name"), params=a.get("params", {}))
            for a in analysis_data.get("analyzers", [])
            if a and a.get("name")
        ]
        analysis = AnalysisConfig(
            enabled=bool(analysis_data.get("enabled", False)),
            analyzers=analyzers,
            concurrency=int(analysis_data.get("concurrency", 4)),
        )

        output_data = data.get("output", {}) or {}
        output = OutputConfig(
            db=output_data.get("db"),
            format=output_data.get("format"),
        )

        scrapy_data = data.get("scrapy", {}) or {}
        scrapy_cfg = ScrapyConfig(
            concurrent_requests=scrapy_data.get("concurrent_requests"),
            autothrottle=scrapy_data.get("autothrottle"),
        )
        return AppConfig(analysis=analysis, output=output, scrapy=scrapy_cfg)


def load_config(path: str) -> AppConfig:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    text = _read_text(path)
    lowered = path.lower()
    if lowered.endswith(".yaml") or lowered.endswith(".yml"):
        data = _load_yaml(text)
    elif lowered.endswith(".toml"):
        data = _load_toml(text)
    else:
        raise ValueError("Obsługiwane formaty to YAML/TOML")
    return AppConfig.from_mapping(data)



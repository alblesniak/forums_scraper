from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from ..fs_core.config import AppConfig, load_config
from ..fs_core.runner import AnalysisRunner


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def list_analyzers():
    """Wypisz dostępne analizery (entry points)."""
    from importlib.metadata import entry_points

    eps = entry_points(group="forums_scraper.analyzers")
    names = sorted(ep.name for ep in eps)
    for n in names:
        typer.echo(n)


@app.command()
def analyze(
    config: Path = typer.Option(..., exists=True, readable=True, help="Ścieżka do configu YAML/TOML"),
    input_jsonl: Optional[Path] = typer.Option(None, help="Wejście JSONL z polami content/text"),
    output_jsonl: Optional[Path] = typer.Option(None, help="Wyjście JSONL z dodanym polem analysis"),
):
    """Uruchom analizy offline na pliku JSONL (po jednym obiekcie na linię)."""

    cfg = load_config(str(config))
    runner = AnalysisRunner(cfg.analysis)

    async def _run():
        await runner.setup()
        try:
            if not input_jsonl:
                typer.echo("Brak input_jsonl; nic do zrobienia")
                return
            out = open(output_jsonl or (input_jsonl.parent / f"{input_jsonl.stem}.analyzed.jsonl"), "w", encoding="utf-8")
            with open(input_jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line)
                    res = await runner.run_all(obj)
                    if res:
                        obj["analysis"] = {**obj.get("analysis", {}), **res}
                    out.write(json.dumps(obj, ensure_ascii=False) + "\n")
            out.close()
        finally:
            await runner.close()

    asyncio.run(_run())


@app.command()
def crawl(
    spider: str = typer.Option(..., help="Nazwa spidera"),
    config: Optional[Path] = typer.Option(None, help="Ścieżka do configu YAML/TOML"),
    extra: Optional[str] = typer.Option(None, help="Dodatkowe argumenty -a dla spidera, np. key=value,key2=value2"),
):
    """Uruchom Scrapy z opcjonalnym configiem forums-scraper."""
    import subprocess
    import shlex

    args = ["scrapy", "crawl", spider]
    if config:
        args.extend(["-s", f"FS_CONFIG_PATH={config}"])
    if extra:
        for pair in extra.split(","):
            if not pair:
                continue
            args.extend(["-a", pair])
    typer.echo("$ " + " ".join(shlex.quote(a) for a in args))
    subprocess.run(args, check=True)


def run():  # entry point
    app()



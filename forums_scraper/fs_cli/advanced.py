"""
Zaawansowany interfejs CLI dla forums-scraper z pełną konfiguracją i raportowaniem.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Dict, List, Optional, Set

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn, 
    MofNCompleteColumn, 
    Progress, 
    SpinnerColumn, 
    TextColumn, 
    TimeElapsedColumn
)
from rich.table import Table
from rich.text import Text

from ..fs_core.config import AppConfig, load_config


console = Console()
app = typer.Typer(
    name="forums-scraper",
    help="🕷️ Zaawansowany scraper forów religijnych z analizami NLP",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich"
)


class AnalysisType(str, Enum):
    """Typy dostępnych analiz."""
    NONE = "none"
    BASIC_TOKENS = "basic_tokens"
    TOKEN_COUNT = "token_count"
    SPACY_FULL = "spacy_full"
    ALL = "all"


class ForumName(str, Enum):
    """Dostępne fora do scrapowania."""
    DOLINA_MODLITWY = "dolina_modlitwy"
    RADIO_KATOLIK = "radio_katolik"
    WIARA = "wiara"
    Z_CHRYSTUSEM = "z_chrystusem"
    ALL = "all"


# Mapowanie nazw forów na nazwy spiderów
FORUM_SPIDER_MAP = {
    ForumName.DOLINA_MODLITWY: "dolina_modlitwy",
    ForumName.RADIO_KATOLIK: "radio_katolik", 
    ForumName.WIARA: "wiara",
    ForumName.Z_CHRYSTUSEM: "z_chrystusem"
}


def create_analysis_config(
    analysis_types: List[AnalysisType],
    spacy_model: str = "pl_core_news_sm",
    include_sentiment: bool = False,
    batch_size: int = 100
) -> Dict:
    """Tworzy konfigurację analiz na podstawie wybranych typów."""
    if AnalysisType.NONE in analysis_types:
        return {
            "analysis": {
                "enabled": False,
                "analyzers": []
            }
        }
    
    analyzers = []
    
    if AnalysisType.TOKEN_COUNT in analysis_types or AnalysisType.ALL in analysis_types:
        analyzers.append({
            "name": "token_counter",
            "config": {
                "encoding": "cl100k_base"
            }
        })
    
    if AnalysisType.BASIC_TOKENS in analysis_types or AnalysisType.ALL in analysis_types:
        analyzers.append({
            "name": "basic_tokenizer",
            "config": {
                "lowercase": True,
                "remove_punctuation": False,
                "min_token_length": 2
            }
        })
    
    if AnalysisType.SPACY_FULL in analysis_types or AnalysisType.ALL in analysis_types:
        analyzers.append({
            "name": "spacy_analyzer",
            "config": {
                "model": spacy_model,
                "include_sentiment": include_sentiment,
                "batch_size": batch_size,
                "max_length": 1000000
            }
        })
    
    return {
        "analysis": {
            "enabled": True,
            "analyzers": analyzers
        }
    }


def save_config_file(config: Dict, path: Path) -> None:
    """Zapisuje konfigurację do pliku YAML."""
    import yaml
    
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)


def get_available_spiders() -> List[str]:
    """Pobiera listę dostępnych spiderów."""
    try:
        result = subprocess.run(
            ["scrapy", "list"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout.strip().split('\n')
    except (subprocess.CalledProcessError, FileNotFoundError):
        return list(FORUM_SPIDER_MAP.values())


def display_analysis_summary(analysis_types: List[AnalysisType]) -> None:
    """Wyświetla podsumowanie wybranych analiz."""
    table = Table(title="🔬 Wybrane analizy", show_header=True, header_style="bold magenta")
    table.add_column("Typ analizy", style="cyan")
    table.add_column("Opis", style="white")
    table.add_column("Wymagania", style="yellow")
    
    for analysis_type in analysis_types:
        if analysis_type == AnalysisType.NONE:
            table.add_row("Brak", "Tylko scrapowanie bez analiz", "Brak")
        elif analysis_type == AnalysisType.TOKEN_COUNT:
            table.add_row("Liczenie tokenów", "Liczba tokenów OpenAI", "tiktoken")
        elif analysis_type == AnalysisType.BASIC_TOKENS:
            table.add_row("Podstawowa tokenizacja", "Podział na słowa + statystyki", "Brak")
        elif analysis_type == AnalysisType.SPACY_FULL:
            table.add_row("Pełna analiza spaCy", "Lematyzacja, POS, składnia, sentyment", "spacy + model")
        elif analysis_type == AnalysisType.ALL:
            table.add_row("Wszystkie analizy", "Kompletna analiza językowa", "tiktoken + spacy")
    
    console.print(table)


def display_forum_summary(forums: List[ForumName]) -> None:
    """Wyświetla podsumowanie wybranych forów."""
    table = Table(title="🏛️ Wybrane fora", show_header=True, header_style="bold blue")
    table.add_column("Forum", style="cyan")
    table.add_column("Spider", style="white")
    table.add_column("Opis", style="green")
    
    forum_descriptions = {
        ForumName.DOLINA_MODLITWY: "Forum katolickie - Dolina Modlitwy",
        ForumName.RADIO_KATOLIK: "Forum Radia Katolik",
        ForumName.WIARA: "Forum Wiara.pl",
        ForumName.Z_CHRYSTUSEM: "Forum Z Chrystusem"
    }
    
    for forum in forums:
        if forum == ForumName.ALL:
            for f in ForumName:
                if f != ForumName.ALL:
                    spider = FORUM_SPIDER_MAP[f]
                    desc = forum_descriptions.get(f, "Brak opisu")
                    table.add_row(f.value, spider, desc)
        else:
            spider = FORUM_SPIDER_MAP[forum]
            desc = forum_descriptions.get(forum, "Brak opisu")
            table.add_row(forum.value, spider, desc)
    
    console.print(table)


@app.command(name="scrape")
def scrape_forums(
    forums: Annotated[List[ForumName], typer.Option(
        "--forum", "-f",
        help="Wybierz fora do scrapowania (można wybrać wiele)"
    )] = [ForumName.ALL],
    
    analysis: Annotated[List[AnalysisType], typer.Option(
        "--analysis", "-a",
        help="Rodzaje analiz do wykonania (można wybrać wiele)"
    )] = [AnalysisType.BASIC_TOKENS],
    
    config_file: Annotated[Optional[Path], typer.Option(
        "--config", "-c",
        help="Ścieżka do pliku konfiguracyjnego YAML"
    )] = None,
    
    output_dir: Annotated[Path, typer.Option(
        "--output", "-o",
        help="Katalog wyjściowy dla baz danych"
    )] = Path("data/databases"),
    
    spacy_model: Annotated[str, typer.Option(
        "--spacy-model",
        help="Model spaCy do analizy językowej"
    )] = "pl_core_news_sm",
    
    include_sentiment: Annotated[bool, typer.Option(
        "--sentiment/--no-sentiment",
        help="Włącz analizę sentymentu"
    )] = False,
    
    batch_size: Annotated[int, typer.Option(
        "--batch-size",
        help="Rozmiar batcha dla analiz",
        min=1, max=1000
    )] = 100,
    
    concurrent_requests: Annotated[int, typer.Option(
        "--concurrent",
        help="Liczba równoległych żądań",
        min=1, max=64
    )] = 16,
    
    download_delay: Annotated[float, typer.Option(
        "--delay",
        help="Opóźnienie między żądaniami (sekundy)",
        min=0.0, max=10.0
    )] = 0.5,
    
    dry_run: Annotated[bool, typer.Option(
        "--dry-run",
        help="Tylko pokaż co zostanie wykonane, nie uruchamiaj"
    )] = False,
    
    verbose: Annotated[bool, typer.Option(
        "--verbose", "-v",
        help="Szczegółowe logowanie"
    )] = False
):
    """
    🕷️ Scrapuj wybrane fora z opcjonalnymi analizami NLP.
    
    Przykłady użycia:
    
    • Scrapuj wszystkie fora z podstawową tokenizacją:
      [cyan]forums-scraper scrape[/cyan]
    
    • Scrapuj tylko Radio Katolik z pełną analizą spaCy:
      [cyan]forums-scraper scrape -f radio_katolik -a spacy_full[/cyan]
    
    • Scrapuj wybrane fora z wszystkimi analizami:
      [cyan]forums-scraper scrape -f wiara -f dolina_modlitwy -a all --sentiment[/cyan]
    """
    
    console.print(Panel.fit(
        "🕷️ [bold blue]Forums Scraper[/bold blue] - Zaawansowany scraper forów religijnych",
        style="blue"
    ))
    
    # Rozwiń 'all' na wszystkie fora
    if ForumName.ALL in forums:
        forums = [f for f in ForumName if f != ForumName.ALL]
    
    # Wyświetl podsumowanie
    display_forum_summary(forums)
    display_analysis_summary(analysis)
    
    # Utwórz katalog wyjściowy
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Utwórz konfigurację
    if not config_file:
        config = create_analysis_config(analysis, spacy_model, include_sentiment, batch_size)
        config_file = output_dir / "scraper_config.yaml"
        save_config_file(config, config_file)
        console.print(f"📝 Utworzono plik konfiguracyjny: [cyan]{config_file}[/cyan]")
    
    # Wyświetl plan działania
    console.print("\n🎯 [bold]Plan działania:[/bold]")
    for i, forum in enumerate(forums, 1):
        spider_name = FORUM_SPIDER_MAP[forum]
        db_path = output_dir / f"forum_{spider_name}.db"
        console.print(f"  {i}. [cyan]{forum.value}[/cyan] → [yellow]{db_path}[/yellow]")
    
    if dry_run:
        console.print("\n[yellow]🔍 Tryb dry-run - nie wykonuję scrapowania[/yellow]")
        return
    
    # Potwierdź wykonanie
    if not typer.confirm("\n❓ Czy chcesz kontynuować?"):
        console.print("[red]❌ Anulowano[/red]")
        return
    
    # Wykonaj scrapowanie
    console.print("\n🚀 [bold green]Rozpoczynam scrapowanie...[/bold green]")
    
    total_forums = len(forums)
    failed_forums = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        
        main_task = progress.add_task("Scrapowanie forów", total=total_forums)
        
        for forum in forums:
            spider_name = FORUM_SPIDER_MAP[forum]
            
            progress.update(
                main_task, 
                description=f"Scrapuję [cyan]{forum.value}[/cyan] ({spider_name})"
            )
            
            try:
                # Przygotuj argumenty dla Scrapy
                scrapy_args = [
                    "scrapy", "crawl", spider_name,
                    "-s", f"FS_CONFIG_PATH={config_file}",
                    "-s", f"SQLITE_DATABASE_PATH={output_dir}/forum_{spider_name}.db",
                    "-s", f"CONCURRENT_REQUESTS={concurrent_requests}",
                    "-s", f"DOWNLOAD_DELAY={download_delay}",
                ]
                
                if verbose:
                    scrapy_args.extend(["-s", "LOG_LEVEL=INFO"])
                else:
                    scrapy_args.extend(["-s", "LOG_LEVEL=WARNING"])
                
                # Uruchom Scrapy
                console.print(f"▶️  Uruchamiam: [dim]{' '.join(scrapy_args)}[/dim]")
                
                result = subprocess.run(
                    scrapy_args,
                    capture_output=not verbose,
                    text=True,
                    check=True
                )
                
                console.print(f"✅ [green]{forum.value} - zakończono pomyślnie[/green]")
                
            except subprocess.CalledProcessError as e:
                console.print(f"❌ [red]{forum.value} - błąd: {e}[/red]")
                failed_forums.append(forum.value)
            
            except KeyboardInterrupt:
                console.print(f"\n[yellow]⏹️  Przerwano przez użytkownika[/yellow]")
                break
                
            progress.advance(main_task)
    
    # Podsumowanie
    console.print(f"\n🎉 [bold green]Scrapowanie zakończone![/bold green]")
    
    successful_count = total_forums - len(failed_forums)
    console.print(f"✅ Pomyślnie: [green]{successful_count}/{total_forums}[/green]")
    
    if failed_forums:
        console.print(f"❌ Niepowodzenia: [red]{len(failed_forums)}[/red]")
        for forum in failed_forums:
            console.print(f"   • {forum}")
    
    # Wyświetl informacje o bazach danych
    console.print(f"\n📊 [bold]Bazy danych zapisane w:[/bold] [cyan]{output_dir}[/cyan]")
    for forum in forums:
        if forum.value not in failed_forums:
            spider_name = FORUM_SPIDER_MAP[forum]
            db_path = output_dir / f"forum_{spider_name}.db"
            if db_path.exists():
                size_mb = db_path.stat().st_size / 1024 / 1024
                console.print(f"   • [cyan]{db_path.name}[/cyan] ([yellow]{size_mb:.1f} MB[/yellow])")


@app.command(name="list-spiders")
def list_available_spiders():
    """📋 Wyświetl dostępne spidery."""
    console.print("🕷️  [bold]Dostępne spidery:[/bold]")
    
    spiders = get_available_spiders()
    for spider in spiders:
        console.print(f"   • [cyan]{spider}[/cyan]")


@app.command(name="list-analyzers") 
def list_available_analyzers():
    """🔬 Wyświetl dostępne analizatory."""
    from importlib.metadata import entry_points
    
    console.print("🔬 [bold]Dostępne analizatory:[/bold]")
    
    try:
        eps = entry_points(group="forums_scraper.analyzers")
        for ep in sorted(eps, key=lambda x: x.name):
            console.print(f"   • [cyan]{ep.name}[/cyan] - [dim]{ep.value}[/dim]")
    except Exception as e:
        console.print(f"[red]Błąd podczas pobierania analizatorów: {e}[/red]")


@app.command(name="config")
def create_config_file(
    output: Annotated[Path, typer.Option(
        "--output", "-o",
        help="Ścieżka do pliku konfiguracyjnego"
    )] = Path("scraper_config.yaml"),
    
    analysis: Annotated[List[AnalysisType], typer.Option(
        "--analysis", "-a",
        help="Rodzaje analiz do włączenia"
    )] = [AnalysisType.BASIC_TOKENS],
    
    spacy_model: Annotated[str, typer.Option(
        "--spacy-model",
        help="Model spaCy"
    )] = "pl_core_news_sm",
    
    include_sentiment: Annotated[bool, typer.Option(
        "--sentiment/--no-sentiment",
        help="Włącz analizę sentymentu"
    )] = False
):
    """📝 Utwórz plik konfiguracyjny dla analiz."""
    
    config = create_analysis_config(analysis, spacy_model, include_sentiment)
    save_config_file(config, output)
    
    console.print(f"📝 [green]Utworzono plik konfiguracyjny:[/green] [cyan]{output}[/cyan]")
    
    # Wyświetl zawartość
    console.print("\n📋 [bold]Zawartość pliku:[/bold]")
    with open(output, 'r', encoding='utf-8') as f:
        content = f.read()
        console.print(f"[dim]{content}[/dim]")


@app.command(name="analyze")
def analyze_offline(
    config: Annotated[Path, typer.Option(
        "--config", "-c",
        exists=True, readable=True,
        help="Ścieżka do pliku konfiguracyjnego"
    )],
    
    input_file: Annotated[Path, typer.Option(
        "--input", "-i",
        exists=True, readable=True,
        help="Plik wejściowy JSONL"
    )],
    
    output_file: Annotated[Optional[Path], typer.Option(
        "--output", "-o",
        help="Plik wyjściowy JSONL (domyślnie: input.analyzed.jsonl)"
    )] = None
):
    """🔬 Uruchom analizy offline na pliku JSONL."""
    
    if not output_file:
        output_file = input_file.parent / f"{input_file.stem}.analyzed.jsonl"
    
    console.print(f"🔬 [bold]Analiza offline[/bold]")
    console.print(f"📁 Wejście: [cyan]{input_file}[/cyan]")
    console.print(f"📁 Wyjście: [cyan]{output_file}[/cyan]")
    console.print(f"⚙️  Konfiguracja: [cyan]{config}[/cyan]")
    
    # Import i uruchomienie analizy (używamy istniejącego kodu)
    from .main import analyze as run_analysis
    
    try:
        run_analysis(config, input_file, output_file)
        console.print(f"✅ [green]Analiza zakończona pomyślnie![/green]")
    except Exception as e:
        console.print(f"❌ [red]Błąd podczas analizy: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="status")
def show_status(
    database_dir: Annotated[Path, typer.Option(
        "--dir", "-d",
        help="Katalog z bazami danych"
    )] = Path("data/databases")
):
    """📊 Pokaż status baz danych i statystyki."""
    
    console.print("📊 [bold]Status baz danych[/bold]")
    
    if not database_dir.exists():
        console.print(f"[red]Katalog nie istnieje: {database_dir}[/red]")
        return
    
    db_files = list(database_dir.glob("*.db"))
    
    if not db_files:
        console.print(f"[yellow]Brak baz danych w katalogu: {database_dir}[/yellow]")
        return
    
    table = Table(title="Bazy danych", show_header=True)
    table.add_column("Plik", style="cyan")
    table.add_column("Rozmiar", style="yellow")
    table.add_column("Modyfikacja", style="green")
    table.add_column("Posty", style="magenta")
    
    for db_file in sorted(db_files):
        size_mb = db_file.stat().st_size / 1024 / 1024
        mtime = datetime.fromtimestamp(db_file.stat().st_mtime)
        
        # Spróbuj policzyć posty
        post_count = "?"
        try:
            import sqlite3
            with sqlite3.connect(db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM posts")
                post_count = str(cursor.fetchone()[0])
        except Exception:
            pass
        
        table.add_row(
            db_file.name,
            f"{size_mb:.1f} MB",
            mtime.strftime("%Y-%m-%d %H:%M"),
            post_count
        )
    
    console.print(table)


def run():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    run()

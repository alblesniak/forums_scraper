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
import os
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

from core.config import AppConfig, load_config


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
    URL_ANALYSIS = "url_analysis"
    DOMAIN_STATS = "domain_stats"
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
            "name": "token_count",
            "config": {
                "encoding": "cl100k_base"
            }
        })
    
    # BasicTokenizer tylko jeśli nie ma spaCy lub explicitly requested
    if (AnalysisType.BASIC_TOKENS in analysis_types and 
        AnalysisType.SPACY_FULL not in analysis_types and 
        AnalysisType.ALL not in analysis_types):
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
    
    if AnalysisType.URL_ANALYSIS in analysis_types or AnalysisType.ALL in analysis_types:
        analyzers.append({
            "name": "url_analyzer",
            "config": {
                "include_domain_analysis": True,
                "include_url_categorization": True,
                "max_urls_per_post": 50
            }
        })
    
    if AnalysisType.DOMAIN_STATS in analysis_types or AnalysisType.ALL in analysis_types:
        analyzers.append({
            "name": "domain_stats",
            "config": {
                "track_popularity": True
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
        elif analysis_type == AnalysisType.URL_ANALYSIS:
            table.add_row("Analiza URL-ów", "Kategoryzacja domen i linków", "Brak")
        elif analysis_type == AnalysisType.DOMAIN_STATS:
            table.add_row("Statystyki domen", "Podstawowe statystyki linków", "Brak")
        elif analysis_type == AnalysisType.ALL:
            table.add_row("Wszystkie analizy", "Kompletna analiza + URL-e", "tiktoken + spacy")
    
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
    )] = "pl_core_news_lg",
    
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
    unified_db_path = output_dir / "forums_unified.db"
    console.print("\n🎯 [bold]Plan działania:[/bold]")
    console.print(f"📊 [bold]Wspólna baza danych:[/bold] [yellow]{unified_db_path}[/yellow]")
    for i, forum in enumerate(forums, 1):
        spider_name = FORUM_SPIDER_MAP[forum]
        console.print(f"  {i}. [cyan]{forum.value}[/cyan] (spider: {spider_name})")
    
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
                    "-s", f"SQLITE_DATABASE_PATH={unified_db_path}",
                    "-s", f"CONCURRENT_REQUESTS={concurrent_requests}",
                    "-s", f"DOWNLOAD_DELAY={download_delay}",
                ]
                
                if verbose:
                    scrapy_args.extend(["-s", "LOG_LEVEL=INFO"])
                else:
                    scrapy_args.extend(["-s", "LOG_LEVEL=WARNING"])
                
                # Uruchom Scrapy
                console.print(f"▶️  Uruchamiam: [dim]{' '.join(scrapy_args)}[/dim]")
                
                # Uruchamiaj z rootu projektu, aby scrapy.cfg był widoczny
                project_root = Path(__file__).resolve().parents[1]
                env = os.environ.copy()
                env.setdefault("SCRAPY_SETTINGS_MODULE", "forums_scraper.settings")
                result = subprocess.run(
                    scrapy_args,
                    cwd=str(project_root),
                    env=env,
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
    
    # Wyświetl informacje o bazie danych
    console.print(f"\n📊 [bold]Wspólna baza danych:[/bold]")
    if unified_db_path.exists():
        size_mb = unified_db_path.stat().st_size / 1024 / 1024
        console.print(f"   📁 [cyan]{unified_db_path.name}[/cyan] ([yellow]{size_mb:.1f} MB[/yellow])")
        
        # Pokaż statystyki per forum jeśli baza istnieje
        try:
            import sqlite3
            with sqlite3.connect(unified_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT f.spider_name, f.title, COUNT(p.id) as posts_count
                    FROM forums f
                    LEFT JOIN sections s ON f.id = s.forum_id
                    LEFT JOIN threads t ON s.id = t.section_id
                    LEFT JOIN posts p ON t.id = p.thread_id
                    GROUP BY f.id, f.spider_name, f.title
                    ORDER BY posts_count DESC
                """)
                results = cursor.fetchall()
                
                if results:
                    console.print("\n📈 [bold]Statystyki per forum:[/bold]")
                    for spider_name, title, posts_count in results:
                        console.print(f"   • [cyan]{spider_name}[/cyan]: [yellow]{posts_count}[/yellow] postów")
                
                # Statystyki domen
                try:
                    cursor.execute("""
                        SELECT category, COUNT(*) as count, SUM(total_references) as total_refs
                        FROM domains 
                        GROUP BY category 
                        ORDER BY total_refs DESC
                    """)
                    domain_results = cursor.fetchall()
                    
                    if domain_results:
                        console.print("\n🌐 [bold]Statystyki domen:[/bold]")
                        for category, count, total_refs in domain_results:
                            console.print(f"   • [cyan]{category}[/cyan]: [yellow]{count}[/yellow] domen, [green]{total_refs}[/green] odniesień")
                
                except Exception:
                    pass  # Tabele domen mogą nie istnieć
                
        except Exception:
            pass  # Ignoruj błędy SQL
    else:
        console.print(f"   📁 [yellow]{unified_db_path}[/yellow] (zostanie utworzona)")


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
    )] = "pl_core_news_lg",
    
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
    database_path: Annotated[Path, typer.Option(
        "--database", "-d",
        help="Ścieżka do bazy danych"
    )] = Path("data/databases/forums_unified.db")
):
    """📊 Pokaż status wspólnej bazy danych i statystyki."""
    
    console.print("📊 [bold]Status wspólnej bazy danych[/bold]")
    
    if not database_path.exists():
        console.print(f"[yellow]Baza danych nie istnieje: {database_path}[/yellow]")
        console.print("💡 Uruchom scrapowanie: [cyan]uv run cli scrape[/cyan]")
        return
    
    # Podstawowe informacje o pliku
    size_mb = database_path.stat().st_size / 1024 / 1024
    mtime = datetime.fromtimestamp(database_path.stat().st_mtime)
    
    console.print(f"📁 [cyan]{database_path.name}[/cyan]")
    console.print(f"📏 Rozmiar: [yellow]{size_mb:.1f} MB[/yellow]")
    console.print(f"🕒 Ostatnia modyfikacja: [green]{mtime.strftime('%Y-%m-%d %H:%M:%S')}[/green]")
    
    # Statystyki z bazy danych
    try:
        import sqlite3
        with sqlite3.connect(database_path) as conn:
            cursor = conn.cursor()
            
            # Statystyki główne
            cursor.execute("SELECT COUNT(*) FROM forums")
            forums_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts")
            posts_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM threads")
            threads_count = cursor.fetchone()[0]
            
            # Tabela głównych statystyk
            main_table = Table(title="📈 Główne statystyki", show_header=True)
            main_table.add_column("Kategoria", style="cyan")
            main_table.add_column("Liczba", style="yellow")
            
            main_table.add_row("Fora", str(forums_count))
            main_table.add_row("Posty", str(posts_count))
            main_table.add_row("Użytkownicy", str(users_count))
            main_table.add_row("Wątki", str(threads_count))
            
            console.print(main_table)
            
            # Statystyki per forum
            cursor.execute("""
                SELECT f.spider_name, f.title, 
                       COUNT(DISTINCT p.id) as posts_count,
                       COUNT(DISTINCT u.id) as users_count,
                       COUNT(DISTINCT t.id) as threads_count
                FROM forums f
                LEFT JOIN sections s ON f.id = s.forum_id
                LEFT JOIN threads t ON s.id = t.section_id
                LEFT JOIN posts p ON t.id = p.thread_id
                LEFT JOIN users u ON p.user_id = u.id
                GROUP BY f.id, f.spider_name, f.title
                ORDER BY posts_count DESC
            """)
            forum_results = cursor.fetchall()
            
            if forum_results:
                forum_table = Table(title="📊 Statystyki per forum", show_header=True)
                forum_table.add_column("Forum", style="cyan")
                forum_table.add_column("Posty", style="yellow")
                forum_table.add_column("Użytkownicy", style="green")
                forum_table.add_column("Wątki", style="magenta")
                
                for spider_name, title, posts, users, threads in forum_results:
                    forum_table.add_row(
                        spider_name or "Nieznane",
                        str(posts),
                        str(users),
                        str(threads)
                    )
                
                console.print(forum_table)
            
            # Statystyki analiz (jeśli są)
            try:
                cursor.execute("SELECT COUNT(*) FROM post_token_stats")
                token_stats_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM post_linguistic_stats")
                linguistic_stats_count = cursor.fetchone()[0]
                
                if token_stats_count > 0 or linguistic_stats_count > 0:
                    analysis_table = Table(title="🔬 Statystyki analiz", show_header=True)
                    analysis_table.add_column("Typ analizy", style="cyan")
                    analysis_table.add_column("Przeanalizowane posty", style="yellow")
                    
                    if token_stats_count > 0:
                        analysis_table.add_row("Tokenizacja", str(token_stats_count))
                    
                    if linguistic_stats_count > 0:
                        analysis_table.add_row("Analiza językowa", str(linguistic_stats_count))
                    
                    # Sprawdź NER
                    try:
                        cursor.execute("SELECT COUNT(*) FROM post_ner_stats")
                        ner_stats_count = cursor.fetchone()[0]
                        
                        if ner_stats_count > 0:
                            analysis_table.add_row("Named Entities", str(ner_stats_count))
                    except Exception:
                        pass
                    
                    console.print(analysis_table)
                    
            except Exception:
                pass  # Tabele analiz mogą nie istnieć
            
    except Exception as e:
        console.print(f"[red]Błąd podczas odczytu bazy danych: {e}[/red]")


def run():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    run()

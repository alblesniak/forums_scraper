#!/usr/bin/env python3
"""
Jednolity pipeline dla projektu:
- pobieranie danych (scrapy)
- łączenie baz
- analiza tokenów
- modelowanie tematyczne

Konfiguracja:
- przez plik JSON (opcjonalnie: --config path)
- lub przez zmienne środowiskowe

Szybki start:
  python scripts/pipeline.py all

Podkomendy:
  - scrape   : uruchamia wszystkie spidery (tak jak run_all_scrapers_final)
  - merge    : łączy bazy forum_* do merged_forums.db
  - analyze  : tworzy analysis_forums.db i liczy tokeny dla postów
  - topics   : uruchamia modelowanie tematyczne (Top2Vec)
  - clean    : czyści pośrednie bazy (z backupem opcjonalnie)
  - all      : wykonuje wszystko po kolei (scrape -> analyze -> topics)
"""

import os
import sys
import json
import argparse
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

# Stałe ścieżek
ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
ANALYSIS_DIR = ROOT_DIR / "analysis"
TOPIC_DIR = ANALYSIS_DIR / "topic_modeling"


# Domyślna konfiguracja
DEFAULT_CONFIG: Dict[str, Any] = {
    "databases": {
        "dir": str(ROOT_DIR / "data/databases"),
        "source_dbs_glob": "forum_*.db",
        "merged": "merged_forums.db",
        "analysis": "analysis_forums.db",
    },
    "analysis": {
        "forums": ["wiara"],
        "use_multiprocessing": True,
        "max_workers": 4,
        "chunk_size": 50,
        "batch_size": 100,
    },
    "topics": {
        "forums": ["wiara"],
        "genders": ["M", "K"],
        "output_dir": str(ROOT_DIR / "data/topics"),
        "combine_forums": False,
        "combined_forum_names": ["radio_katolik", "dolina_modlitwy"]
    },
    "clean": {
        "keep_merged": True,
        "keep_analysis": True,
        "remove_per_forum": True,
        "backup": False,
        "backup_dir": str(ROOT_DIR / "backups"),
    },
}


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Ładuje konfigurację z pliku JSON i scala z domyślną."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if config_path:
        cfg_file = Path(config_path)
        if not cfg_file.exists():
            raise FileNotFoundError(f"Nie znaleziono pliku konfiguracyjnego: {config_path}")
        with open(cfg_file, "r", encoding="utf-8") as f:
            file_cfg = json.load(f)
            deep_update(config, file_cfg)
    return config


def deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value
    return base


def step_scrape() -> None:
    """Uruchamia wszystkie spidery korzystając z istniejącego managera."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from run_all_scrapers_final import FinalScraperManager

    manager = FinalScraperManager()
    # Uwaga: FinalScraperManager.run() już sam łączy bazy po scrapowaniu
    manager.run()


def step_merge(config: Dict[str, Any]) -> None:
    """Łączy bazy forum_* do jednej merged_forums.db."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from merge_all_databases import DatabaseMerger

    db_dir = Path(config["databases"]["dir"]) \
        if os.path.isabs(config["databases"]["dir"]) \
        else ROOT_DIR / config["databases"]["dir"]

    target = str(db_dir / config["databases"]["merged"])
    merger = DatabaseMerger(target_db=target)
    merger.merge_all_databases()


def step_analyze(config: Dict[str, Any]) -> None:
    """Tworzy bazę analizy i uruchamia liczenie tokenów."""
    if str(ANALYSIS_DIR) not in sys.path:
        sys.path.insert(0, str(ANALYSIS_DIR))
    from cli import AnalysisCLI

    db_dir = Path(config["databases"]["dir"]) \
        if os.path.isabs(config["databases"]["dir"]) \
        else ROOT_DIR / config["databases"]["dir"]

    source_db = str(db_dir / config["databases"]["merged"])
    analysis_db = str(db_dir / config["databases"]["analysis"])

    forums = config["analysis"].get("forums") or None

    cli = AnalysisCLI()

    # Nadpisz ustawienia multiprocessing zgodnie z configiem pipeline
    if not config["analysis"].get("use_multiprocessing", True):
        cli.config['multiprocessing']['use_multiprocessing'] = False
    if config["analysis"].get("max_workers") is not None:
        cli.config['multiprocessing']['max_workers'] = int(config["analysis"]["max_workers"])
    if config["analysis"].get("chunk_size") is not None:
        cli.config['multiprocessing']['chunk_size'] = int(config["analysis"]["chunk_size"])

    cli.setup_analyzer(source_db=source_db, analysis_db=analysis_db, forums=forums)
    cli.create_database()
    cli.analyze_all_posts(show_progress=True)
    cli.show_summary()


def step_topics(config: Dict[str, Any]) -> None:
    """Uruchamia modelowanie tematyczne dla wskazanych forów i płci."""
    # Upewnij się, że katalog wyjściowy istnieje
    out_dir = Path(config["topics"].get("output_dir", str(TOPIC_DIR)))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ustaw zmienne środowiskowe rozumiane przez analysis/topic_modeling/config.py
    db_dir = Path(config["databases"]["dir"]) \
        if os.path.isabs(config["databases"]["dir"]) \
        else ROOT_DIR / config["databases"]["dir"]

    os.environ["TOPIC_DATABASE_PATH"] = str(db_dir / config["databases"]["analysis"])
    os.environ["TOPIC_OUTPUT_DIR"] = str(out_dir)
    os.environ["TOPIC_FORUMS"] = ",".join(config["topics"].get("forums", []))
    os.environ["TOPIC_GENDERS"] = ",".join(config["topics"].get("genders", []))

    # Import po ustawieniu env, żeby config użył nowych wartości
    if str(TOPIC_DIR) not in sys.path:
        sys.path.insert(0, str(TOPIC_DIR))
    from topic_modeling_script import TopicModelingAnalyzer
    from config import FORUMS, GENDERS, DATABASE_PATH, OUTPUT_DIR, ANALYSIS_PARAMS

    analyzer = TopicModelingAnalyzer(DATABASE_PATH, OUTPUT_DIR)
    analyzer.min_tokens = ANALYSIS_PARAMS['min_tokens']
    analyzer.max_tokens = ANALYSIS_PARAMS['max_tokens']
    analyzer.max_posts_per_user = ANALYSIS_PARAMS['max_posts_per_user']

    combine_forums = bool(config["topics"].get("combine_forums", False))
    combined_forum_names = config["topics"].get("combined_forum_names", [])

    if combine_forums and combined_forum_names:
        for gender in GENDERS:
            print(f"\n=== Top2Vec (łączone fora): {combined_forum_names} / {gender} ===")
            try:
                analyzer.run_combined_analysis(combined_forum_names, gender)
                print("✓ OK")
            except Exception as exc:
                print(f"✗ Błąd: {exc}")
    else:
        for forum in FORUMS:
            for gender in GENDERS:
                print(f"\n=== Top2Vec: {forum} / {gender} ===")
                try:
                    analyzer.run_analysis(forum, gender)
                    print("✓ OK")
                except Exception as exc:
                    print(f"✗ Błąd: {exc}")


def step_clean(config: Dict[str, Any], hard: bool = False) -> None:
    """Czyści artefakty. Gdy hard=True, usuwa wszystkie wygenerowane pliki."""
    db_dir = Path(config["databases"]["dir"]) \
        if os.path.isabs(config["databases"]["dir"]) \
        else ROOT_DIR / config["databases"]["dir"]

    if hard:
        # 1) Usuń wszystkie pliki baz danych (*.db, *.db-shm, *.db-wal)
        if db_dir.exists():
            for f in db_dir.glob("**/*"):
                if f.is_file() and any(
                    str(f).endswith(suf) for suf in [".db", ".db-shm", ".db-wal"]
                ):
                    try:
                        f.unlink()
                        print(f"🗑️  Usunięto {f}")
                    except Exception as exc:
                        print(f"⚠️  Nie udało się usunąć {f}: {exc}")
        # 2) Usuń artefakty topics
        for rel in [
            TOPIC_DIR / "models",
            TOPIC_DIR / "results",
            TOPIC_DIR / "logs",
        ]:
            try:
                shutil.rmtree(rel, ignore_errors=True)
                print(f"🗑️  Usunięto {rel}")
            except Exception as exc:
                print(f"⚠️  Nie udało się usunąć {rel}: {exc}")
        # 3) Usuń logi
        for rel in [ROOT_DIR / "logs", ANALYSIS_DIR / "logs"]:
            try:
                shutil.rmtree(rel, ignore_errors=True)
                print(f"🗑️  Usunięto {rel}")
            except Exception as exc:
                print(f"⚠️  Nie udało się usunąć {rel}: {exc}")
        # 4) Odtwórz puste katalogi
        db_dir.mkdir(parents=True, exist_ok=True)
        (ROOT_DIR / "logs").mkdir(parents=True, exist_ok=True)
        (ANALYSIS_DIR / "logs").mkdir(parents=True, exist_ok=True)
        (TOPIC_DIR / "models").mkdir(parents=True, exist_ok=True)
        (TOPIC_DIR / "results").mkdir(parents=True, exist_ok=True)
        (TOPIC_DIR / "logs").mkdir(parents=True, exist_ok=True)
        print("✅ Twarde czyszczenie zakończone")
        return

    # Miękkie czyszczenie wg configu
    keep_merged = bool(config["clean"].get("keep_merged", True))
    keep_analysis = bool(config["clean"].get("keep_analysis", True))
    remove_per_forum = bool(config["clean"].get("remove_per_forum", True))
    do_backup = bool(config["clean"].get("backup", False))
    backup_dir = Path(config["clean"].get("backup_dir", str(ROOT_DIR / "backups")))

    merged_path = db_dir / config["databases"]["merged"]
    analysis_path = db_dir / config["databases"]["analysis"]

    if do_backup:
        backup_dir.mkdir(parents=True, exist_ok=True)

    if remove_per_forum:
        for db_file in db_dir.glob(config["databases"]["source_dbs_glob"]):
            if do_backup:
                shutil.copy2(db_file, backup_dir / db_file.name)
            db_file.unlink(missing_ok=True)
            print(f"🗑️  Usunięto {db_file}")

    if not keep_analysis and analysis_path.exists():
        if do_backup:
            shutil.copy2(analysis_path, backup_dir / analysis_path.name)
        analysis_path.unlink(missing_ok=True)
        print(f"🗑️  Usunięto {analysis_path}")

    if not keep_merged and merged_path.exists():
        if do_backup:
            shutil.copy2(merged_path, backup_dir / merged_path.name)
        merged_path.unlink(missing_ok=True)
        print(f"🗑️  Usunięto {merged_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Jednolity pipeline: scrapy -> merge -> analyze -> topics -> clean",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady:
  python scripts/pipeline.py all
  python scripts/pipeline.py analyze --config scripts/pipeline.config.json
  python scripts/pipeline.py clean --config scripts/pipeline.config.json
""",
    )

    parser.add_argument("command", choices=[
        "scrape", "merge", "analyze", "topics", "clean", "all"
    ])
    parser.add_argument(
        "--config", dest="config_path", help="Ścieżka do pliku JSON z konfiguracją pipeline"
    )
    parser.add_argument(
        "--hard", action="store_true", help="Dla 'clean': usuń wszystkie artefakty (bazy, logi, models/results)"
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config_path)

    # Zawsze upewnij się, że katalog baz istnieje
    db_dir = Path(config["databases"]["dir"]) \
        if os.path.isabs(config["databases"]["dir"]) \
        else ROOT_DIR / config["databases"]["dir"]
    db_dir.mkdir(parents=True, exist_ok=True)

    # Upewnij się, że katalogi logów istnieją (przenosimy do data/logs)
    (ROOT_DIR / 'data/logs').mkdir(parents=True, exist_ok=True)

    if args.command == "scrape":
        step_scrape()
        return 0

    if args.command == "merge":
        step_merge(config)
        return 0

    if args.command == "analyze":
        step_analyze(config)
        return 0

    if args.command == "topics":
        step_topics(config)
        return 0

    if args.command == "clean":
        step_clean(config, hard=args.hard)
        return 0

    if args.command == "all":
        # Uwaga: FinalScraperManager.run() już łączy bazy, więc nie wywołujemy step_merge()
        step_scrape()
        step_analyze(config)
        step_topics(config)
        # Sprzątanie po wszystkim wg domyślnej polityki
        step_clean(config)
        return 0

    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n🛑 Przerwano przez użytkownika")
        sys.exit(1)


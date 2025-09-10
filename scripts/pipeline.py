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
import secrets

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
        "combined_forum_names": ["radio_katolik", "dolina_modlitwy"],
        "repeats": 1,
    },
    "gender": {
        # Nadpisywalne parametry reguł predykcji płci
        "weights": {},
        "thresholds": {},
    },
    "clean": {
        "keep_merged": True,
        "keep_analysis": True,
        "remove_per_forum": True,
        "backup": False,
        "backup_dir": str(ROOT_DIR / "backups"),
    },
    "examples": {
        "model_path": "",
        "topic_num": None,
        "top_n": 50,
        "results_dir": ""
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
        # zapamiętaj fizyczną ścieżkę do bieżącej konfiguracji, by przekazać do modułu topics
        config['__config_path__'] = str(cfg_file.resolve())
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

    # Upewnij się, że katalog docelowy na bazy istnieje (tworzymy tylko przed zapisem)
    db_dir.mkdir(parents=True, exist_ok=True)

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


def step_gender(config: Dict[str, Any]) -> None:
    """Uruchamia predykcję płci na podstawie reguł językowych dla wskazanych forów."""
    if str(ANALYSIS_DIR) not in sys.path:
        sys.path.insert(0, str(ANALYSIS_DIR))
    from cli import AnalysisCLI

    db_dir = Path(config["databases"]["dir"]) \
        if os.path.isabs(config["databases"]["dir"]) \
        else ROOT_DIR / config["databases"]["dir"]

    analysis_db = str(db_dir / config["databases"]["analysis"])
    forums = config["analysis"].get("forums") or None

    cli = AnalysisCLI()
    # Nie potrzebujemy pełnej analizy tokenów, ale CLI wymaga setupu
    cli.setup_analyzer(source_db=analysis_db, analysis_db=analysis_db, forums=forums)

    # Użyj opcji CLI do uruchomienia gender-rules (lokalna baza analizy)
    from gender_prediction import run_gender_rules
    print("\n=== Predykcja płci (rules_v1) ===")
    rules_params = config.get("gender") or None
    res = run_gender_rules(analysis_db, forums=forums, rules_params=rules_params, method_tag='rules_v1')
    print(f"Użytkownicy przetworzeni: {res.get('processed_users', 0)}")
    print(f"Zapisane predykcje: {res.get('saved_predictions', 0)} ({res.get('predicted_pct', 0):.2f}%)")
    if res.get('accuracy_pct') is not None:
        print(f"Ground truth: {res.get('truth_users', 0)}; poprawnych: {res.get('correct_predictions', 0)} ({res.get('accuracy_pct', 0):.2f}%)")


def step_gender_all_forums(config: Dict[str, Any], rules_params: Optional[Dict] = None) -> None:
    """Uruchamia cross-DB predykcję dla wszystkich forów źródłowych i zapisuje wyniki
    do osobnych baz analysis_forums_*.db, wraz z podsumowaniem i trafnością.
    """
    if str(ANALYSIS_DIR) not in sys.path:
        sys.path.insert(0, str(ANALYSIS_DIR))

    from gender_prediction import run_gender_rules_into_analysis

    db_dir = Path(config["databases"]["dir"]) \
        if os.path.isabs(config["databases"]["dir"]) \
        else ROOT_DIR / config["databases"]["dir"]

    forums_to_process = [
        {
            'spider': 'dolina_modlitwy',
            'source': db_dir / 'forum_dolina_modlitwy.db',
            'analysis': db_dir / 'analysis_forums_dolina_modlitwy.db',
        },
        {
            'spider': 'radio_katolik',
            'source': db_dir / 'forum_radio_katolik.db',
            'analysis': db_dir / 'analysis_forums_radio_katolik.db',
        },
        {
            'spider': 'wiara',
            'source': db_dir / 'forum_wiara.db',
            'analysis': db_dir / 'analysis_forums_wiara.db',
        },
        {
            'spider': 'z_chrystusem',
            'source': db_dir / 'forum_z_chrystusem.db',
            'analysis': db_dir / 'analysis_forums_z_chrystusem.db',
        },
    ]

    rules_params = config.get("gender") or None
    for entry in forums_to_process:
        source_db = str(entry['source'])
        analysis_db = str(entry['analysis'])
        entry['analysis'].parent.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Predykcja płci (rules_v1) dla forum: {entry['spider']} ===")
        try:
            res = run_gender_rules_into_analysis(
                analysis_db=analysis_db,
                source_db=source_db,
                forums=[entry['spider']],
                method_tag='rules_v1',
                rules_params=rules_params,
            )
            print(f"Użytkownicy przetworzeni: {res.get('processed_users', 0)}")
            print(f"Zapisane predykcje: {res.get('saved_predictions', 0)} ({res.get('predicted_pct', 0):.2f}%)")
            if res.get('accuracy_pct') is not None:
                print(f"Ground truth: {res.get('truth_users', 0)}; poprawnych: {res.get('correct_predictions', 0)} ({res.get('accuracy_pct', 0):.2f}%)")
        except Exception as exc:
            print(f"✗ Błąd predykcji dla {entry['spider']}: {exc}")


def step_topics(config: Dict[str, Any]) -> None:
    """Uruchamia modelowanie tematyczne dla wskazanych forów i płci."""
    # Ścieżka katalogu wyjściowego (katalogi będą tworzone w trakcie zapisu plików)
    out_dir = Path(config["topics"].get("output_dir", str(TOPIC_DIR)))

    # Ustaw zmienne środowiskowe rozumiane przez analysis/topic_modeling/config.py
    db_dir = Path(config["databases"]["dir"]) \
        if os.path.isabs(config["databases"]["dir"]) \
        else ROOT_DIR / config["databases"]["dir"]

    os.environ["TOPIC_DATABASE_PATH"] = str(db_dir / config["databases"]["analysis"])
    os.environ["TOPIC_OUTPUT_DIR"] = str(out_dir)
    # Fora: specjalna wartość "ALL" oznacza autodetekcję z bazy
    cfg_forums = config["topics"].get("forums", []) or []
    if any(str(f).upper() == "ALL" for f in cfg_forums):
        try:
            import sqlite3
            conn = sqlite3.connect(os.environ["TOPIC_DATABASE_PATH"])
            cur = conn.cursor()
            cur.execute("SELECT spider_name FROM forums")
            detected = [row[0] for row in cur.fetchall()]
            conn.close()
            forums_env = ",".join(detected)
        except Exception:
            forums_env = ""
    else:
        forums_env = ",".join(cfg_forums)
    os.environ["TOPIC_FORUMS"] = forums_env
    os.environ["TOPIC_GENDERS"] = ",".join(config["topics"].get("genders", []))
    # Seed do losowań (limit postów per user itp.) – wspiera 'auto' dla losowego ziarna
    rs_val = config["topics"].get("random_seed")
    if rs_val is not None:
        if isinstance(rs_val, str) and rs_val.lower() in ("auto", "random"):
            seed = secrets.randbelow(2**31 - 1) or 1
            os.environ["TOPIC_RANDOM_SEED"] = str(seed)
            print(f"[topics] Ustawiono losowe random_seed={seed}")
        else:
            os.environ["TOPIC_RANDOM_SEED"] = str(rs_val)
    # Przekazanie flag przez env (opcjonalnie)
    if str(config["topics"].get("keep_documents_in_model", "")).lower() in ("true", "false", "1", "0"):
        os.environ["TOPIC_KEEP_DOCUMENTS"] = str(config["topics"].get("keep_documents_in_model")).lower()
    if config["topics"].get("embedding_model"):
        os.environ["TOPIC_EMBEDDING_MODEL"] = str(config["topics"].get("embedding_model"))
    # Docelowa liczba tematów (opcjonalnie)
    target_num_topics = config["topics"].get("num_topics")
    if target_num_topics is None:
        target_num_topics = config["topics"].get("target_num_topics")
    if target_num_topics is not None and str(target_num_topics).strip() != "":
        try:
            os.environ["TOPIC_NUM_TOPICS"] = str(int(target_num_topics))
        except Exception:
            pass
    # Lista wykluczanych sekcji (opcjonalnie)
    excluded_sections = config["topics"].get("excluded_sections")
    if excluded_sections is not None:
        os.environ["TOPIC_EXCLUDED_SECTIONS"] = ",".join(excluded_sections)

    # Przekazuj ścieżkę do aktualnego pliku configu do modułu analizy (kopiowanie do wyników)
    if config_path := config.get('__config_path__'):
        os.environ["TOPIC_PIPELINE_CONFIG_PATH"] = str(config_path)

    # Import po ustawieniu env, żeby config użył nowych wartości
    if str(TOPIC_DIR) not in sys.path:
        sys.path.insert(0, str(TOPIC_DIR))
    from topic_modeling_script import TopicModelingAnalyzer
    from config import FORUMS, GENDERS, DATABASE_PATH, OUTPUT_DIR, ANALYSIS_PARAMS, TOPICS_PARAMS, FORUM_CODES

    analyzer = TopicModelingAnalyzer(DATABASE_PATH, OUTPUT_DIR)
    analyzer.min_tokens = ANALYSIS_PARAMS['min_tokens']
    analyzer.max_tokens = ANALYSIS_PARAMS['max_tokens']
    analyzer.max_posts_per_user = ANALYSIS_PARAMS['max_posts_per_user']
    analyzer.random_seed = ANALYSIS_PARAMS.get('random_seed', 42)
    analyzer.embedding_model = TOPICS_PARAMS.get('embedding_model', 'doc2vec')
    analyzer.keep_documents_in_model = bool(TOPICS_PARAMS.get('keep_documents_in_model', True))

    combine_forums = bool(config["topics"].get("combine_forums", False))
    combined_forum_names = config["topics"].get("combined_forum_names", [])

    # Rozwiąż listę forów do łączenia: wspiera pustą listę oraz specjalne "ALL"
    resolved_combined = combined_forum_names
    if combine_forums and (not resolved_combined or any(str(f).upper() == "ALL" for f in resolved_combined)):
        # Jeśli TOPIC_FORUMS zostało ustawione (w tym autodetekcja), użyj go jako źródła prawdy
        forums_from_env = os.environ.get("TOPIC_FORUMS", "")
        if forums_from_env:
            resolved_combined = [f.strip() for f in forums_from_env.split(',') if f.strip()]
        else:
            resolved_combined = FORUMS

    repeats = int(config["topics"].get("repeats", 1) or 1)
    if combine_forums and resolved_combined:
        for gender in GENDERS:
            for i in range(1, repeats + 1):
                # Losuj lub deterministycznie modyfikuj seed, jeśli nie podano --topics-seed='auto'
                base_seed = os.environ.get("TOPIC_RANDOM_SEED")
                if base_seed is not None and str(base_seed).lower() not in ("auto", "random"):
                    try:
                        os.environ["TOPIC_RANDOM_SEED"] = str(int(base_seed) + i - 1)
                    except Exception:
                        pass
                else:
                    # auto/random – ustaw losowy seed
                    seed = secrets.randbelow(2**31 - 1) or 1
                    os.environ["TOPIC_RANDOM_SEED"] = str(seed)
                    print(f"[topics] Powtórzenie {i}/{repeats}: losowe random_seed={seed}")

                print(f"\n=== Top2Vec (łączone fora): {resolved_combined} / {gender} / run #{i} ===")
                try:
                    analyzer.random_seed = int(os.environ.get("TOPIC_RANDOM_SEED", analyzer.random_seed))
                    analyzer.run_combined_analysis(resolved_combined, gender)
                    print("✓ OK")
                except Exception as exc:
                    print(f"✗ Błąd: {exc}")
    else:
        for forum in FORUMS:
            for gender in GENDERS:
                for i in range(1, repeats + 1):
                    base_seed = os.environ.get("TOPIC_RANDOM_SEED")
                    if base_seed is not None and str(base_seed).lower() not in ("auto", "random"):
                        try:
                            os.environ["TOPIC_RANDOM_SEED"] = str(int(base_seed) + i - 1)
                        except Exception:
                            pass
                    else:
                        seed = secrets.randbelow(2**31 - 1) or 1
                        os.environ["TOPIC_RANDOM_SEED"] = str(seed)
                        print(f"[topics] Powtórzenie {i}/{repeats}: losowe random_seed={seed}")

                    print(f"\n=== Top2Vec: {forum} / {gender} / run #{i} ===")
                    try:
                        analyzer.random_seed = int(os.environ.get("TOPIC_RANDOM_SEED", analyzer.random_seed))
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
            TOPIC_DIR / "runs",
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
        "scrape", "merge", "analyze", "gender", "gender-all", "topics", "examples", "llm-batch", "domains", "domain-posts", "clean", "all"
    ])
    parser.add_argument(
        "--config", dest="config_path", help="Ścieżka do pliku JSON z konfiguracją pipeline"
    )
    parser.add_argument(
        "--use-merged-as-analysis", action="store_true", help="Użyj jednej bazy: analysis=merged"
    )
    # Parametry dla predykcji płci (reguły)
    parser.add_argument("--gender-weights", help="JSON z wagami reguł (np. '{\"bylam\":4,\"no_diac\":1}')")
    parser.add_argument("--gender-thresholds", help="JSON z progami (np. '{\"min_total\":2,\"min_diff\":1}')")
    # Opcjonalne nadpisania parametrów topics z wiersza poleceń
    parser.add_argument("--topics-forums", help="Lista forów rozdzielona przecinkami, np. wiara,z_chrystusem lub ALL")
    parser.add_argument("--topics-genders", help="Lista płci, np. K,M lub KM")
    parser.add_argument("--topics-combine", action="store_true", help="Łącz fora w jeden model")
    parser.add_argument("--topics-combined-names", help="Lista forów do łączenia (przecinki) lub ALL")
    parser.add_argument("--topics-output", help="Katalog wyjściowy dla topics")
    parser.add_argument("--topics-num-topics", type=int, help="Docelowa liczba tematów po redukcji")
    parser.add_argument("--topics-seed", help="random_seed (liczba lub 'auto')")
    parser.add_argument("--topics-embedding", help="embedding_model (np. doc2vec)")
    parser.add_argument("--topics-keep-docs", choices=["true", "false"], help="Czy przechowywać dokumenty w modelu")
    parser.add_argument("--topics-excluded", help="Lista wykluczanych sekcji (przecinki)")
    parser.add_argument("--topics-repeats", type=int, help="Liczba powtórzeń trenowania per kombinacja (domyślnie 1)")
    parser.add_argument(
        "--hard", action="store_true", help="Dla 'clean': usuń wszystkie artefakty (bazy, logi, models/results)"
    )

    # Parametry dla raportu domen (content_urls)
    parser.add_argument("--domains-forums", help="Lista forów (spider_name) rozdzielona przecinkami; domyślnie radio_katolik")
    parser.add_argument("--domains-output", help="Katalog wyjściowy CSV dla raportu domen")

    # Parametry dla eksportu postów po domenie
    parser.add_argument("--domain", help="Domena do wyszukania w content_urls, np. spowiedz.katolik.pl")
    parser.add_argument("--domain-forums", help="Lista forów (spider_name) dla eksportu postów; domyślnie radio_katolik")
    parser.add_argument("--domain-output", help="Katalog wyjściowy CSV dla eksportu postów")

    # Parametry dla exportu przykładów z modelu
    parser.add_argument("--examples-model", help="Ścieżka do modelu Top2Vec (katalog/plik 'model')")
    parser.add_argument("--examples-topic", type=int, help="Numer tematu (topic_num)")
    parser.add_argument("--examples-topn", type=int, help="Liczba dokumentów Top N wg score")
    parser.add_argument("--examples-results-dir", help="Katalog wyników (opcjonalnie; domyślnie obok modelu w strukturze results)")

    # Parametry dla llm-batch klasyfikacji z Excela
    parser.add_argument("--llm-excel", help="Ścieżka do pliku Excel z kolumnami content i opcjonalnie post_id")
    parser.add_argument("--llm-batch-size", type=int, default=10, help="Rozmiar batcha (domyślnie 10)")
    parser.add_argument("--llm-poll", type=int, default=10, help="Interwał sprawdzania statusu batcha w sekundach (domyślnie 10)")
    parser.add_argument("--llm-concurrency", type=int, default=1, help="Maksymalna liczba równoległych jobów Batch API (domyślnie 1)")
    parser.add_argument("--llm-resume", help="Ścieżka do istniejącego katalogu run_dir (llm_batch_...) w celu wznowienia")
    parser.add_argument("--llm-process-existing", action="store_true", help="Przetwórz LOKALNIE wszystkie istniejące batch_*_input.jsonl bez wyników (bez Batch API)")
    parser.add_argument("--llm-local", action="store_true", help="Przetwarzaj LOKALNIE całe wejście (bez Batch API), realtime")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config_path)

    # Flaga: jedna baza dla źródła i analizy
    if args.use_merged_as_analysis:
        try:
            merged = config["databases"]["merged"]
            config["databases"]["analysis"] = merged
            print("[config] Ustawiono analysis=merged (jedna baza danych)")
        except Exception:
            pass

    # Nadpisz config wg argumentów topics z CLI
    if args.topics_forums:
        val = args.topics_forums.strip()
        if val.upper() == "ALL":
            config["topics"]["forums"] = ["ALL"]
        else:
            config["topics"]["forums"] = [f.strip() for f in val.split(',') if f.strip()]
    if args.topics_genders:
        config["topics"]["genders"] = [g.strip() for g in args.topics_genders.split(',') if g.strip()]
    if args.topics_combine:
        config["topics"]["combine_forums"] = True
    if args.topics_combined_names:
        val = args.topics_combined_names.strip()
        if val.upper() == "ALL":
            config["topics"]["combined_forum_names"] = ["ALL"]
        else:
            config["topics"]["combined_forum_names"] = [f.strip() for f in val.split(',') if f.strip()]
    if args.topics_output:
        config["topics"]["output_dir"] = args.topics_output
    if args.topics_num_topics is not None:
        config["topics"]["num_topics"] = int(args.topics_num_topics)
    if args.topics_seed is not None:
        config["topics"]["random_seed"] = args.topics_seed
    if args.topics_embedding:
        config["topics"]["embedding_model"] = args.topics_embedding
    if args.topics_keep_docs:
        config["topics"]["keep_documents_in_model"] = True if args.topics_keep_docs == "true" else False
    if args.topics_excluded:
        config["topics"]["excluded_sections"] = [s.strip() for s in args.topics_excluded.split(',') if s.strip()]
    if args.topics_repeats is not None:
        config["topics"]["repeats"] = max(1, int(args.topics_repeats))

    # Katalogi będą tworzone dopiero w krokach, które zapisują pliki

    # Nadpisanie parametrów płci z CLI, jeśli podano
    try:
        if args.gender_weights:
            config.setdefault("gender", {}).setdefault("weights", {})
            config["gender"]["weights"].update(json.loads(args.gender_weights))
        if args.gender_thresholds:
            config.setdefault("gender", {}).setdefault("thresholds", {})
            config["gender"]["thresholds"].update(json.loads(args.gender_thresholds))
    except Exception as exc:
        print(f"⚠️  Nieprawidłowy JSON w --gender-weights/--gender-thresholds: {exc}")

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

    if args.command == "examples":
        # Wyprowadź ścieżki i argumenty; dla eksportu użyj merged_forums.db (zawiera forum_posts)
        db_dir = Path(config["databases"]["dir"]) \
            if os.path.isabs(config["databases"]["dir"]) \
            else ROOT_DIR / config["databases"]["dir"]
        database_path = str(db_dir / config["databases"]["merged"])

        model_path = args.examples_model or config.get("examples", {}).get("model_path")
        topic_num = args.examples_topic if args.examples_topic is not None else config.get("examples", {}).get("topic_num")
        # Jeśli nie podano --examples-topn, domyślnie bierzemy wszystkie dokumenty (None)
        top_n = args.examples_topn if args.examples_topn is not None else None
        results_dir = args.examples_results_dir or config.get("examples", {}).get("results_dir") or None

        if not model_path or topic_num is None:
            print("Brak wymaganych argumentów: --examples-model, --examples-topic")
            return 2

        # Uruchom eksport
        if str(TOPIC_DIR) not in sys.path:
            sys.path.insert(0, str(TOPIC_DIR))
        from examples_export import cli_export
        out_path = cli_export(model_path=model_path, database_path=database_path, topic_num=topic_num, top_n=top_n, results_dir=results_dir)
        print(f"✓ Zapisano przykłady: {out_path}")
        return 0

    if args.command == "domains":
        # Wykonaj raport domen z merged_forums.db
        db_dir = Path(config["databases"]["dir"]) \
            if os.path.isabs(config["databases"]["dir"]) \
            else ROOT_DIR / config["databases"]["dir"]
        database_path = str(db_dir / config["databases"]["merged"])

        # Fora: CLI -> --domains-forums; domyślnie radio_katolik
        forums_cli = (args.domains_forums or "radio_katolik").strip()
        forums = [f.strip() for f in forums_cli.split(',') if f.strip()] if forums_cli else None

        # Katalog wyjściowy
        output_dir = args.domains_output or str(ROOT_DIR / "data/reports")

        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        from report_content_url_domains import cli_report
        try:
            res = cli_report(database_path=database_path, forums=forums, output_dir=output_dir)
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception as exc:
            print(f"✗ Błąd w domains: {exc}")
            return 2

    if args.command == "domain-posts":
        # Eksport postów zawierających URL-e z danej domeny
        db_dir = Path(config["databases"]["dir"]) \
            if os.path.isabs(config["databases"]["dir"]) \
            else ROOT_DIR / config["databases"]["dir"]
        database_path = str(db_dir / config["databases"]["merged"])

        domain = (args.domain or "spowiedz.katolik.pl").strip()
        forums_cli = (args.domain_forums or "radio_katolik").strip()
        forums = [f.strip() for f in forums_cli.split(',') if f.strip()] if forums_cli else None
        output_dir = args.domain_output or str(ROOT_DIR / "data/reports")

        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        from export_posts_by_domain import export_posts_by_domain
        try:
            res = export_posts_by_domain(database_path=database_path, domain=domain, forums=forums, output_dir=output_dir, preview=5)
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception as exc:
            print(f"✗ Błąd w domain-posts: {exc}")
            return 2

    if args.command == "llm-batch":
        # Uruchom klasyfikację LLM Batch API na podstawie Excela
        excel_path = args.llm_excel or "data/topics/results/20250821/M/ALL/185832/examples/topic_2_pi_pis_sld.xlsx"
        batch_size = int(args.llm_batch_size or 10)
        poll_interval = int(args.llm_poll or 10)
        llm_concurrency = int(args.llm_concurrency or 1)

        # Import modułu po dodaniu analysis do sys.path
        # 1) Dodaj ROOT_DIR, aby 'analysis.config' był importowalny i mógł wczytać .env z repo root
        if str(ROOT_DIR) not in sys.path:
            sys.path.insert(0, str(ROOT_DIR))
        # 2) Dodaj katalog topic_modeling, aby bezpośrednio zaimportować batch_classifier
        if str(TOPIC_DIR) not in sys.path:
            sys.path.insert(0, str(TOPIC_DIR))
        try:
            from batch_classifier import run_batch_classification  # type: ignore
        except Exception as exc:
            print(f"✗ Nie można zaimportować batch_classifier: {exc}")
            return 2

        try:
            result = run_batch_classification(
                excel_path=excel_path,
                batch_size=batch_size,
                poll_interval_s=poll_interval,
                concurrency=llm_concurrency,
                resume_dir=args.llm_resume,
                local_from_inputs_only=bool(args.llm_process_existing),
                local_all=bool(args.llm_local),
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(f"✗ Błąd w llm-batch: {exc}")
            return 2

    if args.command == "gender":
        # Jeśli użytkownik nie podał forów – uruchom wersję domyślną dla wszystkich forów (cross-DB)
        if not (config["analysis"].get("forums") or []):
            step_gender_all_forums(config)
        else:
            step_gender(config)
        return 0

    if args.command == "gender-all":
        step_gender_all_forums(config)
        return 0

    if args.command == "clean":
        step_clean(config, hard=args.hard)
        return 0

    if args.command == "all":
        # Uwaga: FinalScraperManager.run() już łączy bazy, więc nie wywołujemy step_merge()
        step_scrape()
        step_analyze(config)
        # Uruchom predykcję płci przed modelowaniem tematów, aby działał fallback COALESCE(..., predicted_gender)
        step_gender_all_forums(config)
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


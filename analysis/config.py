"""
Konfiguracja modułu analizy tokenów
"""

import os
from pathlib import Path

# Wczytaj zmienne z pliku .env (repo root) – najpierw przez python-dotenv, a jeśli brak, prosty parser
def _load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
        # Szukaj .env w katalogu głównym repo (rodzic katalogu analysis)
        root = Path(__file__).resolve().parents[1]
        env_path = root / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=str(env_path), override=False)
        else:
            # Fallback: bieżący katalog roboczy
            cwd_env = Path.cwd() / ".env"
            if cwd_env.exists():
                load_dotenv(dotenv_path=str(cwd_env), override=False)
    except Exception:
        # Ręczne, proste wczytanie klucz=wartość (bez obsługi złożonych przypadków)
        for candidate in [Path(__file__).resolve().parents[1] / ".env", Path.cwd() / ".env"]:
            try:
                if candidate.exists():
                    with open(candidate, "r", encoding="utf-8") as f:
                        for line in f:
                            s = line.strip()
                            if not s or s.startswith("#"):
                                continue
                            if "=" in s:
                                k, v = s.split("=", 1)
                                k = k.strip()
                                v = v.strip().strip('"').strip("'")
                                if k and (k not in os.environ):
                                    os.environ[k] = v
                    break
            except Exception:
                pass

_load_dotenv_if_present()

# Ścieżki baz danych
DEFAULT_SOURCE_DB = "../data/databases/merged_forums.db"
DEFAULT_ANALYSIS_DB = "../data/databases/analysis_forums.db"

# Konfiguracja analizy
DEFAULT_BATCH_SIZE = 100
DEFAULT_INTERVAL_SECONDS = 300  # 5 minut
DEFAULT_MAX_BATCHES = None  # Bez limitu

# Domyślne fora do analizy
DEFAULT_FORUMS_TO_ANALYZE = ['wiara']

# Konfiguracja multiprocessing
MULTIPROCESSING_CONFIG = {
    'max_workers': 4,  # Maksymalna liczba procesów roboczych
    'chunk_size': 50,  # Rozmiar chunka dla multiprocessing
    'use_multiprocessing': True,  # Czy używać multiprocessing
    'process_timeout': 300,  # Timeout dla procesów w sekundach
}

# Konfiguracja tokenizacji
TOKENIZATION_CONFIG = {
    'tokenizer': 'spacy',  # 'spacy', 'simple', 'hybrid'
    'spacy_model': 'pl_core_news_sm',  # Model spaCy dla języka polskiego
    'fallback_to_simple': True,  # Użyj prostego algorytmu jeśli spaCy nie działa
    'polish_language_factor': 0.75,  # 1 token ≈ 0.75 słowa dla prostego algorytmu
    'min_word_length': 2,  # Minimalna długość słowa do liczenia
    'exclude_chars': ['\n', '\r', '\t', ' '],  # Znaki do wykluczenia
    'include_punctuation': False,  # Czy liczyć znaki interpunkcyjne jako tokeny
    'include_whitespace': False,  # Czy liczyć białe znaki jako tokeny
}

# Konfiguracja logowania
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'logs/token_analysis.log',
    'max_file_size': 10 * 1024 * 1024,  # 10 MB
    'backup_count': 5,
}

# Konfiguracja wydajności
PERFORMANCE_CONFIG = {
    'max_workers': 4,  # Maksymalna liczba wątków roboczych
    'connection_timeout': 30,  # Timeout połączenia z bazą w sekundach
    'batch_timeout': 300,  # Timeout przetwarzania partii w sekundach
    'memory_limit_mb': 512,  # Limit pamięci w MB
}

# Konfiguracja bazy danych
DATABASE_CONFIG = {
    'journal_mode': 'WAL',  # Tryb dziennika SQLite
    'synchronous': 'NORMAL',  # Synchronizacja
    'cache_size': -64000,  # Rozmiar cache w kilobajtach (-64MB)
    'temp_store': 'MEMORY',  # Tymczasowe tabele w pamięci
    'mmap_size': 268435456,  # Rozmiar mapowania pamięci (256MB)
}

# Konfiguracja monitorowania
MONITORING_CONFIG = {
    'health_check_interval': 60,  # Sprawdzanie zdrowia co 60 sekund
    'metrics_collection_interval': 300,  # Zbieranie metryk co 5 minut
    'alert_threshold_errors': 10,  # Próg błędów do alertu
    'alert_threshold_memory': 80,  # Próg użycia pamięci do alertu (%)
}

# Konfiguracja LLM (OpenRouter domyślnie)
# Domyślnie korzystamy z OpenRouter (kompatybilny klient OpenAI z base_url).
# Można nadpisać przez LLM_PROVIDER=openai oraz OPENAI_API_KEY.
# LLM_CONFIG = {
#     'provider': os.environ.get('LLM_PROVIDER', 'openrouter'),
#     'model': os.environ.get('LLM_MODEL', 'gpt-5-mini'),
#     'temperature': float(os.environ.get('LLM_TEMPERATURE', 0.5)),
#     'max_tokens': int(os.environ.get('LLM_MAX_TOKENS', 800)),
#     # Klucz: preferuj OPENROUTER_API_KEY, fallback do OPENAI_API_KEY
#     'api_key': os.environ.get('OPENROUTER_API_KEY', os.environ.get('OPENAI_API_KEY', '')),
#     # Endpoint dla OpenRouter; dla OpenAI pozostaw puste lub nadpisz env
#     'base_url': os.environ.get('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1'),
#     # Nagłówki identyfikujące aplikację (opcjonalne dla OpenRouter)
#     'default_headers': {
#         **({'HTTP-Referer': os.environ.get('OPENROUTER_HTTP_REFERER', '')} if os.environ.get('OPENROUTER_HTTP_REFERER') else {}),
#         **({'X-Title': os.environ.get('OPENROUTER_APP_TITLE', '')} if os.environ.get('OPENROUTER_APP_TITLE') else {}),
#     },
# }
LLM_CONFIG = {
    'provider': 'openai',
    'model': 'gpt-5-mini',
    'temperature': 0.5,
    'max_tokens': 800,
    'api_key': os.environ.get('OPENAI_API_KEY', ''),
    'base_url': 'https://api.openai.com/v1',
    'default_headers': None,
}

def get_config():
    """Zwraca konfigurację z możliwością nadpisania zmiennymi środowiskowymi"""
    config = {
        'source_db': os.getenv('ANALYSIS_SOURCE_DB', DEFAULT_SOURCE_DB),
        'analysis_db': os.getenv('ANALYSIS_DB', DEFAULT_ANALYSIS_DB),
        'batch_size': int(os.getenv('ANALYSIS_BATCH_SIZE', DEFAULT_BATCH_SIZE)),
        'interval_seconds': int(os.getenv('ANALYSIS_INTERVAL', DEFAULT_INTERVAL_SECONDS)),
        'max_batches': os.getenv('ANALYSIS_MAX_BATCHES', DEFAULT_MAX_BATCHES),
        'forums_to_analyze': os.getenv('ANALYSIS_FORUMS', ','.join(DEFAULT_FORUMS_TO_ANALYZE)).split(','),
        'tokenization': TOKENIZATION_CONFIG,
        'logging': LOGGING_CONFIG,
        'performance': PERFORMANCE_CONFIG,
        'database': DATABASE_CONFIG,
        'monitoring': MONITORING_CONFIG,
        'multiprocessing': MULTIPROCESSING_CONFIG,
    }
    
    # Konwertuj max_batches na int jeśli podano
    if config['max_batches']:
        try:
            config['max_batches'] = int(config['max_batches'])
        except ValueError:
            config['max_batches'] = None
    
    return config

def validate_config(config):
    """Waliduje konfigurację"""
    errors = []
    
    # Sprawdź ścieżki
    if not os.path.exists(config['source_db']):
        errors.append(f"Baza źródłowa nie istnieje: {config['source_db']}")
    
    # Sprawdź wartości liczbowe
    if config['batch_size'] <= 0:
        errors.append("Rozmiar partii musi być większy od 0")
    
    if config['interval_seconds'] <= 0:
        errors.append("Interwał musi być większy od 0")
    
    if config['max_batches'] is not None and config['max_batches'] <= 0:
        errors.append("Maksymalna liczba partii musi być większa od 0")
    
    # Sprawdź katalogi
    analysis_db_path = Path(config['analysis_db'])
    analysis_dir = analysis_db_path.parent
    if not analysis_dir.exists():
        try:
            analysis_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Nie można utworzyć katalogu: {analysis_dir} - {e}")
    
    # Nie twórz katalogu logów tutaj – zostanie utworzony przy inicjalizacji loggera
    
    return errors

def get_database_connection_string(db_path: str, **kwargs):
    """Tworzy string połączenia z bazą danych z dodatkowymi opcjami"""
    conn_str = f"file:{db_path}"
    
    # Dodaj opcje konfiguracyjne
    options = []
    
    # Opcje z konfiguracji
    config = get_config()
    for key, value in config['database'].items():
        options.append(f"{key}={value}")
    
    # Dodatkowe opcje
    for key, value in kwargs.items():
        options.append(f"{key}={value}")
    
    if options:
        conn_str += "?" + "&".join(options)
    
    return conn_str

def get_environment_info():
    """Zwraca informacje o środowisku"""
    import platform
    import sys
    
    return {
        'python_version': sys.version,
        'platform': platform.platform(),
        'architecture': platform.architecture(),
        'processor': platform.processor(),
        'working_directory': os.getcwd(),
        'environment_variables': {
            'ANALYSIS_SOURCE_DB': os.getenv('ANALYSIS_SOURCE_DB'),
            'ANALYSIS_DB': os.getenv('ANALYSIS_DB'),
            'ANALYSIS_BATCH_SIZE': os.getenv('ANALYSIS_BATCH_SIZE'),
            'ANALYSIS_INTERVAL': os.getenv('ANALYSIS_INTERVAL'),
            'ANALYSIS_MAX_BATCHES': os.getenv('ANALYSIS_MAX_BATCHES'),
        }
    }

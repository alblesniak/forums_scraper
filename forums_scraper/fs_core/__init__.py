"""Core moduł dla forums-scraper.

Zawiera:
- konfigurację (ładowanie YAML/TOML),
- protokół i rejestr analiz (pluginy),
- runner do wykonywania analiz (async, z limitem równoległości),
- opcjonalny dostęp do DB.
"""

__all__ = [
    "config",
]



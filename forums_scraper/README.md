# forums-scraper

Uniwersalny scraper forów (Scrapy) z opcjonalnymi analizami per‑post (online w pipeline lub offline na pliku JSONL/DB).

- Wbudowane "lekkie" analizery: zliczanie tokenów (tiktoken)
- Plug‑inowa architektura analiz (entry points): dodajesz własne analizery bez modyfikacji core
- Tryby pracy:
  - online: podczas scrapowania (Scrapy Item Pipeline)
  - offline: CLI na plikach JSONL lub bazie

## Instalacja (dev)

```bash
pip install -e .[cli,yaml,toml,analyzers-basic]
```

## Szybki start: crawl z analizą online

```bash
fs-cli crawl wiara --config packages/forums_scraper/examples/forums_scraper.yaml
```

Ustaw w `scraper/settings.py` ścieżkę `FS_CONFIG_PATH` lub podaj `--config`.

## Analiza offline (JSONL)

```bash
fs-cli analyze --config packages/forums_scraper/examples/forums_scraper.yaml \
  --input-jsonl data/posts.jsonl --output-jsonl data/posts.analyzed.jsonl
```

Każdy wiersz JSON musi zawierać `content` lub `text`.

## Pluginy (Analyzers)

- Interfejs:

```python
class Analyzer(Protocol):
    name: str
    async def setup(self) -> None: ...
    async def analyze(self, item: Dict[str, Any], context: Optional[Dict] = None) -> Dict[str, Any]: ...
    async def close(self) -> None: ...
```

- Rejestracja jako entry point w `pyproject.toml`:

```toml
[project.entry-points."forums_scraper.analyzers"]
my_analyzer = "my_pkg.my_mod:MyAnalyzer"
```

- Włączenie w configu YAML:

```yaml
analysis:
  enabled: true
  analyzers:
    - name: my_analyzer
      params: {key: value}
  concurrency: 4
```

## Konfiguracja YAML/TOML

Patrz `examples/forums_scraper.yaml`. Ważne pola:
- `analysis.enabled`: włącza/wyłącza analizy
- `analysis.analyzers`: lista analiz do uruchomienia
- `analysis.concurrency`: limit równoległości analiz
- `output.db`: docelowa baza (opcjonalnie)
- `scrapy.concurrent_requests`, `scrapy.autothrottle`: wskazówki dla Scrapy

## Struktura pakietu

```
scraper/               # projekt Scrapy (spiders, pipelines, settings)
fs_core/               # core: config, protokół, rejestr, runner
analyzers_basic/       # przykładowe analizery (token_count)
fs_cli/                # CLI (fs-cli)
examples/              # przykładowe konfiguracje
```

## Rozszerzenia

- Dodaj własny pakiet z analyzerem i zarejestruj entry point.
- Dla analiz CPU‑ciężkich rozważ serwis HTTP (extra `http` + throttling) i analyzer, który woła API.

## Licencja

TBD

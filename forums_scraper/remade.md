# remade.md

Ten dokument opisuje architekturę, moduły i sposób użycia pakietu `forums-scraper`, w tym tworzenie własnych analiz, tryb online/offline, konfigurację oraz najlepsze praktyki.

## 1. Architektura

- `scraper/`: projekt Scrapy (spiders, pipelines, settings).
- `fs_core/`: rdzeń analityki:
  - `config.py`: ładowanie konfiguracji YAML/TOML do `AppConfig`.
  - `protocol.py`: interfejs `Analyzer` (setup/analyze/close).
  - `registry.py`: ładowanie pluginów przez entry points (`forums_scraper.analyzers`).
  - `runner.py`: asynchroniczny uruchamiacz analiz z limitem równoległości.
- `analyzers_basic/`: przykładowe analizery (np. `TokenCountAnalyzer`).
- `fs_cli/`: CLI (`fs-cli`) z komendami: `crawl`, `analyze`, `list-analyzers`.
- `examples/`: przykładowe konfiguracje.

Kluczowe założenia:
- Analizy per‑post wykonujemy w `Item Pipeline` (tryb online).
- Analizy korpusowe (np. topic modeling) rekomendowane offline po crawl’u.
- Pluginy są wykrywane i wstrzykiwane wg konfiguracji użytkownika (entry points).

## 2. Tryby pracy

### 2.1 Online (Scrapy Item Pipeline)
- Włączane przez konfigurację (`analysis.enabled: true`).
- Pipeline `scraper.pipelines.analysis.AnalysisPipeline` ładuje config i uruchamia `AnalysisRunner`.
- Każdy item jest wzbogacany o pole `analysis` (słownik wyników). 
- Bezpieczne, asynchroniczne wywołania z semaforem (`analysis.concurrency`).

### 2.2 Offline (CLI na JSONL/DB)
- Komenda `fs-cli analyze` przetwarza plik JSONL, dodając pole `analysis` do każdego rekordu.
- Idealne do ponownego uruchamiania analiz lub testów jakości.

## 3. Konfiguracja

Przykład (`examples/forums_scraper.yaml`):

```yaml
analysis:
  enabled: true
  analyzers:
    - name: token_count
      params:
        model: cl100k_base
  concurrency: 4
output:
  db: sqlite:///data/databases/forums.db
scrapy:
  concurrent_requests: 16
  autothrottle: true
```

- `analysis.enabled`: włącza/wyłącza analizy w pipeline.
- `analysis.analyzers`: lista pluginów wg nazw entry pointów.
- `analysis.concurrency`: limit równoległości analiz (I/O CPU‑light).
- `output.*`: miejsce na konfigurację zapisu (opcjonalne, zależnie od Twojej warstwy DB).

## 4. Pluginy (Analyzers)

Interfejs (zob. `fs_core/protocol.py`):

```python
class Analyzer(Protocol):
    name: str
    async def setup(self) -> None: ...
    async def analyze(self, item: Dict[str, Any], context: Optional[Dict] = None) -> Dict[str, Any]: ...
    async def close(self) -> None: ...
```

Rejestracja pluginu w `pyproject.toml` (Twojego pakietu):

```toml
[project.entry-points."forums_scraper.analyzers"]
my_analyzer = "my_pkg.my_mod:MyAnalyzer"
```

Włączanie pluginu w YAML:

```yaml
analysis:
  enabled: true
  analyzers:
    - name: my_analyzer
      params: {threshold: 0.5}
```

Wskazówki implementacyjne:
- `setup()`: inicjalizacja modelu/klienta (np. ładowanie tokenizera, sesji HTTP).
- `analyze(item)`: spodziewa się, że `item` zawiera `content` lub `text`.
- Zwracaj słownik: najlepiej pod własnym kluczem, np. `{"my_analyzer": {...}}` lub prostą wartość.
- Obsługuj błędy lokalnie i zwracaj sygnał błędu (runner i tak izoluje wyjątki).

## 5. Integracja z Scrapy

- W `scraper/settings.py` dodaliśmy:
  - `ITEM_PIPELINES` z `scraper.pipelines.analysis.AnalysisPipeline`.
  - `FS_CONFIG_PATH` – domyślną ścieżkę do configu (można przekazać `-s FS_CONFIG_PATH=...`).
  - `TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"` (wsparcie `async` w pipeline).

Uruchomienie:

```bash
fs-cli crawl wiara --config packages/forums_scraper/examples/forums_scraper.yaml
```

## 6. CLI

- `fs-cli list-analyzers` – wypisuje nazwy dostępnych pluginów.
- `fs-cli analyze --config CFG --input-jsonl IN --output-jsonl OUT` – analiza offline.
- `fs-cli crawl SPIDER --config CFG [-a key=val,...]` – uruchamia spidera z konfiguracją.

## 7. Zależności i extras

Core jest lekki. Dodatkowe możliwości instalujesz jako „extras”:

```toml
[project.optional-dependencies]
cli = ["typer>=0.12"]
analyzers-basic = ["tiktoken>=0.7"]
http = ["httpx>=0.27"]
yaml = ["pyyaml>=6.0"]
toml = ["tomli>=2.0; python_version < '3.11'"]
```

Przykład instalacji:

```bash
pip install -e .[cli,yaml,toml,analyzers-basic]
```

## 8. Najlepsze praktyki wydajności

- Ustaw `analysis.concurrency` adekwatnie do typu zadań (I/O vs CPU).
- Zewnętrzne modele/LLM – używaj pluginów HTTP z kontrolą QPS i retry.
- Ciężkie CPU uruchamiaj poza procesem Scrapy (osobny serwis / offline / executor).

## 9. Testy i debugowanie

- Testuj pluginy niezależnie, mockując `item`y.
- Używaj `fs-cli analyze` do powtarzalnych testów na małych plikach JSONL.
- Włącz logging Scrapy (`LOG_LEVEL=INFO`) podczas debugowania.

## 10. Roadmapa

- Dodatkowe pluginy: lematyzacja spaCy (extra), prosty NER, detekcja języka.
- Eksport Parquet/Arrow, wsparcie dla DB (SQLAlchemy async) jako opcja.
- Throttling per‑plugin, metryki (Prometheus/OTel).

## 11. FAQ

- "Czy muszę mieć YAML?" – możesz użyć TOML (`tomli` dla py<3.11).
- "Czy muszę włączać analizy online?" – nie; ustaw `analysis.enabled: false`.
- "Jak dodać własny analyzer?" – napisz klasę zgodną z `Analyzer`, zarejestruj entry point, włącz w YAML.

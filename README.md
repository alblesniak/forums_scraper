# Forums Scraper

Aplikacja do scrapowania forów religijnych zbudowana w Scrapy z zaawansowanym modułem analizy tokenów.

## Struktura projektu

```
forums_scraper/
├── README.md                    # Ten plik
├── pyproject.toml              # Konfiguracja projektu Python
├── uv.lock                     # Lock file dla uv
├── scrapy.cfg                  # Konfiguracja Scrapy
├── scraper/                    # Główny moduł Scrapy
│   ├── __init__.py
│   ├── items.py               # Definicje elementów danych
│   ├── middlewares.py         # Middleware Scrapy
│   ├── pipelines.py           # Pipeline do przetwarzania danych
│   ├── settings.py            # Ustawienia Scrapy
│   ├── utils.py               # Funkcje pomocnicze
│   └── spiders/               # Pająki Scrapy
│       ├── __init__.py
│       ├── dolina_modlitwy.py
│       ├── radio_katolik.py
│       ├── wiara.py
│       └── z_chrystusem.py
├── data/
│   ├── databases/              # Bazy danych SQLite (per-spider, merged, analysis)
│   ├── logs/                   # Logi (scrapy, analysis)
│   └── topics/                 # Artefakty Top2Vec: models/, results/, logs/
├── logs/                       # Logi aplikacji
├── scripts/                    # Skrypty pomocnicze
│   ├── run_all_scrapers.py    # Uruchamianie wszystkich scraperów
│   ├── merge_databases.py     # Łączenie baz danych
│   ├── test_scraper.py        # Testowanie pojedynczego scrapera
│   └── run_analysis_with_spiders.py  # Uruchamianie analizy równolegle ze spiderami
├── analysis/                   # Moduł analizy tokenów
│   ├── __init__.py            # Inicjalizacja modułu
│   ├── README.md              # Główna dokumentacja modułu
│   ├── config.py              # Konfiguracja
│   ├── cli.py                 # Interfejs wiersza poleceń
│   ├── run_analysis_daemon.py # Skrypt daemon
│   ├── test_analysis.py       # Testy modułu
│   ├── requirements.txt        # Zależności
│   └── tokenization/          # Moduł tokenizacji
│       ├── __init__.py        # Inicjalizacja tokenizacji
│       ├── token_analyzer.py  # Główny analizator tokenów
│       ├── install_spacy_model.py # Instalacja spaCy
│       ├── compare_tokenizers.py  # Porównanie algorytmów
│       └── README.md          # Dokumentacja tokenizacji
└── requirements.txt            # Zależności Python
```

## Instalacja

```bash
# Używając uv (zalecane)
uv sync

# Lub tradycyjnie
pip install -r requirements.txt
```

## Uruchomienie

### Jednolity pipeline (zalecane)

```bash
# Wykonaj pełny pipeline: scrapowanie -> analiza tokenów -> modelowanie tematów -> czyszczenie
python scripts/pipeline.py all

# Lub poszczególne kroki
python scripts/pipeline.py scrape   # uruchamia wszystkie spidery i łączy bazy
python scripts/pipeline.py analyze  # tworzy analysis_forums.db i liczy tokeny
python scripts/pipeline.py topics   # modelowanie tematyczne (Top2Vec)
python scripts/pipeline.py clean    # czyści pośrednie bazy wg configu

# Z własną konfiguracją
python scripts/pipeline.py all --config scripts/pipeline.config.json
```

Konfiguracja domyślna jest wbudowana w `scripts/pipeline.py`. Możesz ją nadpisać przez `scripts/pipeline.config.json` lub zmienne środowiskowe dla modelowania tematycznego. Artefakty trzymamy w `data/`:

```bash
export TOPIC_DATABASE_PATH=databases/analysis_forums.db
export TOPIC_OUTPUT_DIR=data/topics
export TOPIC_FORUMS=wiara
export TOPIC_GENDERS=M,K
```

### Pojedynczy scraper (alternatywnie)

```bash
cd scraper
scrapy crawl nazwa_spidera
```

### Mini test E2E: jedna strona konkretnego wątku (szybko)

Dla szybkiej weryfikacji end-to-end dodano tryb `only_thread_url` w spiderach: `wiara`, `radio_katolik`, `dolina_modlitwy`, `z_chrystusem`.

1. Pobierz jedną stronę wątku i zapisz do lokalnej bazy danego spidera:

```bash
python -m scrapy crawl wiara -s SETTINGS_MODULE=scraper.settings \
  -a only_thread_url='https://forum.wiara.pl/viewtopic.php?f=37&t=42547' \
  -s CLOSESPIDER_PAGECOUNT=1 -s LOG_LEVEL=INFO
```

Analogicznie dla pozostałych forów (podaj URL `viewtopic.php?...` z danego forum). Poniżej przykłady i wskazówki, jak znaleźć linki:

#### Radio Katolik

- Jak znaleźć: otwórz `https://dyskusje.radiokatolik.pl/`, wejdź do dowolnej sekcji, skopiuj adres wątku (zawiera `viewtopic.php?...`).
- Przykład (zamień na realny URL wątku):

```bash
python -m scrapy crawl radio_katolik -s SETTINGS_MODULE=scraper.settings \
  -a only_thread_url='https://dyskusje.radiokatolik.pl/viewtopic.php?f=1&t=1' \
  -s CLOSESPIDER_PAGECOUNT=1 -s LOG_LEVEL=INFO
```

#### Dolina Modlitwy

- Jak znaleźć: otwórz `https://dolinamodlitwy.pl/forum/`, wejdź do sekcji, skopiuj link wątku `viewtopic.php?...`.
- Przykład (zamień na realny URL wątku):

```bash
python -m scrapy crawl dolina_modlitwy -s SETTINGS_MODULE=scraper.settings \
  -a only_thread_url='https://dolinamodlitwy.pl/forum/viewtopic.php?f=2&t=4' \
  -s CLOSESPIDER_PAGECOUNT=1 -s LOG_LEVEL=INFO
```

#### Z Chrystusem

- Jak znaleźć: otwórz `https://zchrystusem.pl/`, wejdź do sekcji, skopiuj link wątku `viewtopic.php?...`.
- Przykład (zamień na realny URL wątku):

```bash
python -m scrapy crawl z_chrystusem -s SETTINGS_MODULE=scraper.settings \
  -a only_thread_url='https://zchrystusem.pl/viewtopic.php?f=2&t=4' \
  -s CLOSESPIDER_PAGECOUNT=1 -s LOG_LEVEL=INFO
```

2. Zmerguj bazy do jednej (na potrzeby analizy):

```bash
python scripts/merge_all_databases.py --target data/databases/merged_forums.db --no-offset
```

3. Uruchom szybką analizę na małej próbce i pokaż podsumowanie:

```bash
python analysis/cli.py --source-db data/databases/merged_forums.db \
  --analysis-db data/databases/analysis_forums.db \
  --create-db --batch 50 --summary
```

### Menedżer scraperów (alternatywnie)

```bash
# Z poziomu głównego katalogu
python run_scrapers.py

# Lub bezpośrednio
python scripts/run_all_scrapers_final.py
```

## Dostępne pająki

- `dolina_modlitwy` - Forum Dolina Modlitwy
- `radio_katolik` - Forum Radio Katolik
- `wiara` - Forum Wiara
- `z_chrystusem` - Forum Z Chrystusem

## Konfiguracja

Główne ustawienia znajdują się w `scraper/settings.py`. Można tam dostosować:

- Opóźnienia między requestami
- Liczbę równoczesnych requestów
- Ustawienia bazy danych
- Poziom logowania

## Bazy danych

Każdy scraper tworzy osobną bazę SQLite w katalogu `data/databases/`. Format nazwy: `forum_[nazwa_spidera].db`

### Połączona baza danych

Skrypt `scripts/merge_all_databases.py` łączy wszystkie bazy w jedną `merged_forums.db` w `data/databases/`.

### Baza analizy

Moduł analizy tworzy kopię bazy danych (`analysis_forums.db`) w `data/databases/` z dodatkowymi tabelami:

- `token_analysis` - wyniki analizy tokenów dla każdego posta
- `analysis_stats` - statystyki dzienne analizy

## Logi

Logi są zapisywane w katalogu `data/logs/` z timestampami i poziomami logowania.

### Logi analizy

- `data/logs/token_analysis.log` - Główne logi analizy tokenów
- `data/logs/analysis_daemon.log` - Logi daemon analizy

## Moduł analizy tokenów

Moduł analizy zapewnia bezpieczne przeliczanie tokenów w postach forum bez zakłócania pracy spiderów:

### 🎯 Funkcjonalności

- **Bezpieczna analiza**: Działa na kopii bazy danych
- **Przeliczanie tokenów**: Automatyczne obliczanie liczby tokenów, słów i znaków
- **Ciągłe monitorowanie**: Może działać w tle jako daemon
- **Inteligentne przetwarzanie**: Analizuje tylko nowe lub zmienione posty
- **Statystyki**: Szczegółowe raporty i metryki analizy

### 🚀 Szybki start

```bash
# Z pipeline (zalecane)
python scripts/pipeline.py analyze

# Bezpośrednio z CLI analizy
python analysis/cli.py --create-db --all --summary
```

### 📊 Metryki

- **Dokładna tokenizacja**: Używa spaCy z modelem polskim dla precyzyjnego liczenia tokenów
- **Fallback**: Automatyczne przełączanie na prosty algorytm jeśli spaCy nie działa
- **Liczba tokenów, słów i znaków** w każdym poście
- **Postęp analizy** (procent przeanalizowanych postów)
- **Statystyki dzienne** i wydajnościowe
- **Hash treści** dla śledzenia zmian
- **Statystyki tokenizacji**: Procent użycia spaCy vs prostego algorytmu

Wszystkie artefakty trzymamy w `data/`. Katalog `analysis/topic_modeling` zawiera tylko kod (bez artefaktów).
Więcej informacji w [dokumentacji modułu analizy](analysis/README.md).

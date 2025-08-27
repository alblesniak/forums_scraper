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

### Generator taksonomii i promptu (Excel + LLM)

Moduł generuje 3‑poziomową taksonomię i finalny prompt systemowy wyłącznie na podstawie pliku Excel z postami. Pipeline działa wieloetapowo: streszczenia + cytat, propozycje głównych kategorii, konsolidacja, indukcja poziomów 2/3, numeracja, przypisania postów, eksport artefaktów, wygenerowanie docelowego `system_message` (PL).

#### Wymagania (OpenRouter + DeepSeek R1 0528)

- Zależność: `openai` (używamy klienta z `base_url`)
- Konfiguracja LLM w `analysis/config.py` (`LLM_CONFIG`) jest domyślnie ustawiona na OpenRouter i model `deepseek/deepseek-r1-0528:free`.
- Ustaw klucz środowiskowy:

```bash
export OPENROUTER_API_KEY="sk-or-..."
# opcjonalnie (dla statystyk w OpenRouter):
export OPENROUTER_HTTP_REFERER="https://twoja-aplikacja.example"
export OPENROUTER_APP_TITLE="Forums Scraper"
```

Możesz nadpisać endpoint/model przez zmienne:

```bash
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
export LLM_MODEL="deepseek/deepseek-r1-0528:free"
export LLM_TEMPERATURE=0.7
export LLM_MAX_TOKENS=1000
```

Źródło modelu i przykłady użycia w API: [DeepSeek: R1 0528 (free) — OpenRouter](https://openrouter.ai/deepseek/deepseek-r1-0528:free)

#### Dane wejściowe (Excel)

Minimalne kolumny:

- `post_id` (jeśli brak, zostanie nadany sekwencyjnie)
- `content` (treść posta)

Domyślnie wykorzystujemy przykład:

```
data/topics/results/20250821/M/ALL/185832/examples/topic_2_pi_pis_sld.xlsx
```

#### Uruchomienie

```bash
# Domyślne ścieżki i temat: polityka
python scripts/pipeline.py taxonomy --taxonomy-theme polityka

# Parametry opcjonalne
python scripts/pipeline.py taxonomy \
  --taxonomy-excel /pełna/ścieżka.xlsx \
  --taxonomy-output /Users/alb/repos/forums_scraper/data/topics \
  --taxonomy-theme polityka \
  --taxonomy-batch 50 \
  --taxonomy-max-posts 500
```

#### Co powstaje (artefakty)

Artefakty zapisują się do katalogu:

```
data/topics/taxonomies/<YYYYMMDD>/<theme_slug>_<HHMMSS>/
```

Wewnątrz znajdziesz:

- `taxonomy.json` – znumerowana taksonomia 3‑poziomowa (`1`, `1.1`, `1.1.1`)
- `prompt_system_message.md` – gotowy system_message (PL) z Twoimi zasadami i pełną listą kategorii
- `assignments.jsonl` – przypisania postów: `post_id`, `path` (np. `3.2.5`), `confidence`
- `labeled_<oryginalny_plik>.xlsx` – Excel z dodatkowymi kolumnami: `summary`, `quote`, `path`, `confidence`

#### Jak to działa (skrót procesu)

1. Streszczenia: dla każdego posta powstaje krótkie podsumowanie (1–2 zdania) i 1 cytat
2. Propozycje głównych kategorii per post (1–3 kandydatury)
3. Konsolidacja kategorii głównych (8–15 spójnych nazw + krótkie opisy)
4. Indukcja podkategorii (poziom 2) i pod‑podkategorii (poziom 3)
5. Numeracja hierarchii (1, 1.1, 1.1.1)
6. Przypisania postów do pełnych ścieżek (`X.Y.Z`) z `confidence`
7. Eksport artefaktów i wygenerowanie `system_message`

#### Dobre praktyki

- Zadbaj o sensowny dobór tematu (`--taxonomy-theme`) – wpływa na jakość nazw
- Batch (`--taxonomy-batch`) dostosuj do limitów tokenów – zwykle 50–100 działa dobrze
- Jeżeli `confidence` często < 0.6 lub dużo „Inne”, uruchom proces na większym zbiorze lub zawęź temat

#### Rozwiązywanie problemów

- Błąd klucza: sprawdź `LLM_CONFIG['api_key']` w `analysis/config.py`
- Brak kolumny `content`: dostosuj nagłówki w Excelu (możesz użyć `text`, `post`, `message`, `body` – zostaną zmapowane)
- Brak `openai`: zainstaluj zależność (`uv sync` lub `pip install -r requirements.txt`)

#### Automatyczny slug tematu

- Jeśli podasz `--taxonomy-theme`, zostanie on zsanityzowany do slug'a (małe litery, myślniki).
- Jeśli nie podasz, slug zostanie automatycznie wyciągnięty z nazwy pliku Excela (zsanityzowany).

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

## Tokenizacja spaCy (uv + CLI)

Poniższe komendy uruchomisz z katalogu głównego. Wykorzystują CLI `token-analysis` dodane w `pyproject.toml` i działają w środowisku `uv`.

### 1) Połącz bazy poszczególnych forów do jednej

```bash
uv run merge-databases --target data/databases/merged_forums.db
```

### 2) Utwórz bazę do analizy (kopię źródłowej bazy)

```bash
uv run --with spacy --with pl-core-news-sm \
  token-analysis \
  --source-db data/databases/merged_forums.db \
  --analysis-db data/databases/analysis_forums.db \
  --forums radio_katolik,dolina_modlitwy \
  --create-db
```

### 3) Uruchom analizę tokenów (spaCy)

```bash
uv run --with spacy --with pl-core-news-sm \
  token-analysis \
  --source-db data/databases/merged_forums.db \
  --analysis-db data/databases/analysis_forums.db \
  --forums radio_katolik,dolina_modlitwy \
  --all
```

### 4) Podsumowanie wyników

```bash
uv run --with spacy --with pl-core-news-sm \
  token-analysis \
  --source-db data/databases/merged_forums.db \
  --analysis-db data/databases/analysis_forums.db \
  --forums radio_katolik,dolina_modlitwy \
  --summary
```

### Opcja: instalacja spaCy i modelu na stałe

Zamiast `--with ...` możesz dodać zależności trwale i pobrać model:

```bash
uv add spacy
uv run python -m spacy download pl_core_news_sm
```

Po tej instalacji `--with spacy --with pl-core-news-sm` nie jest już potrzebne.

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

# Moduł Analizy Tokenów z Multiprocessing

Zaawansowany moduł do analizy tokenów dla postów forum z wykorzystaniem multiprocessing, tqdm i możliwością wyboru forów.

## 🚀 Funkcjonalności

- **Multiprocessing**: Analiza postów w wielu procesach dla lepszej wydajności
- **Paski postępu**: Wizualizacja postępu analizy z użyciem tqdm
- **Wybór forów**: Możliwość analizy tylko określonych forów
- **Konfiguracja**: Elastyczna konfiguracja przez pliki i zmienne środowiskowe
- **Monitoring**: Ciągła analiza w tle z możliwością zatrzymania
- **Statystyki**: Szczegółowe statystyki analizy i postępu

## 📦 Instalacja

```bash
# Zainstaluj zależności
pip install -r requirements.txt

# Lub używając uv
uv pip install -r requirements.txt
```

## ⚙️ Konfiguracja

### Zmienne środowiskowe

```bash
# Bazy danych
export ANALYSIS_SOURCE_DB="databases/merged_forums.db"
export ANALYSIS_DB="databases/analysis_forums.db"

# Fora do analizy (oddzielone przecinkami)
export ANALYSIS_FORUMS="radio_katolik,dolina_modlitwy"

# Multiprocessing
export ANALYSIS_BATCH_SIZE=100
export ANALYSIS_INTERVAL=300
```

### Domyślne fora

Domyślnie analizowane są fora:
- `radio_katolik`
- `dolina_modlitwy`

## 🎯 Użycie

### Interfejs CLI

```bash
# Utwórz bazę analizy
python cli.py --create-db

# Pokaż informacje o forach
python cli.py --info

# Analizuj partię postów
python cli.py --batch 100

# Analizuj wszystkie posty z określonych forów
python cli.py --all

# Ciągła analiza co 5 minut
python cli.py --continuous --interval 300

# Pokaż podsumowanie
python cli.py --summary

# Wybierz fora do analizy
python cli.py --forums "radio_katolik,wiara" --all

# Wyłącz multiprocessing
python cli.py --no-multiprocessing --all

# Dostosuj liczbę procesów
python cli.py --workers 8 --chunk-size 100 --all
```

### Opcje multiprocessing

```bash
# 8 procesów roboczych
--workers 8

# Rozmiar chunka 100 postów
--chunk-size 100

# Wyłącz multiprocessing
--no-multiprocessing

# Wyłącz paski postępu
--no-progress
```

### Przykłady użycia

```bash
# Szybka analiza małej partii
python cli.py --batch 50

# Pełna analiza wszystkich forów z postępem
python cli.py --all

# Ciągła analiza w tle
python cli.py --continuous --interval 600 --batch-size 200

# Analiza tylko jednego forum
python cli.py --forums "radio_katolik" --all

# Analiza z 16 procesami dla maksymalnej wydajności
python cli.py --workers 16 --chunk-size 200 --all
```

## 🔧 Konfiguracja zaawansowana

### Plik config.py

```python
# Konfiguracja multiprocessing
MULTIPROCESSING_CONFIG = {
    'max_workers': 4,           # Liczba procesów
    'chunk_size': 50,           # Rozmiar chunka
    'use_multiprocessing': True, # Włącz/wyłącz
    'process_timeout': 300,     # Timeout w sekundach
}

# Domyślne fora
DEFAULT_FORUMS_TO_ANALYZE = ['radio_katolik', 'dolina_modlitwy']
```

### Zmienne środowiskowe

```bash
# Multiprocessing
export ANALYSIS_MULTIPROCESSING_MAX_WORKERS=8
export ANALYSIS_MULTIPROCESSING_CHUNK_SIZE=100
export ANALYSIS_MULTIPROCESSING_USE=false

# Fora
export ANALYSIS_FORUMS="radio_katolik,dolina_modlitwy,wiara"
```

## 📊 Monitorowanie

### Statystyki w czasie rzeczywistym

```bash
# Pokaż aktualny status
python cli.py --summary

# Informacje o forach
python cli.py --info

# Ciągłe monitorowanie
python cli.py --continuous --interval 60
```

### Logi

Logi są zapisywane w katalogu `logs/`:
- `token_analysis.log` - Główne logi analizy
- `analysis_daemon.log` - Logi daemon (jeśli używany)

## 🚨 Rozwiązywanie problemów

### Błąd multiprocessing

```bash
# Wyłącz multiprocessing
python cli.py --no-multiprocessing --all

# Zmniejsz liczbę procesów
python cli.py --workers 2 --all
```

### Błąd pamięci

```bash
# Zmniejsz rozmiar chunka
python cli.py --chunk-size 25 --all

# Użyj mniejszej liczby procesów
python cli.py --workers 2 --chunk-size 25 --all
```

### Błąd bazy danych

```bash
# Sprawdź połączenie
python cli.py --info

# Utwórz nową bazę analizy
python cli.py --create-db
```

## 📈 Wydajność

### Optymalne ustawienia

- **4-8 procesów** dla większości systemów
- **Rozmiar chunka 50-100** postów
- **Włącz multiprocessing** dla partii >10 postów

### Przykłady wydajności

```bash
# Szybka analiza (małe partie)
python cli.py --workers 4 --chunk-size 50 --batch 100

# Wydajna analiza (duże partie)
python cli.py --workers 8 --chunk-size 200 --all

# Oszczędna analiza (mało pamięci)
python cli.py --workers 2 --chunk-size 25 --all
```

## 🔄 Ciągła analiza

### Uruchomienie daemon

```bash
# Uruchom w tle
python cli.py --continuous --interval 300 --batch-size 100

# Lub użyj oryginalnego daemon
python run_analysis_daemon.py --daemon
```

### Zatrzymanie

```bash
# Ctrl+C w trybie continuous
# Lub dla daemon
python run_analysis_daemon.py --stop
```

## 🧪 Testowanie

```bash
# Uruchom testy
python test_analysis.py

# Test z określonymi forami
ANALYSIS_FORUMS="radio_katolik" python test_analysis.py
```

## 📁 Struktura plików

```
analysis/
├── cli.py                 # Interfejs wiersza poleceń
├── config.py             # Konfiguracja
├── tokenization/         # Moduł analizy tokenów
│   ├── token_analyzer.py # Główny analizator
│   └── ...
├── test_analysis.py      # Testy
└── requirements.txt      # Zależności
```

## 🤝 Wsparcie

- Sprawdź logi w katalogu `logs/`
- Użyj `--help` dla opcji CLI
- Testuj z małymi partiami przed pełną analizą
- Dostosuj liczbę procesów do możliwości systemu

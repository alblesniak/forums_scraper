# Moduł Tokenizacji

Moduł odpowiedzialny za dokładną analizę i liczenie tokenów w postach forum.

## 🎯 Funkcjonalności

- **Dokładna tokenizacja** używając spaCy z modelem polskim
- **Automatyczny fallback** do prostego algorytmu
- **Inteligentne filtrowanie** tokenów (interpunkcja, białe znaki)
- **Statystyki tokenizacji** (spaCy vs prosty algorytm)
- **Optymalizacja wydajności** z cache'owaniem

## 📁 Struktura

```
tokenization/
├── __init__.py              # Inicjalizacja modułu
├── token_analyzer.py        # Główny analizator tokenów
├── install_spacy_model.py   # Instalacja spaCy i modelu polskiego
├── compare_tokenizers.py    # Porównanie algorytmów tokenizacji
└── README.md                # Ta dokumentacja
```

## 🚀 Szybki start

### Instalacja spaCy

```bash
# Automatyczna instalacja
python analysis/tokenization/install_spacy_model.py

# Lub ręcznie
pip install spacy>=3.5.0
python -m spacy download pl_core_news_sm
```

### Użycie w kodzie

```python
from analysis.tokenization import TokenAnalyzer

# Utwórz analizator
analyzer = TokenAnalyzer()

# Analizuj tekst
result = analyzer.calculate_tokens("To jest test polskiego tekstu.")
print(f"Tokeny: {result['tokens']}, Słowa: {result['words']}")
```

### Porównanie algorytmów

```bash
python analysis/tokenization/compare_tokenizers.py
```

## 🔧 Konfiguracja

### Parametry tokenizacji

```python
TOKENIZATION_CONFIG = {
    'tokenizer': 'spacy',           # 'spacy', 'simple', 'hybrid'
    'spacy_model': 'pl_core_news_sm',  # Model spaCy
    'fallback_to_simple': True,     # Użyj prostego algorytmu jako fallback
    'include_punctuation': False,   # Czy liczyć interpunkcję
    'include_whitespace': False,    # Czy liczyć białe znaki
    'min_word_length': 2,           # Minimalna długość tokenu
}
```

## 🤖 Algorytmy Tokenizacji

### 1. spaCy (Główny)
- **Model**: `pl_core_news_sm` - specjalistyczny dla języka polskiego
- **Dokładność**: Wysoka - prawdziwa analiza lingwistyczna
- **Wydajność**: Średnia - wymaga załadowania modelu

### 2. Prosty Algorytm (Fallback)
- **Metoda**: `words * 0.75` (dostosowane dla języka polskiego)
- **Dokładność**: Niska - przybliżenie
- **Wydajność**: Wysoka - szybkie obliczenia

## 📊 Metryki i Statystyki

### Statystyki tokenizacji

```python
stats = {
    'spacy_tokens': 1250,      # Posty przetworzone przez spaCy
    'simple_tokens': 50,       # Posty przetworzone przez prosty algorytm
    'total_processed': 1300,   # Łączna liczba przetworzonych postów
}
```

## 🧪 Testowanie

### Testy jednostkowe

```bash
# Uruchom testy modułu
python -m analysis.test_analysis

# Testy tokenizacji
python analysis/tokenization/compare_tokenizers.py
```

## 🚨 Rozwiązywanie Problemów

### Błąd: "spaCy nie jest dostępne"

```bash
# Sprawdź instalację
python -c "import spacy; print('spaCy OK')"

# Zainstaluj ponownie
python analysis/tokenization/install_spacy_model.py
```

## 📚 API Reference

### TokenAnalyzer

```python
class TokenAnalyzer:
    def __init__(self, source_db: str, analysis_db: str, config: Dict = None)
    def calculate_tokens(self, text: str) -> Dict[str, int]
    def _calculate_tokens_spacy(self, text: str) -> Optional[int]
    def _calculate_tokens_simple(self, text: str) -> int
```

### TokenAnalysisResult

```python
@dataclass
class TokenAnalysisResult:
    post_id: int
    token_count: int
    word_count: int
    character_count: int
    analysis_hash: str
    analyzed_at: datetime
    processing_time_ms: float
```

"""
Moduł analizy danych forum
Zapewnia bezpieczną analizę danych bez zakłócania pracy spiderów
"""

from .tokenization import TokenAnalyzer, TokenAnalysisResult
from .values.classifier import run_values_classification
from .politics.classifier import run_politics_preference_classification

__version__ = "1.0.0"
__author__ = "Forum Scraper Team"

__all__ = ['TokenAnalyzer', 'TokenAnalysisResult', 'run_values_classification', 'run_politics_preference_classification']

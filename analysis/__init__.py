"""
Moduł analizy danych forum
Zapewnia bezpieczną analizę danych bez zakłócania pracy spiderów
"""

from .tokenization import TokenAnalyzer, TokenAnalysisResult

__version__ = "1.0.0"
__author__ = "Forum Scraper Team"

__all__ = ['TokenAnalyzer', 'TokenAnalysisResult']

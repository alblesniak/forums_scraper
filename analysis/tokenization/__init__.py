"""
Moduł tokenizacji dla analizy postów forum
Zapewnia dokładną tokenizację używając spaCy lub prostego algorytmu jako fallback
"""

from .token_analyzer import TokenAnalyzer, TokenAnalysisResult

__version__ = "1.0.0"
__author__ = "Forum Scraper Team"

__all__ = ['TokenAnalyzer', 'TokenAnalysisResult']

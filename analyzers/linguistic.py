"""
Analizatory językowe z wykorzystaniem spaCy dla tokenizacji, lematyzacji i analizy morfosyntaktycznej.
"""

import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

try:
    import spacy
    from spacy.lang.pl import Polish
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None
    Polish = None

from core.protocol import Analyzer


@dataclass
class TokenInfo:
    """Informacje o tokenie."""
    token: str
    lemma: str
    pos: str
    tag: str
    dep: str
    is_alpha: bool
    is_stop: bool
    is_punct: bool
    sentiment_score: Optional[float] = None


class BasicTokenizer(Analyzer):
    """Podstawowy tokenizer bez zależności zewnętrznych."""
    
    def __init__(self, **kwargs):
        self.lowercase = kwargs.get('lowercase', True)
        self.remove_punctuation = kwargs.get('remove_punctuation', False)
        self.min_token_length = kwargs.get('min_token_length', 1)
    
    async def setup(self):
        """Przygotowanie analizatora."""
        pass
    
    async def close(self):
        """Zamknięcie analizatora."""
        pass
    
    async def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Podstawowa tokenizacja tekstu."""
        content = data.get('content', '')
        if not content:
            return {}
        
        # Podstawowa tokenizacja przez podział na słowa
        tokens = re.findall(r'\b\w+\b', content)
        
        if self.lowercase:
            tokens = [token.lower() for token in tokens]
        
        if self.min_token_length > 1:
            tokens = [token for token in tokens if len(token) >= self.min_token_length]
        
        # Statystyki
        unique_tokens = list(set(tokens))
        avg_token_length = sum(len(token) for token in tokens) / len(tokens) if tokens else 0
        
        return {
            'tokens': tokens,
            'token_stats': {
                'total_tokens': len(tokens),
                'unique_tokens': len(unique_tokens),
                'avg_token_length': avg_token_length
            }
        }


class SpacyAnalyzer(Analyzer):
    """Zaawansowany analizator wykorzystujący spaCy."""
    
    def __init__(self, **kwargs):
        if not SPACY_AVAILABLE:
            raise ImportError("spaCy nie jest zainstalowane. Zainstaluj: pip install spacy")
        
        self.model_name = kwargs.get('model', 'pl_core_news_lg')
        self.nlp = None
        self.include_sentiment = kwargs.get('include_sentiment', False)
        self.batch_size = kwargs.get('batch_size', 100)
        self.max_length = kwargs.get('max_length', 1000000)  # 1M znaków
    
    async def setup(self):
        """Ładowanie modelu spaCy."""
        try:
            self.nlp = spacy.load(self.model_name)
            self.nlp.max_length = self.max_length
        except OSError:
            # Fallback do podstawowego modelu polskiego
            try:
                self.nlp = Polish()
                # Dodaj podstawowe komponenty
                if 'tagger' not in self.nlp.pipe_names:
                    self.nlp.add_pipe('tagger')
                if 'parser' not in self.nlp.pipe_names:
                    self.nlp.add_pipe('parser')
            except Exception as e:
                raise RuntimeError(f"Nie można załadować modelu spaCy: {e}")
    
    async def close(self):
        """Zamknięcie analizatora."""
        if self.nlp:
            # spaCy nie wymaga specjalnego zamykania
            pass
    
    async def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Zaawansowana analiza językowa z wykorzystaniem spaCy."""
        content = data.get('content', '')
        if not content or not self.nlp:
            return {}
        
        # Ogranicz długość tekstu jeśli jest za długi
        if len(content) > self.max_length:
            content = content[:self.max_length]
        
        try:
            # Przetwórz tekst przez spaCy
            doc = self.nlp(content)
            
            # Analiza tokenów
            tokens_info = []
            simple_tokens = []
            
            # Named Entity Recognition
            entities = []
            for ent in doc.ents:
                entities.append({
                    'text': ent.text,
                    'label': ent.label_,
                    'start': ent.start_char,
                    'end': ent.end_char,
                    'description': spacy.explain(ent.label_) if hasattr(spacy, 'explain') else ent.label_
                })
            
            for token in doc:
                if not token.is_space:  # Pomiń białe znaki
                    # Wykorzystaj morphologizer jeśli dostępny
                    morph_features = {}
                    if hasattr(token, 'morph') and token.morph:
                        try:
                            morph_features = dict(token.morph)
                        except Exception:
                            morph_features = {}
                    
                    token_info = TokenInfo(
                        token=token.text,
                        lemma=token.lemma_,
                        pos=token.pos_,
                        tag=token.tag_,
                        dep=token.dep_,
                        is_alpha=token.is_alpha,
                        is_stop=token.is_stop,
                        is_punct=token.is_punct
                    )
                    
                    tokens_info.append({
                        'token': token_info.token,
                        'lemma': token_info.lemma,
                        'pos': token_info.pos,
                        'tag': token_info.tag,
                        'dep': token_info.dep,
                        'is_alpha': token_info.is_alpha,
                        'is_stop': token_info.is_stop,
                        'is_punct': token_info.is_punct,
                        'sentiment_score': token_info.sentiment_score,
                        'morph_features': morph_features  # Dodane cechy morfologiczne
                    })
                    
                    simple_tokens.append(token.text.lower())
            
            # Statystyki tokenów
            unique_tokens = list(set(simple_tokens))
            avg_token_length = sum(len(token) for token in simple_tokens) / len(simple_tokens) if simple_tokens else 0
            
            # Statystyki zdań
            sentences = list(doc.sents)
            sentence_count = len(sentences)
            word_count = len([token for token in doc if token.is_alpha])
            char_count = len(content)
            avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
            
            # Podstawowa analiza sentymentu (jeśli dostępna)
            sentiment_polarity = 0.0
            sentiment_subjectivity = 0.0
            
            if self.include_sentiment:
                try:
                    # Rozszerzona analiza sentymentu na podstawie słów religijnych
                    positive_words = {
                        'dobry', 'świetny', 'wspaniały', 'piękny', 'radość', 'szczęście',
                        'błogosławiony', 'miłość', 'pokój', 'nadzieja', 'wiara', 'łaska',
                        'zbawienie', 'święty', 'boży', 'duchowy', 'modlitwa', 'dziękuję'
                    }
                    negative_words = {
                        'zły', 'okropny', 'straszny', 'smutek', 'ból', 'cierpienie',
                        'grzech', 'diabeł', 'piekło', 'przekleństwo', 'nienawiść', 'złość',
                        'rozpacz', 'lęk', 'strach', 'wątpliwość', 'kłamstwo', 'zdrada'
                    }
                    
                    # Słowa religijne neutralne (zwiększają subiektywność)
                    religious_words = {
                        'bóg', 'jezus', 'chrystus', 'maryja', 'duch', 'kościół',
                        'papież', 'ksiądz', 'biskup', 'kardynał', 'msza', 'eucharystia'
                    }
                    
                    words_lower = [token.lower() for token in simple_tokens]
                    positive_count = sum(1 for word in words_lower if word in positive_words)
                    negative_count = sum(1 for word in words_lower if word in negative_words)
                    religious_count = sum(1 for word in words_lower if word in religious_words)
                    
                    if positive_count + negative_count > 0:
                        sentiment_polarity = (positive_count - negative_count) / (positive_count + negative_count)
                        # Uwzględnij słowa religijne w subiektywności
                        sentiment_subjectivity = (positive_count + negative_count + religious_count * 0.5) / len(words_lower)
                        sentiment_subjectivity = min(1.0, sentiment_subjectivity)  # Max 1.0
                    elif religious_count > 0:
                        # Jeśli są tylko słowa religijne, neutralny sentyment ale wysoka subiektywność
                        sentiment_polarity = 0.0
                        sentiment_subjectivity = min(1.0, religious_count / len(words_lower))
                        
                except Exception:
                    pass  # Ignoruj błędy analizy sentymentu
            
            # Wykrywanie języka (bardzo podstawowe)
            language_detected = 'pl'  # Zakładamy polski
            
            # Oblicz wskaźnik czytelności (uproszczony)
            readability_score = self._calculate_readability(word_count, sentence_count, char_count)
            
            return {
                'tokens': simple_tokens,
                'token_stats': {
                    'total_tokens': len(simple_tokens),
                    'unique_tokens': len(unique_tokens),
                    'avg_token_length': avg_token_length
                },
                'linguistic': tokens_info,
                'linguistic_stats': {
                    'sentence_count': sentence_count,
                    'word_count': word_count,
                    'char_count': char_count,
                    'avg_sentence_length': avg_sentence_length,
                    'readability_score': readability_score,
                    'sentiment_polarity': sentiment_polarity,
                    'sentiment_subjectivity': sentiment_subjectivity,
                    'language_detected': language_detected
                },
                'named_entities': entities
            }
            
        except Exception as e:
            # W przypadku błędu zwróć podstawowe informacje
            return {
                'error': f"Błąd analizy spaCy: {str(e)}",
                'tokens': content.split(),  # Fallback tokenizacja
                'token_stats': {
                    'total_tokens': len(content.split()),
                    'unique_tokens': len(set(content.split())),
                    'avg_token_length': 0
                }
            }
    
    def _calculate_readability(self, word_count: int, sentence_count: int, char_count: int) -> float:
        """Oblicza uproszczony wskaźnik czytelności."""
        if sentence_count == 0 or word_count == 0:
            return 0.0
        
        avg_sentence_length = word_count / sentence_count
        avg_word_length = char_count / word_count
        
        # Uproszczony wzór podobny do Flesch Reading Ease
        # Im wyższy wynik, tym łatwiejszy tekst
        readability = 206.835 - (1.015 * avg_sentence_length) - (84.6 * avg_word_length)
        return max(0.0, min(100.0, readability))



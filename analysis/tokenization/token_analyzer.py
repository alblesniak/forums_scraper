#!/usr/bin/env python3
"""
Moduł analizy tokenów dla postów forum
Działa na kopii bazy danych, aby nie zakłócać pracy spiderów
"""

import sqlite3
import os
import shutil
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import threading
import queue
from dataclasses import dataclass
import hashlib
import importlib.util
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

DEFAULT_LOG_FILE = Path('data/logs/token_analysis.log')

@dataclass
class TokenAnalysisResult:
    """Wynik analizy tokenów dla posta"""
    post_id: int
    token_count: int
    word_count: int
    character_count: int
    analysis_hash: str
    analyzed_at: datetime
    processing_time_ms: float

class TokenAnalyzer:
    """
    Analizator tokenów działający na kopii bazy danych
    Bezpieczny dla równoległego działania ze spiderami
    """
    
    def __init__(self, source_db: str = "data/databases/merged_forums.db", 
                 analysis_db: str = "data/databases/analysis_forums.db",
                 config: Dict = None, forums_to_analyze: List[str] = None):
        self.source_db = source_db
        self.analysis_db = analysis_db
        # Konfiguracja logowania tylko przy tworzeniu analizatora
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

            # Strumień na konsolę
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

            # Plik logów (utwórz katalog dopiero teraz)
            try:
                log_file = DEFAULT_LOG_FILE
                log_file.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(str(log_file))
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except Exception:
                # Jeśli nie można zapisać do pliku, kontynuuj tylko z konsolą
                pass
            self.logger.propagate = False
        self.lock = threading.Lock()
        
        # Konfiguracja
        if config is None:
            try:
                from config import get_config
                full_config = get_config()
                self.config = full_config['tokenization']
                self.multiprocessing_config = full_config['multiprocessing']
                if forums_to_analyze is None:
                    # forums_to_analyze=None oznacza auto-detekcję z bazy
                    self.forums_to_analyze = None
                else:
                    self.forums_to_analyze = forums_to_analyze
            except ImportError:
                self.config = {
                    'tokenizer': 'simple',
                    'polish_language_factor': 0.75,
                    'min_word_length': 2,
                    'include_punctuation': False,
                    'include_whitespace': False
                }
                self.multiprocessing_config = {
                    'max_workers': 4,
                    'chunk_size': 50,
                    'use_multiprocessing': True,
                    'process_timeout': 300
                }
                self.forums_to_analyze = ['radio_katolik', 'dolina_modlitwy']
        else:
            self.config = config
            self.multiprocessing_config = config.get('multiprocessing', {
                'max_workers': 4,
                'chunk_size': 50,
                'use_multiprocessing': True,
                'process_timeout': 300
            })
            if forums_to_analyze is None:
                # forums_to_analyze=None oznacza auto-detekcję z bazy
                self.forums_to_analyze = None
            else:
                self.forums_to_analyze = forums_to_analyze
        
        # Kolejka zadań do przetwarzania
        self.task_queue = queue.Queue()
        self.is_running = False
        
        # Statystyki
        self.stats = {
            'total_posts_analyzed': 0,
            'total_tokens_processed': 0,
            'last_analysis_time': None,
            'processing_errors': 0,
            'spacy_tokens': 0,
            'simple_tokens': 0,
            'forums_analyzed': (self.forums_to_analyze or []).copy()
        }
    
    def create_analysis_database(self) -> bool:
        """
        Przygotowuje bazę analizy (bez kopiowania bazy źródłowej).
        Tworzy tylko tabele wynikowe w bazie analizy.
        """
        try:
            self.logger.info(f"Tworzenie bazy analizy: {self.analysis_db}")
            
            # Upewnij się, że katalog docelowy istnieje
            analysis_dir = Path(self.analysis_db).parent
            analysis_dir.mkdir(parents=True, exist_ok=True)

            if not os.path.exists(self.source_db):
                raise FileNotFoundError(f"Brak bazy źródłowej do analizy: {self.source_db}")

            # Nie kopiujemy bazy źródłowej; baza analizy zawiera jedynie tabele wynikowe.
            
            # Dodaj tabele analizy
            conn, cursor, src = self._open_connection_with_source()
            
            # Tabela wyników analizy tokenów
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS token_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    token_count INTEGER NOT NULL,
                    word_count INTEGER NOT NULL,
                    character_count INTEGER NOT NULL,
                    analysis_hash TEXT NOT NULL,
                    analyzed_at TIMESTAMP NOT NULL,
                    processing_time_ms REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(post_id)
                )
            """)
            
            # Tabela statystyk analizy
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_date DATE NOT NULL,
                    posts_analyzed INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    total_words INTEGER NOT NULL,
                    total_characters INTEGER NOT NULL,
                    processing_time_seconds REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indeksy dla wydajności
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_token_analysis_post_id ON token_analysis(post_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_token_analysis_date ON token_analysis(analyzed_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_analysis_stats_date ON analysis_stats(analysis_date)")
            
            conn.commit()
            conn.close()
            
            self.logger.info("Baza analizy utworzona pomyślnie")
            return True
            
        except Exception as e:
            self.logger.error(f"Błąd tworzenia bazy analizy: {e}")
            return False
    
    def _open_connection_with_source(self) -> Tuple[sqlite3.Connection, sqlite3.Cursor, str]:
        """
        Otwiera połączenie do bazy analizy. Jeśli pliki bazy źródłowej i analizy
        są różne, dołącza bazę źródłową jako alias 'src' i zwraca prefiks 'src.'.
        Jeśli są takie same (tryb in-place), zwraca pusty prefiks ''.
        """
        conn = sqlite3.connect(self.analysis_db)
        cursor = conn.cursor()
        analysis_abs = os.path.abspath(self.analysis_db)
        source_abs = os.path.abspath(self.source_db)
        if analysis_abs != source_abs:
            cursor.execute("ATTACH DATABASE ? AS src", (self.source_db,))
            return conn, cursor, "src."
        return conn, cursor, ""
    
    def calculate_tokens(self, text: str) -> Dict[str, int]:
        """
        Oblicza liczbę tokenów, słów i znaków w tekście
        Używa spaCy dla dokładnej tokenizacji lub prostego algorytmu jako fallback
        """
        if not text:
            return {'tokens': 0, 'words': 0, 'characters': 0}
        
        # Liczba znaków
        character_count = len(text)
        
        # Liczba słów (prosty algorytm)
        words = text.split()
        word_count = len(words)
        
        # Liczba tokenów - spróbuj spaCy, jeśli nie działa użyj prostego algorytmu
        token_count = self._calculate_tokens_spacy(text)
        
        if token_count is not None:
            # Użyto spaCy
            with self.lock:
                self.stats['spacy_tokens'] += 1
        else:
            # Fallback do prostego algorytmu
            token_count = self._calculate_tokens_simple(text)
            with self.lock:
                self.stats['simple_tokens'] += 1
        
        return {
            'tokens': token_count,
            'words': word_count,
            'characters': character_count
        }
    
    def _calculate_tokens_spacy(self, text: str) -> Optional[int]:
        """
        Oblicza liczbę tokenów używając spaCy
        Zwraca None jeśli spaCy nie jest dostępne
        """
        try:
            # Sprawdź czy spaCy jest zainstalowane
            if not self._is_spacy_available():
                return None
            
            # Sprawdź czy model jest dostępny
            if not self._is_spacy_model_available():
                return None
            
            # Import spaCy
            import spacy
            
            # Załaduj model
            nlp = spacy.load(self.config.get('spacy_model', 'pl_core_news_sm'))
            
            # Przetwórz tekst
            doc = nlp(text)
            
            # Policz tokeny zgodnie z konfiguracją
            token_count = 0
            for token in doc:
                # Sprawdź czy token spełnia kryteria
                if self._should_count_token(token):
                    token_count += 1
            
            self.logger.debug(f"spaCy tokenizacja: {token_count} tokenów")
            return token_count
            
        except Exception as e:
            self.logger.warning(f"Błąd tokenizacji spaCy: {e}")
            return None
    
    def _calculate_tokens_simple(self, text: str) -> int:
        """
        Oblicza liczbę tokenów używając prostego algorytmu
        Jako fallback gdy spaCy nie działa
        """
        try:
            # Pobierz konfigurację
            factor = self.config.get('polish_language_factor', 0.75)
            min_length = self.config.get('min_word_length', 2)
            
            # Podziel na słowa i filtruj
            words = text.split()
            filtered_words = [word for word in words if len(word) >= min_length]
            
            # Oblicz tokeny
            token_count = int(len(filtered_words) * factor)
            
            self.logger.debug(f"Prosty algorytm tokenizacji: {token_count} tokenów")
            return token_count
            
        except Exception as e:
            self.logger.error(f"Błąd prostego algorytmu tokenizacji: {e}")
            return 0
    
    def _should_count_token(self, token) -> bool:
        """
        Sprawdza czy token powinien być liczony
        """
        config = self.config
        
        # Sprawdź długość
        if len(token.text) < config.get('min_word_length', 2):
            return False
        
        # Sprawdź czy to biały znak
        if not config.get('include_whitespace', False) and token.is_space:
            return False
        
        # Sprawdź czy to interpunkcja
        if not config.get('include_punctuation', False) and token.is_punct:
            return False
        
        return True
    
    def _is_spacy_available(self) -> bool:
        """Sprawdza czy spaCy jest zainstalowane"""
        return importlib.util.find_spec("spacy") is not None
    
    def _is_spacy_model_available(self) -> bool:
        """Sprawdza czy model spaCy jest dostępny"""
        try:
            import spacy
            model_name = self.config.get('spacy_model', 'pl_core_news_sm')
            spacy.load(model_name)
            return True
        except:
            return False
    
    def generate_analysis_hash(self, text: str) -> str:
        """Generuje hash treści posta dla śledzenia zmian"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def analyze_single_post(self, post_id: int, content: str) -> Optional[TokenAnalysisResult]:
        """
        Analizuje pojedynczy post i zwraca wynik
        """
        try:
            start_time = time.time()
            
            # Oblicz tokeny
            token_info = self.calculate_tokens(content)
            
            # Generuj hash analizy
            analysis_hash = self.generate_analysis_hash(content)
            
            # Oblicz czas przetwarzania
            processing_time = (time.time() - start_time) * 1000  # w milisekundach
            
            result = TokenAnalysisResult(
                post_id=post_id,
                token_count=token_info['tokens'],
                word_count=token_info['words'],
                character_count=token_info['characters'],
                analysis_hash=analysis_hash,
                analyzed_at=datetime.now(),
                processing_time_ms=processing_time
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Błąd analizy posta {post_id}: {e}")
            return None
    
    def get_posts_to_analyze(self, batch_size: int = 100) -> List[Tuple[int, str]]:
        """
        Pobiera posty do analizy z określonych forów, które jeszcze nie zostały przeanalizowane
        lub których treść się zmieniła
        """
        try:
            conn, cursor, src = self._open_connection_with_source()
            
            # Jeżeli fora nie zostały jawnie ustawione, wykryj je z bazy
            if not self.forums_to_analyze:
                cursor.execute(f"SELECT spider_name FROM {src}forums")
                detected_forums = [row[0] for row in cursor.fetchall()]
                self.forums_to_analyze = detected_forums

            # Pobierz posty z określonych forów, które nie mają analizy
            placeholders = ','.join(['?' for _ in self.forums_to_analyze])
            cursor.execute(
                f"""
                SELECT p.id, p.content 
                FROM {src}forum_posts p
                JOIN {src}forum_threads t ON p.thread_id = t.id
                JOIN {src}forum_sections s ON t.section_id = s.id
                JOIN {src}forums f ON s.forum_id = f.id
                LEFT JOIN token_analysis ta ON p.id = ta.post_id
                WHERE f.spider_name IN ({placeholders})
                  AND ta.post_id IS NULL
                ORDER BY p.id
                LIMIT ?
                """,
                self.forums_to_analyze + [batch_size]
            )
            
            posts = cursor.fetchall()
            conn.close()
            
            return posts
            
        except Exception as e:
            self.logger.error(f"Błąd pobierania postów do analizy: {e}")
            return []
    
    def save_analysis_result(self, result: TokenAnalysisResult) -> bool:
        """
        Zapisuje wynik analizy do bazy
        """
        try:
            conn, cursor, src = self._open_connection_with_source()
            
            cursor.execute("""
                INSERT OR REPLACE INTO token_analysis 
                (post_id, token_count, word_count, character_count, analysis_hash, analyzed_at, processing_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                result.post_id,
                result.token_count,
                result.word_count,
                result.character_count,
                result.analysis_hash,
                result.analyzed_at.isoformat(),
                result.processing_time_ms
            ))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Błąd zapisywania wyniku analizy: {e}")
            return False
    
    def update_analysis_stats(self, batch_results: List[TokenAnalysisResult]) -> None:
        """
        Aktualizuje statystyki analizy
        """
        try:
            if not batch_results:
                return
                
            conn, cursor, src = self._open_connection_with_source()
            
            # Oblicz statystyki dla partii
            total_tokens = sum(r.token_count for r in batch_results)
            total_words = sum(r.word_count for r in batch_results)
            total_characters = sum(r.character_count for r in batch_results)
            total_time = sum(r.processing_time_ms for r in batch_results) / 1000  # w sekundach
            
            # Zapisz statystyki dzienne
            today = datetime.now().date().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO analysis_stats 
                (analysis_date, posts_analyzed, total_tokens, total_words, total_characters, processing_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                today,
                len(batch_results),
                total_tokens,
                total_words,
                total_characters,
                total_time
            ))
            
            conn.commit()
            conn.close()
            
            # Aktualizuj statystyki w pamięci
            with self.lock:
                self.stats['total_posts_analyzed'] += len(batch_results)
                self.stats['total_tokens_processed'] += total_tokens
                self.stats['last_analysis_time'] = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Błąd aktualizacji statystyk: {e}")
    
    def process_batch(self, batch_size: int = 100) -> int:
        """
        Przetwarza partię postów do analizy
        """
        try:
            posts = self.get_posts_to_analyze(batch_size)
            if not posts:
                return 0
            
            self.logger.info(f"Przetwarzanie partii {len(posts)} postów")
            
            if self.multiprocessing_config.get('use_multiprocessing', True) and len(posts) > 10:
                return self._process_batch_multiprocessing(posts)
            else:
                return self._process_batch_sequential(posts)
            
        except Exception as e:
            self.logger.error(f"Błąd przetwarzania partii: {e}")
            self.stats['processing_errors'] += 1
            return 0
    
    def _process_batch_sequential(self, posts: List[Tuple[int, str]]) -> int:
        """
        Przetwarza partię postów sekwencyjnie
        """
        results = []
        processed_count = 0
        
        for post_id, content in posts:
            if content is None:
                continue
                
            result = self.analyze_single_post(post_id, content)
            if result:
                results.append(result)
                processed_count += 1
                
                # Zapisz wynik
                if self.save_analysis_result(result):
                    self.stats['total_posts_analyzed'] += 1
                else:
                    self.stats['processing_errors'] += 1
        
        # Aktualizuj statystyki
        if results:
            self.update_analysis_stats(results)
        
        self.logger.info(f"Przetworzono {processed_count} postów sekwencyjnie")
        return processed_count
    
    def _process_batch_multiprocessing(self, posts: List[Tuple[int, str]]) -> int:
        """
        Przetwarza partię postów używając multiprocessing
        """
        try:
            max_workers = self.multiprocessing_config.get('max_workers', 4)
            chunk_size = self.multiprocessing_config.get('chunk_size', 50)
            
            self.logger.info(f"Przetwarzanie {len(posts)} postów używając {max_workers} procesów")
            
            # Podziel posty na chunki
            chunks = [posts[i:i + chunk_size] for i in range(0, len(posts), chunk_size)]
            
            results = []
            processed_count = 0
            
            # Użyj tqdm do pokazywania postępu
            with tqdm(total=len(posts), desc="🔍 Analiza postów", unit="post") as pbar:
                with ProcessPoolExecutor(max_workers=max_workers) as executor:
                    # Prześlij chunki do przetwarzania
                    future_to_chunk = {
                        executor.submit(_process_chunk_worker_static, chunk): chunk 
                        for chunk in chunks
                    }
                    
                    # Zbierz wyniki
                    for future in as_completed(future_to_chunk):
                        chunk_results = future.result()
                        if chunk_results:
                            results.extend(chunk_results)
                            processed_count += len(chunk_results)
                        
                        # Aktualizuj pasek postępu
                        chunk = future_to_chunk[future]
                        pbar.update(len(chunk))
            
            # Zapisz wyniki do bazy
            for result_dict in results:
                # Konwertuj słownik na TokenAnalysisResult
                result = TokenAnalysisResult(
                    post_id=result_dict['post_id'],
                    token_count=result_dict['token_count'],
                    word_count=result_dict['word_count'],
                    character_count=result_dict['character_count'],
                    analysis_hash=result_dict['analysis_hash'],
                    analyzed_at=datetime.fromisoformat(result_dict['analyzed_at']),
                    processing_time_ms=result_dict['processing_time_ms']
                )
                
                if self.save_analysis_result(result):
                    self.stats['total_posts_analyzed'] += 1
                else:
                    self.stats['processing_errors'] += 1
            
            # Aktualizuj statystyki
            if results:
                # Konwertuj słowniki na TokenAnalysisResult dla statystyk
                token_results = []
                for result_dict in results:
                    token_result = TokenAnalysisResult(
                        post_id=result_dict['post_id'],
                        token_count=result_dict['token_count'],
                        word_count=result_dict['word_count'],
                        character_count=result_dict['character_count'],
                        analysis_hash=result_dict['analysis_hash'],
                        analyzed_at=datetime.fromisoformat(result_dict['analyzed_at']),
                        processing_time_ms=result_dict['processing_time_ms']
                    )
                    token_results.append(token_result)
                
                self.update_analysis_stats(token_results)
            
            self.logger.info(f"Przetworzono {processed_count} postów używając multiprocessing")
            return processed_count
            
        except Exception as e:
            self.logger.error(f"Błąd multiprocessing: {e}")
            # Fallback do sekwencyjnego przetwarzania
            return self._process_batch_sequential(posts)
    
    def _process_chunk_worker(self, chunk: List[Tuple[int, str]]) -> List[Dict]:
        """
        Funkcja robocza do przetwarzania chunka postów w osobnym procesie
        Zwraca słowniki zamiast obiektów TokenAnalysisResult
        """
        results = []
        
        for post_id, content in chunk:
            if content is None:
                continue
                
            try:
                # Pomiar czasu rozpoczęcia
                start_time = time.time()
                
                # Oblicz tokeny lokalnie w procesie roboczym
                token_result = self._calculate_tokens_worker(content)
                
                # Utwórz hash analizy
                analysis_hash = self.generate_analysis_hash(content)
                
                # Pomiar czasu zakończenia
                processing_time = (time.time() - start_time) * 1000  # w milisekundach
                
                # Utwórz wynik jako słownik
                result = {
                    'post_id': post_id,
                    'token_count': token_result['tokens'],
                    'word_count': token_result['words'],
                    'character_count': token_result['characters'],
                    'analysis_hash': analysis_hash,
                    'analyzed_at': datetime.now().isoformat(),
                    'processing_time_ms': processing_time
                }
                
                results.append(result)
            except Exception as e:
                # Logowanie błędów w procesie roboczym
                print(f"Błąd analizy posta {post_id}: {e}")
                continue
        
        return results
    
    def _calculate_tokens_worker(self, text: str) -> Dict[str, int]:
        """
        Uproszczona funkcja obliczania tokenów dla procesów roboczych
        """
        if not text:
            return {'tokens': 0, 'words': 0, 'characters': 0}
        
        # Liczba znaków
        character_count = len(text)
        
        # Liczba słów
        words = text.split()
        word_count = len([word for word in words if len(word) >= 2])
        
        # Liczba tokenów (uproszczone)
        token_count = int(word_count * 0.75)  # Przybliżenie dla języka polskiego
        
        return {
            'tokens': token_count,
            'words': word_count,
            'characters': character_count
        }
    
    def start_continuous_analysis(self, interval_seconds: int = 300, batch_size: int = 100):
        """
        Uruchamia ciągłą analizę w tle
        """
        self.is_running = True
        self.logger.info(f"Uruchomiono ciągłą analizę (interwał: {interval_seconds}s)")
        
        while self.is_running:
            try:
                # Przetwórz partię
                processed = self.process_batch(batch_size)
                
                if processed > 0:
                    self.logger.info(f"Przetworzono {processed} postów w tej iteracji")
                else:
                    self.logger.debug("Brak nowych postów do analizy")
                
                # Czekaj do następnej iteracji
                time.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                self.logger.info("Zatrzymano analizę (Ctrl+C)")
                break
            except Exception as e:
                self.logger.error(f"Błąd w ciągłej analizie: {e}")
                time.sleep(60)  # Czekaj minutę przed ponowną próbą
    
    def stop_continuous_analysis(self):
        """Zatrzymuje ciągłą analizę"""
        self.is_running = False
        self.logger.info("Zatrzymano ciągłą analizę")
    
    def get_analysis_summary(self) -> Dict:
        """
        Zwraca podsumowanie analizy
        """
        try:
            conn, cursor, src = self._open_connection_with_source()
            
            # Pobierz ogólne statystyki
            cursor.execute("SELECT COUNT(*) FROM token_analysis")
            total_analyzed = cursor.fetchone()[0]
            
            cursor.execute(f"SELECT COUNT(*) FROM {src}forum_posts")
            total_posts = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(token_count) FROM token_analysis")
            total_tokens = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT SUM(word_count) FROM token_analysis")
            total_words = cursor.fetchone()[0] or 0
            
            # Pobierz ostatnie statystyki dzienne
            cursor.execute("""
                SELECT analysis_date, posts_analyzed, total_tokens, total_words, processing_time_seconds
                FROM analysis_stats 
                ORDER BY analysis_date DESC 
                LIMIT 7
            """)
            daily_stats = cursor.fetchall()
            
            conn.close()
            
            return {
                'total_posts': total_posts,
                'total_analyzed': total_analyzed,
                'analysis_progress': (total_analyzed / total_posts * 100) if total_posts > 0 else 0,
                'total_tokens': total_tokens,
                'total_words': total_words,
                'daily_stats': [
                    {
                        'date': row[0],
                        'posts_analyzed': row[1],
                        'total_tokens': row[2],
                        'total_words': row[3],
                        'processing_time': row[4]
                    }
                    for row in daily_stats
                ],
                'memory_stats': self.stats
            }
            
        except Exception as e:
            self.logger.error(f"Błąd pobierania podsumowania: {e}")
            return {}
    
    def refresh_analysis_database(self) -> bool:
        """
        Odświeża bazę analizy, kopiując najnowsze dane
        """
        try:
            self.logger.info("Odświeżanie bazy analizy...")
            
            # Zatrzymaj analizę jeśli działa
            was_running = self.is_running
            if was_running:
                self.stop_continuous_analysis()
            
            # Utwórz nową kopię
            success = self.create_analysis_database()
            
            # Uruchom ponownie analizę jeśli była aktywna
            if was_running and success:
                self.start_continuous_analysis()
            
            return success
            
        except Exception as e:
            self.logger.error(f"Błąd odświeżania bazy analizy: {e}")
            return False
    
    def analyze_all_forums_posts(self, show_progress: bool = True) -> Dict:
        """
        Analizuje wszystkie posty z określonych forów
        """
        try:
            # Zapewnij, że fora są wykryte zanim wypiszemy log
            if not self.forums_to_analyze:
                conn_probe, cur_probe, src = self._open_connection_with_source()
                cur_probe.execute(f"SELECT spider_name FROM {src}forums")
                self.forums_to_analyze = [row[0] for row in cur_probe.fetchall()]
                conn_probe.close()

            self.logger.info(f"Rozpoczynam analizę wszystkich postów z forów: {', '.join(self.forums_to_analyze)}")
            
            # Pobierz całkowitą liczbę postów do analizy
            total_posts = self._get_total_posts_to_analyze()
            
            if total_posts == 0:
                self.logger.info("Brak postów do analizy")
                return {
                    'total_analyzed': 0,
                    'total_posts': 0,
                    'forums_analyzed': self.forums_to_analyze
                }
            
            self.logger.info(f"Znaleziono {total_posts} postów do analizy")
            
            # Analizuj wszystkie posty partiami
            batch_size = self.multiprocessing_config.get('chunk_size', 50) * 2
            total_analyzed = 0
            
            if show_progress:
                # Użyj tqdm do pokazywania ogólnego postępu
                with tqdm(total=total_posts, desc="🚀 Analiza wszystkich forów", unit="post") as pbar:
                    while total_analyzed < total_posts:
                        # Pobierz partię postów
                        posts = self.get_posts_to_analyze(batch_size)
                        if not posts:
                            break
                        
                        # Przetwórz partię
                        processed = self.process_batch(batch_size)
                        total_analyzed += processed
                        
                        # Aktualizuj pasek postępu
                        pbar.update(processed)
                        
                        # Sprawdź czy wszystkie posty zostały przeanalizowane
                        remaining = self._get_total_posts_to_analyze()
                        if remaining == 0:
                            break
            else:
                # Bez paska postępu
                while True:
                    posts = self.get_posts_to_analyze(batch_size)
                    if not posts:
                        break
                    
                    processed = self.process_batch(batch_size)
                    total_analyzed += processed
                    
                    remaining = self._get_total_posts_to_analyze()
                    if remaining == 0:
                        break
            
            self.logger.info(f"Zakończono analizę. Przeanalizowano {total_analyzed} postów")
            
            return {
                'total_analyzed': total_analyzed,
                'total_posts': total_posts,
                'forums_analyzed': self.forums_to_analyze
            }
            
        except Exception as e:
            self.logger.error(f"Błąd analizy wszystkich postów: {e}")
            return {
                'total_analyzed': 0,
                'total_posts': 0,
                'forums_analyzed': self.forums_to_analyze,
                'error': str(e)
            }
    
    def _get_total_posts_to_analyze(self) -> int:
        """
        Pobiera całkowitą liczbę postów do analizy z określonych forów
        """
        try:
            conn, cursor, src = self._open_connection_with_source()
            
            # Jeżeli fora nie zostały jawnie ustawione, wykryj je z bazy
            if not self.forums_to_analyze:
                cursor.execute(f"SELECT spider_name FROM {src}forums")
                detected_forums = [row[0] for row in cursor.fetchall()]
                self.forums_to_analyze = detected_forums

            placeholders = ','.join(['?' for _ in self.forums_to_analyze])
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {src}forum_posts p
                JOIN {src}forum_threads t ON p.thread_id = t.id
                JOIN {src}forum_sections s ON t.section_id = s.id
                JOIN {src}forums f ON s.forum_id = f.id
                LEFT JOIN token_analysis ta ON p.id = ta.post_id
                WHERE f.spider_name IN ({placeholders})
                  AND ta.post_id IS NULL
                """,
                self.forums_to_analyze
            )
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count
            
        except Exception as e:
            self.logger.error(f"Błąd pobierania liczby postów do analizy: {e}")
            return 0
    
    def get_forums_info(self) -> Dict:
        """
        Zwraca informacje o forach do analizy
        """
        try:
            conn, cursor, src = self._open_connection_with_source()
            
            forums_info = []
            # Jeżeli fora nie zostały jawnie ustawione, wykryj je z bazy
            if not self.forums_to_analyze:
                cursor.execute(f"SELECT spider_name FROM {src}forums")
                detected_forums = [row[0] for row in cursor.fetchall()]
                self.forums_to_analyze = detected_forums

            for forum_name in self.forums_to_analyze:
                # Pobierz liczbę postów w forum
                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {src}forum_posts p
                    JOIN {src}forum_threads t ON p.thread_id = t.id
                    JOIN {src}forum_sections s ON t.section_id = s.id
                    JOIN {src}forums f ON s.forum_id = f.id
                    WHERE f.spider_name = ?
                    """,
                    (forum_name,)
                )
                
                total_posts = cursor.fetchone()[0]
                
                # Pobierz liczbę przeanalizowanych postów
                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {src}forum_posts p
                    JOIN {src}forum_threads t ON p.thread_id = t.id
                    JOIN {src}forum_sections s ON t.section_id = s.id
                    JOIN {src}forums f ON s.forum_id = f.id
                    JOIN token_analysis ta ON p.id = ta.post_id
                    WHERE f.spider_name = ?
                    """,
                    (forum_name,)
                )
                
                analyzed_posts = cursor.fetchone()[0]
                
                forums_info.append({
                    'name': forum_name,
                    'total_posts': total_posts,
                    'analyzed_posts': analyzed_posts,
                    'progress': (analyzed_posts / total_posts * 100) if total_posts > 0 else 0
                })
            
            conn.close()
            
            return {
                'forums': forums_info,
                'total_forums': len(self.forums_to_analyze)
            }
            
        except Exception as e:
            self.logger.error(f"Błąd pobierania informacji o forach: {e}")
            return {'forums': [], 'total_forums': 0}


def _process_chunk_worker_static(chunk: List[Tuple[int, str]]) -> List[Dict]:
    """
    Statyczna funkcja robocza do przetwarzania chunka postów w osobnym procesie
    Zwraca słowniki zamiast obiektów TokenAnalysisResult
    """
    results = []
    
    for post_id, content in chunk:
        if content is None:
            continue
            
        try:
            # Pomiar czasu rozpoczęcia
            start_time = time.time()
            
            # Oblicz tokeny lokalnie w procesie roboczym
            token_result = _calculate_tokens_worker_static(content)
            
            # Utwórz hash analizy
            analysis_hash = _generate_analysis_hash_static(content)
            
            # Pomiar czasu zakończenia
            processing_time = (time.time() - start_time) * 1000  # w milisekundach
            
            # Utwórz wynik jako słownik
            result = {
                'post_id': post_id,
                'token_count': token_result['tokens'],
                'word_count': token_result['words'],
                'character_count': token_result['characters'],
                'analysis_hash': analysis_hash,
                'analyzed_at': datetime.now().isoformat(),
                'processing_time_ms': processing_time
            }
            
            results.append(result)
        except Exception as e:
            # Logowanie błędów w procesie roboczym
            print(f"Błąd analizy posta {post_id}: {e}")
            continue
    
    return results


def _calculate_tokens_worker_static(text: str) -> Dict[str, int]:
    """
    Statyczna funkcja obliczania tokenów dla procesów roboczych
    """
    if not text:
        return {'tokens': 0, 'words': 0, 'characters': 0}
    
    # Liczba znaków
    character_count = len(text)
    
    # Liczba słów
    words = text.split()
    word_count = len([word for word in words if len(word) >= 2])
    
    # Liczba tokenów (uproszczone)
    token_count = int(word_count * 0.75)  # Przybliżenie dla języka polskiego
    
    return {
        'tokens': token_count,
        'words': word_count,
        'characters': character_count
    }


def _generate_analysis_hash_static(text: str) -> str:
    """
    Statyczna funkcja generowania hasha analizy
    """
    import hashlib
    return hashlib.md5(text.encode('utf-8')).hexdigest()

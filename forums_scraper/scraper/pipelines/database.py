"""
SQLite pipeline dla zapisywania danych forum wraz z analizami.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

import scrapy
from scrapy.exceptions import DropItem


logger = logging.getLogger(__name__)


class SQLitePipeline:
    """Pipeline do zapisywania itemów w bazie danych SQLite z analizami."""
    
    def __init__(self, database_path: str = "data/databases/forums.db"):
        self.database_path = database_path
        self.connection: Optional[sqlite3.Connection] = None
        
    @classmethod
    def from_crawler(cls, crawler):
        # Pobierz ścieżkę z ustawień lub użyj domyślnej
        database_path = crawler.settings.get('SQLITE_DATABASE_PATH', 'data/databases/forums_unified.db')
        # Używamy jednej wspólnej bazy danych dla wszystkich forów
        return cls(database_path=database_path)
    
    def open_spider(self, spider):
        """Inicjalizacja połączenia z bazą danych."""
        # Utwórz katalog jeśli nie istnieje
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        
        # Utwórz tabele
        self._create_tables()
        
        logger.info(f"Otwarto bazę danych: {self.database_path}")
    
    def close_spider(self, spider):
        """Zamknięcie połączenia z bazą danych."""
        if self.connection:
            self.connection.close()
            logger.info(f"Zamknięto bazę danych: {self.database_path}")
    
    def _create_tables(self):
        """Tworzy tabele w bazie danych."""
        cursor = self.connection.cursor()
        
        # Tabela forów
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS forums (
                id TEXT PRIMARY KEY,
                spider_name TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela sekcji
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sections (
                id TEXT PRIMARY KEY,
                forum_id TEXT,
                title TEXT,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (forum_id) REFERENCES forums (id)
            )
        ''')
        
        # Tabela wątków
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                section_id TEXT,
                title TEXT,
                url TEXT,
                author TEXT,
                replies INTEGER,
                views INTEGER,
                last_post_date TEXT,
                last_post_author TEXT,
                section_url TEXT,
                section_title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (section_id) REFERENCES sections (id)
            )
        ''')
        
        # Tabela użytkowników
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                join_date TEXT,
                posts_count INTEGER,
                religion TEXT,
                gender TEXT,
                localization TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela postów
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                user_id TEXT,
                post_number INTEGER,
                content TEXT,
                content_urls TEXT,  -- JSON
                post_date TEXT,
                url TEXT,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES threads (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tabele analiz
        
        # Analiza tokenizacji
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                token TEXT,
                position INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        
        # Statystyki tokenów
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_token_stats (
                post_id TEXT PRIMARY KEY,
                total_tokens INTEGER,
                unique_tokens INTEGER,
                avg_token_length REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        
        # Analiza morfosyntaktyczna (spaCy)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_linguistic_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                token TEXT,
                lemma TEXT,
                pos TEXT,  -- część mowy
                tag TEXT,  -- szczegółowy tag
                dep TEXT,  -- relacja składniowa
                morph_features TEXT,  -- cechy morfologiczne (JSON)
                is_alpha BOOLEAN,
                is_stop BOOLEAN,
                is_punct BOOLEAN,
                sentiment_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        
        # Statystyki językowe
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_linguistic_stats (
                post_id TEXT PRIMARY KEY,
                sentence_count INTEGER,
                word_count INTEGER,
                char_count INTEGER,
                avg_sentence_length REAL,
                readability_score REAL,
                sentiment_polarity REAL,
                sentiment_subjectivity REAL,
                language_detected TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        
        # Tabela domen
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE NOT NULL,
                category TEXT,  -- 'religious', 'media', 'social', 'educational', 'unknown'
                is_religious BOOLEAN DEFAULT 0,
                is_media BOOLEAN DEFAULT 0,
                is_social BOOLEAN DEFAULT 0,
                is_educational BOOLEAN DEFAULT 0,
                trust_score REAL DEFAULT 0.5,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_references INTEGER DEFAULT 0
            )
        ''')
        
        # Tabela URL-ów z postów
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                url TEXT,
                domain_id INTEGER,
                url_type TEXT,  -- 'article', 'video', 'image', 'social', 'unknown'
                is_external BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id),
                FOREIGN KEY (domain_id) REFERENCES domains (id)
            )
        ''')
        
        # Statystyki URL-ów per post
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_url_stats (
                post_id TEXT PRIMARY KEY,
                total_urls INTEGER DEFAULT 0,
                unique_domains INTEGER DEFAULT 0,
                religious_urls INTEGER DEFAULT 0,
                media_urls INTEGER DEFAULT 0,
                social_urls INTEGER DEFAULT 0,
                educational_urls INTEGER DEFAULT 0,
                unknown_urls INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        
        # Named Entities (rozpoznane nazwy własne)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_named_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                entity_text TEXT,        -- Tekst encji (np. "Jan Paweł II")
                entity_label TEXT,       -- Typ encji (PERSON, ORG, GPE, etc.)
                entity_description TEXT, -- Opis typu encji
                start_char INTEGER,      -- Pozycja początkowa w tekście
                end_char INTEGER,        -- Pozycja końcowa w tekście
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        
        # Statystyki Named Entities per post
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_ner_stats (
                post_id TEXT PRIMARY KEY,
                total_entities INTEGER DEFAULT 0,
                person_entities INTEGER DEFAULT 0,    -- Osoby
                org_entities INTEGER DEFAULT 0,       -- Organizacje
                gpe_entities INTEGER DEFAULT 0,       -- Miejsca geograficzne
                event_entities INTEGER DEFAULT 0,     -- Wydarzenia
                other_entities INTEGER DEFAULT 0,     -- Inne
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        
        # Indeksy dla lepszej wydajności
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_thread_id ON posts(thread_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tokens_post_id ON post_tokens(post_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_linguistic_post_id ON post_linguistic_analysis(post_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at)')
        
        # Indeksy dla URL-ów i domen
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_urls_post_id ON post_urls(post_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_urls_domain_id ON post_urls(domain_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_domains_category ON domains(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_domains_domain ON domains(domain)')
        
        # Indeksy dla Named Entities
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_named_entities_post_id ON post_named_entities(post_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_named_entities_label ON post_named_entities(entity_label)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_named_entities_text ON post_named_entities(entity_text)')
        
        self.connection.commit()
        logger.info("Tabele utworzone pomyślnie")
    
    def process_item(self, item, spider):
        """Przetwarza item i zapisuje do bazy danych."""
        try:
            if isinstance(item, scrapy.Item):
                item_type = type(item).__name__
                
                if item_type == 'ForumItem':
                    self._save_forum(item)
                elif item_type == 'ForumSectionItem':
                    self._save_section(item)
                elif item_type == 'ForumThreadItem':
                    self._save_thread(item)
                elif item_type == 'ForumUserItem':
                    self._save_user(item)
                elif item_type == 'ForumPostItem':
                    self._save_post(item)
                    # Zapisz analizy jeśli są dostępne
                    self._save_analysis(item)
                else:
                    logger.warning(f"Nieznany typ itemu: {item_type}")
            
            return item
            
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania itemu: {e}")
            raise DropItem(f"Błąd podczas zapisywania do bazy danych: {e}")
    
    def _save_forum(self, item):
        """Zapisuje forum do bazy danych."""
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO forums 
            (id, spider_name, title, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (
            item.get('id'),
            item.get('spider_name'),
            item.get('title'),
            datetime.now().isoformat()
        ))
        self.connection.commit()
    
    def _save_section(self, item):
        """Zapisuje sekcję do bazy danych."""
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sections 
            (id, forum_id, title, url, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            item.get('id'),
            item.get('forum_id'),
            item.get('title'),
            item.get('url'),
            datetime.now().isoformat()
        ))
        self.connection.commit()
    
    def _save_thread(self, item):
        """Zapisuje wątek do bazy danych."""
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO threads 
            (id, section_id, title, url, author, replies, views, 
             last_post_date, last_post_author, section_url, section_title, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item.get('id'),
            item.get('section_id'),
            item.get('title'),
            item.get('url'),
            item.get('author'),
            item.get('replies'),
            item.get('views'),
            item.get('last_post_date'),
            item.get('last_post_author'),
            item.get('section_url'),
            item.get('section_title'),
            datetime.now().isoformat()
        ))
        self.connection.commit()
    
    def _save_user(self, item):
        """Zapisuje użytkownika do bazy danych."""
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (id, username, join_date, posts_count, religion, gender, localization, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item.get('id'),
            item.get('username'),
            item.get('join_date'),
            item.get('posts_count'),
            item.get('religion'),
            item.get('gender'),
            item.get('localization'),
            datetime.now().isoformat()
        ))
        self.connection.commit()
    
    def _save_post(self, item):
        """Zapisuje post do bazy danych."""
        cursor = self.connection.cursor()
        
        # Serializuj content_urls do JSON
        content_urls_json = json.dumps(item.get('content_urls', []))
        
        cursor.execute('''
            INSERT OR REPLACE INTO posts 
            (id, thread_id, user_id, post_number, content, content_urls, 
             post_date, url, username, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item.get('id'),
            item.get('thread_id'),
            item.get('user_id'),
            item.get('post_number'),
            item.get('content'),
            content_urls_json,
            item.get('post_date'),
            item.get('url'),
            item.get('username'),
            datetime.now().isoformat()
        ))
        self.connection.commit()
    
    def _save_analysis(self, item):
        """Zapisuje wyniki analiz do bazy danych."""
        analysis_data = item.get('analysis', {})
        if not analysis_data:
            return
        
        post_id = item.get('id')
        if not post_id:
            return
        
        cursor = self.connection.cursor()
        
        # Zapisz tokenizację
        if 'tokens' in analysis_data:
            self._save_tokens(cursor, post_id, analysis_data['tokens'])
        
        # Zapisz statystyki tokenów
        if 'token_stats' in analysis_data:
            self._save_token_stats(cursor, post_id, analysis_data['token_stats'])
        
        # Zapisz analizę językową
        if 'linguistic' in analysis_data:
            self._save_linguistic_analysis(cursor, post_id, analysis_data['linguistic'])
        
        # Zapisz statystyki językowe
        if 'linguistic_stats' in analysis_data:
            self._save_linguistic_stats(cursor, post_id, analysis_data['linguistic_stats'])
        
        # Zapisz analizę URL-ów
        if 'url_analysis' in analysis_data:
            self._save_url_analysis(cursor, post_id, analysis_data['url_analysis'])
        
        # Zapisz statystyki domen
        if 'domain_stats' in analysis_data:
            self._save_domain_stats(cursor, post_id, analysis_data['domain_stats'])
        
        # Zapisz Named Entities
        if 'named_entities' in analysis_data:
            self._save_named_entities(cursor, post_id, analysis_data['named_entities'])
        
        self.connection.commit()
    
    def _save_tokens(self, cursor, post_id: str, tokens_data):
        """Zapisuje tokeny do bazy danych."""
        # Usuń stare tokeny dla tego posta
        cursor.execute('DELETE FROM post_tokens WHERE post_id = ?', (post_id,))
        
        # Zapisz nowe tokeny
        if isinstance(tokens_data, list):
            for i, token in enumerate(tokens_data):
                cursor.execute('''
                    INSERT INTO post_tokens (post_id, token, position)
                    VALUES (?, ?, ?)
                ''', (post_id, str(token), i))
    
    def _save_token_stats(self, cursor, post_id: str, stats_data):
        """Zapisuje statystyki tokenów do bazy danych."""
        cursor.execute('''
            INSERT OR REPLACE INTO post_token_stats 
            (post_id, total_tokens, unique_tokens, avg_token_length)
            VALUES (?, ?, ?, ?)
        ''', (
            post_id,
            stats_data.get('total_tokens'),
            stats_data.get('unique_tokens'),
            stats_data.get('avg_token_length')
        ))
    
    def _save_linguistic_analysis(self, cursor, post_id: str, linguistic_data):
        """Zapisuje analizę językową do bazy danych."""
        # Usuń starą analizę dla tego posta
        cursor.execute('DELETE FROM post_linguistic_analysis WHERE post_id = ?', (post_id,))
        
        # Zapisz nową analizę
        if isinstance(linguistic_data, list):
            for token_data in linguistic_data:
                # Serializuj cechy morfologiczne do JSON
                morph_json = json.dumps(token_data.get('morph_features', {}))
                
                cursor.execute('''
                    INSERT INTO post_linguistic_analysis 
                    (post_id, token, lemma, pos, tag, dep, morph_features, is_alpha, is_stop, is_punct, sentiment_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    post_id,
                    token_data.get('token'),
                    token_data.get('lemma'),
                    token_data.get('pos'),
                    token_data.get('tag'),
                    token_data.get('dep'),
                    morph_json,
                    token_data.get('is_alpha'),
                    token_data.get('is_stop'),
                    token_data.get('is_punct'),
                    token_data.get('sentiment_score')
                ))
    
    def _save_linguistic_stats(self, cursor, post_id: str, stats_data):
        """Zapisuje statystyki językowe do bazy danych."""
        cursor.execute('''
            INSERT OR REPLACE INTO post_linguistic_stats 
            (post_id, sentence_count, word_count, char_count, avg_sentence_length, 
             readability_score, sentiment_polarity, sentiment_subjectivity, language_detected)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            post_id,
            stats_data.get('sentence_count'),
            stats_data.get('word_count'),
            stats_data.get('char_count'),
            stats_data.get('avg_sentence_length'),
            stats_data.get('readability_score'),
            stats_data.get('sentiment_polarity'),
            stats_data.get('sentiment_subjectivity'),
            stats_data.get('language_detected')
        ))
    
    def _save_url_analysis(self, cursor, post_id: str, url_data):
        """Zapisuje analizę URL-ów do bazy danych."""
        if not isinstance(url_data, dict):
            return
        
        categorized_urls = url_data.get('categorized_urls', [])
        domain_categories = url_data.get('domain_categories', {})
        
        # Usuń stare URL-e dla tego posta
        cursor.execute('DELETE FROM post_urls WHERE post_id = ?', (post_id,))
        
        # Zapisz domeny i URL-e
        for url_info in categorized_urls:
            domain = url_info.get('domain')
            if not domain:
                continue
            
            # Znajdź lub utwórz domenę
            domain_id = self._get_or_create_domain(cursor, domain, domain_categories.get(domain, {}))
            
            # Zapisz URL
            cursor.execute('''
                INSERT INTO post_urls 
                (post_id, url, domain_id, url_type, is_external)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                post_id,
                url_info.get('url'),
                domain_id,
                url_info.get('url_type', 'unknown'),
                url_info.get('is_external', True)
            ))
        
        # Zapisz statystyki URL-ów
        domain_stats = url_data.get('domain_stats', {})
        if domain_stats:
            cursor.execute('''
                INSERT OR REPLACE INTO post_url_stats 
                (post_id, total_urls, unique_domains, religious_urls, media_urls, 
                 social_urls, educational_urls, unknown_urls)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                post_id,
                url_data.get('total_urls', 0),
                domain_stats.get('total_domains', 0),
                domain_stats.get('religious_domains', 0),
                domain_stats.get('media_domains', 0),
                domain_stats.get('social_domains', 0),
                domain_stats.get('educational_domains', 0),
                domain_stats.get('unknown_domains', 0)
            ))
    
    def _save_domain_stats(self, cursor, post_id: str, stats_data):
        """Zapisuje podstawowe statystyki domen."""
        if not isinstance(stats_data, dict):
            return
        
        cursor.execute('''
            INSERT OR REPLACE INTO post_url_stats 
            (post_id, total_urls, unique_domains)
            VALUES (?, ?, ?)
        ''', (
            post_id,
            stats_data.get('external_links_count', 0),
            stats_data.get('unique_domains_count', 0)
        ))
    
    def _get_or_create_domain(self, cursor, domain: str, domain_info: dict) -> int:
        """Znajdź lub utwórz domenę w bazie danych."""
        # Sprawdź czy domena już istnieje
        cursor.execute('SELECT id FROM domains WHERE domain = ?', (domain,))
        result = cursor.fetchone()
        
        if result:
            domain_id = result[0]
            # Zaktualizuj last_seen i total_references
            cursor.execute('''
                UPDATE domains 
                SET last_seen = CURRENT_TIMESTAMP, 
                    total_references = total_references + 1
                WHERE id = ?
            ''', (domain_id,))
            return domain_id
        else:
            # Utwórz nową domenę
            cursor.execute('''
                INSERT INTO domains 
                (domain, category, is_religious, is_media, is_social, is_educational, trust_score, total_references)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                domain,
                domain_info.get('category', 'unknown'),
                domain_info.get('is_religious', False),
                domain_info.get('is_media', False),
                domain_info.get('is_social', False),
                domain_info.get('is_educational', False),
                domain_info.get('trust_score', 0.5)
            ))
            return cursor.lastrowid
    
    def _save_named_entities(self, cursor, post_id: str, entities_data):
        """Zapisuje Named Entities do bazy danych."""
        if not isinstance(entities_data, list):
            return
        
        # Usuń stare encje dla tego posta
        cursor.execute('DELETE FROM post_named_entities WHERE post_id = ?', (post_id,))
        
        # Liczniki dla statystyk
        entity_counts = {
            'total': 0,
            'person': 0,
            'org': 0,
            'gpe': 0,  # Geopolitical entities (miejsca)
            'event': 0,
            'other': 0
        }
        
        # Zapisz każdą encję
        for entity in entities_data:
            if not isinstance(entity, dict):
                continue
                
            entity_text = entity.get('text', '').strip()
            entity_label = entity.get('label', 'OTHER')
            
            if not entity_text:
                continue
            
            cursor.execute('''
                INSERT INTO post_named_entities 
                (post_id, entity_text, entity_label, entity_description, start_char, end_char)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                post_id,
                entity_text,
                entity_label,
                entity.get('description', ''),
                entity.get('start', 0),
                entity.get('end', 0)
            ))
            
            # Aktualizuj liczniki
            entity_counts['total'] += 1
            
            if entity_label in ['PERSON', 'PER']:
                entity_counts['person'] += 1
            elif entity_label in ['ORG', 'ORGANIZATION']:
                entity_counts['org'] += 1
            elif entity_label in ['GPE', 'LOC', 'LOCATION']:
                entity_counts['gpe'] += 1
            elif entity_label in ['EVENT']:
                entity_counts['event'] += 1
            else:
                entity_counts['other'] += 1
        
        # Zapisz statystyki NER
        cursor.execute('''
            INSERT OR REPLACE INTO post_ner_stats 
            (post_id, total_entities, person_entities, org_entities, 
             gpe_entities, event_entities, other_entities)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            post_id,
            entity_counts['total'],
            entity_counts['person'],
            entity_counts['org'],
            entity_counts['gpe'],
            entity_counts['event'],
            entity_counts['other']
        ))

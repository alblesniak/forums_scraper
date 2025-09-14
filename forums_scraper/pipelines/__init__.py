# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

import sqlite3
import os
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
import json
from itemadapter import ItemAdapter
from ..items import ForumItem, ForumSectionItem, ForumThreadItem, ForumUserItem, ForumPostItem


def convert_polish_date_to_standard(polish_date_str):
    """
    Konwertuje polski format daty na standardowy format YYYY-MM-DD HH:MM:SS
    
    Obsługiwane formaty:
    - "27 lip 2025, 16:46"
    - "dzisiaj, 8:12"
    - "19 paź 2024, 17:30"
    - "21 maja 2022, 17:58"
    - "So lip 20, 2024 20:57" (stary format)
    """
    if not polish_date_str or not isinstance(polish_date_str, str):
        return None
    
    # Mapowanie polskich skrótów miesięcy na numery
    month_mapping = {
        'sty': 1, 'lut': 2, 'mar': 3, 'kwi': 4, 'kwie': 4, 'maj': 5, 'maja': 5, 'cze': 6,
        'lip': 7, 'lipa': 7, 'sie': 8, 'sierpnia': 8, 'wrz': 9, 'września': 9, 
        'paź': 10, 'października': 10, 'lis': 11, 'listopada': 11, 'gru': 12, 'grudnia': 12
    }
    
    try:
        date_clean = polish_date_str.strip()
        
        # Sprawdź czy to "dzisiaj" lub "wczoraj"
        if date_clean.startswith('dzisiaj'):
            # Dla "dzisiaj" używamy aktualnej daty
            today = datetime.now()
            time_match = re.search(r'(\d{1,2}):(\d{2})', date_clean)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                return today.replace(hour=hour, minute=minute).strftime('%Y-%m-%d %H:%M:%S')
            return today.strftime('%Y-%m-%d %H:%M:%S')
        elif date_clean.startswith('wczoraj'):
            # Dla "wczoraj" używamy wczorajszej daty
            from datetime import timedelta
            yesterday = datetime.now() - timedelta(days=1)
            time_match = re.search(r'(\d{1,2}):(\d{2})', date_clean)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                return yesterday.replace(hour=hour, minute=minute).strftime('%Y-%m-%d %H:%M:%S')
            return yesterday.strftime('%Y-%m-%d %H:%M:%S')
        
        # Format: "27 lip 2025, 16:46" lub "21 maja 2022, 17:58"
        pattern1 = r'(\d{1,2})\s+(\w+)\s+(\d{4}),\s+(\d{1,2}):(\d{2})'
        match = re.match(pattern1, date_clean)
        
        if match:
            day, month_name, year, hour, minute = match.groups()
            
            # Konwertuj nazwę miesiąca na numer
            month_name_lower = month_name.lower()
            if month_name_lower not in month_mapping:
                return None
            
            month = month_mapping[month_name_lower]
            day = int(day)
            year = int(year)
            hour = int(hour)
            minute = int(minute)
            
            # Utwórz obiekt datetime
            dt = datetime(year, month, day, hour, minute)
            
            # Zwróć w formacie YYYY-MM-DD HH:MM:SS
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Stary format: "So lip 20, 2024 20:57"
        pattern2 = r'^[^\s]+\s+([a-ząćęłńóśźż]+)\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})$'
        match = re.match(pattern2, date_clean)
        
        if match:
            month_name = match.group(1)
            day = int(match.group(2))
            year = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            
            # Konwertuj nazwę miesiąca na numer
            month = month_mapping.get(month_name.lower())
            if not month:
                return None
            
            # Utwórz obiekt datetime
            dt = datetime(year, month, day, hour, minute)
            
            # Zwróć w formacie YYYY-MM-DD HH:MM:SS
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Format numeryczny: "2022-07-11, 09:07" lub "2022-07-11 09:07" (phpBB nowe motywy)
        pattern3 = r'^(\d{4})-(\d{2})-(\d{2})(?:,|)\s+(\d{1,2}):(\d{2})'
        match = re.match(pattern3, date_clean)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            dt = datetime(year, month, day, hour, minute)
            return dt.strftime('%Y-%m-%d %H:%M:%S')

        # Jeśli żaden wzorzec nie pasuje, zwróć None
        return None
        
    except (ValueError, AttributeError, TypeError) as e:
        # W przypadku błędu zwróć None
        return None


class SQLitePipeline:
    def __init__(self, database_path=None):
        self.database_path = database_path
        self.connection = None
        self.cursor = None
        self.current_forum_id = None
        self.section_url_mapping = {}  # Mapowanie URL sekcji na ID
        self.username_mapping = {}  # Mapowanie username na user_id
        self.thread_url_mapping = {}  # Mapowanie URL wątku lub parametru 't' na thread_id
        self.batch_size = 500  # Zwiększony rozmiar batch dla szybszego zapisywania
        self.post_batch = []  # Batch dla postów
        self.user_batch = []  # Batch dla użytkowników

    @classmethod
    def from_crawler(cls, crawler):
        # Użyj domyślnej ścieżki z ustawień, ale będzie nadpisana przez nazwę spidera
        database_path = crawler.settings.get('SQLITE_DATABASE_PATH', 'forums.db')
        return cls(database_path)

    def open_spider(self, spider):
        """Otwiera połączenie z bazą danych i tworzy tabele"""
        # Utwórz nazwę bazy danych na podstawie nazwy spidera
        spider_name = spider.name
        # Zapisy w zunifikowanej lokalizacji artefaktów
        os.makedirs("data/databases", exist_ok=True)
        self.database_path = f"data/databases/forum_{spider_name}.db"
        
        spider.logger.info(f"Używam bazy danych: {self.database_path}")
        
        self.connection = sqlite3.connect(self.database_path)
        self.connection.execute('PRAGMA foreign_keys=ON')
        # Włącz WAL mode dla lepszej wydajności
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA synchronous=NORMAL')
        self.connection.execute('PRAGMA cache_size=10000')
        self.connection.execute('PRAGMA temp_store=MEMORY')
        self.cursor = self.connection.cursor()
        
        # Tworzenie tabeli forums
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spider_name TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        ''')
        
        # Tworzenie tabeli forum_sections
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forum_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                forum_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY (forum_id) REFERENCES forums (id)
            )
        ''')
        
        # Tworzenie tabeli forum_threads
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forum_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                author TEXT,
                replies INTEGER,
                views INTEGER,
                last_post_date TEXT,
                last_post_author TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY (section_id) REFERENCES forum_sections (id)
            )
        ''')
        
        # Tworzenie tabeli forum_users
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forum_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                join_date TEXT,
                posts_count INTEGER,
                religion TEXT,
                gender TEXT,
                localization TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        ''')
        
        # Dodaj nowe kolumny jeśli nie istnieją (dla istniejących tabel)
        try:
            self.cursor.execute('ALTER TABLE forum_users ADD COLUMN religion TEXT')
        except sqlite3.OperationalError:
            pass  # Kolumna już istnieje
        
        try:
            self.cursor.execute('ALTER TABLE forum_users ADD COLUMN gender TEXT')
        except sqlite3.OperationalError:
            pass  # Kolumna już istnieje
        
        try:
            self.cursor.execute('ALTER TABLE forum_users ADD COLUMN localization TEXT')
        except sqlite3.OperationalError:
            pass  # Kolumna już istnieje
        
        # Tworzenie tabeli forum_posts
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS forum_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                post_number INTEGER,
                content TEXT,
                post_date TEXT,
                url TEXT,
                content_urls TEXT,
                username TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES forum_threads (id),
                FOREIGN KEY (user_id) REFERENCES forum_users (id)
            )
        ''')

        # Upewnij się, że kolumna content_urls istnieje w już istniejących bazach
        try:
            self.cursor.execute('ALTER TABLE forum_posts ADD COLUMN content_urls TEXT')
        except sqlite3.OperationalError:
            pass  # Kolumna już istnieje
        
        self.connection.commit()
        
        # Dodaj indeksy dla szybszych zapytań
        self._create_indexes()

    def _create_indexes(self):
        """Tworzy indeksy dla szybszych zapytań"""
        try:
            # Indeks na URL wątków dla szybkiego wyszukiwania
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_threads_url ON forum_threads(url)')
            
            # Indeks na thread_id w postach
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_thread_id ON forum_posts(thread_id)')
            
            # Indeks na user_id w postach
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_user_id ON forum_posts(user_id)')
            
            # Indeks na post_number w postach
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_post_number ON forum_posts(post_number)')
            
            # Unikalny indeks na kombinację thread_id i post_number
            self.cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_thread_post ON forum_posts(thread_id, post_number)')
            
            # Indeks na username w użytkownikach
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON forum_users(username)')
            
            # Indeks na section_id w wątkach
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_threads_section_id ON forum_threads(section_id)')
            
            # Indeks na URL sekcji
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_sections_url ON forum_sections(url)')
            
            # Indeks na forum_id w sekcjach
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_sections_forum_id ON forum_sections(forum_id)')
            
            # Spróbuj dodać unikalne indeksy (mogą się nie udać, jeśli istnieją duplikaty w starej bazie)
            try:
                self.cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS uniq_sections_forum_url ON forum_sections(forum_id, url)')
            except Exception:
                pass
            try:
                self.cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS uniq_threads_section_url ON forum_threads(section_id, url)')
            except Exception:
                pass

            self.connection.commit()
            print("Utworzono indeksy dla szybszych zapytań")
            
        except Exception as e:
            print(f"Błąd podczas tworzenia indeksów: {e}")
            self.connection.rollback()

    def close_spider(self, spider):
        """Zamyka połączenie z bazą danych"""
        # Zapisz pozostałe batche przed zamknięciem
        self._flush_post_batch()
        self._flush_user_batch()
        
        if self.connection:
            self.connection.close()

    def process_item(self, item, spider):
        """Przetwarza itemy i zapisuje je do bazy danych"""
        adapter = ItemAdapter(item)
        
        if isinstance(item, ForumItem):
            return self._process_forum_item(adapter)
        elif isinstance(item, ForumSectionItem):
            return self._process_section_item(adapter)
        elif isinstance(item, ForumThreadItem):
            return self._process_thread_item(adapter)
        elif isinstance(item, ForumUserItem):
            return self._process_user_item(adapter)
        elif isinstance(item, ForumPostItem):
            return self._process_post_item(adapter)
        
        return item

    def _normalize_url_without_sid(self, raw_url):
        """Usuwa parametr sid z URL (jeśli istnieje) i zwraca znormalizowany URL."""
        try:
            if not raw_url:
                return raw_url
            parsed = urlparse(raw_url)
            # Rozbij parametry zapytania i usuń 'sid'
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            if 'sid' in query_params:
                query_params.pop('sid', None)
            # Złóż ponownie parametry (obsługa wielu wartości)
            new_query = urlencode(query_params, doseq=True)
            normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
            # Usuń ewentualne końcowe znaki '?', '&'
            if normalized.endswith('?'):
                normalized = normalized[:-1]
            if normalized.endswith('&'):
                normalized = normalized[:-1]
            return normalized
        except Exception:
            return raw_url

    def _flush_post_batch(self):
        """Zapisuje batch postów do bazy danych"""
        if not self.post_batch:
            return
            
        try:
            # UPSERT na bazie unikalności (thread_id, post_number)
            self.cursor.executemany(
                'INSERT INTO forum_posts (thread_id, user_id, post_number, content, post_date, url, content_urls, username, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(thread_id, post_number) DO UPDATE SET '
                'content=excluded.content, post_date=excluded.post_date, url=excluded.url, content_urls=excluded.content_urls, '
                'username=excluded.username, updated_at=excluded.updated_at',
                self.post_batch
            )
            self.connection.commit()
            self.post_batch = []
        except Exception as e:
            self.connection.rollback()
            raise e

    def _flush_user_batch(self):
        """Zapisuje batch użytkowników do bazy danych"""
        if not self.user_batch:
            return
            
        try:
            self.cursor.executemany(
                'INSERT INTO forum_users (username, join_date, posts_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                self.user_batch
            )
            self.connection.commit()
            self.user_batch = []
        except Exception as e:
            self.connection.rollback()
            raise e

    def _process_forum_item(self, adapter):
        """Przetwarza item forum"""
        spider_name = adapter.get('spider_name')
        title = adapter.get('title')
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Sprawdź czy forum już istnieje
        self.cursor.execute(
            'SELECT id FROM forums WHERE spider_name = ? AND title = ?',
            (spider_name, title)
        )
        existing_forum = self.cursor.fetchone()
        
        if existing_forum:
            # Aktualizuj istniejące forum
            forum_id = existing_forum[0]
            self.cursor.execute(
                'UPDATE forums SET updated_at = ? WHERE id = ?',
                (current_time, forum_id)
            )
            self.current_forum_id = forum_id
        else:
            # Dodaj nowe forum
            self.cursor.execute(
                'INSERT INTO forums (spider_name, title, created_at, updated_at) VALUES (?, ?, ?, ?)',
                (spider_name, title, current_time, current_time)
            )
            self.current_forum_id = self.cursor.lastrowid
        
        self.connection.commit()
        return adapter.item

    def _process_section_item(self, adapter):
        """Przetwarza item sekcji forum"""
        if not self.current_forum_id:
            # Jeśli nie ma forum_id, pomiń sekcję
            return adapter.item
        
        title = adapter.get('title')
        raw_url = adapter.get('url')
        # Znormalizuj URL (usuń sid)
        url = self._normalize_url_without_sid(raw_url)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Sprawdź czy sekcja już istnieje
        self.cursor.execute(
            'SELECT id FROM forum_sections WHERE forum_id = ? AND url = ?',
            (self.current_forum_id, url)
        )
        existing_section = self.cursor.fetchone()
        
        if existing_section:
            # Aktualizuj istniejącą sekcję
            section_id = existing_section[0]
            self.cursor.execute(
                'UPDATE forum_sections SET title = ?, updated_at = ? WHERE id = ?',
                (title, current_time, section_id)
            )
        else:
            # Dodaj nową sekcję
            self.cursor.execute(
                'INSERT INTO forum_sections (forum_id, title, url, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                (self.current_forum_id, title, url, current_time, current_time)
            )
            section_id = self.cursor.lastrowid
        
        # Dodaj mapowanie URL sekcji na ID (mapuj znormalizowany URL)
        self.section_url_mapping[url] = section_id
        
        self.connection.commit()
        return adapter.item

    def _process_thread_item(self, adapter):
        """Przetwarza item wątku forum"""
        title = adapter.get('title')
        raw_url = adapter.get('url')
        # Znormalizuj URL (usuń sid)
        url = self._normalize_url_without_sid(raw_url)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # print(f"Pipeline: Przetwarzam wątek '{title}'")
        
        # Konwertuj polską datę na standardowy format
        last_post_date = adapter.get('last_post_date')
        if last_post_date:
            converted_date = convert_polish_date_to_standard(last_post_date)
            if converted_date:
                last_post_date = converted_date
        
        # Znajdź section_id na podstawie URL sekcji lub URL wątku
        section_id = None
        section_url = adapter.get('section_url')
        if section_url:
            # Użyj URL sekcji do znalezienia section_id
            section_id = self._get_section_id_from_section_url(section_url)
        
        if not section_id:
            # Fallback: spróbuj znaleźć na podstawie URL wątku
            section_id = self._get_section_id_from_thread_url(url)
            
        if not section_id:
            # Jeśli nie można znaleźć sekcji, pomiń wątek
            return adapter.item
        
        # Sprawdź czy wątek już istnieje
        self.cursor.execute(
            'SELECT id FROM forum_threads WHERE section_id = ? AND url = ?',
            (section_id, url)
        )
        existing_thread = self.cursor.fetchone()
        
        if existing_thread:
            # Aktualizuj istniejący wątek
            thread_id = existing_thread[0]
            self.cursor.execute(
                '''UPDATE forum_threads SET 
                   title = ?, author = ?, replies = ?, views = ?, 
                   last_post_date = ?, last_post_author = ?, updated_at = ? 
                   WHERE id = ?''',
                (title, adapter.get('author'), adapter.get('replies'), adapter.get('views'),
                 last_post_date, adapter.get('last_post_author'), current_time, thread_id)
            )
        else:
            # Dodaj nowy wątek
            self.cursor.execute(
                '''INSERT INTO forum_threads 
                   (section_id, title, url, author, replies, views, last_post_date, last_post_author, created_at, updated_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (section_id, title, url, adapter.get('author'), adapter.get('replies'),
                 adapter.get('views'), last_post_date, adapter.get('last_post_author'),
                 current_time, current_time)
            )
            thread_id = self.cursor.lastrowid

        # Cache: mapuj URL oraz parametr 't' na thread_id
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            t_param = params.get('t', [None])[0]
            if t_param:
                self.thread_url_mapping[str(t_param)] = thread_id
        except Exception:
            pass
        self.thread_url_mapping[url] = thread_id
        
        self.connection.commit()
        return adapter.item

    def _get_section_id_from_section_url(self, section_url):
        """Znajduje section_id na podstawie URL sekcji"""
        try:
            # Użyj znormalizowanego URL (bez sid) i dopasuj dokładnie w obrębie bieżącego forum
            normalized = self._normalize_url_without_sid(section_url)
            self.cursor.execute(
                'SELECT id FROM forum_sections WHERE forum_id = ? AND url = ?',
                (self.current_forum_id, normalized)
            )
            result = self.cursor.fetchone()
            if result:
                return result[0]
            return None
            
        except Exception as e:
            print(f"Błąd podczas znajdowania section_id z URL sekcji: {e}")
            return None

    def _get_section_id_from_thread_url(self, thread_url):
        """Znajduje section_id na podstawie URL wątku"""
        try:
            # Wyciągnij parametr 'f' z URL wątku
            parsed_url = urlparse(thread_url)
            query_params = parse_qs(parsed_url.query)
            forum_param = query_params.get('f', [None])[0]
            
            if not forum_param:
                return None
            
            # Znajdź sekcję na podstawie parametru 'f' (ignorując sid)
            # Sprawdź wszystkie sekcje i dopasuj na podstawie parametru f
            self.cursor.execute(
                'SELECT id, url FROM forum_sections'
            )
            sections = self.cursor.fetchall()
            
            for section_id, section_url in sections:
                # Wyciągnij parametr 'f' z URL sekcji
                section_parsed = urlparse(section_url)
                section_params = parse_qs(section_parsed.query)
                section_forum_param = section_params.get('f', [None])[0]
                
                if section_forum_param == forum_param:
                    return section_id
            
            return None
            
        except Exception as e:
            print(f"Błąd podczas znajdowania section_id: {e}")
            return None

    def _process_user_item(self, adapter):
        """Przetwarza item użytkownika forum"""
        username = adapter.get('username')
        join_date = adapter.get('join_date')
        posts_count = adapter.get('posts_count')
        religion = adapter.get('religion')
        gender = adapter.get('gender')
        localization = adapter.get('localization')
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Konwertuj datę dołączenia jeśli jest w polskim formacie
        if join_date:
            converted_join_date = convert_polish_date_to_standard(join_date)
            if converted_join_date:
                join_date = converted_join_date
        
        # Sprawdź czy użytkownik już istnieje
        self.cursor.execute(
            'SELECT id FROM forum_users WHERE username = ?',
            (username,)
        )
        existing_user = self.cursor.fetchone()
        
        if existing_user:
            user_id = existing_user[0]
            # Aktualizuj istniejącego użytkownika
            self.cursor.execute(
                'UPDATE forum_users SET join_date = ?, posts_count = ?, religion = ?, gender = ?, localization = ?, updated_at = ? WHERE id = ?',
                (join_date, posts_count, religion, gender, localization, current_time, user_id)
            )
        else:
            # Dodaj nowego użytkownika
            self.cursor.execute(
                'INSERT INTO forum_users (username, join_date, posts_count, religion, gender, localization, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (username, join_date, posts_count, religion, gender, localization, current_time, current_time)
            )
            user_id = self.cursor.lastrowid
        
        # Zapisz mapowanie username na user_id
        self.username_mapping[username] = user_id
        
        self.connection.commit()
        return adapter.item

    def _process_post_item(self, adapter):
        """Przetwarza item postu forum"""
        thread_id = adapter.get('thread_id')
        user_id = adapter.get('user_id')
        post_number = adapter.get('post_number')
        content = adapter.get('content')
        content_urls_value = adapter.get('content_urls')
        post_date = adapter.get('post_date')
        url = adapter.get('url')
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Konwertuj datę postu jeśli jest w polskim formacie
        if post_date:
            converted_post_date = convert_polish_date_to_standard(post_date)
            if converted_post_date:
                post_date = converted_post_date
        
        # Znajdź thread_id w bazie danych na podstawie parametru t
        if isinstance(thread_id, str):
            # Użyj cache mapowania URL wątków dla szybszego dostępu
            if thread_id in self.thread_url_mapping:
                thread_id = self.thread_url_mapping[thread_id]
            else:
                # thread_id to parametr t z URL, znajdź odpowiadający mu thread_id w bazie
                self.cursor.execute(
                    'SELECT id FROM forum_threads WHERE url LIKE ? LIMIT 1',
                    (f'%t={thread_id}%',)
                )
                result = self.cursor.fetchone()
                if result:
                    thread_id = result[0]
                    # Dodaj do cache
                    self.thread_url_mapping[thread_id] = thread_id
                else:
                    # Jeśli nie znaleziono wątku, pomiń post
                    return adapter.item
        
        # Znajdź user_id na podstawie username (będzie ustawione przez spider)
        if not user_id:
            # Sprawdź czy mamy username w mapowaniu
            username = adapter.get('username')
            if username and username in self.username_mapping:
                user_id = self.username_mapping[username]
            else:
                # Jeśli nie mamy user_id, pomiń post
                return adapter.item
        
        # Sprawdź czy post już istnieje (na podstawie thread_id i post_number)
        # Użyj INSERT OR IGNORE zamiast sprawdzania i aktualizacji
        username = adapter.get('username')
        # Serializuj content_urls do JSON (lista -> string), puste listy jako []
        try:
            if isinstance(content_urls_value, str):
                content_urls_json = content_urls_value
            else:
                content_urls_json = json.dumps(content_urls_value or [], ensure_ascii=False)
        except Exception:
            content_urls_json = '[]'

        self.post_batch.append((
            thread_id, user_id, post_number, content, post_date, url, content_urls_json, username, current_time, current_time
        ))
        
        # Jeśli batch jest pełny, zapisz go
        if len(self.post_batch) >= self.batch_size:
            self._flush_post_batch()
        return adapter.item


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class ScraperPipeline:
    def process_item(self, item, spider):
        return item

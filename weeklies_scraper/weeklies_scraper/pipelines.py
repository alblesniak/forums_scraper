# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

import sqlite3
import logging
from datetime import datetime
from itemadapter import ItemAdapter


class WeekliesScraperPipeline:
    """Podstawowy pipeline dla tygodników - na razie tylko logowanie"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        
        # Logowanie informacji o itemach
        item_type = item.__class__.__name__
        self.logger.info(f"Przetwarzam {item_type}: {adapter.get('title', adapter.get('name', 'Unknown'))}")
        
        return item


class SQLitePipeline:
    """Pipeline do zapisywania danych do bazy SQLite"""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
    
    @classmethod
    def from_crawler(cls, crawler):
        db_path = crawler.settings.get('SQLITE_DATABASE_PATH', 'data/databases/weeklies_unified.db')
        return cls(db_path)
    
    def open_spider(self, spider):
        """Otwórz połączenie z bazą danych"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()
        self.logger.info(f"Otwarto bazę danych: {self.db_path}")
    
    def close_spider(self, spider):
        """Zamknij połączenie z bazą danych"""
        if hasattr(self, 'conn'):
            self.conn.close()
            self.logger.info(f"Zamknięto bazę danych: {self.db_path}")
    
    def _create_tables(self):
        """Utwórz tabele w bazie danych"""
        tables = [
            """CREATE TABLE IF NOT EXISTS weeklies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                description TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            
            """CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weekly_name TEXT NOT NULL,
                issue_name TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                issue_year INTEGER NOT NULL,
                issue_date DATE,
                issue_url TEXT NOT NULL,
                issue_cover_url TEXT,
                issue_description TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(weekly_name, issue_number, issue_year)
            )""",
            
            """CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weekly_name TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                issue_year INTEGER NOT NULL,
                section_name TEXT NOT NULL,
                section_url TEXT,
                section_description TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(weekly_name, issue_number, issue_year, section_name)
            )""",
            
            """CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weekly_name TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                issue_year INTEGER NOT NULL,
                section_name TEXT,
                article_title TEXT NOT NULL,
                article_intro TEXT,
                article_authors TEXT,
                article_url TEXT NOT NULL,
                article_content TEXT,
                article_tags TEXT,
                article_word_count INTEGER,
                article_image_urls TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(weekly_name, issue_number, issue_year, article_url)
            )""",
            
            """CREATE TABLE IF NOT EXISTS authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                bio TEXT,
                photo_url TEXT,
                social_media TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        ]
        
        for table_sql in tables:
            self.cursor.execute(table_sql)
        
        self.conn.commit()
        self.logger.info("Tabele utworzone pomyślnie")
    
    def process_item(self, item, spider):
        """Zapisz item do odpowiedniej tabeli"""
        adapter = ItemAdapter(item)
        
        try:
            if item.__class__.__name__ == 'WeeklyItem':
                self._save_weekly(adapter)
            elif item.__class__.__name__ == 'IssueItem':
                self._save_issue(adapter)
            elif item.__class__.__name__ == 'SectionItem':
                self._save_section(adapter)
            elif item.__class__.__name__ == 'ArticleItem':
                self._save_article(adapter)
            elif item.__class__.__name__ == 'AuthorItem':
                self._save_author(adapter)
            
            self.conn.commit()
            
        except Exception as e:
            self.logger.error(f"Błąd podczas zapisywania {item.__class__.__name__}: {e}")
            self.conn.rollback()
            raise
        
        return item
    
    def _save_weekly(self, adapter):
        """Zapisz tygodnik"""
        self.cursor.execute("""
            INSERT OR REPLACE INTO weeklies (name, url, description, scraped_at)
            VALUES (?, ?, ?, ?)
        """, (
            adapter.get('name'),
            adapter.get('url'),
            adapter.get('description'),
            adapter.get('scraped_at', datetime.now())
        ))
    
    def _save_issue(self, adapter):
        """Zapisz wydanie"""
        self.cursor.execute("""
            INSERT OR REPLACE INTO issues 
            (weekly_name, issue_name, issue_number, issue_year, issue_date, 
             issue_url, issue_cover_url, issue_description, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            adapter.get('weekly_name'),
            adapter.get('issue_name'),
            adapter.get('issue_number'),
            adapter.get('issue_year'),
            adapter.get('issue_date'),
            adapter.get('issue_url'),
            adapter.get('issue_cover_url'),
            adapter.get('issue_description'),
            adapter.get('scraped_at', datetime.now())
        ))
    
    def _save_section(self, adapter):
        """Zapisz sekcję"""
        self.cursor.execute("""
            INSERT OR REPLACE INTO sections 
            (weekly_name, issue_number, issue_year, section_name, 
             section_url, section_description, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            adapter.get('weekly_name'),
            adapter.get('issue_number'),
            adapter.get('issue_year'),
            adapter.get('section_name'),
            adapter.get('section_url'),
            adapter.get('section_description'),
            adapter.get('scraped_at', datetime.now())
        ))
    
    def _save_article(self, adapter):
        """Zapisz artykuł"""
        self.cursor.execute("""
            INSERT OR REPLACE INTO articles 
            (weekly_name, issue_number, issue_year, section_name, article_title,
             article_intro, article_authors, article_url, article_content,
             article_tags, article_word_count, article_image_urls, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            adapter.get('weekly_name'),
            adapter.get('issue_number'),
            adapter.get('issue_year'),
            adapter.get('section_name'),
            adapter.get('article_title'),
            adapter.get('article_intro'),
            adapter.get('article_authors'),
            adapter.get('article_url'),
            adapter.get('article_content'),
            adapter.get('article_tags'),
            adapter.get('article_word_count'),
            adapter.get('article_image_urls'),
            adapter.get('scraped_at', datetime.now())
        ))
    
    def _save_author(self, adapter):
        """Zapisz autora"""
        self.cursor.execute("""
            INSERT OR REPLACE INTO authors (name, bio, photo_url, social_media, scraped_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            adapter.get('name'),
            adapter.get('bio'),
            adapter.get('photo_url'),
            adapter.get('social_media'),
            adapter.get('scraped_at', datetime.now())
        ))

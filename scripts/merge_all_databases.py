#!/usr/bin/env python3
"""
Skrypt do łączenia wszystkich baz danych forum w jedną
z zachowaniem unikalności ID i bezpiecznym zarządzaniem konfliktami
"""

import sqlite3
import os
import glob
from datetime import datetime
import argparse
import shutil

class DatabaseMerger:
    def __init__(self, target_db="data/databases/merged_forums.db"):
        self.target_db = target_db
        self.source_dbs = []
        self.max_ids = {}  # Maksymalne ID dla każdej tabeli
        self.offset_ids = {}  # Offset ID dla każdej tabeli i bazy
        self.db_dir = os.path.dirname(self.target_db) or "data/databases"
        
    def find_databases(self):
        """Znajduje wszystkie pliki .db w katalogu"""
        db_files = glob.glob("data/databases/forum_*.db")
        # Wykluczamy już połączone bazy
        db_files = [f for f in db_files if not f.startswith("merged_")]
        
        print(f"🔍 Znalezione bazy danych: {len(db_files)}")
        for db in db_files:
            size = os.path.getsize(db) / (1024 * 1024)  # MB
            print(f"   📁 {db} ({size:.1f} MB)")
        
        return db_files
    
    def analyze_database_structure(self, db_path):
        """Analizuje strukturę bazy danych"""
        print(f"\n📊 Analiza struktury: {db_path}")
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Pobierz listę tabel (pomiń tabele systemowe)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = cursor.fetchall()
            
            structure = {}
            for table in tables:
                table_name = table[0]
                
                # Pobierz strukturę tabeli
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                
                # Pobierz liczbę rekordów
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cursor.fetchone()[0]
                
                # Znajdź maksymalne ID (jeśli kolumna id istnieje)
                try:
                    cursor.execute(f"SELECT MAX(id) FROM {table_name};")
                    max_id = cursor.fetchone()[0] or 0
                except sqlite3.Error:
                    max_id = 0
                
                structure[table_name] = {
                    'columns': columns,
                    'count': count,
                    'max_id': max_id
                }
                
                print(f"   📋 {table_name}: {count:,} rekordów, max_id: {max_id}")
            
            conn.close()
            return structure
            
        except sqlite3.Error as e:
            print(f"❌ Błąd analizy {db_path}: {e}")
            return None
    
    def create_target_database(self, structure):
        """Tworzy docelową bazę danych z odpowiednią strukturą"""
        print(f"\n🏗️  Tworzenie docelowej bazy: {self.target_db}")
        
        try:
            # Usuń istniejącą bazę jeśli istnieje
            if os.path.exists(self.target_db):
                os.remove(self.target_db)
                print("   🗑️  Usunięto istniejącą bazę")
            
            conn = sqlite3.connect(self.target_db)
            cursor = conn.cursor()
            
            # Utwórz tabele na podstawie struktury pierwszej bazy
            for table_name, table_info in structure.items():
                columns = table_info['columns']
                
                # Buduj CREATE TABLE statement
                column_defs = []
                for col in columns:
                    col_id, col_name, col_type, not_null, default_val, pk = col
                    col_def = f"{col_name} {col_type}"
                    
                    if not_null:
                        col_def += " NOT NULL"
                    if default_val is not None:
                        col_def += f" DEFAULT {default_val}"
                    if pk:
                        col_def += " PRIMARY KEY AUTOINCREMENT"
                    
                    column_defs.append(col_def)
                
                # Dodaj forum_id do forum_users jeśli nie istnieje
                if table_name == "forum_users" and "forum_id" not in [col[1] for col in columns]:
                    column_defs.append("forum_id TEXT")
                    print("   🔧 Dodano kolumnę forum_id do forum_users")
                
                create_sql = f"CREATE TABLE {table_name} (\n  " + ",\n  ".join(column_defs) + "\n);"
                
                print(f"   📋 Tworzenie tabeli: {table_name}")
                cursor.execute(create_sql)
            
            # Utwórz indeksy dla lepszej wydajności
            print("   🔍 Tworzenie indeksów...")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_forum_posts_user_id ON forum_posts(user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_forum_posts_thread_id ON forum_posts(thread_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_forum_threads_section_id ON forum_threads(section_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_forum_sections_forum_id ON forum_sections(forum_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_forum_users_username ON forum_users(username);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_forum_users_forum_id ON forum_users(forum_id);")
            
            conn.commit()
            conn.close()
            print("✅ Docelowa baza utworzona")
            
        except sqlite3.Error as e:
            print(f"❌ Błąd tworzenia bazy: {e}")
            return False
        
        return True

    def _ensure_analysis_tables(self) -> None:
        """Zapewnia istnienie tabel analitycznych w bazie docelowej."""
        conn = sqlite3.connect(self.target_db)
        cur = conn.cursor()
        # token_analysis
        cur.execute(
            """
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
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_token_analysis_post_id ON token_analysis(post_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_token_analysis_date ON token_analysis(analyzed_at)")

        # analysis_stats
        cur.execute(
            """
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
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_analysis_stats_date ON analysis_stats(analysis_date)")

        # gender_predictions
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gender_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                predicted_gender TEXT,
                score_m REAL,
                score_k REAL,
                evidence_count INTEGER,
                posts_with_evidence INTEGER,
                method TEXT,
                evidence_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gender_predictions_user ON gender_predictions(user_id)")
        conn.commit()
        conn.close()

    def _merge_analysis_for_forum(self, forum_name: str, offset_ids: dict | None) -> None:
        """Scal tabele analityczne z per-forum analizy (jeśli istnieją) do bazy docelowej.
        Oczekuje pliku analysis_forums_<forum>.db w tym samym katalogu co target.
        """
        # Wywnioskuj ścieżkę analizy per-forum
        cand = os.path.join(self.db_dir, f"analysis_forums_{forum_name}.db")
        if not os.path.exists(cand):
            return
        try:
            print(f"   ➕ Dołączanie analityki z: {cand}")
            self._ensure_analysis_tables()

            src_conn = sqlite3.connect(cand)
            src_cur = src_conn.cursor()
            tgt_conn = sqlite3.connect(self.target_db)
            tgt_cur = tgt_conn.cursor()

            # Oblicz przesunięcia
            post_off = int((offset_ids or {}).get("forum_posts", 0) or 0)
            user_off = int((offset_ids or {}).get("forum_users", 0) or 0)

            # token_analysis
            try:
                src_cur.execute("SELECT post_id, token_count, word_count, character_count, analysis_hash, analyzed_at, processing_time_ms, created_at FROM token_analysis")
                rows = src_cur.fetchall()
                if rows:
                    ins = (
                        "INSERT OR IGNORE INTO token_analysis (post_id, token_count, word_count, character_count, analysis_hash, analyzed_at, processing_time_ms, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    )
                    batch = []
                    for r in rows:
                        pid = (r[0] or 0) + post_off
                        batch.append((pid, r[1], r[2], r[3], r[4], r[5], r[6], r[7]))
                    tgt_cur.executemany(ins, batch)
            except sqlite3.Error as e:
                print(f"      ⚠️ token_analysis: {e}")

            # analysis_stats (kopiuj 1:1)
            try:
                src_cur.execute("SELECT analysis_date, posts_analyzed, total_tokens, total_words, total_characters, processing_time_seconds, created_at FROM analysis_stats")
                rows = src_cur.fetchall()
                if rows:
                    ins = (
                        "INSERT INTO analysis_stats (analysis_date, posts_analyzed, total_tokens, total_words, total_characters, processing_time_seconds, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)"
                    )
                    tgt_cur.executemany(ins, rows)
            except sqlite3.Error as e:
                print(f"      ⚠️ analysis_stats: {e}")

            # gender_predictions
            try:
                src_cur.execute("SELECT user_id, predicted_gender, score_m, score_k, evidence_count, posts_with_evidence, method, evidence_json, created_at, updated_at FROM gender_predictions")
                rows = src_cur.fetchall()
                if rows:
                    ins = (
                        "INSERT OR REPLACE INTO gender_predictions (user_id, predicted_gender, score_m, score_k, evidence_count, posts_with_evidence, method, evidence_json, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    )
                    batch = []
                    for r in rows:
                        uid = (r[0] or 0) + user_off
                        batch.append((uid, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]))
                    tgt_cur.executemany(ins, batch)
            except sqlite3.Error as e:
                print(f"      ⚠️ gender_predictions: {e}")

            tgt_conn.commit()
            src_conn.close()
            tgt_conn.close()
            print("   ✅ Złączono analitykę dla forum:", forum_name)
        except Exception as e:
            print(f"   ⚠️ Błąd łączenia analityki ({forum_name}): {e}")
    
    def get_max_ids_from_target(self):
        """Pobiera maksymalne ID z docelowej bazy"""
        try:
            conn = sqlite3.connect(self.target_db)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = cursor.fetchall()
            
            max_ids = {}
            for table in tables:
                table_name = table[0]
                try:
                    cursor.execute(f"SELECT MAX(id) FROM {table_name};")
                    max_id = cursor.fetchone()[0] or 0
                except sqlite3.Error:
                    max_id = 0
                max_ids[table_name] = max_id
            
            conn.close()
            return max_ids
            
        except sqlite3.Error as e:
            print(f"❌ Błąd pobierania max ID: {e}")
            return {}
    
    def merge_database(self, source_db, offset_ids=None, forum_prefix=""):
        """Łączy pojedynczą bazę z docelową"""
        print(f"\n🔄 Łączenie: {source_db}")
        
        try:
            # Połącz z bazą źródłową
            source_conn = sqlite3.connect(source_db)
            source_cursor = source_conn.cursor()
            
            # Połącz z bazą docelową
            target_conn = sqlite3.connect(self.target_db)
            target_cursor = target_conn.cursor()
            
            # Pobierz nazwę forum z bazy źródłowej
            source_cursor.execute("SELECT spider_name FROM forums LIMIT 1;")
            forum_result = source_cursor.fetchone()
            forum_name = forum_result[0] if forum_result else "unknown"
            
            print(f"   📍 Forum: {forum_name}")
            
            # Pobierz listę tabel (pomiń tabele systemowe)
            source_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = source_cursor.fetchall()
            
            total_merged = 0
            
            # Ustaw tryb WAL dla lepszej wydajności
            target_cursor.execute("PRAGMA journal_mode=WAL;")
            target_cursor.execute("PRAGMA synchronous=NORMAL;")
            target_cursor.execute("PRAGMA cache_size=10000;")
            
            for table in tables:
                table_name = table[0]
                
                # Pobierz wszystkie dane z tabeli źródłowej
                source_cursor.execute(f"SELECT * FROM {table_name};")
                rows = source_cursor.fetchall()
                
                if not rows:
                    continue
                
                # Pobierz nazwy kolumn
                source_cursor.execute(f"PRAGMA table_info({table_name});")
                columns = source_cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                # Przygotuj placeholdery dla INSERT
                placeholders = ", ".join(["?" for _ in column_names])
                insert_sql = f"INSERT OR IGNORE INTO {table_name} ({', '.join(column_names)}) VALUES ({placeholders});"
                
                # Specjalne przetwarzanie dla forum_users - dodaj forum_id i prefiks username
                if table_name == "forum_users":
                    print(f"   🔧 Przetwarzanie forum_users z prefiksem: {forum_name}_")
                    
                    # Sprawdź czy forum_id istnieje w kolumnach
                    has_forum_id = "forum_id" in column_names
                    
                    if not has_forum_id:
                        # Dodaj forum_id jako ostatnią kolumnę
                        column_names.append("forum_id")
                        placeholders = ", ".join(["?" for _ in column_names])
                        insert_sql = f"INSERT OR IGNORE INTO {table_name} ({', '.join(column_names)}) VALUES ({placeholders});"
                    
                    # Przetwórz dane
                    processed_rows = []
                    for row in rows:
                        row_list = list(row)
                        
                        # Dodaj forum_id jeśli nie istnieje
                        if not has_forum_id:
                            row_list.append(forum_name)
                        
                        # Prefiksuj username żeby uniknąć konfliktów
                        username_idx = column_names.index("username") if "username" in column_names else -1
                        if username_idx >= 0 and row_list[username_idx]:
                            row_list[username_idx] = f"{forum_name}_{row_list[username_idx]}"
                        
                        processed_rows.append(tuple(row_list))
                    
                    rows = processed_rows
                
                # Jeśli mamy offsety, zaktualizuj ID oraz klucze obce zależnie od tabeli
                if offset_ids:
                    updated_rows = []
                    # Zbuduj mapę indeksów kolumn dla wygody
                    column_index = {name: idx for idx, name in enumerate(column_names)}

                    for row in rows:
                        row_list = list(row)

                        # Zawsze przesuwaj własne ID jeśli dotyczy
                        if table_name in offset_ids and row_list and row_list[0] is not None:
                            row_list[0] = row_list[0] + offset_ids[table_name]

                        # Przesuwaj klucze obce zgodnie z tabelą nadrzędną
                        if table_name == "forum_sections":
                            # forum_sections.forum_id odnosi się do forums.id
                            if "forum_id" in column_index and row_list[column_index["forum_id"]] is not None:
                                if "forums" in offset_ids:
                                    row_list[column_index["forum_id"]] = row_list[column_index["forum_id"]] + offset_ids["forums"]

                        elif table_name == "forum_threads":
                            # forum_threads.section_id odnosi się do forum_sections.id
                            if "section_id" in column_index and row_list[column_index["section_id"]] is not None:
                                if "forum_sections" in offset_ids:
                                    row_list[column_index["section_id"]] = row_list[column_index["section_id"]] + offset_ids["forum_sections"]

                        elif table_name == "forum_posts":
                            # forum_posts.thread_id odnosi się do forum_threads.id
                            if "thread_id" in column_index and row_list[column_index["thread_id"]] is not None:
                                if "forum_threads" in offset_ids:
                                    row_list[column_index["thread_id"]] = row_list[column_index["thread_id"]] + offset_ids["forum_threads"]
                            # forum_posts.user_id (jeśli istnieje) do forum_users.id
                            if "user_id" in column_index and row_list[column_index["user_id"]] is not None:
                                if "forum_users" in offset_ids:
                                    row_list[column_index["user_id"]] = row_list[column_index["user_id"]] + offset_ids["forum_users"]

                        elif table_name == "forum_users":
                            # forum_users może mieć user_id? (zwykle nie), nic do przesunięcia poza własnym ID
                            pass

                        updated_rows.append(tuple(row_list))

                    rows = updated_rows
                
                # Wstaw dane w mniejszych partiach dla lepszej wydajności
                batch_size = 1000
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    target_cursor.executemany(insert_sql, batch)
                
                merged_count = len(rows)
                total_merged += merged_count
                
                print(f"   📋 {table_name}: {merged_count:,} rekordów")
            
            source_conn.close()
            target_conn.commit()
            target_conn.close()
            
            print(f"✅ Łącznie połączono: {total_merged:,} rekordów")
            # Po połączeniu bazy forum spróbuj dociągnąć analitykę sidecar
            try:
                self._merge_analysis_for_forum(forum_name, offset_ids or {})
            except Exception as e:
                print(f"⚠️ Nie udało się złączyć analityki dla {forum_name}: {e}")
            return total_merged
            
        except sqlite3.Error as e:
            print(f"❌ Błąd łączenia {source_db}: {e}")
            return 0
    
    def merge_all_databases(self, use_id_offset=True):
        """Łączy wszystkie bazy danych"""
        print("🚀 Rozpoczynam łączenie wszystkich baz danych")
        print("=" * 60)
        
        # Znajdź wszystkie bazy
        db_files = self.find_databases()
        if not db_files:
            print("❌ Nie znaleziono baz do połączenia")
            return False
        
        # Analizuj pierwszą bazę aby poznać strukturę
        first_structure = self.analyze_database_structure(db_files[0])
        if not first_structure:
            return False
        
        # Utwórz docelową bazę
        if not self.create_target_database(first_structure):
            return False
        
        total_merged = 0
        
        # Łącz każdą bazę
        for i, db_file in enumerate(db_files):
            print(f"\n📦 Przetwarzanie {i+1}/{len(db_files)}: {db_file}")
            
            if use_id_offset and i > 0:
                # Pobierz aktualne maksymalne ID z docelowej bazy
                current_max_ids = self.get_max_ids_from_target()
                offset_ids = {}
                
                # Oblicz offset dla każdej tabeli
                for table_name in current_max_ids:
                    offset_ids[table_name] = current_max_ids[table_name]
                
                merged_count = self.merge_database(db_file, offset_ids)
            else:
                merged_count = self.merge_database(db_file)
            
            total_merged += merged_count
        
        # Sprawdź finalne statystyki
        print("\n📊 Sprawdzanie finalnych statystyk...")
        self.check_final_statistics()
        
        # Podsumowanie
        print("\n" + "=" * 60)
        print("🎉 ŁĄCZENIE ZAKOŃCZONE")
        print(f"📊 Łącznie połączono: {total_merged:,} rekordów")
        print(f"📁 Docelowa baza: {self.target_db}")
        
        # Sprawdź rozmiar docelowej bazy
        if os.path.exists(self.target_db):
            size_mb = os.path.getsize(self.target_db) / (1024 * 1024)
            print(f"📏 Rozmiar docelowej bazy: {size_mb:.1f} MB")
        
        return True
    
    def check_final_statistics(self):
        """Sprawdza finalne statystyki połączonej bazy"""
        try:
            conn = sqlite3.connect(self.target_db)
            cursor = conn.cursor()
            
            print("   📊 Statystyki połączonej bazy:")
            
            # Sprawdź fora
            cursor.execute("SELECT f.id as forum_id, f.spider_name, COUNT(fs.id) as sections, COUNT(fp.id) as posts FROM forums f LEFT JOIN forum_sections fs ON f.id = fs.forum_id LEFT JOIN forum_threads ft ON fs.id = ft.section_id LEFT JOIN forum_posts fp ON ft.id = fp.thread_id GROUP BY f.id, f.spider_name;")
            forums_stats = cursor.fetchall()
            
            for forum_id, spider_name, sections, posts in forums_stats:
                print(f"      Forum {spider_name}: {sections:,} sekcji, {posts:,} postów")
            
            # Sprawdź użytkowników z podziałem na fora
            cursor.execute("SELECT forum_id, gender, COUNT(*) FROM forum_users GROUP BY forum_id, gender ORDER BY forum_id, gender;")
            users_stats = cursor.fetchall()
            
            print("      Użytkownicy:")
            current_forum = None
            for forum_id, gender, count in users_stats:
                if forum_id != current_forum:
                    print(f"         Forum {forum_id}:")
                    current_forum = forum_id
                
                gender_name = "Męscy" if gender == "M" else "Kobiece" if gender == "K" else f"Nieznane ({gender})"
                print(f"            {gender_name}: {count:,}")
            
            # Sprawdź czy są duplikaty username
            cursor.execute("SELECT username, COUNT(*) as count FROM forum_users GROUP BY username HAVING count > 1 LIMIT 5;")
            duplicates = cursor.fetchall()
            
            if duplicates:
                print("      ⚠️  Duplikaty username (powinno być 0):")
                for username, count in duplicates:
                    print(f"         {username}: {count} wystąpień")
            else:
                print("      ✅ Brak duplikatów username")
            
            conn.close()
            
        except sqlite3.Error as e:
            print(f"   ❌ Błąd sprawdzania statystyk: {e}")

def main():
    parser = argparse.ArgumentParser(description="Łączenie baz danych forum")
    parser.add_argument("--target", default="data/databases/merged_forums.db", 
                       help="Nazwa docelowej bazy danych (domyślnie: data/databases/merged_forums.db)")
    parser.add_argument("--no-offset", action="store_true",
                       help="Nie używaj offset dla ID (może powodować konflikty)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Tylko analiza, bez łączenia")
    
    args = parser.parse_args()
    
    merger = DatabaseMerger(args.target)
    
    if args.dry_run:
        print("🔍 ANALIZA STRUKTURY BAZ DANYCH")
        print("=" * 50)
        
        db_files = merger.find_databases()
        for db_file in db_files:
            merger.analyze_database_structure(db_file)
    else:
        merger.merge_all_databases(use_id_offset=not args.no_offset)

if __name__ == "__main__":
    main() 

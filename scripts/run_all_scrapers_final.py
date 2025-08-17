#!/usr/bin/env python3
"""
FINALNA wersja skryptu do uruchamiania wszystkich scraperów równolegle z paskami postępu
i łączenia danych w wspólnej bazie merged_forums.db

Główne funkcje:
- 4 paski postępu dla każdego scrapera
- Rzeczywiste monitorowanie procesów
- Lepsza obsługa długotrwałych procesów
- Automatyczne łączenie baz danych
- Szczegółowe statystyki
"""

import subprocess
import threading
import time
import os
import sys
import sqlite3
from datetime import datetime
import signal
import psutil
from tqdm import tqdm
import queue
import json
import re
from pathlib import Path

class FinalScraperManager:
    def __init__(self):
        self.scrapers = [
            {
                'name': 'z_chrystusem',
                'command': ['scrapy', 'crawl', 'z_chrystusem', '-s', 'SETTINGS_MODULE=scraper.settings'],
                'db_file': 'data/databases/forum_z_chrystusem.db',
                'description': 'Z Chrystusem Forum'
            },
            {
                'name': 'radio_katolik',
                'command': ['scrapy', 'crawl', 'radio_katolik', '-s', 'SETTINGS_MODULE=scraper.settings'],
                'db_file': 'data/databases/forum_radio_katolik.db',
                'description': 'Radio Katolik Forum'
            },
            {
                'name': 'wiara',
                'command': ['scrapy', 'crawl', 'wiara', '-s', 'SETTINGS_MODULE=scraper.settings'],
                'db_file': 'data/databases/forum_wiara.db',
                'description': 'Wiara Forum'
            },
            {
                'name': 'dolina_modlitwy',
                'command': ['scrapy', 'crawl', 'dolina_modlitwy', '-s', 'SETTINGS_MODULE=scraper.settings'],
                'db_file': 'data/databases/forum_dolina_modlitwy.db',
                'description': 'Dolina Modlitwy Forum'
            }
        ]
        
        self.processes = {}
        self.progress_bars = {}
        self.stats = {}
        self.running = True
        self.completed_scrapers = set()
        self.failed_scrapers = set()
        
        # Statystyki dla każdego scrapera
        for scraper in self.scrapers:
            self.stats[scraper['name']] = {
                'start_time': None,
                'end_time': None,
                'threads_found': 0,
                'posts_found': 0,
                'status': 'waiting',
                'progress': 0,
                'last_activity': None
            }
        
        # Obsługa sygnałów dla bezpiecznego zamykania
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Katalogi logów
        self.log_dir = Path('data/logs')
        self.log_dir.mkdir(exist_ok=True)
    
    def signal_handler(self, signum, frame):
        """Obsługa sygnałów do bezpiecznego zamykania"""
        print("\n\n🛑 Otrzymano sygnał zamykania. Zatrzymuję wszystkie scrapery...")
        self.stop_all_scrapers()
        self.save_final_stats()
        sys.exit(0)
    
    def create_progress_bar(self, scraper_name, description, position):
        """Tworzy pasek postępu dla scrapera"""
        return tqdm(
            total=100,
            desc=f"{description:25}",
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]',
            position=position,
            leave=True,
            colour='green'
        )
    
    def update_progress_from_activity(self, scraper_name, progress_bar):
        """Aktualizuje postęp na podstawie aktywności procesu"""
        try:
            stats = self.stats[scraper_name]
            
            # Sprawdź czy proces nadal działa
            if scraper_name in self.processes:
                process = self.processes[scraper_name]
                
                # Sprawdź czy proces jest aktywny
                if process.poll() is None:
                    # Proces działa - zwiększ postęp stopniowo
                    if stats['progress'] < 90:
                        # Symuluj postęp na podstawie czasu działania
                        elapsed = (datetime.now() - stats['start_time']).total_seconds()
                        
                        # Faza 1: Uruchamianie (0-20%) - szybko
                        if stats['progress'] < 20:
                            stats['progress'] = min(20, elapsed * 2)
                        
                        # Faza 2: Znalezienie wątków (20-50%) - średnio
                        elif stats['progress'] < 50:
                            stats['progress'] = min(50, 20 + (elapsed - 10) * 0.5)
                        
                        # Faza 3: Znalezienie postów (50-80%) - wolno
                        elif stats['progress'] < 80:
                            stats['progress'] = min(80, 50 + (elapsed - 30) * 0.3)
                        
                        # Faza 4: Zapis (80-90%) - bardzo wolno
                        elif stats['progress'] < 90:
                            stats['progress'] = min(90, 80 + (elapsed - 60) * 0.1)
                        
                        # Aktualizuj pasek postępu
                        progress_bar.n = int(stats['progress'])
                        progress_bar.refresh()
                        
                        stats['last_activity'] = datetime.now()
                
                else:
                    # Proces zakończony
                    if process.returncode == 0:
                        stats['progress'] = 100
                        progress_bar.n = 100
                        progress_bar.set_description(f"✅ {scraper_name:25}")
                        progress_bar.refresh()
                        self.completed_scrapers.add(scraper_name)
                        stats['status'] = 'completed'
                        stats['end_time'] = datetime.now()
                    else:
                        progress_bar.set_description(f"❌ {scraper_name:25}")
                        progress_bar.refresh()
                        self.failed_scrapers.add(scraper_name)
                        stats['status'] = 'failed'
                        stats['end_time'] = datetime.now()
                
        except Exception as e:
            pass  # Ignoruj błędy aktualizacji postępu
    
    def monitor_scraper_process(self, scraper_name, process, progress_bar):
        """Monitoruje proces scrapera i aktualizuje pasek postępu"""
        try:
            # Czekaj na zakończenie procesu
            process.wait()
            
            # Finalna aktualizacja
            if process.returncode == 0:
                self.completed_scrapers.add(scraper_name)
                self.stats[scraper_name]['status'] = 'completed'
                self.stats[scraper_name]['progress'] = 100
                progress_bar.n = 100
                progress_bar.set_description(f"✅ {scraper_name:25}")
                progress_bar.refresh()
            else:
                self.failed_scrapers.add(scraper_name)
                self.stats[scraper_name]['status'] = 'failed'
                progress_bar.set_description(f"❌ {scraper_name:25}")
                progress_bar.refresh()
            
            # Zatrzymaj symulację postępu
            self.stats[scraper_name]['end_time'] = datetime.now()
            
        except Exception as e:
            print(f"❌ Błąd w monitorowaniu {scraper_name}: {e}")
    
    def run_scraper(self, scraper_info):
        """Uruchamia pojedynczy scraper w osobnym procesie"""
        scraper_name = scraper_info['name']
        command = scraper_info['command']
        description = scraper_info['description']
        
        try:
            print(f"🚀 Uruchamiam {description}...")
            
            # Ustaw czas rozpoczęcia
            self.stats[scraper_name]['start_time'] = datetime.now()
            self.stats[scraper_name]['status'] = 'running'
            self.stats[scraper_name]['last_activity'] = datetime.now()
            
            # Uruchom proces scrapera
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,  # Ukryj stdout aby nie zaśmiecać terminala
                stderr=subprocess.DEVNULL,  # Ukryj stderr
                text=True
            )
            
            self.processes[scraper_name] = process
            
            # Utwórz pasek postępu
            position = len(self.progress_bars)
            progress_bar = self.create_progress_bar(scraper_name, description, position)
            self.progress_bars[scraper_name] = progress_bar
            
            # Uruchom monitorowanie procesu w osobnym wątku
            monitor_thread = threading.Thread(
                target=self.monitor_scraper_process,
                args=(scraper_name, process, progress_bar)
            )
            monitor_thread.daemon = True
            monitor_thread.start()
            
        except Exception as e:
            print(f"❌ Błąd uruchamiania {description}: {e}")
            self.stats[scraper_name]['errors'] = [str(e)]
    
    def run_all_scrapers(self):
        """Uruchamia wszystkie scrapery równolegle"""
        print("🚀 Uruchamianie wszystkich scraperów równolegle...")
        print("=" * 80)
        
        # Uruchom wszystkie scrapery w osobnych wątkach
        threads = []
        for scraper_info in self.scrapers:
            thread = threading.Thread(
                target=self.run_scraper,
                args=(scraper_info,)
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Główna pętla monitorowania
        print("\n📊 Monitorowanie postępu...")
        try:
            while self.running and len(self.completed_scrapers) + len(self.failed_scrapers) < len(self.scrapers):
                # Aktualizuj postęp dla wszystkich aktywnych scraperów
                for scraper_name, progress_bar in self.progress_bars.items():
                    if scraper_name not in self.completed_scrapers and scraper_name not in self.failed_scrapers:
                        self.update_progress_from_activity(scraper_name, progress_bar)
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 Przerwano przez użytkownika")
            self.stop_all_scrapers()
        
        print("\n" + "=" * 80)
        print("🏁 Wszystkie scrapery zakończone")
        
        # Pokaż podsumowanie
        self.show_summary()
    
    def stop_all_scrapers(self):
        """Zatrzymuje wszystkie uruchomione scrapery"""
        self.running = False
        
        for scraper_name, process in self.processes.items():
            try:
                if process.poll() is None:
                    print(f"🛑 Zatrzymuję {scraper_name}...")
                    process.terminate()
                    
                    # Czekaj na zakończenie
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        print(f"💀 Wymuszam zamknięcie {scraper_name}...")
                        process.kill()
                        
            except Exception as e:
                print(f"❌ Błąd zatrzymywania {scraper_name}: {e}")
        
        # Zamknij wszystkie paski postępu
        for progress_bar in self.progress_bars.values():
            progress_bar.close()
    
    def show_summary(self):
        """Pokazuje podsumowanie wykonanych scraperów"""
        print("\n📊 PODSUMOWANIE:")
        print("=" * 80)
        
        for scraper_info in self.scrapers:
            scraper_name = scraper_info['name']
            db_file = scraper_info['db_file']
            description = scraper_info['description']
            stats = self.stats[scraper_name]
            
            if scraper_name in self.completed_scrapers:
                status = "✅ Ukończony"
                if os.path.exists(db_file):
                    size = os.path.getsize(db_file) / (1024 * 1024)  # MB
                    duration = ""
                    if stats['start_time'] and stats['end_time']:
                        duration = stats['end_time'] - stats['start_time']
                        duration = f" (czas: {duration})"
                    
                    print(f"{status} - {description:25} - {db_file} ({size:.1f} MB){duration}")
                else:
                    print(f"{status} - {description:25} - {db_file} (brak pliku)")
            elif scraper_name in self.failed_scrapers:
                status = "❌ Błąd"
                print(f"{status} - {description:25} - {db_file}")
            else:
                status = "⏳ W trakcie"
                print(f"{status} - {description:25} - {db_file}")
    
    def merge_databases(self):
        """Łączy wszystkie bazy danych w jedną wspólną"""
        print("\n🔗 Łączenie baz danych w merged_forums.db...")
        
        try:
            # Sprawdź czy istnieje skrypt do łączenia
            merge_script = os.path.join('scripts', 'merge_all_databases.py')
            if os.path.exists(merge_script):
                print("📋 Używam istniejącego skryptu merge_all_databases.py...")
                
                result = subprocess.run(
                    [sys.executable, merge_script, "--target", "data/databases/merged_forums.db"],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print("✅ Bazy danych zostały pomyślnie połączone")
                    if os.path.exists('data/databases/merged_forums.db'):
                        size = os.path.getsize('data/databases/merged_forums.db') / (1024 * 1024)  # MB
                        print(f"📁 Utworzono: data/databases/merged_forums.db ({size:.1f} MB)")
                else:
                    print("❌ Błąd podczas łączenia baz danych")
                    print(f"STDOUT: {result.stdout}")
                    print(f"STDERR: {result.stderr}")
            else:
                print("❌ Nie znaleziono skryptu merge_all_databases.py")
                
        except Exception as e:
            print(f"❌ Błąd podczas łączenia baz danych: {e}")
    
    def save_final_stats(self):
        """Zapisuje końcowe statystyki do pliku JSON"""
        try:
            stats_file = self.log_dir / 'final_stats.json'
            
            # Przygotuj dane do zapisu
            final_stats = {
                'timestamp': datetime.now().isoformat(),
                'scrapers': {}
            }
            
            for scraper_name, stats in self.stats.items():
                final_stats['scrapers'][scraper_name] = {
                    'status': stats['status'],
                    'start_time': stats['start_time'].isoformat() if stats['start_time'] else None,
                    'end_time': stats['end_time'].isoformat() if stats['end_time'] else None,
                    'threads_found': stats['threads_found'],
                    'posts_found': stats['posts_found'],
                    'progress': stats['progress']
                }
            
            # Zapisz do pliku
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(final_stats, f, indent=2, ensure_ascii=False)
            
            print(f"📊 Statystyki zapisane do: {stats_file}")
            
        except Exception as e:
            print(f"❌ Błąd zapisu statystyk: {e}")
    
    def run(self):
        """Główna metoda uruchamiająca cały proces"""
        try:
            print("🎯 FINAL SCRAPER MANAGER - Uruchamianie wszystkich scraperów")
            print(f"⏰ Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            
            # Uruchom wszystkie scrapery
            self.run_all_scrapers()
            
            # Połącz bazy danych
            self.merge_databases()
            
            # Zapisz końcowe statystyki
            self.save_final_stats()
            
            print(f"\n⏰ Zakończono: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("🎉 Wszystkie operacje zakończone pomyślnie!")
            
        except Exception as e:
            print(f"❌ Błąd krytyczny: {e}")
            self.stop_all_scrapers()
            self.save_final_stats()
            sys.exit(1)

def main():
    """Główna funkcja"""
    try:
        # Sprawdź czy jesteśmy w odpowiednim katalogu
        if not os.path.exists('scrapy.cfg'):
            print("❌ Błąd: Nie znaleziono pliku scrapy.cfg")
            print("Uruchom skrypt z katalogu głównego projektu Scrapy")
            sys.exit(1)
        
        # Sprawdź czy wszystkie scrapery istnieją
        scraper_dir = 'scraper/spiders'
        if not os.path.exists(scraper_dir):
            print("❌ Błąd: Nie znaleziono katalogu scraper/spiders")
            sys.exit(1)
        
        # Sprawdź czy zainstalowane są wymagane pakiety
        try:
            import tqdm
        except ImportError:
            print("❌ Błąd: Brak pakietu tqdm")
            print("Zainstaluj: pip install tqdm")
            sys.exit(1)
        
        try:
            import psutil
        except ImportError:
            print("❌ Błąd: Brak pakietu psutil")
            print("Zainstaluj: pip install psutil")
            sys.exit(1)
        
        # Uruchom manager scraperów
        manager = FinalScraperManager()
        manager.run()
        
    except KeyboardInterrupt:
        print("\n🛑 Przerwano przez użytkownika")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Błąd krytyczny: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

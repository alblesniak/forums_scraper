#!/usr/bin/env python3
"""
Interfejs wiersza poleceń dla analizy tokenów
Wspiera multiprocessing, tqdm i wybór forów
"""

import os
import sys
import argparse
import time
from pathlib import Path
from typing import List, Optional

# Dodaj ścieżkę do modułu analizy
sys.path.append(str(Path(__file__).parent))

from tokenization import TokenAnalyzer
from config import get_config

class AnalysisCLI:
    """Interfejs wiersza poleceń dla analizy"""
    
    def __init__(self):
        self.config = get_config()
        self.analyzer = None
    
    def setup_analyzer(self, source_db: str, analysis_db: str, forums: List[str] = None):
        """Konfiguruje analizator"""
        try:
            if forums is None:
                forums = self.config['forums_to_analyze']
            
            self.analyzer = TokenAnalyzer(
                source_db=source_db,
                analysis_db=analysis_db,
                forums_to_analyze=forums
            )
            
            print(f"✅ Analizator skonfigurowany")
            print(f"   📍 Baza źródłowa: {source_db}")
            print(f"   📍 Baza analizy: {analysis_db}")
            print(f"   🎯 Fora do analizy: {', '.join(forums)}")
            print(f"   ⚡ Multiprocessing: {'Włączone' if self.config['multiprocessing']['use_multiprocessing'] else 'Wyłączone'}")
            print(f"   🔧 Liczba procesów: {self.config['multiprocessing']['max_workers']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Błąd konfiguracji analizatora: {e}")
            return False
    
    def create_database(self) -> bool:
        """Tworzy bazę analizy"""
        try:
            print("🏗️  Tworzenie bazy analizy...")
            
            if self.analyzer.create_analysis_database():
                print("✅ Baza analizy utworzona pomyślnie")
                return True
            else:
                print("❌ Błąd tworzenia bazy analizy")
                return False
                
        except Exception as e:
            print(f"❌ Błąd tworzenia bazy: {e}")
            return False
    
    def show_forums_info(self):
        """Pokazuje informacje o forach"""
        try:
            if not self.analyzer:
                print("❌ Analizator nie jest skonfigurowany")
                return False
            
            print("📊 INFORMACJE O FORACH")
            print("=" * 50)
            
            forums_info = self.analyzer.get_forums_info()
            
            for forum in forums_info['forums']:
                print(f"🎯 {forum['name']}")
                print(f"   📝 Wszystkie posty: {forum['total_posts']:,}")
                print(f"   🔍 Przeanalizowane: {forum['analyzed_posts']:,}")
                print(f"   📈 Postęp: {forum['progress']:.1f}%")
                print()
            
            return True
            
        except Exception as e:
            print(f"❌ Błąd pobierania informacji o forach: {e}")
            return False
    
    def analyze_single_batch(self, batch_size: int) -> bool:
        """Analizuje pojedynczą partię postów"""
        try:
            if not self.analyzer:
                print("❌ Analizator nie jest skonfigurowany")
                return False
            
            print(f"📦 Analiza partii {batch_size} postów...")
            
            start_time = time.time()
            processed = self.analyzer.process_batch(batch_size)
            elapsed = time.time() - start_time
            
            if processed > 0:
                print(f"✅ Przetworzono {processed} postów w {elapsed:.2f}s")
                print(f"   ⚡ Wydajność: {processed/elapsed:.1f} postów/s")
            else:
                print("ℹ️  Brak postów do analizy")
            
            return True
            
        except Exception as e:
            print(f"❌ Błąd analizy partii: {e}")
            return False
    
    def analyze_all_posts(self, show_progress: bool = True) -> bool:
        """Analizuje wszystkie posty z określonych forów"""
        try:
            if not self.analyzer:
                print("❌ Analizator nie jest skonfigurowany")
                return False
            
            print("🚀 Rozpoczynam analizę wszystkich postów...")
            
            start_time = time.time()
            result = self.analyzer.analyze_all_forums_posts(show_progress=show_progress)
            elapsed = time.time() - start_time
            
            if 'error' not in result:
                print(f"\n✅ Analiza zakończona!")
                print(f"   📝 Przeanalizowane posty: {result['total_analyzed']:,}")
                print(f"   🎯 Wszystkie posty: {result['total_posts']:,}")
                print(f"   ⏱️  Czas wykonania: {elapsed:.2f}s")
                print(f"   ⚡ Średnia wydajność: {result['total_analyzed']/elapsed:.1f} postów/s")
                print(f"   🎯 Fora: {', '.join(result['forums_analyzed'])}")
                return True
            else:
                print(f"❌ Błąd analizy: {result['error']}")
                return False
                
        except Exception as e:
            print(f"❌ Błąd analizy wszystkich postów: {e}")
            return False
    
    def show_summary(self):
        """Pokazuje podsumowanie analizy"""
        try:
            if not self.analyzer:
                print("❌ Analizator nie jest skonfigurowany")
                return False
            
            print("📊 PODSUMOWANIE ANALIZY")
            print("=" * 50)
            
            summary = self.analyzer.get_analysis_summary()
            
            if summary:
                print(f"📝 Wszystkie posty: {summary['total_posts']:,}")
                print(f"🔍 Przeanalizowane: {summary['total_analyzed']:,}")
                print(f"📈 Postęp: {summary['analysis_progress']:.1f}%")
                print(f"🔢 Łączna liczba tokenów: {summary['total_tokens']:,}")
                print(f"📝 Łączna liczba słów: {summary['total_words']:,}")
                
                # Statystyki dzienne
                if summary['daily_stats']:
                    print(f"\n📅 Statystyki dzienne:")
                    for day in summary['daily_stats'][:5]:  # Pokaż ostatnie 5 dni
                        print(f"   📅 {day['date']}: {day['posts_analyzed']} postów, {day['total_tokens']:,} tokenów")
                
                # Statystyki pamięci
                if 'memory_stats' in summary:
                    mem_stats = summary['memory_stats']
                    print(f"\n💾 Statystyki pamięci:")
                    print(f"   🔍 Posty przeanalizowane: {mem_stats.get('total_posts_analyzed', 0):,}")
                    print(f"   ❌ Błędy przetwarzania: {mem_stats.get('processing_errors', 0)}")
                    print(f"   🤖 Tokeny spaCy: {mem_stats.get('spacy_tokens', 0):,}")
                    print(f"   🔢 Tokeny proste: {mem_stats.get('simple_tokens', 0):,}")
                
                return True
            else:
                print("❌ Nie udało się pobrać podsumowania")
                return False
                
        except Exception as e:
            print(f"❌ Błąd pobierania podsumowania: {e}")
            return False
    
    def run_continuous_analysis(self, interval: int, batch_size: int):
        """Uruchamia ciągłą analizę"""
        try:
            if not self.analyzer:
                print("❌ Analizator nie jest skonfigurowany")
                return False
            
            print(f"🔄 Uruchamiam ciągłą analizę (interwał: {interval}s, partia: {batch_size})")
            print("   Naciśnij Ctrl+C aby zatrzymać")
            
            self.analyzer.start_continuous_analysis(interval, batch_size)
            
        except KeyboardInterrupt:
            print("\n🛑 Zatrzymano analizę (Ctrl+C)")
            if self.analyzer:
                self.analyzer.stop_continuous_analysis()
        except Exception as e:
            print(f"❌ Błąd ciągłej analizy: {e}")

def main():
    """Główna funkcja CLI"""
    parser = argparse.ArgumentParser(
        description="Analiza tokenów dla postów forum z multiprocessing i tqdm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:
  python cli.py --create-db                    # Utwórz bazę analizy
  python cli.py --info                         # Pokaż informacje o forach
  python cli.py --batch 100                    # Analizuj partię 100 postów
  python cli.py --all                          # Analizuj wszystkie posty
  python cli.py --continuous --interval 300    # Ciągła analiza co 5 minut
  python cli.py --summary                      # Pokaż podsumowanie
  python cli.py --forums radio_katolik,wiara   # Wybierz fora do analizy
        """
    )
    
    # Opcje bazy danych
    parser.add_argument("--source-db", default="../data/databases/merged_forums.db",
                       help="Ścieżka do źródłowej bazy danych")
    parser.add_argument("--analysis-db", default="../data/databases/analysis_forums.db",
                       help="Ścieżka do bazy analizy")
    
    # Opcje forów
    parser.add_argument("--forums", 
                       help="Lista forów do analizy (oddzielone przecinkami)")
    
    # Opcje multiprocessing
    parser.add_argument("--no-multiprocessing", action="store_true",
                       help="Wyłącz multiprocessing")
    parser.add_argument("--workers", type=int,
                       help="Liczba procesów roboczych")
    parser.add_argument("--chunk-size", type=int,
                       help="Rozmiar chunka dla multiprocessing")
    
    # Akcje
    parser.add_argument("--create-db", action="store_true",
                       help="Utwórz bazę analizy")
    parser.add_argument("--info", action="store_true",
                       help="Pokaż informacje o forach")
    parser.add_argument("--batch", type=int, metavar="SIZE",
                       help="Analizuj partię postów o określonym rozmiarze")
    parser.add_argument("--all", action="store_true",
                       help="Analizuj wszystkie posty z określonych forów")
    parser.add_argument("--continuous", action="store_true",
                       help="Uruchom ciągłą analizę")
    parser.add_argument("--summary", action="store_true",
                       help="Pokaż podsumowanie analizy")
    
    # Opcje ciągłej analizy
    parser.add_argument("--interval", type=int, default=300,
                       help="Interwał dla ciągłej analizy w sekundach")
    parser.add_argument("--batch-size", type=int, default=100,
                       help="Rozmiar partii dla analizy")
    
    # Opcje wyświetlania
    parser.add_argument("--no-progress", action="store_true",
                       help="Wyłącz paski postępu")
    
    args = parser.parse_args()
    
    # Sprawdź czy podano akcję
    if not any([args.create_db, args.info, args.batch, args.all, args.continuous, args.summary]):
        parser.print_help()
        return False
    
    # Utwórz CLI
    cli = AnalysisCLI()
    
    # Konfiguruj multiprocessing jeśli podano
    if args.no_multiprocessing:
        cli.config['multiprocessing']['use_multiprocessing'] = False
    
    if args.workers:
        cli.config['multiprocessing']['max_workers'] = args.workers
    
    if args.chunk_size:
        cli.config['multiprocessing']['chunk_size'] = args.chunk_size
    
    # Parsuj fora
    forums = None
    if args.forums:
        forums = [f.strip() for f in args.forums.split(',')]
    
    # Konfiguruj analizator
    if not cli.setup_analyzer(args.source_db, args.analysis_db, forums):
        return False
    
    # Wykonaj akcje
    success = True
    
    if args.create_db:
        success &= cli.create_database()
    
    if args.info:
        success &= cli.show_forums_info()
    
    if args.batch:
        success &= cli.analyze_single_batch(args.batch)
    
    if args.all:
        success &= cli.analyze_all_posts(show_progress=not args.no_progress)
    
    if args.summary:
        success &= cli.show_summary()
    
    if args.continuous:
        cli.run_continuous_analysis(args.interval, args.batch_size)
    
    return success

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Przerwano przez użytkownika")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Błąd krytyczny: {e}")
        sys.exit(1)

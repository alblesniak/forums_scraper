#!/usr/bin/env python3
"""
Raport domen z kolumny content_urls w merged_forums.db

Funkcjonalność:
- wczytuje wszystkie wpisy z forum_posts dla wskazanych forów (po spider_name)
- parsuje JSON z kolumny content_urls (lista URL-i)
- ekstrahuje domeny (netloc), normalizuje (lowercase, bez wiodącego 'www.')
- zlicza częstotliwości i drukuje ranking
- opcjonalnie zapisuje wynik do CSV w katalogu data/reports

Domyślne forum: radio_katolik
"""

from __future__ import annotations

import os
import csv
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse


def _normalize_domain(raw_url: str) -> Optional[str]:
    """Zwraca znormalizowaną domenę (netloc) lub None dla nieprawidłowego URL.

    Normalizacja:
    - lowercase
    - usuń wiodące 'www.'
    - usuń trailing kropki
    """
    if not raw_url or not isinstance(raw_url, str):
        return None
    try:
        parsed = urlparse(raw_url.strip())
        netloc = parsed.netloc or ""
        if not netloc and parsed.path and "://" not in raw_url:
            # próba parsowania bez schematu – dodaj https
            parsed = urlparse("https://" + raw_url.strip())
            netloc = parsed.netloc or ""
        if not netloc:
            return None
        netloc = netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        while netloc.endswith("."):
            netloc = netloc[:-1]
        return netloc or None
    except Exception:
        return None


def _iter_content_urls(rows: Iterable[Tuple[str]]) -> Iterable[str]:
    """Iterator po wszystkich URL-ach z JSON-ów content_urls (tekstowych kolumn).

    Każdy wiersz to: (content_urls_json,)
    """
    for (content_urls_json,) in rows:
        if not content_urls_json:
            continue
        try:
            if content_urls_json.strip().startswith("["):
                data = json.loads(content_urls_json)
                if isinstance(data, list):
                    for url in data:
                        if isinstance(url, str):
                            yield url
            else:
                # fallback: pojedyńczy URL jako tekst
                yield content_urls_json
        except Exception:
            # ignoranćja uszkodzonych JSON-ów
            continue


def generate_domain_frequency_report(
    database_path: str,
    forums: Optional[List[str]] = None,
) -> Dict[str, int]:
    """Generuje mapę domena -> liczba wystąpień dla wskazanych forów.

    forums: lista nazw spiderów (np. ["radio_katolik"]). Gdy None lub pusta – wszystkie fora.
    """
    db_path = Path(database_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Nie znaleziono bazy: {database_path}")

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Zbuduj zapytanie z joinami, aby filtrować po forums.spider_name
    base_sql = (
        "SELECT fp.content_urls "
        "FROM forum_posts fp "
        "JOIN forum_threads ft ON fp.thread_id = ft.id "
        "JOIN forum_sections fs ON ft.section_id = fs.id "
        "JOIN forums f ON fs.forum_id = f.id "
        "WHERE fp.content_urls IS NOT NULL AND TRIM(fp.content_urls) <> '[]'"
    )

    params: List[str] = []
    if forums:
        placeholders = ",".join(["?"] * len(forums))
        sql = base_sql + f" AND f.spider_name IN ({placeholders})"
        params = forums
    else:
        sql = base_sql

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    # Zlicz domeny
    freq: Dict[str, int] = {}
    for url in _iter_content_urls(rows):
        domain = _normalize_domain(url)
        if not domain:
            continue
        freq[domain] = freq.get(domain, 0) + 1

    return freq


def save_report_csv(freq: Dict[str, int], output_dir: str, forums: Optional[List[str]]) -> str:
    """Zapisuje raport do CSV i zwraca ścieżkę do pliku."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    forum_tag = "ALL" if not forums else "+".join(forums)
    csv_path = out_dir / f"domains_{forum_tag}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["domain", "count"])
        for domain, count in sorted(freq.items(), key=lambda kv: kv[1], reverse=True):
            writer.writerow([domain, count])
    return str(csv_path)


def cli_report(database_path: str, forums: Optional[List[str]] = None, output_dir: Optional[str] = None) -> Dict[str, str]:
    """Wygodna funkcja CLI: liczy, drukuje top i (opcjonalnie) zapisuje CSV.

    Zwraca: dict z kluczami 'saved_csv' (gdy zapisano) i 'total_domains'.
    """
    freq = generate_domain_frequency_report(database_path=database_path, forums=forums)

    # Drukuj krótkie podsumowanie
    total_urls = sum(freq.values())
    print("\n=== Raport domen (content_urls) ===")
    print(f"Fora: {', '.join(forums) if forums else 'ALL'}")
    print(f"Unikalnych domen: {len(freq)}; Łącznie URL-i: {total_urls}")
    print("Top 30:")
    for i, (domain, count) in enumerate(sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:30], start=1):
        print(f"{i:2d}. {domain:40s} {count}")

    saved_csv = None
    if output_dir:
        saved_csv = save_report_csv(freq=freq, output_dir=output_dir, forums=forums)
        print(f"\n✓ Zapisano CSV: {saved_csv}")

    return {"saved_csv": saved_csv or "", "total_domains": str(len(freq))}


if __name__ == "__main__":
    # Prosty tryb standalone: użyj zmiennych środowiskowych albo domyślnych ścieżek
    root = Path(__file__).resolve().parents[1]
    db_default = root / "data/databases/merged_forums.db"
    forums_env = os.environ.get("DOMAINS_FORUMS", "radio_katolik").strip()
    forums_list = [f.strip() for f in forums_env.split(',') if f.strip()] if forums_env else None
    out_dir = os.environ.get("DOMAINS_OUTPUT_DIR", str(root / "data/reports"))
    cli_report(database_path=str(db_default), forums=forums_list, output_dir=out_dir)



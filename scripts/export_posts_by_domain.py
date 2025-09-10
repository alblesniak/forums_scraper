#!/usr/bin/env python3
"""
Eksportuje treści postów, które zawierają URL-e z danej domeny (kolumna forum_posts.content_urls).

Domyślnie:
- forum: radio_katolik
- domena: spowiedz.katolik.pl

Wynik:
- wypisanie krótkiego podsumowania i kilku pierwszych postów w stdout
- pełny eksport do JSON w data/reports (można nadpisać ścieżkę)
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse


def _normalize_domain(value: str) -> str:
    v = (value or "").strip().lower()
    if v.startswith("www."):
        v = v[4:]
    while v.endswith("."):
        v = v[:-1]
    return v


def _url_domain(url: str) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    try:
        p = urlparse(url.strip())
        netloc = p.netloc
        if not netloc and "://" not in url:
            p = urlparse("https://" + url.strip())
            netloc = p.netloc
        if not netloc:
            return None
        return _normalize_domain(netloc)
    except Exception:
        return None


def _iter_rows_with_urls(cur: sqlite3.Cursor, forums: Optional[List[str]]) -> Iterable[Tuple]:
    base_sql = (
        "SELECT fp.id, fp.content, fp.url, fp.post_date, fp.username, fp.content_urls, "
        "ft.title AS thread_title, ft.url AS thread_url, fs.title AS section_title, f.spider_name "
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
    yield from cur.fetchall()


def _row_matches_domain(content_urls_json: str, domain: str) -> Tuple[bool, List[str]]:
    matched_urls: List[str] = []
    if not content_urls_json:
        return False, matched_urls
    try:
        if content_urls_json.strip().startswith("["):
            data = json.loads(content_urls_json)
            if isinstance(data, list):
                for u in data:
                    if not isinstance(u, str):
                        continue
                    d = _url_domain(u)
                    if d == domain or (d and d.endswith("." + domain)):
                        matched_urls.append(u)
        else:
            # pojedynczy string
            d = _url_domain(content_urls_json)
            if d == domain or (d and d.endswith("." + domain)):
                matched_urls.append(content_urls_json)
    except Exception:
        return False, matched_urls
    return (len(matched_urls) > 0), matched_urls


def export_posts_by_domain(
    database_path: str,
    domain: str,
    forums: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    preview: int = 5,
) -> Dict[str, str]:
    db_path = Path(database_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Nie znaleziono bazy: {database_path}")

    domain_norm = _normalize_domain(domain)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    rows = _iter_rows_with_urls(cur, forums)

    results: List[Dict[str, str]] = []
    for row in rows:
        post_id, content, post_url, post_date, username, content_urls_json, thread_title, thread_url, section_title, spider_name = row
        ok, matched_urls = _row_matches_domain(content_urls_json, domain_norm)
        if not ok:
            continue
        results.append({
            "post_id": str(post_id),
            "forum": spider_name or "",
            "post_url": post_url or "",
            "post_date": post_date or "",
            "username": username or "",
            "thread_title": thread_title or "",
            "thread_url": thread_url or "",
            "section_title": section_title or "",
            "matched_urls": " | ".join(matched_urls),
            "content": content or "",
        })

    conn.close()

    # Podsumowanie + podgląd
    print("\n=== Posty z URL-ami domeny ===")
    print(f"Domena: {domain_norm}")
    print(f"Fora: {', '.join(forums) if forums else 'ALL'}")
    print(f"Liczba postów: {len(results)}")
    print("\nPodgląd (pierwsze wpisy):")
    for i, r in enumerate(results[:max(0, preview)]):
        print("-" * 80)
        print(f"[{i+1}] {r['forum']} | {r['post_date']} | {r['username']}")
        print(f"Wątek: {r['thread_title']}")
        print(f"URL postu: {r['post_url']}")
        print(f"Dopasowane URL-e: {r['matched_urls']}")
        print("Treść:")
        print(r.get("content", ""))

    saved_json = ""
    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        forum_tag = "ALL" if not forums else "+".join(forums)
        fname = f"posts_by_domain__{domain_norm}__{forum_tag}.json"
        json_path = out_dir / fname
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        saved_json = str(json_path)
        print(f"\n✓ Zapisano JSON: {saved_json}")

    return {"count": str(len(results)), "saved_json": saved_json}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    db_default = root / "data/databases/merged_forums.db"
    domain = os.environ.get("DOMAIN", "spowiedz.katolik.pl")
    forums_env = os.environ.get("DOMAIN_FORUMS", "radio_katolik").strip()
    forums_list = [f.strip() for f in forums_env.split(',') if f.strip()] if forums_env else None
    out_dir = os.environ.get("DOMAIN_OUTPUT_DIR", str(root / "data/reports"))
    export_posts_by_domain(
        database_path=str(db_default), domain=domain, forums=forums_list, output_dir=out_dir, preview=5
    )



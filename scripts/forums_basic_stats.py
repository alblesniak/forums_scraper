#!/usr/bin/env python3
import csv
import os
import sqlite3
from typing import List, Tuple


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DB_PATH = os.path.join(REPO_ROOT, "data", "databases", "merged_forums.db")
OUTPUT_CSV = os.path.join(REPO_ROOT, "data", "forums_basic_stats.csv")


def fetch_forum_stats(conn: sqlite3.Connection) -> List[Tuple]:
    query = r"""
    WITH
    posts AS (
      SELECT f.id AS forum_id, COUNT(p.id) AS posts_count
      FROM forums f
      LEFT JOIN forum_sections s ON s.forum_id = f.id
      LEFT JOIN forum_threads t ON t.section_id = s.id
      LEFT JOIN forum_posts p ON p.thread_id = t.id
      GROUP BY f.id
    ),
    users AS (
      SELECT f.id AS forum_id, COUNT(u.id) AS users_count
      FROM forums f
      LEFT JOIN forum_users u ON u.forum_id = f.spider_name
      GROUP BY f.id
    ),
    tokens AS (
      SELECT f.id AS forum_id, COALESCE(SUM(ta.token_count), 0) AS total_tokens
      FROM forums f
      LEFT JOIN forum_sections s ON s.forum_id = f.id
      LEFT JOIN forum_threads t ON t.section_id = s.id
      LEFT JOIN forum_posts p ON p.thread_id = t.id
      LEFT JOIN token_analysis ta ON ta.post_id = p.id
      GROUP BY f.id
    ),
    years AS (
      SELECT f.id AS forum_id,
             MIN(COALESCE(strftime('%Y', p.post_date), substr(p.post_date, 1, 4))) AS year_min,
             MAX(COALESCE(strftime('%Y', p.post_date), substr(p.post_date, 1, 4))) AS year_max
      FROM forums f
      LEFT JOIN forum_sections s ON s.forum_id = f.id
      LEFT JOIN forum_threads t ON t.section_id = s.id
      LEFT JOIN forum_posts p ON p.thread_id = t.id
      WHERE p.post_date IS NOT NULL AND p.post_date <> ''
      GROUP BY f.id
    )
    SELECT f.title AS forum,
           COALESCE(posts.posts_count, 0) AS posts_count,
           COALESCE(users.users_count, 0) AS users_count,
           COALESCE(tokens.total_tokens, 0) AS total_tokens,
           years.year_min AS year_from,
           years.year_max AS year_to
    FROM forums f
    LEFT JOIN posts  ON posts.forum_id  = f.id
    LEFT JOIN users  ON users.forum_id  = f.id
    LEFT JOIN tokens ON tokens.forum_id = f.id
    LEFT JOIN years  ON years.forum_id  = f.id
    ORDER BY f.id
    ;
    """

    cur = conn.cursor()
    cur.execute(query)
    return cur.fetchall()


def write_csv(rows: List[Tuple], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    headers = [
        "forum",
        "posts_count",
        "users_count",
        "total_tokens",
        "year_from",
        "year_to",
    ]
    with open(output_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


def main() -> None:
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"Nie znaleziono bazy danych: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = fetch_forum_stats(conn)
    finally:
        conn.close()

    write_csv(rows, OUTPUT_CSV)
    print(f"Zapisano statystyki do: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()



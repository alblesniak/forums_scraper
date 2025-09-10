#!/usr/bin/env python3
import csv
import os
import sqlite3
from typing import Dict, List, Tuple


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DB_PATH = os.path.join(REPO_ROOT, "data", "databases", "merged_forums.db")
OUTPUT_DATA_DIR = os.path.join(REPO_ROOT, "data")
OUTPUT_PRESENTATION_DIR = os.path.join(REPO_ROOT, "presentation", "data")
FILENAME = "yearly_posts_stats.csv"


def fetch_yearly_posts(conn: sqlite3.Connection) -> List[Tuple[int, str, str, int]]:
    query = r"""
    WITH yearly AS (
      SELECT
        f.id AS forum_id,
        f.title AS forum_title,
        COALESCE(strftime('%Y', p.post_date), substr(p.post_date, 1, 4)) AS year,
        COUNT(p.id) AS posts_count
      FROM forums f
      LEFT JOIN forum_sections s ON s.forum_id = f.id
      LEFT JOIN forum_threads t ON t.section_id = s.id
      LEFT JOIN forum_posts p ON p.thread_id = t.id
      WHERE p.post_date IS NOT NULL AND p.post_date <> ''
      GROUP BY f.id, f.title, year
    )
    SELECT forum_id, forum_title, year, posts_count
    FROM yearly
    ORDER BY forum_id, year
    ;
    """

    cur = conn.cursor()
    cur.execute(query)
    return cur.fetchall()


def build_wide_table(rows: List[Tuple[int, str, str, int]]) -> Tuple[List[str], List[List[object]]]:
    years: List[str] = []
    forum_order: List[Tuple[int, str]] = []  # (forum_id, forum_title)
    seen_forums: Dict[int, str] = {}
    data: Dict[str, Dict[str, int]] = {}

    for forum_id, forum_title, year, posts_count in rows:
        if year is None or year == "":
            continue
        if year not in data:
            data[year] = {}
            years.append(year)
        if forum_id not in seen_forums:
            seen_forums[forum_id] = forum_title
            forum_order.append((forum_id, forum_title))
        data[year][forum_title] = posts_count

    years = sorted(set(years), key=lambda y: int(y))
    forum_order = sorted(forum_order, key=lambda it: it[0])

    headers = ["year"] + [title for _, title in forum_order] + ["avg_all"]
    wide_rows: List[List[object]] = []

    for year in years:
        row_vals: List[object] = [year]
        counts_for_avg: List[int] = []
        for _, title in forum_order:
            count = int(data.get(year, {}).get(title, 0))
            row_vals.append(count)
            if count > 0:
                counts_for_avg.append(count)
        avg_all = round(sum(counts_for_avg) / len(counts_for_avg), 2) if counts_for_avg else 0
        row_vals.append(avg_all)
        wide_rows.append(row_vals)

    return headers, wide_rows


def write_csv(headers: List[str], rows: List[List[object]], out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, FILENAME)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)
    return out_path


def main() -> None:
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"Nie znaleziono bazy danych: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = fetch_yearly_posts(conn)
    finally:
        conn.close()

    headers, wide_rows = build_wide_table(rows)

    data_out = write_csv(headers, wide_rows, OUTPUT_DATA_DIR)
    presentation_out = write_csv(headers, wide_rows, OUTPUT_PRESENTATION_DIR)

    print("Zapisano:")
    print(f"- {data_out}")
    print(f"- {presentation_out}")


if __name__ == "__main__":
    main()



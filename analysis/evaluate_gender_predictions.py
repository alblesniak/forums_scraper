#!/usr/bin/env python3
"""
Ewaluacja predykcji płci na bazie SQLite.

Łączy `forum_users.gender` (ground truth) z `gender_predictions.predicted_gender`
i liczy accuracy oraz precision/recall/F1 (per klasa i macro).

Przykład:
  python analysis/evaluate_gender_predictions.py \
    --db data/databases/merged_forums.db \
    --method rules_v1 \
    --per-forum
"""

import argparse
import sqlite3
from typing import Dict, List, Tuple, Optional


def _fetch_rows(conn: sqlite3.Connection, method: str, forums: Optional[List[str]]) -> List[Tuple[str, str, Optional[str]]]:
    """
    Zwraca listę (true_gender, pred_gender, forum_id?) dla użytkowników z etykietą i predykcją.
    """
    cur = conn.cursor()

    forum_filter = ""
    params: List = [method]
    if forums:
        placeholders = ",".join(["?"] * len(forums))
        forum_filter = f" AND u.forum_id IN ({placeholders})"
        params.extend(forums)

    # Ensure column forum_id exists; if not, still return None for forum
    has_forum_id = False
    try:
        cur.execute("PRAGMA table_info(forum_users)")
        cols = [row[1] for row in cur.fetchall()]
        has_forum_id = "forum_id" in cols
    except Exception:
        has_forum_id = False

    select_forum = "u.forum_id" if has_forum_id else "NULL"

    sql = f"""
        SELECT u.gender AS true_gender,
               gp.predicted_gender AS pred_gender,
               {select_forum} AS forum_id
        FROM forum_users u
        JOIN gender_predictions gp ON gp.user_id = u.id AND gp.method = ?
        WHERE u.gender IN ('M','K')
        {forum_filter}
    """
    cur.execute(sql, params)
    return cur.fetchall()


def _metrics(p: int, r_: int, n: int, true_pos_label: str, rows: List[Tuple[str, str, Optional[str]]]) -> Dict[str, float]:
    """
    Oblicza accuracy, precision, recall, f1; parametry:
    - p: liczba pozytywnych (dla danej etykiety)
    - r_: liczba predykowanych pozytywnych (dla danej etykiety)
    - n: liczba wszystkich przykładów
    """
    # Wylicz confusion dla danej etykiety jako pozytywnej
    tp = sum(1 for t, y, _ in rows if t == true_pos_label and y == true_pos_label)
    fp = sum(1 for t, y, _ in rows if t != true_pos_label and y == true_pos_label)
    fn = sum(1 for t, y, _ in rows if t == true_pos_label and y != true_pos_label)
    tn = n - tp - fp - fn

    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0

    return {
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'accuracy': accuracy, 'precision': precision, 'recall': recall, 'f1': f1,
    }


def evaluate(conn: sqlite3.Connection, method: str, forums: Optional[List[str]], per_forum: bool) -> None:
    rows = _fetch_rows(conn, method=method, forums=forums)
    if not rows:
        print("Brak danych do ewaluacji (czy są predykcje i etykiety?)")
        return

    def report(rows_subset: List[Tuple[str, str, Optional[str]]], title: str) -> None:
        n = len(rows_subset)
        correct = sum(1 for t, y, _ in rows_subset if t == y)
        accuracy = correct / n if n else 0.0

        # Statystyki klasowe
        count_true_K = sum(1 for t, _, _ in rows_subset if t == 'K')
        count_true_M = sum(1 for t, _, _ in rows_subset if t == 'M')
        count_pred_K = sum(1 for _, y, _ in rows_subset if y == 'K')
        count_pred_M = sum(1 for _, y, _ in rows_subset if y == 'M')

        metr_K = _metrics(count_true_K, count_pred_K, n, 'K', rows_subset)
        metr_M = _metrics(count_true_M, count_pred_M, n, 'M', rows_subset)
        macro_f1 = (metr_K['f1'] + metr_M['f1']) / 2

        print(f"\n=== Ewaluacja: {title} ===")
        print(f"Przykładów (z etykietą i predykcją): {n}")
        print(f"Accuracy: {accuracy:.4f}")
        print(f"F1 (K):   {metr_K['f1']:.4f}  | P: {metr_K['precision']:.4f}  R: {metr_K['recall']:.4f}")
        print(f"F1 (M):   {metr_M['f1']:.4f}  | P: {metr_M['precision']:.4f}  R: {metr_M['recall']:.4f}")
        print(f"F1 macro: {macro_f1:.4f}")

    if per_forum:
        # Grupuj po forum_id (może być NULL, wtedy jedna grupa)
        by_forum: Dict[Optional[str], List[Tuple[str, str, Optional[str]]]] = {}
        for t, y, f in rows:
            by_forum.setdefault(f, []).append((t, y, f))
        for forum_id, group in sorted(by_forum.items(), key=lambda x: (str(x[0]) if x[0] is not None else "")):
            report(group, title=f"forum_id={forum_id}")
        # Całość
        report(rows, title="SUMA (wszystkie fora)")
    else:
        report(rows, title="SUMA (wszystkie fora)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ewaluacja predykcji płci względem forum_users.gender")
    parser.add_argument("--db", required=True, help="Ścieżka do bazy SQLite (merged_forums.db lub analysis_forums.db)")
    parser.add_argument("--method", default="rules_v1", help="Metoda w gender_predictions (domyślnie: rules_v1)")
    parser.add_argument("--forums", help="Lista forów (forum_id) oddzielona przecinkami")
    parser.add_argument("--per-forum", action="store_true", help="Raport per forum")
    args = parser.parse_args()

    forums = None
    if args.forums:
        forums = [f.strip() for f in args.forums.split(',') if f.strip()]

    conn = sqlite3.connect(args.db)
    try:
        evaluate(conn, method=args.method, forums=forums, per_forum=args.per_forum)
    finally:
        conn.close()


if __name__ == "__main__":
    main()



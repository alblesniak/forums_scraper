#!/usr/bin/env python3
"""
Prosty, szybki predyktor płci użytkownika oparty o markery językowe (PL)
Reguły wysokiej precyzji: formy 1. os. l.poj. czasu przeszłego (-łam/-łem),
autodeskrypcje po "jestem/byłem/byłam" z przymiotnikami/rolami, sygnały pośrednie ("moja żona"/"mój mąż").

Wyniki zapisywane do tabeli `gender_predictions` w tej samej bazie (analysis_db / merged).
"""

import re
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path


def _try_import_cleaner():
    """Próbuje zaimportować cleaner HTML z modułu scraper.utils; fallback do prostego czyszczenia."""
    try:
        # Dodaj ścieżkę główną repo, aby import się powiódł niezależnie od cwd
        root = Path(__file__).resolve().parents[1]
        scraper_dir = root / 'scraper'
        import sys
        if str(scraper_dir) not in sys.path:
            sys.path.insert(0, str(scraper_dir))
        from utils import clean_post_content  # type: ignore
        return clean_post_content
    except Exception:
        def _basic_clean(text: str) -> str:
            if not text:
                return ""
            # Usuń proste znaczniki HTML i zbędne białe znaki
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            return text.strip()
        return _basic_clean


_clean_post_content = _try_import_cleaner()


class GenderRulesPredictor:
    """Predyktor płci na podstawie reguł językowych, działający na SQLite."""

    def __init__(self, database_path: str, rules_params: Optional[Dict] = None):
        self.database_path = database_path
        self.conn = None  # type: Optional[sqlite3.Connection]

        # Parametry (wagi i progi) – można nadpisać przez rules_params
        rp = rules_params or {}
        default_weights = {
            'bylam': 3,
            'bylem': 3,
            'lam_suffix': 3,
            'lem_suffix': 3,
            'no_diac': 2,
            'adj': 2,
            'role': 2,
            'relation': 2,
            'adj_negated': 1,
        }
        default_thresholds = {
            'min_total': 2,
            'min_diff': 1,
            'strong_single_diff': 1,
        }
        self.weights: Dict[str, int | float] = {**default_weights, **(rp.get('weights') or {})}
        self.thresholds: Dict[str, int | float] = {**default_thresholds, **(rp.get('thresholds') or {})}

        # Kompilacja wzorców (diakrytyka – wysoka precyzja)
        self.re_bylam = re.compile(r"\bbyłam\b", re.IGNORECASE)
        self.re_bylem = re.compile(r"\bbyłem\b", re.IGNORECASE)
        self.re_lam = re.compile(r"\b\w+łam\b", re.IGNORECASE)
        self.re_lem = re.compile(r"\b\w+łem\b", re.IGNORECASE)

        # Najczęstsze formy bez diakrytyki – kura torowana lista (niższa waga)
        female_no_diac = [
            r"\bzrobilam\b", r"\bchcialam\b", r"\bnapisalam\b", r"\bmyslalam\b",
            r"\bpracowalam\b", r"\bstudiowalam\b", r"\bposzlam\b", r"\bylam\b",
        ]
        male_no_diac = [
            r"\bzrobilem\b", r"\bchcialem\b", r"\bnapisalem\b", r"\bmyslalem\b",
            r"\bpracowalem\b", r"\bstudiowalem\b", r"\bposzedlem\b", r"\bbylem\b",
        ]
        self.re_f_no_diac = [re.compile(p, re.IGNORECASE) for p in female_no_diac]
        self.re_m_no_diac = [re.compile(p, re.IGNORECASE) for p in male_no_diac]

        # Przymiotniki po jestem/byłam/byłem/czuję się
        adj_pairs = [
            ('nowa','nowy'), ('zainteresowana','zainteresowany'), ('wdzięczna','wdzięczny'),
            ('zmęczona','zmęczony'), ('gotowa','gotowy'), ('pewna','pewny'), ('spokojna','spokojny'),
            ('samotna','samotny'), ('wierząca','wierzący'), ('szczęśliwa','szczęśliwy'), ('chora','chory'),
        ]
        adj_f = [f for f, _ in adj_pairs]
        adj_m = [m for _, m in adj_pairs]
        self.re_jestem_f = re.compile(
            r"\b(jestem|byłam|czuję się)\s+(?:bardzo\s+)?(" + '|'.join(map(re.escape, adj_f)) + r")\b",
            re.IGNORECASE,
        )
        self.re_jestem_m = re.compile(
            r"\b(jestem|byłem|czuję się)\s+(?:bardzo\s+)?(" + '|'.join(map(re.escape, adj_m)) + r")\b",
            re.IGNORECASE,
        )

        # Role / stany
        roles_f = ['kobietą','mamą','żoną','studentką','nauczycielką','pielęgniarką','katoliczką','parafianką']
        roles_m = ['mężczyzną','tatą','mężem','studentem','nauczycielem','pielęgniarzem','katolikiem','parafianinem']
        self.re_role_f = re.compile(r"\b(jestem|byłam)\s+(" + '|'.join(map(re.escape, roles_f)) + r")\b", re.IGNORECASE)
        self.re_role_m = re.compile(r"\b(jestem|byłem)\s+(" + '|'.join(map(re.escape, roles_m)) + r")\b", re.IGNORECASE)

        # Sygnały pośrednie
        self.re_zona = re.compile(r"\bmoja\s+żona\b", re.IGNORECASE)  # -> M
        self.re_maz = re.compile(r"\bmój\s+mąż\b", re.IGNORECASE)     # -> K

    def connect(self) -> None:
        self.conn = sqlite3.connect(self.database_path)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA synchronous=NORMAL')

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def ensure_tables(self) -> None:
        assert self.conn is not None
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gender_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                predicted_gender TEXT NOT NULL CHECK(predicted_gender IN ('M','K')),
                score_m REAL NOT NULL,
                score_k REAL NOT NULL,
                evidence_count INTEGER NOT NULL,
                posts_with_evidence INTEGER NOT NULL,
                method TEXT NOT NULL,
                evidence_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(user_id, method),
                FOREIGN KEY (user_id) REFERENCES forum_users(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gender_predictions_user ON gender_predictions(user_id)")
        self.conn.commit()

    # -------- Reguły ---------
    def extract_evidence(self, text: str) -> List[Dict]:
        """Zwraca listę dowodów {'gender','type','weight','span'} dla pojedynczego tekstu."""
        if not text:
            return []
        cleaned = _clean_post_content(text)
        ev: List[Dict] = []

        # -łam / -łem oraz byłam/byłem
        for m in self.re_bylam.finditer(cleaned):
            ev.append({'gender': 'K', 'type': 'bylam', 'weight': int(self.weights.get('bylam', 3)), 'span': m.group(0)})
        for m in self.re_bylem.finditer(cleaned):
            ev.append({'gender': 'M', 'type': 'bylem', 'weight': int(self.weights.get('bylem', 3)), 'span': m.group(0)})
        for m in self.re_lam.finditer(cleaned):
            ev.append({'gender': 'K', 'type': 'lam_suffix', 'weight': int(self.weights.get('lam_suffix', 3)), 'span': m.group(0)})
        for m in self.re_lem.finditer(cleaned):
            ev.append({'gender': 'M', 'type': 'lem_suffix', 'weight': int(self.weights.get('lem_suffix', 3)), 'span': m.group(0)})

        # Formy bez diakrytyki (niższa waga)
        for regex in self.re_f_no_diac:
            for m in regex.finditer(cleaned):
                ev.append({'gender': 'K', 'type': 'no_diac', 'weight': int(self.weights.get('no_diac', 2)), 'span': m.group(0)})
        for regex in self.re_m_no_diac:
            for m in regex.finditer(cleaned):
                ev.append({'gender': 'M', 'type': 'no_diac', 'weight': int(self.weights.get('no_diac', 2)), 'span': m.group(0)})

        # Jestem + ADJ
        for m in self.re_jestem_f.finditer(cleaned):
            span = m.group(0)
            weight = int(self.weights.get('adj', 2))
            if re.search(r"\bnie\s+jestem\b", span, flags=re.IGNORECASE):
                weight = int(self.weights.get('adj_negated', 1))
            ev.append({'gender': 'K', 'type': 'adj', 'weight': weight, 'span': span})
        for m in self.re_jestem_m.finditer(cleaned):
            span = m.group(0)
            weight = int(self.weights.get('adj', 2))
            if re.search(r"\bnie\s+jestem\b", span, flags=re.IGNORECASE):
                weight = int(self.weights.get('adj_negated', 1))
            ev.append({'gender': 'M', 'type': 'adj', 'weight': weight, 'span': span})

        # Role
        for m in self.re_role_f.finditer(cleaned):
            ev.append({'gender': 'K', 'type': 'role', 'weight': int(self.weights.get('role', 2)), 'span': m.group(0)})
        for m in self.re_role_m.finditer(cleaned):
            ev.append({'gender': 'M', 'type': 'role', 'weight': int(self.weights.get('role', 2)), 'span': m.group(0)})

        # Pośrednie
        for m in self.re_zona.finditer(cleaned):
            ev.append({'gender': 'M', 'type': 'relation', 'weight': int(self.weights.get('relation', 2)), 'span': m.group(0)})
        for m in self.re_maz.finditer(cleaned):
            ev.append({'gender': 'K', 'type': 'relation', 'weight': int(self.weights.get('relation', 2)), 'span': m.group(0)})

        return ev

    def aggregate_user(self, evidences_by_post: List[List[Dict]]) -> Tuple[Optional[str], Dict]:
        """Agreguje dowody dla użytkownika i zwraca (pred_gender, stats)."""
        sum_k = 0
        sum_m = 0
        evidence_count = 0
        posts_with_evidence = 0
        sample = []
        for ev_list in evidences_by_post:
            if not ev_list:
                continue
            posts_with_evidence += 1
            for ev in ev_list:
                evidence_count += 1
                sample.append(ev)
                if ev['gender'] == 'K':
                    sum_k += ev['weight']
                else:
                    sum_m += ev['weight']

        # Decyzja: mocny, prosty próg
        pred = None  # type: Optional[str]
        min_total = int(self.thresholds.get('min_total', 3))
        min_diff = int(self.thresholds.get('min_diff', 2))
        strong_single_min_diff = int(self.thresholds.get('strong_single_diff', 1))
        strong_single_post = any(any(e['type'] in ('bylam','bylem','lam_suffix','lem_suffix') for e in ev) for ev in evidences_by_post)

        if (sum_k >= min_total or sum_m >= min_total) and abs(sum_k - sum_m) >= min_diff:
            pred = 'K' if sum_k > sum_m else 'M'
        elif strong_single_post and abs(sum_k - sum_m) >= strong_single_min_diff:
            pred = 'K' if sum_k > sum_m else 'M'

        stats = {
            'sum_k': float(sum_k),
            'sum_m': float(sum_m),
            'evidence_count': int(evidence_count),
            'posts_with_evidence': int(posts_with_evidence),
            'evidence_sample': sample[:20],  # ogranicz rozmiar
        }
        return pred, stats

    # --------- Przetwarzanie ---------
    def _iter_user_posts(self, forums: Optional[List[str]] = None):
        """Generator: zwraca (user_id, [post_contents]) dla wskazanych forów lub wszystkich."""
        assert self.conn is not None
        cur = self.conn.cursor()

        params: List = []
        forum_filter_sql = ''
        if forums and len(forums) > 0:
            placeholders = ','.join(['?'] * len(forums))
            forum_filter_sql = f"AND f.spider_name IN ({placeholders})"
            params.extend(forums)

        # Pobierz pary (user_id, post_content) posortowane po user_id, by móc grupować w pamięci
        sql = f"""
            SELECT u.id AS user_id, p.content
            FROM forum_posts p
            JOIN forum_users u ON u.id = p.user_id
            JOIN forum_threads t ON p.thread_id = t.id
            JOIN forum_sections s ON t.section_id = s.id
            JOIN forums f ON s.forum_id = f.id
            WHERE p.content IS NOT NULL AND TRIM(p.content) <> ''
            {forum_filter_sql}
            ORDER BY u.id
        """
        cur.execute(sql, params)

        current_user = None
        contents: List[str] = []
        for user_id, content in cur.fetchall():
            if current_user is None:
                current_user = user_id
            if user_id != current_user:
                yield current_user, contents
                current_user = user_id
                contents = []
            contents.append(content)
        if current_user is not None:
            yield current_user, contents

    def run(self, forums: Optional[List[str]] = None, method_tag: str = 'rules_v1') -> Dict:
        """Wykonuje predykcję dla wybranych forów; zapisuje do gender_predictions."""
        self.connect()
        try:
            self.ensure_tables()
            cur = self.conn.cursor()

            processed_users = 0
            saved_predictions = 0

            for user_id, posts in self._iter_user_posts(forums=forums):
                # Pomiń użytkowników już oznaczonych w forum_users.gender (opcjonalnie – nadal zapiszemy prediction jako informacyjny)
                # Można odkomentować, by nie liczyć dla już znanych:
                # g = cur.execute("SELECT gender FROM forum_users WHERE id=?", (user_id,)).fetchone()
                # if g and g[0] in ('M','K'):
                #     continue

                evidences = [self.extract_evidence(p) for p in posts]
                pred, stats = self.aggregate_user(evidences)
                processed_users += 1

                if pred is None:
                    continue

                evidence_json = json.dumps(stats.get('evidence_sample', []), ensure_ascii=False)
                now = datetime.now().isoformat()
                cur.execute(
                    """
                    INSERT INTO gender_predictions (user_id, predicted_gender, score_m, score_k, evidence_count, posts_with_evidence, method, evidence_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, method) DO UPDATE SET
                        predicted_gender=excluded.predicted_gender,
                        score_m=excluded.score_m,
                        score_k=excluded.score_k,
                        evidence_count=excluded.evidence_count,
                        posts_with_evidence=excluded.posts_with_evidence,
                        evidence_json=excluded.evidence_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        user_id,
                        pred,
                        stats['sum_m'],
                        stats['sum_k'],
                        stats['evidence_count'],
                        stats['posts_with_evidence'],
                        method_tag,
                        evidence_json,
                        now,
                        now,
                    ),
                )
                saved_predictions += 1

            self.conn.commit()
            # Ewaluacja trafności względem forum_users.gender
            eval_stats = self.evaluate_accuracy(forums)
            predicted_pct = (saved_predictions / processed_users * 100.0) if processed_users > 0 else 0.0
            result: Dict = {
                'processed_users': int(processed_users),
                'saved_predictions': int(saved_predictions),
                'predicted_pct': float(predicted_pct),
            }
            result.update(eval_stats)
            return result
        finally:
            self.close()

    def evaluate_accuracy(self, forums: Optional[List[str]] = None) -> Dict:
        """Porównuje predykcje do ground truth w forum_users.gender (lokalna baza).
        Zwraca: {'truth_users', 'correct_predictions', 'accuracy_pct'}.
        Ogranicza się do użytkowników z ground truth (M/K). Opcjonalnie filtruje po forach.
        """
        assert self.conn is not None
        cur = self.conn.cursor()
        try:
            params: List = []
            forum_filter_sql = ''
            if forums and len(forums) > 0:
                placeholders = ','.join(['?'] * len(forums))
                forum_filter_sql = f"AND f.spider_name IN ({placeholders})"
                params.extend(forums)

            sql_base = f"""
                FROM gender_predictions gp
                JOIN forum_users fu ON fu.id = gp.user_id
                WHERE fu.gender IN ('M','K')
            """
            if forum_filter_sql:
                sql_base += (
                    " AND EXISTS (\n"
                    "   SELECT 1 FROM forum_posts p\n"
                    "   JOIN forum_threads t ON p.thread_id = t.id\n"
                    "   JOIN forum_sections s ON t.section_id = s.id\n"
                    "   JOIN forums f ON s.forum_id = f.id\n"
                    f"   WHERE p.user_id = gp.user_id {forum_filter_sql}\n"
                    ")"
                )

            total = cur.execute("SELECT COUNT(*) " + sql_base, params).fetchone()[0] or 0
            correct = cur.execute(
                "SELECT COUNT(*) " + sql_base + " AND gp.predicted_gender = fu.gender",
                params,
            ).fetchone()[0] or 0
            acc = (correct / total * 100.0) if total > 0 else None
            return {
                'truth_users': int(total),
                'correct_predictions': int(correct),
                'accuracy_pct': float(acc) if acc is not None else None,
            }
        except Exception:
            return {
                'truth_users': 0,
                'correct_predictions': 0,
                'accuracy_pct': None,
            }


def run_gender_rules(database_path: str, forums: Optional[List[str]] = None, rules_params: Optional[Dict] = None, method_tag: str = 'rules_v1') -> Dict:
    predictor = GenderRulesPredictor(database_path, rules_params=rules_params)
    return predictor.run(forums=forums, method_tag=method_tag)


# ====== Wersja cross‑DB: odczyt ze źródła (forum_*.db), zapis do bazy analizy ======

class _CrossDBGenderPredictor(GenderRulesPredictor):
    """Predyktor działający na połączeniu z ATTACH src: czyta tabele forum z source_db,
    a zapisuje tabelę gender_predictions w głównej bazie (analysis_db)."""

    def __init__(self, analysis_db: str, source_db: str):
        super().__init__(analysis_db)
        self.source_db = source_db

    def connect(self) -> None:
        # Połącz do bazy analizy i dołącz źródło jako 'src'
        self.conn = sqlite3.connect(self.database_path)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA synchronous=NORMAL')
        self.conn.execute("ATTACH DATABASE ? AS src", (self.source_db,))

    def ensure_tables(self) -> None:
        # Tworzymy tabelę wynikową w bazie analizy (bez FK do nieistniejących tabel)
        assert self.conn is not None
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gender_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                predicted_gender TEXT NOT NULL CHECK(predicted_gender IN ('M','K')),
                score_m REAL NOT NULL,
                score_k REAL NOT NULL,
                evidence_count INTEGER NOT NULL,
                posts_with_evidence INTEGER NOT NULL,
                method TEXT NOT NULL,
                evidence_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(user_id, method)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gender_predictions_user ON gender_predictions(user_id)")
        self.conn.commit()

    def _iter_user_posts(self, forums: Optional[List[str]] = None):
        """Nadpisanie: czytamy z src.* (forum_*.db) i grupujemy po użytkowniku."""
        assert self.conn is not None
        cur = self.conn.cursor()

        params: List = []
        forum_filter_sql = ''
        if forums and len(forums) > 0:
            placeholders = ','.join(['?'] * len(forums))
            forum_filter_sql = f"AND f.spider_name IN ({placeholders})"
            params.extend(forums)

        sql = f"""
            SELECT u.id AS user_id, p.content
            FROM src.forum_posts p
            JOIN src.forum_users u ON u.id = p.user_id
            JOIN src.forum_threads t ON p.thread_id = t.id
            JOIN src.forum_sections s ON t.section_id = s.id
            JOIN src.forums f ON s.forum_id = f.id
            WHERE p.content IS NOT NULL AND TRIM(p.content) <> ''
            {forum_filter_sql}
            ORDER BY u.id
        """
        cur.execute(sql, params)

        current_user = None
        contents: List[str] = []
        for user_id, content in cur.fetchall():
            if current_user is None:
                current_user = user_id
            if user_id != current_user:
                yield current_user, contents
                current_user = user_id
                contents = []
            contents.append(content)
        if current_user is not None:
            yield current_user, contents

    def evaluate_accuracy(self, forums: Optional[List[str]] = None) -> Dict:
        """Porównuje predykcje do ground truth w src.forum_users.gender.
        Zwraca: {'truth_users', 'correct_predictions', 'accuracy_pct'}
        Ogranicza się do użytkowników posiadających ground truth (M/K).
        """
        assert self.conn is not None
        cur = self.conn.cursor()
        try:
            params: List = []
            forum_filter_sql = ''
            if forums and len(forums) > 0:
                placeholders = ','.join(['?'] * len(forums))
                forum_filter_sql = f"AND f.spider_name IN ({placeholders})"
                params.extend(forums)

            sql_base = f"""
                FROM gender_predictions gp
                JOIN src.forum_users fu ON fu.id = gp.user_id
                WHERE fu.gender IN ('M','K')
            """
            if forum_filter_sql:
                sql_base += (
                    " AND EXISTS (\n"
                    "   SELECT 1 FROM src.forum_posts p\n"
                    "   JOIN src.forum_threads t ON p.thread_id = t.id\n"
                    "   JOIN src.forum_sections s ON t.section_id = s.id\n"
                    "   JOIN src.forums f ON s.forum_id = f.id\n"
                    f"   WHERE p.user_id = gp.user_id {forum_filter_sql}\n"
                    ")"
                )

            total = cur.execute("SELECT COUNT(*) " + sql_base, params).fetchone()[0] or 0
            correct = cur.execute(
                "SELECT COUNT(*) " + sql_base + " AND gp.predicted_gender = fu.gender",
                params,
            ).fetchone()[0] or 0
            acc = (correct / total * 100.0) if total > 0 else None
            return {
                'truth_users': int(total),
                'correct_predictions': int(correct),
                'accuracy_pct': float(acc) if acc is not None else None,
            }
        except Exception:
            return {
                'truth_users': 0,
                'correct_predictions': 0,
                'accuracy_pct': None,
            }


def run_gender_rules_into_analysis(analysis_db: str, source_db: str, forums: Optional[List[str]] = None, method_tag: str = 'rules_v1', rules_params: Optional[Dict] = None) -> Dict:
    """Uruchamia predykcję płci z odczytem z source_db i zapisem wyników do analysis_db."""
    predictor = _CrossDBGenderPredictor(analysis_db, source_db)
    # Nadpisz parametry reguł jeśli podano
    if rules_params:
        predictor.weights = {**predictor.weights, **(rules_params.get('weights') or {})}
        predictor.thresholds = {**predictor.thresholds, **(rules_params.get('thresholds') or {})}
    return predictor.run(forums=forums, method_tag=method_tag)


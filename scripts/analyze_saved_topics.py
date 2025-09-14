#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analiza zapisanych modeli Top2Vec i generowanie artefaktów w ściśle określonej
strukturze wyników oraz logów.

Wejście: dwie ścieżki do modelu (katalog/plik "model") – patrz zmienna MODELS.
Wyjście:
- results_dir = data/topics/results/{run_date}/{K|M}/ALL/{run_id}/
- logs_dir    = data/topics/logs/{run_date}/{K|M}/ALL/{run_id}/

Artefakty (per model):
- analysis_{run_date}_{HHMMSS}.json
- topic_distribution.png
- doc_scores_distribution.png
- topic_map.html
- wordcloud/topic_{topic_id}_wordcloud.png
- topics_top50_full.json
- topics_2_11_top50.json
- topics_2_11_top50_fulltexts.json
- TEMATY_{KOBIETY|MEZCZYZNI}.json
- examples/{POLITYKA_*.xlsx, SPOWIEDZ_*.xlsx}

Założenia:
- Modele to Top2Vec (ścieżka kończy się na "model").
- Baza do pobrania metadanych dokumentów: data/databases/merged_forums.db
- Seed = 42
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from plotly import express as px
from plotly import graph_objects as go
from top2vec import Top2Vec
from wordcloud import WordCloud
import sqlite3

# Ustalony seed dla powtarzalności
import random
random.seed(42)
np.random.seed(42)
os.environ["PYTHONHASHSEED"] = "42"

# Wejścia (twardo ustawione zgodnie z wymaganiem użytkownika)
MODELS: List[Dict[str, str]] = [
    {"group": "K", "path": "data/topics/models/20250827/K/ALL/155429_038844/model"},
    {"group": "M", "path": "data/topics/models/20250827/M/ALL/194903_560595/model"},
]
RUN_DATE = "20250827"
COHORT = "ALL"
DATABASE_PATH = Path("data/databases/merged_forums.db")

# Stopwords PL i tokeny techniczne – prosta lista lokalna
POLISH_STOPWORDS = {
    "i", "oraz", "lub", "albo", "ale", "więc", "że", "to", "jest", "są", "być", "nie",
    "w", "we", "na", "po", "u", "o", "od", "do", "za", "przez", "dla", "jak", "jakie", "które",
    "który", "która", "którzy", "których", "gdy", "kiedy", "ten", "ta", "to", "te", "tam", "tu",
    "się", "siebie", "sobie", "też", "również", "czy", "by", "było", "była", "były", "być",
    "jego", "jej", "ich", "nas", "nasze", "was", "wasze", "ja", "ty", "on", "ona", "ono", "my",
    "wy", "oni", "one", "którym", "którego", "której", "którym", "które",
    # techniczne/artefakty tokenizacji
    "http", "https", "www", "com", "pl", "jpg", "png", "gif", "pdf", "rtf", "doc", "html",
}

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "POLITYKA": [
        "polityk", "polityka", "rząd", "sejm", "senat", "partia", "wybory", "kampania", "prezydent",
        "pis", "po", "konfederacja", "lewica", "koalicja", "minister", "ustawa", "premier",
    ],
    "SPOWIEDZ": [
        "spowiedź", "spowiedz", "spowiednik", "grzech", "grzesz", "rachunek", "sumienia",
        "rozgrzeszenie", "sakrament", "pokuta", "konfesjonał", "spowiadać",
    ],
}

@dataclass
class RunMeta:
    run_date: str
    group: str
    cohort: str
    run_id: str
    model_path: Path
    results_dir: Path
    logs_dir: Path


def parse_run_meta(group: str, model_path: str) -> RunMeta:
    p = Path(model_path).resolve()
    # Oczekiwana struktura: data/topics/models/{run_date}/{K|M}/ALL/{run_id}/model
    try:
        run_id = p.parent.name
        cohort = p.parents[1].name
        group_dir = p.parents[2].name
        run_date = p.parents[3].name
    except Exception:
        raise ValueError(f"Nieprawidłowa ścieżka modelu: {model_path}")
    if group.upper() != group_dir.upper():
        # Zaufaj ścieżce
        group = group_dir.upper()
    results_dir = Path(f"data/topics/results/{run_date}/{group}/{cohort}/{run_id}")
    logs_dir = Path(f"data/topics/logs/{run_date}/{group}/{cohort}/{run_id}")
    return RunMeta(run_date=run_date, group=group, cohort=cohort, run_id=run_id, model_path=p, results_dir=results_dir, logs_dir=logs_dir)


def setup_logger(logs_dir: Path, run_date: str) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    log_file = logs_dir / f"analysis_{run_date}_{ts}.log"
    logger = logging.getLogger(f"topics_saved_{logs_dir}")
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def safe_get_topics(model: Top2Vec) -> Tuple[List[int], List[List[str]], List[List[float]]]:
    try:
        got = model.get_topics()
        if isinstance(got, tuple) and len(got) == 4:
            topic_words_all, word_scores_all, _topic_scores, topic_nums = got
        elif isinstance(got, tuple) and len(got) == 3:
            topic_words_all, word_scores_all, topic_nums = got
        else:
            topic_words_all, word_scores_all, topic_nums = model.get_topics()
        topic_ids = [int(t) for t in (topic_nums.tolist() if hasattr(topic_nums, "tolist") else list(topic_nums))]
        words_per_topic: List[List[str]] = []
        scores_per_topic: List[List[float]] = []
        for idx in range(len(topic_ids)):
            words = topic_words_all[idx]
            scores = word_scores_all[idx]
            words_list = (words.tolist() if hasattr(words, "tolist") else list(words))
            scores_list = (scores.tolist() if hasattr(scores, "tolist") else list(scores))
            words_per_topic.append([str(w) for w in words_list])
            scores_per_topic.append([float(s) for s in scores_list])
        return topic_ids, words_per_topic, scores_per_topic
    except Exception:
        # Fallback: iteruj po zakresie
        try:
            n = int(model.get_num_topics())
        except Exception:
            n = 0
        topic_ids = list(range(n))
        words_per_topic, scores_per_topic = [], []
        for t in topic_ids:
            try:
                w, s = model.get_topic_words(int(t))
                words_per_topic.append([str(x) for x in (w.tolist() if hasattr(w, "tolist") else list(w))])
                scores_per_topic.append([float(x) for x in (s.tolist() if hasattr(s, "tolist") else list(s))])
            except Exception:
                words_per_topic.append([])
                scores_per_topic.append([])
        return topic_ids, words_per_topic, scores_per_topic


def get_topic_sizes(model: Top2Vec) -> Dict[int, int]:
    try:
        sizes, topic_nums = model.get_topic_sizes()
        tnums = topic_nums.tolist() if hasattr(topic_nums, "tolist") else list(topic_nums)
        sz = sizes.tolist() if hasattr(sizes, "tolist") else list(sizes)
        return {int(t): int(s) for s, t in zip(sz, tnums)}
    except Exception:
        return {i: 0 for i in range(int(getattr(model, "get_num_topics", lambda: 0)()))}


def build_doc_max_scores(model: Top2Vec, topic_ids: Sequence[int], topic_sizes: Dict[int, int]) -> Dict[str, float]:
    doc_to_max: Dict[str, float] = {}
    for t in topic_ids:
        size = int(topic_sizes.get(int(t), 0))
        if size <= 0:
            continue
        try:
            _docs, scores, doc_ids = model.search_documents_by_topic(int(t), num_docs=size)
            ids_list = doc_ids.tolist() if hasattr(doc_ids, "tolist") else list(doc_ids)
            scores_list = scores.tolist() if hasattr(scores, "tolist") else list(scores)
            for pid, sc in zip(ids_list, scores_list):
                k = str(pid)
                v = float(sc)
                if k not in doc_to_max or v > doc_to_max[k]:
                    doc_to_max[k] = v
        except Exception:
            continue
    return doc_to_max


def draw_topic_distribution_png(topic_sizes: Dict[int, int], out_path: Path) -> None:
    topics = sorted(topic_sizes.keys())
    counts = [int(topic_sizes[t]) for t in topics]
    plt.figure(figsize=(14, 8))
    bars = plt.bar([str(t) for t in topics], counts, color="#6baed6")
    plt.xlabel("ID tematu")
    plt.ylabel("Liczba dokumentów")
    plt.title("Udział dokumentów per temat")
    for b, c in zip(bars, counts):
        plt.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.01, str(c), ha="center", va="bottom", fontsize=8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def draw_doc_scores_distribution_png(doc_scores: Dict[str, float], out_path: Path) -> None:
    values = list(doc_scores.values())
    if not values:
        values = [0.0]
    plt.figure(figsize=(12, 7))
    plt.hist(values, bins=30, color="#fb6a4a", alpha=0.8, edgecolor="white")
    plt.xlabel("Maksymalna waga tematu dla dokumentu")
    plt.ylabel("Liczba dokumentów")
    plt.title("Rozkład maksymalnych wag tematów")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def write_topic_map_html(model: Top2Vec, topic_ids: Sequence[int], out_path: Path, title: str) -> None:
    coords = None
    try:
        tc = getattr(model, "get_topic_coordinates", None)
        if callable(tc):
            tmp = tc()
            if tmp is not None:
                coords = tmp
    except Exception:
        coords = None
    if coords is None:
        topic_vectors = getattr(model, "topic_vectors", None)
        if topic_vectors is None:
            out_path.write_text("<html><body><p>Brak danych do mapy tematów.</p></body></html>", encoding="utf-8")
            return
        X = np.array(topic_vectors)
        if X.ndim != 2 or X.shape[0] < 2:
            out_path.write_text("<html><body><p>Za mało tematów do rzutowania 2D.</p></body></html>", encoding="utf-8")
            return
        Xc = X - X.mean(axis=0, keepdims=True)
        U, S, _Vt = np.linalg.svd(Xc, full_matrices=False)
        coords = U[:, :2] * S[:2]
    xs = coords[:, 0]
    ys = coords[:, 1]
    # Zbuduj etykiety i hover z pierwszych słów tematów
    try:
        t_ids2, words2, _scores2 = safe_get_topics(model)
        id_to_words = {int(tid): [str(w) for w in words2[idx]] for idx, tid in enumerate(t_ids2)}
    except Exception:
        id_to_words = {int(t): [] for t in topic_ids}
    # Rozmiary punktów wg liczby dokumentów
    try:
        sz_map = get_topic_sizes(model)
    except Exception:
        sz_map = {int(t): 1 for t in topic_ids}
    # Średnie score’y dokumentów per temat (kolorowanie)
    avg_scores_map: Dict[int, float] = {}
    for t in topic_ids:
        try:
            _docs, scs, _ids = model.search_documents_by_topic(int(t), num_docs=min(200, max(20, sz_map.get(int(t), 0))))
            if scs is not None and len(scs) > 0:
                if hasattr(scs, 'tolist'):
                    vals = [float(x) for x in scs.tolist()]
                else:
                    vals = [float(x) for x in scs]
                avg_scores_map[int(t)] = float(np.mean(vals))
            else:
                avg_scores_map[int(t)] = 0.0
        except Exception:
            avg_scores_map[int(t)] = 0.0
    text_labels = []
    hover_texts = []
    sizes_vals = []
    colors_vals = []
    for t in topic_ids:
        ws = id_to_words.get(int(t), [])
        first_word = (ws[0] if ws else None)
        text_labels.append(str(first_word) if first_word else f"Temat {int(t)}")
        doc_count = int(sz_map.get(int(t), 0))
        sizes_vals.append(max(1, doc_count))
        colors_vals.append(float(avg_scores_map.get(int(t), 0.0)))
        hover_texts.append(
            (f"Temat {int(t)}\n"
             f"Słowa: {', '.join(ws[:5])}\n"
             f"Dokumenty: {doc_count}\n"
             f"Śr. score: {avg_scores_map.get(int(t), 0.0):.3f}") if ws else (
                 f"Temat {int(t)}\nDokumenty: {doc_count}\nŚr. score: {avg_scores_map.get(int(t), 0.0):.3f}")
        )
    # Wykres ze skalowaniem rozmiarów (area) i kolorowaniem wg średniego score
    # Przekażemy dodatkowe, ukryte dane (customdata): topic_id, top5, doc_count
    customdata = []
    for t in topic_ids:
        ws = id_to_words.get(int(t), [])
        doc_count = int(sz_map.get(int(t), 0))
        customdata.append([
            int(t),
            ", ".join(ws[:5]),
            doc_count,
        ])
    fig = px.scatter(
        x=xs,
        y=ys,
        text=text_labels,
        size=sizes_vals,
        color=colors_vals,
        title=title,
        color_continuous_scale='Turbo'
    )
    fig.update_traces(
        textposition="top center",
        marker=dict(color="red", opacity=0.75),
        hovertext=hover_texts,
        hovertemplate="%{hovertext}<extra></extra>",
        customdata=customdata,
    )
    # Parametry skalowania bąbelków
    try:
        max_size_val = max(sizes_vals) if sizes_vals else 1
        desired_max_px = 50.0
        sizeref = (2.0 * max_size_val) / (desired_max_px ** 2)
        fig.update_traces(marker_sizemode='area', marker_sizeref=sizeref, marker_sizemin=6)
    except Exception:
        pass
    # Heatmapa gęstości
    try:
        fig.add_trace(
            go.Histogram2dContour(
                x=xs,
                y=ys,
                colorscale='Blues',
                showscale=True,
                contours=dict(showlines=False),
                opacity=0.25,
                ncontours=20,
                hoverinfo='skip',
                name='Gęstość'
            )
        )
        # Dodatkowo półprzezroczysty obraz heatmapy (opcjonalne)
        fig.add_trace(
            go.Histogram2d(
                x=xs,
                y=ys,
                colorscale='Blues',
                showscale=False,
                opacity=0.15,
                hoverinfo='skip',
                name='Heatmapa'
            )
        )
        # Uporządkuj kolejność: heatmapa pod punktami
        for tr in fig.data:
            if isinstance(tr, (go.Histogram2d, go.Histogram2dContour)):
                tr.update(zauto=True)
        fig.update_traces(selector=dict(type='scatter'), marker=dict(line=dict(width=0)))
    except Exception:
        pass
    fig.update_layout(xaxis_title="Wymiar 1", yaxis_title="Wymiar 2", showlegend=False)

    # Dodaj tabelę pod wykresem, uzupełnianą po kliknięciu w punkt (temat)
    # Osadzamy prosty skrypt JS wykorzystujący plotly_click do uzupełnienia <div id="topic-table">
    table_div = """
<div id="topic-table" style="margin-top:16px;font-family:system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Ubuntu,Helvetica,Arial,sans-serif;"></div>
<script>
  (function(){
    const plotDiv = document.querySelector('div.plotly-graph-div');
    if (!plotDiv) return;
    plotDiv.on('plotly_click', function(data){
      try {
        if (!data || !data.points || !data.points.length) return;
        const pt = data.points[0];
        const cd = pt.customdata || [];
        const topicId = cd[0];
        // W embedzie umieszczamy JSON z top-10 dokumentami per temat
        const payload = window.__TOPIC_DOCS__ || {};
        const rows = (payload[String(topicId)] || []).slice(0,10);
        const container = document.getElementById('topic-table');
        if (!container) return;
        if (!rows.length){
          container.innerHTML = '<p><i>Brak danych dla tematu ' + topicId + '</i></p>';
          return;
        }
        let html = '<h3>Top 10 postów dla tematu ' + topicId + '</h3>';
        html += '<table style="border-collapse:collapse;width:100%;">';
        html += '<thead><tr>' +
                '<th style="text-align:left;border-bottom:1px solid #ddd;padding:6px;">forum</th>' +
                '<th style="text-align:left;border-bottom:1px solid #ddd;padding:6px;">data</th>' +
                '<th style="text-align:left;border-bottom:1px solid #ddd;padding:6px;">content</th>' +
                '</tr></thead><tbody>';
        for (const r of rows){
          const forum = r.forum || '';
          const date = r.post_date || '';
          const content = (r.content || '').replace(/\n/g,' ').slice(0,500);
          html += '<tr>' +
                  '<td style="vertical-align:top;border-bottom:1px solid #eee;padding:6px;">' + forum + '</td>' +
                  '<td style="vertical-align:top;border-bottom:1px solid #eee;padding:6px;">' + date + '</td>' +
                  '<td style="vertical-align:top;border-bottom:1px solid #eee;padding:6px;">' + content + '</td>' +
                  '</tr>';
        }
        html += '</tbody></table>';
        container.innerHTML = html;
      } catch(e) {
        console && console.warn && console.warn('plotly_click handler error', e);
      }
    });
  })();
</script>
"""

    # Przygotuj dane top-10 dokumentów per temat do osadzenia w JS (window.__TOPIC_DOCS__)
    topic_docs_map: Dict[str, List[Dict[str, Any]]] = {}
    try:
        with sqlite3.connect(str(DATABASE_PATH)) as conn:
            for t in topic_ids:
                try:
                    _docs, scs, doc_ids = model.search_documents_by_topic(int(t), num_docs=10)
                    ids_list = [str(x) for x in (doc_ids.tolist() if hasattr(doc_ids, 'tolist') else list(doc_ids))]
                except Exception:
                    ids_list = []
                posts_map = fetch_posts_meta(conn, ids_list)
                rows: List[Dict[str, Any]] = []
                for pid in ids_list:
                    meta_p = posts_map.get(pid, {})
                    rows.append({
                        'post_id': pid,
                        'forum': meta_p.get('forum'),
                        'post_date': meta_p.get('post_date'),
                        'content': meta_p.get('content'),
                    })
                topic_docs_map[str(int(t))] = rows
    except Exception:
        topic_docs_map = {}

    # Zapisz HTML wykresu
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_core = fig.to_html(include_plotlyjs=True, full_html=True)
    # Wstrzyknij payload i kontener tabeli tuż przed </body>
    try:
        import json as _json
        payload_js = f"<script>window.__TOPIC_DOCS__ = {_json.dumps(topic_docs_map)}</script>" + table_div
        html_core = html_core.replace("</body>", payload_js + "</body>")
    except Exception:
        pass
    Path(out_path).write_text(html_core, encoding='utf-8')


def make_wordcloud(word_weights: Dict[str, float], out_path: Path) -> None:
    # Filtr stopwords
    filtered = {w: float(s) for w, s in word_weights.items() if w.lower() not in POLISH_STOPWORDS and len(str(w)) >= 2}
    if not filtered:
        filtered = word_weights
    wc = WordCloud(
        width=1200,
        height=900,
        background_color="white",
        max_words=150,
        colormap="viridis",
        stopwords=set(),
        prefer_horizontal=0.9,
        random_state=42,
    )
    wc.generate_from_frequencies(filtered)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wc.to_file(str(out_path))


def compute_intra_topic_diversity(words_per_topic: List[List[str]], top_k: int = 10) -> Optional[float]:
    try:
        top_sets = [set([w.lower() for w in ws[:top_k]]) for ws in words_per_topic]
        if not top_sets:
            return None
        union_all = set().union(*top_sets) if top_sets else set()
        total_tokens = len(top_sets) * top_k
        unique_tokens = len(union_all)
        if total_tokens == 0:
            return None
        return float(unique_tokens / total_tokens)
    except Exception:
        return None


def fetch_posts_meta(conn: sqlite3.Connection, post_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    if not post_ids:
        return {}
    placeholders = ",".join(["?"] * len(post_ids))
    query = f"""
        SELECT
            fp.id AS post_id,
            fp.content AS content,
            fp.url AS url,
            fp.post_date AS post_date,
            ft.title AS thread_title,
            f.spider_name AS forum
        FROM forum_posts fp
        JOIN forum_threads ft ON fp.thread_id = ft.id
        JOIN forum_sections fs ON ft.section_id = fs.id
        JOIN forums f ON fs.forum_id = f.id
        WHERE fp.id IN ({placeholders})
    """
    cur = conn.cursor()
    cur.execute(query, list(post_ids))
    rows = cur.fetchall()
    result: Dict[str, Dict[str, Any]] = {}
    for post_id, content, url, post_date, thread_title, forum in rows:
        result[str(post_id)] = {
            "post_id": str(post_id),
            "content": None if content is None else str(content),
            "url": None if url is None else str(url),
            "post_date": None if post_date is None else str(post_date),
            "thread_title": None if thread_title is None else str(thread_title),
            "forum": None if forum is None else str(forum),
        }
    return result


def topic_label_from_words(top_words: Sequence[str]) -> Tuple[str, str, List[str]]:
    lw = [w.lower() for w in top_words[:20]]
    # Heurystyki etykietowania
    if any(any(k in w for k in CATEGORY_KEYWORDS["POLITYKA"]) for w in lw):
        return ("Polityka i życie publiczne", "Dominują słowa polityczne (partie, wybory, rząd)", top_words[:10])
    if any(any(k in w for k in CATEGORY_KEYWORDS["SPOWIEDZ"]) for w in lw):
        return ("Sakrament spowiedzi i pokuta", "Słowa o spowiedzi, grzechu, rozgrzeszeniu", top_words[:10])
    if any(s in lw for s in ["modlitwa", "modlić", "różaniec", "rózaniec", "zdrowaś"]):
        return ("Modlitwa i praktyki pobożne", "Słowa związane z modlitwą i praktykami", top_words[:10])
    if any(s in lw for s in ["kościół", "kosciol", "parafia", "msza", "liturgia", "ksiądz", "ksiadz"]):
        return ("Kościół i liturgia", "Słowa o parafii, liturgii i duchowieństwie", top_words[:10])
    if any(s in lw for s in ["rodzina", "małżeństwo", "malzenstwo", "dzieci", "związek", "zwiazek"]):
        return ("Rodzina i relacje", "Słowa o rodzinie, małżeństwie, relacjach", top_words[:10])
    return ("Ogólne dyskusje religijne", "Brak dominujących słów jednej kategorii", top_words[:10])


def save_topics_exports(
    model: Top2Vec,
    meta: RunMeta,
    topic_ids: Sequence[int],
    words_per_topic: List[List[str]],
    scores_per_topic: List[List[float]],
    topic_sizes: Dict[int, int],
    out_files: List[Path],
) -> None:
    # Ranking 50 największych tematów
    ranked = sorted([(int(t), int(topic_sizes.get(int(t), 0))) for t in topic_ids], key=lambda x: x[1], reverse=True)
    top50 = [t for t, _ in ranked[:50]]
    conn = sqlite3.connect(str(DATABASE_PATH))
    try:
        # Pełne
        items_full: List[Dict[str, Any]] = []
        items_2_11: List[Dict[str, Any]] = []
        items_fulltexts: List[Dict[str, Any]] = []
        for t in top50:
            idx = topic_ids.index(int(t))
            words = words_per_topic[idx]
            scores = scores_per_topic[idx]
            top_words_20 = [str(w) for w in words[:20]]
            top_words_weights = dict(zip([str(w) for w in words[:75]], [float(s) for s in scores[:75]]))
            # Dokumenty reprezentatywne
            try:
                _docs, scs, doc_ids = model.search_documents_by_topic(int(t), num_docs=min(200, max(50, topic_sizes.get(int(t), 0))))
                ids_list = [str(x) for x in (doc_ids.tolist() if hasattr(doc_ids, "tolist") else list(doc_ids))]
                scores_list = [float(x) for x in (scs.tolist() if hasattr(scs, "tolist") else list(scs))]
            except Exception:
                ids_list, scores_list = [], []
            posts_map = fetch_posts_meta(conn, ids_list)
            # Snippety
            repr_doc_ids = ids_list[:50]
            repr_doc_snippets = []
            for pid in repr_doc_ids[:50]:
                content = (posts_map.get(pid, {}).get("content") or "").strip()
                if not content:
                    repr_doc_snippets.append("")
                else:
                    snippet = content[:280].replace("\n", " ")
                    repr_doc_snippets.append(snippet)
            item = {
                "topic_id": int(t),
                "size": int(topic_sizes.get(int(t), 0)),
                "top_words": top_words_20,
                "repr_doc_ids": [int(x) if str(x).isdigit() else x for x in repr_doc_ids],
                "repr_doc_snippets": repr_doc_snippets,
            }
            items_full.append(item)
            # 2..11
            words_2_11 = [w for w in top_words_20[1:11]]
            item_2_11 = {
                "topic_id": int(t),
                "size": int(topic_sizes.get(int(t), 0)),
                "top_words": words_2_11,
                "repr_doc_ids": [int(x) if str(x).isdigit() else x for x in repr_doc_ids],
                "repr_doc_snippets": repr_doc_snippets,
            }
            items_2_11.append(item_2_11)
            # Fulltexts (min 3)
            ft_doc_ids = ids_list[:max(3, min(50, len(ids_list)))]
            ft_snippets = []
            for pid in ft_doc_ids:
                content = (posts_map.get(pid, {}).get("content") or "").strip()
                ft_snippets.append(content)
            item_fulltexts = {
                "topic_id": int(t),
                "size": int(topic_sizes.get(int(t), 0)),
                "top_words": words_2_11,
                "repr_doc_ids": [int(x) if str(x).isdigit() else x for x in ft_doc_ids],
                "repr_doc_snippets": ft_snippets,
            }
            items_fulltexts.append(item_fulltexts)
        # Zapis
        p1 = meta.results_dir / "topics_top50_full.json"
        p2 = meta.results_dir / "topics_2_11_top50.json"
        p3 = meta.results_dir / "topics_2_11_top50_fulltexts.json"
        meta.results_dir.mkdir(parents=True, exist_ok=True)
        with open(p1, "w", encoding="utf-8") as f:
            json.dump(items_full, f, ensure_ascii=False, indent=2)
        with open(p2, "w", encoding="utf-8") as f:
            json.dump(items_2_11, f, ensure_ascii=False, indent=2)
        with open(p3, "w", encoding="utf-8") as f:
            json.dump(items_fulltexts, f, ensure_ascii=False, indent=2)
        out_files.extend([p1, p2, p3])
    finally:
        try:
            conn.close()
        except Exception:
            pass


def save_labels(meta: RunMeta, topic_ids: Sequence[int], words_per_topic: List[List[str]]) -> Path:
    items: List[Dict[str, Any]] = []
    for t in topic_ids:
        idx = topic_ids.index(int(t))
        top_words = [str(w) for w in words_per_topic[idx][:20]]
        label, rationale, ex = topic_label_from_words(top_words)
        items.append({
            "topic_id": int(t),
            "label": label,
            "rationale": rationale,
            "example_words": ex,
        })
    if meta.group.upper() == "K":
        out = meta.results_dir / "TEMATY_KOBIETY.json"
    else:
        out = meta.results_dir / "TEMATY_MEZCZYZNI.json"
    meta.results_dir.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return out


def save_examples_xlsx(
    model: Top2Vec,
    meta: RunMeta,
    topic_ids: Sequence[int],
    words_per_topic: List[List[str]],
) -> List[Path]:
    # Mapuj tematy -> etykiety, wybierz te należące do POLITYKA i SPOWIEDZ
    label_map: Dict[int, str] = {}
    category_for_topic: Dict[int, Optional[str]] = {}
    for t in topic_ids:
        idx = topic_ids.index(int(t))
        top_words = [str(w) for w in words_per_topic[idx][:20]]
        label, _rationale, _ex = topic_label_from_words(top_words)
        label_map[int(t)] = label
        if "Polityka" in label:
            category_for_topic[int(t)] = "POLITYKA"
        elif "spowiedzi" in label.lower() or "spowied" in " ".join(top_words).lower():
            category_for_topic[int(t)] = "SPOWIEDZ"
        else:
            category_for_topic[int(t)] = None
    examples_dir = meta.results_dir / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    # Zbierz rekordy per kategoria
    def collect_for_category(category: str) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        for t in topic_ids:
            if category_for_topic.get(int(t)) != category:
                continue
            try:
                _docs, scs, doc_ids = model.search_documents_by_topic(int(t), num_docs=1000)
                ids_list = [str(x) for x in (doc_ids.tolist() if hasattr(doc_ids, "tolist") else list(doc_ids))]
                scores_list = [float(x) for x in (scs.tolist() if hasattr(scs, "tolist") else list(scs))]
            except Exception:
                continue
            with sqlite3.connect(str(DATABASE_PATH)) as conn:
                posts_map = fetch_posts_meta(conn, ids_list)
            for pid, sc in zip(ids_list, scores_list):
                meta_post = posts_map.get(pid, {})
                rows.append({
                    "doc_id": pid,
                    "topic_id": int(t),
                    "topic_label": label_map.get(int(t)),
                    "topic_score": float(sc),
                    "title|thread": meta_post.get("thread_title"),
                    "url|source": meta_post.get("url") or meta_post.get("forum"),
                    "snippet": (meta_post.get("content") or "").strip().replace("\n", " ")[:300],
                    "full_text": meta_post.get("content"),
                })
        if not rows:
            return pd.DataFrame(columns=["doc_id", "topic_id", "topic_label", "topic_score", "title|thread", "url|source", "snippet", "full_text"])
        df = pd.DataFrame(rows)
        df = df.sort_values("topic_score", ascending=False)
        if len(df) > 100:
            df = df.head(100)
        return df
    files: List[Path] = []
    # POLITYKA
    df_pol = collect_for_category("POLITYKA")
    if meta.group.upper() == "K":
        p_pol = examples_dir / "POLITYKA_KOBIETY.xlsx"
    else:
        p_pol = examples_dir / "POLITYKA_MEZCZYZNI.xlsx"
    with pd.ExcelWriter(p_pol, engine="openpyxl") as writer:
        df_pol.to_excel(writer, index=False)
    files.append(p_pol)
    # SPOWIEDZ
    df_sp = collect_for_category("SPOWIEDZ")
    if meta.group.upper() == "K":
        p_sp = examples_dir / "SPOWIEDZ_KOBIETY.xlsx"
    else:
        p_sp = examples_dir / "SPOWIEDZ_MEZCZYZNI.xlsx"
    with pd.ExcelWriter(p_sp, engine="openpyxl") as writer:
        df_sp.to_excel(writer, index=False)
    files.append(p_sp)
    return files


def save_analysis_json(
    meta: RunMeta,
    topic_ids: Sequence[int],
    words_per_topic: List[List[str]],
    topic_sizes: Dict[int, int],
    seed: int = 42,
) -> Path:
    ts = datetime.now().strftime("%H%M%S")
    out_path = meta.results_dir / f"analysis_{meta.run_date}_{ts}.json"
    n_docs = int(sum(topic_sizes.values())) if topic_sizes else None
    top10_map: Dict[int, List[str]] = {}
    for t in topic_ids:
        idx = topic_ids.index(int(t))
        top10_map[int(t)] = [str(w) for w in words_per_topic[idx][:10]]
    diversity = compute_intra_topic_diversity(words_per_topic, top_k=10)
    payload = {
        "run_date": meta.run_date,
        "group": meta.group.upper(),
        "run_id": meta.run_id,
        "n_docs": None if n_docs is None else int(n_docs),
        "n_topics_total": int(len(topic_ids)),
        "topics_sizes": {int(k): int(v) for k, v in topic_sizes.items()},
        "top_words_per_topic": {int(t): top10_map[int(t)] for t in topic_ids},
        "coherence_umass": None,
        "coherence_c_npmi": None,
        "intra_topic_diversity": diversity,
        "seed": int(seed),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def process_single_model(entry: Dict[str, str]) -> Dict[str, Any]:
    group = entry.get("group") or ""
    model_path = entry.get("path") or ""
    meta = parse_run_meta(group, model_path)
    logger = setup_logger(meta.logs_dir, meta.run_date)
    saved_files: List[Path] = []
    logger.info(f"Start analizy: group={meta.group} run_date={meta.run_date} run_id={meta.run_id}")
    logger.info(f"Model: {meta.model_path}")
    if not DATABASE_PATH.exists():
        logger.warning(f"Brak bazy danych: {DATABASE_PATH}")
    # 1) Wczytaj model
    model = Top2Vec.load(str(meta.model_path))
    logger.info("Model wczytany")
    # 2) Ekstrakcja tematów
    topic_ids, words_per_topic, scores_per_topic = safe_get_topics(model)
    topic_sizes = get_topic_sizes(model)
    logger.info(f"Liczba tematów: {len(topic_ids)}")
    # 3) Metryki + analysis_*.json
    analysis_json = save_analysis_json(meta, topic_ids, words_per_topic, topic_sizes, seed=42)
    saved_files.append(analysis_json)
    logger.info(f"Zapisano: {analysis_json}")
    # 4) Wykresy PNG
    td_png = meta.results_dir / "topic_distribution.png"
    draw_topic_distribution_png(topic_sizes, td_png)
    saved_files.append(td_png)
    logger.info(f"Zapisano: {td_png}")
    doc_scores = build_doc_max_scores(model, topic_ids, topic_sizes)
    ds_png = meta.results_dir / "doc_scores_distribution.png"
    draw_doc_scores_distribution_png(doc_scores, ds_png)
    saved_files.append(ds_png)
    logger.info(f"Zapisano: {ds_png}")
    # 5) Mapa tematów
    tm_html = meta.results_dir / "topic_map.html"
    write_topic_map_html(model, topic_ids, tm_html, title=f"Mapa tematów – {meta.group} {meta.run_id}")
    saved_files.append(tm_html)
    logger.info(f"Zapisano: {tm_html}")
    # 6) Wordcloudy
    wc_dir = meta.results_dir / "wordcloud"
    wc_dir.mkdir(parents=True, exist_ok=True)
    for t in topic_ids:
        idx = topic_ids.index(int(t))
        w = words_per_topic[idx]
        s = scores_per_topic[idx]
        weights = {str(x): float(y) for x, y in zip(w[:150], s[:150])}
        out = wc_dir / f"topic_{int(t)}_wordcloud.png"
        make_wordcloud(weights, out)
    saved_files.extend(sorted(wc_dir.glob("*.png")))
    logger.info(f"Zapisano chmury słów: {wc_dir}")
    # 7) Eksporty topics_*
    save_topics_exports(model, meta, topic_ids, words_per_topic, scores_per_topic, topic_sizes, saved_files)
    logger.info("Zapisano eksporty topics_*")
    # 8) Etykiety
    labels_json = save_labels(meta, topic_ids, words_per_topic)
    saved_files.append(labels_json)
    logger.info(f"Zapisano etykiety: {labels_json}")
    # 9) Przykłady XLSX
    try:
        xlsx_files = save_examples_xlsx(model, meta, topic_ids, words_per_topic)
        saved_files.extend(xlsx_files)
        logger.info(f"Zapisano przykłady: {', '.join(str(x) for x in xlsx_files)}")
    except Exception as e:
        logger.warning(f"Nie udało się zapisać przykładów XLSX: {e}")
    # 10) Log lista plików
    rel_paths = [str(Path(p).relative_to(Path("data"))) if str(p).startswith("data/") or str(p).startswith("data\\") else str(p) for p in saved_files]
    logger.info("Wygenerowane pliki:")
    for rp in rel_paths:
        logger.info(f" - {rp}")
    return {
        "meta": meta,
        "topic_count": len(topic_ids),
        "doc_count": int(sum(topic_sizes.values())) if topic_sizes else None,
        "files": [str(p) for p in saved_files],
    }


def main() -> int:
    results: List[Dict[str, Any]] = []
    for entry in MODELS:
        res = process_single_model(entry)
        results.append(res)
    # Krótkie podsumowanie na stdout (dla użytkownika)
    summary = []
    for r in results:
        meta: RunMeta = r["meta"]
        files_rel = []
        for p in r["files"]:
            try:
                files_rel.append(str(Path(p).relative_to(Path("data"))))
            except Exception:
                files_rel.append(p)
        summary.append({
            "group": meta.group,
            "run_id": meta.run_id,
            "n_topics": r["topic_count"],
            "n_docs": r["doc_count"],
            "files": files_rel,
        })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

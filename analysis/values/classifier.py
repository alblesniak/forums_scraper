#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Klasyfikacja wartości (M vs K) w treści postów.

Funkcjonalności:
- Wczytanie dwóch plików Excel (K i M), kolumna 'content' (opcjonalnie 'post_id')
- Dodanie metadanych 'gender' do rekordów
- Batchowanie po 10 postów i wywołanie LLM jednym żądaniem (1 paczka = 10 postów)
- Zapis surowych odpowiedzi oraz sparsowanych wyników per batch i per płeć
- Agregacja: liczba przypisań, suma/średnia confidence, normalizacja na 1000 słów, osobno dla M i K
- Raporty: tabele porównawcze, różnice (M–K), wykresy Top‑10, przykładowe evidence_span
- Excel z surowymi danymi (treść postów i predykcje)
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import logging

try:
    from tqdm import tqdm  # type: ignore
except Exception:  # pragma: no cover
    def tqdm(x, **kwargs):  # type: ignore
        return x

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

try:
    # Gdy moduł ładowany jako analysis.values.classifier
    from analysis.config import LLM_CONFIG  # type: ignore
except Exception:
    try:
        # Gdy sys.path zawiera katalog analysis i import jest jako values.classifier
        from config import LLM_CONFIG  # type: ignore
    except Exception:
        # Fallback minimalny, jak w topic_modeling.batch_classifier
        LLM_CONFIG = {
            'provider': 'openai',
            'model': 'gpt-5-mini',
            'temperature': 0.5,
            'max_tokens': 800,
            'api_key': os.environ.get('OPENAI_API_KEY', ''),
            'base_url': 'https://api.openai.com/v1',
            'default_headers': None,
        }
from .prompt import build_values_system_prompt, build_values_user_prompt


# ==== Pomocnicze ====

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_str(x: Any) -> str:
    return (str(x) if x is not None else '').strip()


def _now_slug() -> Tuple[str, str]:
    dt = datetime.now()
    return dt.strftime('%Y%m%d'), dt.strftime('%H%M%S')


def _setup_logger(run_dir: Optional[Path] = None) -> logging.Logger:
    logger = logging.getLogger("values_llm")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        if run_dir is not None:
            try:
                _ensure_dir(run_dir)
                fh = logging.FileHandler(run_dir / 'llm_values.log', encoding='utf-8')
                fh.setFormatter(fmt)
                logger.addHandler(fh)
            except Exception:
                pass
    return logger


def _load_excel_posts(xlsx_path: Path, gender: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path)
    if 'post_id' not in df.columns:
        if 'id' in df.columns:
            df['post_id'] = df['id']
        else:
            df['post_id'] = pd.RangeIndex(start=1, stop=len(df) + 1, step=1)
    try:
        df['post_id'] = df['post_id'].astype(str)
    except Exception:
        df['post_id'] = df['post_id'].map(lambda x: str(x))
    if 'content' not in df.columns:
        candidates = [c for c in df.columns if str(c).lower() in ('text', 'content', 'post', 'message', 'body')]
        if candidates:
            df.rename(columns={candidates[0]: 'content'}, inplace=True)
        else:
            raise ValueError("W Excelu brakuje kolumny 'content'.")
    df['gender'] = gender
    return df[['post_id', 'content', 'gender']].copy()


def _chunk_iter(lst: List[Any], size: int) -> Iterable[List[Any]]:
    if size <= 0:
        yield lst
        return
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def _is_openrouter() -> bool:
    prov = _safe_str(LLM_CONFIG.get('provider')) if isinstance(LLM_CONFIG, dict) else ''
    base = _safe_str(LLM_CONFIG.get('base_url')) if isinstance(LLM_CONFIG, dict) else ''
    return prov.lower() == 'openrouter' or 'openrouter.ai' in base.lower()


def _get_openai_client() -> Any:
    if OpenAI is None:
        raise RuntimeError("Brak biblioteki openai. Zainstaluj 'openai'.")
    cfg_key = _safe_str(LLM_CONFIG.get('api_key')) if isinstance(LLM_CONFIG, dict) else ''
    env_or = os.environ.get('OPENROUTER_API_KEY', '')
    env_oa = os.environ.get('OPENAI_API_KEY', '')
    api_key = cfg_key or env_or or env_oa
    if not api_key:
        raise RuntimeError("Brak klucza API (OPENROUTER_API_KEY/OPENAI_API_KEY).")
    kwargs: Dict[str, Any] = {'api_key': api_key}
    if _is_openrouter():
        base = _safe_str(LLM_CONFIG.get('base_url'))
        if base:
            kwargs['base_url'] = base
        headers = LLM_CONFIG.get('default_headers') if isinstance(LLM_CONFIG, dict) else None
        if isinstance(headers, dict) and headers:
            kwargs['default_headers'] = headers
    return OpenAI(**kwargs)


def _parse_json_safe(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        s1, s2 = text.find('{'), text.find('[')
        starts = [x for x in (s1, s2) if x != -1]
        if not starts:
            return None
        s = min(starts)
        e1, e2 = text.rfind('}'), text.rfind(']')
        e = max(e1, e2)
        if e > s:
            try:
                return json.loads(text[s:e+1])
            except Exception:
                return None
        return None


def _word_count(text: str) -> int:
    if not text:
        return 0
    try:
        return len(re.findall(r"\w+", text, flags=re.UNICODE))
    except Exception:
        return len((text or '').split())


@dataclass
class ValuesRunParams:
    k_excel_path: Path
    m_excel_path: Path
    output_dir: Path
    batch_size: int = 10
    poll_interval_s: int = 2
    model: str = str(LLM_CONFIG.get('model', 'gpt-5-mini'))
    temperature: float = float(LLM_CONFIG.get('temperature', 0.5))


def _chat_batch(client: Any, params: ValuesRunParams, batch_posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "model": params.model,
        "messages": [
            {"role": "system", "content": build_values_system_prompt()},
            {"role": "user", "content": build_values_user_prompt(batch_posts)},
        ],
    }
    try:
        if _is_openrouter():
            kwargs["temperature"] = params.temperature
    except Exception:
        pass
    return client.chat.completions.create(**kwargs)


def _explode_labels(parsed_items: List[Dict[str, Any]], content_map: Dict[Tuple[str, str], str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for item in parsed_items:
        if not isinstance(item, dict):
            continue
        pid = _safe_str(item.get('post_id'))
        gender = _safe_str(item.get('gender'))
        labels = item.get('labels') or []
        text = content_map.get((pid, gender), '')
        words = _word_count(text)
        if not isinstance(labels, list) or len(labels) == 0:
            rows.append({
                'post_id': pid,
                'gender': gender,
                'value': None,
                'is_present': False,
                'polarity': None,
                'confidence': 0.0,
                'reason_short': None,
                'evidence_span': None,
                'content': text,
                'word_count': words,
            })
            continue
        for lab in labels:
            try:
                rows.append({
                    'post_id': pid,
                    'gender': gender,
                    'value': _safe_str(lab.get('value')) or None,
                    'is_present': bool(lab.get('is_present', False)),
                    'polarity': _safe_str(lab.get('polarity')) or None,
                    'confidence': float(lab.get('confidence', 0.0) or 0.0),
                    'reason_short': _safe_str(lab.get('reason_short')) or None,
                    'evidence_span': _safe_str(lab.get('evidence_span')) or None,
                    'content': text,
                    'word_count': words,
                })
            except Exception:
                continue
    return pd.DataFrame(rows)


def _aggregate(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df['assign'] = df['is_present'].astype(bool).astype(int)
    # Suma słów per płeć
    words_per_gender = df.groupby('gender')['word_count'].sum().rename('total_words').reset_index()
    # Agregacje podstawowe
    base = (
        df[df['assign'] == 1]
        .groupby(['gender', 'value'], dropna=False)
        .agg(
            num_assignments=('assign', 'sum'),
            confidence_sum=('confidence', 'sum'),
            confidence_avg=('confidence', 'mean'),
        )
        .reset_index()
    )
    # Dołącz słowa i policz normę na 1000 słów
    agg = base.merge(words_per_gender, on='gender', how='left')
    agg['per_1000_words'] = agg.apply(
        lambda r: (1000.0 * float(r['num_assignments']) / float(r['total_words'])) if float(r['total_words'] or 0) > 0 else 0.0,
        axis=1
    )
    # Tabela porównawcza i różnice (M-K)
    pivot = agg.pivot_table(index='value', columns='gender', values='per_1000_words', fill_value=0.0)
    if 'M' not in pivot.columns:
        pivot['M'] = 0.0
    if 'K' not in pivot.columns:
        pivot['K'] = 0.0
    pivot['diff_M_minus_K'] = pivot['M'] - pivot['K']
    pivot = pivot.reset_index()
    return agg, pivot


def _save_plots(agg: pd.DataFrame, out_dir: Path) -> List[str]:
    paths: List[str] = []
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return paths
    for g in ['M', 'K']:
        sub = agg[agg['gender'] == g].sort_values('per_1000_words', ascending=False).head(10)
        if sub.empty:
            continue
        plt.figure(figsize=(10, 6))
        plt.barh(sub['value'], sub['per_1000_words'], color='#4f81bd')
        plt.gca().invert_yaxis()
        plt.xlabel('Przypisania na 1000 słów')
        plt.title(f'Top-10 wartości ({g})')
        plt.tight_layout()
        p = out_dir / f"top10_{g}.png"
        plt.savefig(p, dpi=150)
        plt.close()
        paths.append(str(p.resolve()))
    return paths


def _save_examples(df: pd.DataFrame, out_dir: Path) -> str:
    # Przykładowe evidence_span dla każdej wartości (po 3 na płeć, jeśli dostępne)
    rows: List[Dict[str, Any]] = []
    for value, grp in df[df['is_present']].groupby('value'):
        for g in ['M', 'K']:
            sub = grp[grp['gender'] == g].sort_values('confidence', ascending=False).head(3)
            for _, r in sub.iterrows():
                rows.append({
                    'value': value,
                    'gender': g,
                    'post_id': r.get('post_id'),
                    'confidence': float(r.get('confidence') or 0.0),
                    'evidence_span': r.get('evidence_span'),
                    'reason_short': r.get('reason_short'),
                })
    ex_df = pd.DataFrame(rows)
    path = out_dir / 'examples_evidence.csv'
    ex_df.to_csv(path, index=False)
    return str(path.resolve())


def run_values_classification(
    k_excel_path: str = "data/topics/results/20250827/K/ALL/155429_038844/examples/POLITYKA_KOBIETY.xlsx",
    m_excel_path: str = "data/topics/results/20250827/M/ALL/194903_560595/examples/POLITYKA_MEZCZYZNI.xlsx",
    batch_size: int = 10,
    show_progress: bool = True,
) -> Dict[str, Any]:
    k_xlsx = Path(k_excel_path)
    m_xlsx = Path(m_excel_path)
    if not k_xlsx.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku (K): {k_xlsx}")
    if not m_xlsx.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku (M): {m_xlsx}")

    date_str, time_str = _now_slug()
    run_dir = Path("data/topics/results") / f"llm_values_{date_str}_{time_str}"
    _ensure_dir(run_dir)
    logger = _setup_logger(run_dir)
    logger.info("Start klasyfikacji wartości (M vs K)")

    # Wczytaj korpusy
    df_k = _load_excel_posts(k_xlsx, gender='K')
    df_m = _load_excel_posts(m_xlsx, gender='M')
    logger.info(f"Wczytano: K={len(df_k)} | M={len(df_m)}")

    # Mapy treści dla późniejszego dołączenia
    content_map: Dict[Tuple[str, str], str] = {}
    for _, r in pd.concat([df_k, df_m], ignore_index=True).iterrows():
        content_map[(str(r['post_id']), str(r['gender']))] = _safe_str(r['content'])

    client = _get_openai_client()
    params = ValuesRunParams(k_excel_path=k_xlsx, m_excel_path=m_xlsx, output_dir=run_dir, batch_size=batch_size)

    all_parsed: List[Dict[str, Any]] = []
    # Przetwarzaj oddzielnie K i M
    for gender, df in [('K', df_k), ('M', df_m)]:
        g_dir = run_dir / gender
        _ensure_dir(g_dir)
        records = df.to_dict(orient='records')
        chunks = list(_chunk_iter(records, batch_size))
        logger.info(f"{gender}: batchy={len(chunks)} (size={batch_size})")
        iterable = tqdm(range(len(chunks)), desc=f"{gender} batches", unit="batch", disable=not show_progress)
        for i in iterable:
            idx = i
            chunk = chunks[idx]
            posts = [
                {
                    'post_id': _safe_str(r.get('post_id')),
                    'gender': _safe_str(r.get('gender')),
                    'content': _safe_str(r.get('content')),
                }
                for r in chunk
            ]
            logger.info(f"[{gender}] Batch {idx+1}/{len(chunks)}: {len(posts)} postów – wysyłam do LLM")
            try:
                resp = _chat_batch(client, params, posts)
                raw_body = {
                    'id': getattr(resp, 'id', None),
                    'model': getattr(resp, 'model', None),
                    'choices': [
                        {
                            'message': {
                                'role': 'assistant',
                                'content': _safe_str(getattr(resp.choices[0].message, 'content', '')) if getattr(resp, 'choices', None) else ''
                            },
                            'finish_reason': getattr(resp.choices[0], 'finish_reason', None) if getattr(resp, 'choices', None) else None,
                        }
                    ] if getattr(resp, 'choices', None) else [],
                }
                content_txt = _safe_str(raw_body['choices'][0]['message'].get('content')) if raw_body.get('choices') else ''
                parsed = _parse_json_safe(content_txt) if content_txt else None
                logger.info(f"[{gender}] Batch {idx+1}/{len(chunks)}: odpowiedź OK, parsed={'list' if isinstance(parsed, list) else type(parsed).__name__}")
            except Exception as exc:
                raw_body = {'error': str(exc)}
                parsed = None
                logger.warning(f"[{gender}] Batch {idx+1}/{len(chunks)}: błąd wywołania LLM: {exc}")

            # Zapisz artefakty
            (g_dir / f"batch_{idx:04d}_input.json").write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding='utf-8')
            (g_dir / f"batch_{idx:04d}_raw.json").write_text(json.dumps(raw_body, ensure_ascii=False, indent=2), encoding='utf-8')
            if parsed is not None:
                (g_dir / f"batch_{idx:04d}_results.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding='utf-8')
                if isinstance(parsed, list):
                    for it in parsed:
                        if isinstance(it, dict):
                            all_parsed.append(it)
            logger.info(f"[{gender}] Batch {idx+1}/{len(chunks)}: zapisano artefakty")
            time.sleep(0.05)

    # Zbierz i eksploduj etykiety
    df_labels = _explode_labels(all_parsed, content_map)
    (run_dir / 'predictions.csv').write_text(df_labels.to_csv(index=False), encoding='utf-8')
    logger.info("Zapisano predictions.csv")

    # Agregacja i raporty
    agg, pivot = _aggregate(df_labels)
    agg_path = run_dir / 'aggregates.csv'
    pivot_path = run_dir / 'comparison_M_vs_K.csv'
    agg.to_csv(agg_path, index=False)
    pivot.to_csv(pivot_path, index=False)
    logger.info("Zapisano agregaty i porównanie (CSV)")

    # Wykresy
    plot_paths = _save_plots(agg, run_dir)
    if plot_paths:
        logger.info(f"Zapisano wykresy: {len(plot_paths)}")

    # Przykłady evidence
    examples_path = _save_examples(df_labels, run_dir)
    logger.info("Zapisano przykłady evidence")

    # Excel z surowymi danymi i agregatami
    excel_out = run_dir / 'values_report.xlsx'
    with pd.ExcelWriter(excel_out, engine='openpyxl') as writer:
        # Surowe posty + predykcje (rozeksplodowane)
        df_labels.to_excel(writer, index=False, sheet_name='predictions')
        agg.to_excel(writer, index=False, sheet_name='aggregates')
        pivot.to_excel(writer, index=False, sheet_name='comparison')
        # Przykłady
        try:
            pd.read_csv(examples_path).to_excel(writer, index=False, sheet_name='examples')
        except Exception:
            pass
    logger.info("Zapisano Excel z raportem")

    result = {
        'run_dir': str(run_dir.resolve()),
        'predictions_csv': str((run_dir / 'predictions.csv').resolve()),
        'aggregates_csv': str(agg_path.resolve()),
        'comparison_csv': str(pivot_path.resolve()),
        'plots': plot_paths,
        'examples_csv': examples_path,
        'excel_out_path': str(excel_out.resolve()),
        'total_posts_K': int(len(df_k)),
        'total_posts_M': int(len(df_m)),
        'batch_size': int(batch_size),
    }
    (run_dir / 'state.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


__all__ = [
    'run_values_classification',
]



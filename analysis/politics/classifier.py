#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Klasyfikacja preferencji wyborczych (partie i liderzy) per płeć (K vs M).

Wejście: dwa pliki Excel (K i M) z kolumnami: content (wymagana), post_id (opcjonalna).
Batching: dokładnie 10 postów w jednym wywołaniu.
Wyjście: katalog run_dir z artefaktami (input, raw, results), CSV i Excel z agregatami.

Schemat odpowiedzi modelu (na 10 postów):
[
  {"post_id":"...","results":[{"target_type":"party|leader","canonical_name":"...","surface_form":"...","evidence_span":"...","sentiment_label":"bardzo negatywny|negatywny|neutralny|pozytywny|bardzo pozytywny","sentiment_score":-2|-1|0|1|2,"confidence":0.00-1.00}]}
]
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import logging

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

try:
    from analysis.config import LLM_CONFIG  # type: ignore
except Exception:
    LLM_CONFIG = {
        'provider': 'openai',
        'model': 'gpt-5-mini',
        'temperature': 0.3,
        'max_tokens': 800,
        'api_key': os.environ.get('OPENAI_API_KEY', ''),
        'base_url': 'https://api.openai.com/v1',
        'default_headers': None,
    }

from .prompt import build_system_prompt, build_user_prompt


# ====== Utils ======

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_str(x: Any) -> str:
    return (str(x) if x is not None else '').strip()


def _now_slug() -> Tuple[str, str]:
    dt = datetime.now()
    return dt.strftime('%Y%m%d'), dt.strftime('%H%M%S')


def _setup_logger(run_dir: Optional[Path] = None) -> logging.Logger:
    logger = logging.getLogger("politics_llm")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        if run_dir is not None:
            try:
                _ensure_dir(run_dir)
                fh = logging.FileHandler(run_dir / 'llm_politics.log', encoding='utf-8')
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


@dataclass
class PoliticsRunParams:
    k_excel_path: Path
    m_excel_path: Path
    output_dir: Path
    batch_size: int = 10
    temperature: float = float(LLM_CONFIG.get('temperature', 0.3))
    model: str = str(LLM_CONFIG.get('model', 'gpt-5-mini'))


def _chat_batch(client: Any, params: PoliticsRunParams, batch_posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "model": params.model,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(batch_posts)},
        ],
    }
    try:
        if _is_openrouter():
            kwargs["temperature"] = params.temperature
    except Exception:
        pass
    return client.chat.completions.create(**kwargs)


def _explode_results(parsed_list: List[Dict[str, Any]], gender: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for item in parsed_list or []:
        if not isinstance(item, dict):
            continue
        pid = _safe_str(item.get('post_id'))
        results = item.get('results') or []
        if not isinstance(results, list) or len(results) == 0:
            rows.append({
                'post_id': pid,
                'gender': gender,
                'target_type': None,
                'canonical_name': None,
                'surface_form': None,
                'evidence_span': None,
                'sentiment_label': None,
                'sentiment_score': 0,
                'confidence': 0.0,
            })
            continue
        for r in results:
            try:
                rows.append({
                    'post_id': pid,
                    'gender': gender,
                    'target_type': _safe_str(r.get('target_type')) or None,
                    'canonical_name': _safe_str(r.get('canonical_name')) or None,
                    'surface_form': _safe_str(r.get('surface_form')) or None,
                    'evidence_span': _safe_str(r.get('evidence_span')) or None,
                    'sentiment_label': _safe_str(r.get('sentiment_label')) or None,
                    'sentiment_score': int(r.get('sentiment_score') if r.get('sentiment_score') is not None else 0),
                    'confidence': float(r.get('confidence') or 0.0),
                })
            except Exception:
                continue
    return pd.DataFrame(rows)


def _aggregate(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df['assign'] = df['sentiment_label'].notna().astype(int)
    # per cel i płeć: liczba, średni score, rozkład confidence
    by_target = (
        df[df['assign'] == 1]
        .groupby(['gender', 'canonical_name'], dropna=False)
        .agg(
            num_assignments=('assign', 'sum'),
            avg_score=('sentiment_score', 'mean'),
            avg_confidence=('confidence', 'mean'),
        )
        .reset_index()
    )
    # Pivot M vs K po avg_score (można też po num_assignments)
    pivot = by_target.pivot_table(index='canonical_name', columns='gender', values='avg_score', fill_value=0.0)
    if 'M' not in pivot.columns:
        pivot['M'] = 0.0
    if 'K' not in pivot.columns:
        pivot['K'] = 0.0
    pivot['diff_M_minus_K'] = pivot['M'] - pivot['K']
    pivot = pivot.reset_index()
    return by_target, pivot


def run_politics_preference_classification(
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
    run_dir = Path("data/topics/results") / f"llm_politics_{date_str}_{time_str}"
    _ensure_dir(run_dir)
    logger = _setup_logger(run_dir)
    logger.info("Start klasyfikacji preferencji (K vs M)")

    # Wczytaj dane
    df_k = _load_excel_posts(k_xlsx, 'K')
    df_m = _load_excel_posts(m_xlsx, 'M')
    logger.info(f"Wczytano: K={len(df_k)} | M={len(df_m)}")

    client = _get_openai_client()
    params = PoliticsRunParams(k_excel_path=k_xlsx, m_excel_path=m_xlsx, output_dir=run_dir, batch_size=batch_size)

    import itertools
    try:
        from tqdm import tqdm  # type: ignore
    except Exception:
        def tqdm(x, **kwargs):  # type: ignore
            return x

    all_rows: List[pd.DataFrame] = []
    for gender, df in [('K', df_k), ('M', df_m)]:
        g_dir = run_dir / gender
        _ensure_dir(g_dir)
        records = df.to_dict(orient='records')
        chunks = list(_chunk_iter(records, batch_size))
        logger.info(f"{gender}: batchy={len(chunks)} (size={batch_size})")
        for idx in tqdm(range(len(chunks)), desc=f"{gender} batches", unit="batch", disable=not show_progress):
            chunk = chunks[idx]
            posts = [
                {
                    'post_id': _safe_str(r.get('post_id')),
                    'gender': gender,
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

            # Artefakty
            (g_dir / f"batch_{idx:04d}_input.json").write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding='utf-8')
            (g_dir / f"batch_{idx:04d}_raw.json").write_text(json.dumps(raw_body, ensure_ascii=False, indent=2), encoding='utf-8')
            if parsed is not None:
                (g_dir / f"batch_{idx:04d}_results.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding='utf-8')
                if isinstance(parsed, list):
                    df_expanded = _explode_results(parsed, gender)
                    all_rows.append(df_expanded)
            logger.info(f"[{gender}] Batch {idx+1}/{len(chunks)}: zapisano artefakty")

    # Zbierz wyniki i zapisz
    df_all = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame([])
    (run_dir / 'predictions.csv').write_text(df_all.to_csv(index=False), encoding='utf-8')
    logger.info("Zapisano predictions.csv")

    # Agregacja
    agg, pivot = _aggregate(df_all)
    agg_path = run_dir / 'aggregates.csv'
    pivot_path = run_dir / 'comparison_M_vs_K.csv'
    agg.to_csv(agg_path, index=False)
    pivot.to_csv(pivot_path, index=False)
    logger.info("Zapisano agregaty i porównanie (CSV)")

    # Excel
    excel_out = run_dir / 'politics_report.xlsx'
    with pd.ExcelWriter(excel_out, engine='openpyxl') as writer:
        df_all.to_excel(writer, index=False, sheet_name='predictions')
        agg.to_excel(writer, index=False, sheet_name='aggregates')
        pivot.to_excel(writer, index=False, sheet_name='comparison')

    result = {
        'run_dir': str(run_dir.resolve()),
        'predictions_csv': str((run_dir / 'predictions.csv').resolve()),
        'aggregates_csv': str(agg_path.resolve()),
        'comparison_csv': str(pivot_path.resolve()),
        'excel_out_path': str(excel_out.resolve()),
        'total_posts_K': int(len(df_k)),
        'total_posts_M': int(len(df_m)),
        'batch_size': int(batch_size),
    }
    (run_dir / 'state.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


__all__ = [
    'run_politics_preference_classification',
]



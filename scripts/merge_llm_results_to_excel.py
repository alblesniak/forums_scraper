#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scalanie wyników LLM z batch_*_results.json do Excela wejściowego.

Przykład użycia:

  uv run python scripts/merge_llm_results_to_excel.py \
    --runs /Users/alb/repos/forums_scraper/data/topics/results/llm_batch_20250902_141627_b05d35 \
    --excel-in /Users/alb/repos/forums_scraper/data/topics/results/20250827/M/ALL/194903_560595/examples/POLITYKA_MEZCZYZNI.xlsx \
    --excel-out /Users/alb/repos/forums_scraper/data/topics/results/llm_batch_20250902_141627_b05d35/labeled_manual_POLITYKA_MEZCZYZNI.xlsx

Możesz podać wiele --runs (powtarzany argument) – wyniki zostaną zebrane i scalone.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
from typing import Dict, List

import pandas as pd


def load_llm_rows_from_run_dir(run_dir: Path) -> List[Dict]:
    rows: List[Dict] = []
    for p in sorted(run_dir.glob("batch_*_results.json")):
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in arr:
            parsed = item.get("parsed")
            if not isinstance(parsed, dict):
                continue
            pid = str(parsed.get("post_id", "")).strip()
            if not pid:
                continue
            summary = (parsed.get("summary") or "").strip()
            cats = []
            for ch in parsed.get("choices") or []:
                mid = str(ch.get("main_id") or "").strip()
                sid = str(ch.get("sub_id") or "").strip()
                ml = str(ch.get("main_label") or "").strip()
                sl = str(ch.get("sub_label") or "").strip()
                cats.append(f"{mid}|{sid}|{ml}|{sl}")
            rows.append({
                "post_id": pid,
                "llm_summary": summary,
                "llm_categories": "; ".join(cats)
            })
    return rows


def merge_to_excel(run_dirs: List[Path], excel_in: Path, excel_out: Path) -> Path:
    all_rows: List[Dict] = []
    for rd in run_dirs:
        all_rows.extend(load_llm_rows_from_run_dir(rd))

    df_llm = pd.DataFrame(all_rows)
    # Deduplicate per post_id, take last occurrence
    if not df_llm.empty:
        df_llm = (df_llm.groupby("post_id", as_index=False)
                  .agg({"llm_summary": "last", "llm_categories": "last"}))

    df_in = pd.read_excel(excel_in)
    if "post_id" not in df_in.columns:
        if "id" in df_in.columns:
            df_in["post_id"] = df_in["id"]
        else:
            df_in["post_id"] = pd.RangeIndex(start=1, stop=len(df_in) + 1, step=1)
    df_in["post_id"] = df_in["post_id"].astype(str)

    if not df_llm.empty:
        df_out = df_in.merge(df_llm, on="post_id", how="left")
    else:
        df_out = df_in.copy()

    excel_out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(excel_out, engine="openpyxl") as w:
        df_out.to_excel(w, index=False, sheet_name="labeled")
    return excel_out


def main() -> int:
    ap = argparse.ArgumentParser(description="Scalanie wyników LLM do Excela")
    ap.add_argument("--runs", action="append", required=True,
                    help="Katalog run_dir (llm_batch_...), można podać wiele razy")
    ap.add_argument("--excel-in", required=True, help="Ścieżka do wejściowego Excela")
    ap.add_argument("--excel-out", required=False, help="Ścieżka do wyjściowego Excela")
    args = ap.parse_args()

    run_dirs = [Path(p) for p in args.runs]
    for rd in run_dirs:
        if not rd.exists():
            raise FileNotFoundError(f"Brak run_dir: {rd}")

    excel_in = Path(args.excel_in)
    if not excel_in.exists():
        raise FileNotFoundError(f"Brak pliku Excela: {excel_in}")

    if args.excel_out:
        excel_out = Path(args.excel_out)
    else:
        # Domyślna lokalizacja: do pierwszego run_dir
        excel_out = run_dirs[0] / f"labeled_manual_{excel_in.name}"

    out_path = merge_to_excel(run_dirs, excel_in, excel_out)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



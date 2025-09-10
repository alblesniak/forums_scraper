#!/usr/bin/env python3
import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib

# Ustaw czcionkę obsługującą polskie znaki i spójny styl
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["figure.dpi"] = 120
matplotlib.rcParams["axes.grid"] = True
matplotlib.rcParams["grid.alpha"] = 0.15
matplotlib.rcParams["grid.linestyle"] = "-"
matplotlib.rcParams["axes.edgecolor"] = "#E0E0E0"
matplotlib.rcParams["axes.linewidth"] = 0.8

import matplotlib.pyplot as plt

PRIMARY_COLOR = "#2F4F4F"
ACCENT_COLOR = "#7AA6A6"
BAR_COLOR_MAIN = "#2F4F4F"
BAR_COLOR_SUB = "#7AA6A6"
TITLE_COLOR = "#1F2D2D"
SUBTITLE_COLOR = "#4D6666"
TEXT_COLOR = "#222222"


@dataclass
class CategoryEntry:
    main_id: str
    sub_id: str
    main_name: str
    sub_name: str


def load_taxonomy(taxonomy_path: str) -> Dict[str, Dict]:
    with open(taxonomy_path, "r", encoding="utf-8") as f:
        taxonomy = json.load(f)
    # Normalizuj klucze do str
    normalized = {}
    for main_id, node in taxonomy.items():
        mid = str(main_id)
        node_children = node.get("children", {}) or {}
        normalized_children = {str(k): v for k, v in node_children.items()}
        normalized[mid] = {"name": node.get("name", mid), "children": normalized_children}
    return normalized


def parse_llm_categories(value: Optional[str]) -> List[CategoryEntry]:
    entries: List[CategoryEntry] = []
    if not isinstance(value, str) or not value.strip():
        return entries
    parts = [p.strip() for p in value.split(";") if p.strip()]
    for p in parts:
        # Oczekiwany format: main_id|sub_id|main_name|sub_name
        fields = [f.strip() for f in p.split("|")]
        if len(fields) < 4:
            if len(fields) == 2:
                main_id, sub_id = fields
                entries.append(CategoryEntry(main_id=main_id, sub_id=sub_id, main_name=main_id, sub_name=sub_id))
            continue
        entries.append(CategoryEntry(main_id=fields[0], sub_id=fields[1], main_name=fields[2], sub_name=fields[3]))
    return entries


def compute_counts(df: pd.DataFrame, taxonomy: Dict[str, Dict]) -> Tuple[Dict[str, int], Dict[str, Dict[str, int]]]:
    main_counts: Dict[str, int] = {mid: 0 for mid in taxonomy.keys()}
    sub_counts: Dict[str, Dict[str, int]] = {mid: {sid: 0 for sid in (taxonomy[mid].get("children", {}) or {}).keys()} for mid in taxonomy.keys()}

    for raw in df.get("llm_categories", []):
        entries = parse_llm_categories(raw)
        for e in entries:
            if e.main_id in main_counts:
                main_counts[e.main_id] += 1
                sub_counts.setdefault(e.main_id, {})
                if e.sub_id not in sub_counts[e.main_id]:
                    sub_counts[e.main_id][e.sub_id] = 0
                sub_counts[e.main_id][e.sub_id] += 1
            else:
                main_counts.setdefault(e.main_id, 0)
                main_counts[e.main_id] += 1
                sub_counts.setdefault(e.main_id, {})
                sub_counts[e.main_id].setdefault(e.sub_id, 0)
                sub_counts[e.main_id][e.sub_id] += 1

    return main_counts, sub_counts


def collect_summaries_by_subcategory(df: pd.DataFrame) -> Dict[str, List[str]]:
    bucket: Dict[str, List[Tuple[float, str]]] = {}
    for _, row in df.iterrows():
        cats_raw = row.get("llm_categories")
        if not isinstance(cats_raw, str) or not cats_raw.strip():
            continue
        summary = str(row.get("llm_summary", "")).strip()
        if not summary:
            continue
        score = float(row.get("word_score", 0.0) or 0.0)
        entries = parse_llm_categories(cats_raw)
        for e in entries:
            bucket.setdefault(e.sub_id, [])
            bucket[e.sub_id].append((score, summary))

    result: Dict[str, List[str]] = {}
    for sub_id, items in bucket.items():
        items_sorted = sorted(items, key=lambda x: x[0], reverse=True)
        seen: set = set()
        unique_texts: List[str] = []
        for _, txt in items_sorted:
            if not txt:
                continue
            key = txt.strip()
            if key in seen:
                continue
            seen.add(key)
            unique_texts.append(txt)
        result[sub_id] = unique_texts
    return result


def save_main_categories_chart(path: Path, taxonomy: Dict[str, Dict], main_counts: Dict[str, int]) -> None:
    items = [(mid, taxonomy.get(mid, {}).get("name", mid), main_counts.get(mid, 0)) for mid in main_counts.keys()]
    items.sort(key=lambda x: x[2], reverse=True)

    labels = [name for _, name, _ in items]
    values = [v for _, _, v in items]

    fig, ax = plt.subplots(figsize=(10, 8))
    y_pos = np.arange(len(labels))
    bars = ax.barh(y_pos, values, color=BAR_COLOR_MAIN, edgecolor="#E8EDED")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, color=TEXT_COLOR)
    ax.invert_yaxis()
    ax.set_xlabel("Liczba przypisań", color=SUBTITLE_COLOR)
    ax.set_title("Kategorie główne (malejąco)", color=TITLE_COLOR, loc="left")

    max_v = max(values) if values else 0
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + max(1, 0.01 * (max_v or 1)), bar.get_y() + bar.get_height() / 2,
                str(v), va="center", fontsize=9, color=TEXT_COLOR)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def save_subcategories_chart(path: Path, main_name: str, sub_items: List[Tuple[str, str, int]]) -> None:
    sub_items = sub_items[:25]
    labels = [name for _, name, _ in sub_items]
    values = [v for _, _, v in sub_items]

    fig, ax = plt.subplots(figsize=(10, 8))
    y_pos = np.arange(len(labels))
    bars = ax.barh(y_pos, values, color=BAR_COLOR_SUB, edgecolor="#E8EDED")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, color=TEXT_COLOR)
    ax.invert_yaxis()
    ax.set_xlabel("Liczba przypisań", color=SUBTITLE_COLOR)
    ax.set_title(f"{main_name} – podkategorie (malejąco)", color=TITLE_COLOR, loc="left")

    max_v = max(values) if values else 0
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + max(1, 0.01 * (max_v or 1)), bar.get_y() + bar.get_height() / 2,
                str(v), va="center", fontsize=9, color=TEXT_COLOR)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def build_markdown(
    excel_path: str,
    taxonomy_path: str,
    output_md_path: str,
    assets_dir: Optional[str] = None,
) -> str:
    df = pd.read_excel(excel_path)

    required_cols = {"llm_categories", "llm_summary"}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Brak wymaganych kolumn w Excelu: {missing}")

    taxonomy = load_taxonomy(taxonomy_path)
    main_counts, sub_counts = compute_counts(df, taxonomy)
    summaries_by_sub = collect_summaries_by_subcategory(df)

    md_path = Path(output_md_path)
    md_dir = md_path.parent
    md_dir.mkdir(parents=True, exist_ok=True)

    # Katalog na obrazy
    if assets_dir:
        assets = Path(assets_dir)
    else:
        assets = md_dir / (md_path.stem + "_assets")
    assets.mkdir(parents=True, exist_ok=True)

    # Rysunek: kategorie główne
    main_chart_path = assets / "main_categories.png"
    save_main_categories_chart(main_chart_path, taxonomy, main_counts)

    # Sortuj kategorie główne malejąco i przygotuj subkategorie
    main_items: List[Tuple[str, str, int]] = [
        (mid, taxonomy.get(mid, {}).get("name", mid), int(main_counts.get(mid, 0))) for mid in main_counts.keys()
    ]
    main_items.sort(key=lambda x: x[2], reverse=True)

    lines: List[str] = []
    title = "Analiza tematu POLITYKA na katolickich forach internetowych (posty pisane przez mężczyzn)"
    lines.append(f"# {title}")
    lines.append("")
    lines.append("![Kategorie główne](" + os.path.relpath(main_chart_path, start=md_dir) + ")")
    lines.append("")

    for mid, main_name, _ in main_items:
        children = taxonomy.get(mid, {}).get("children", {}) or {}
        sub_items: List[Tuple[str, str, int]] = []
        for sid, count in (sub_counts.get(mid, {}) or {}).items():
            sname = children.get(sid, {}).get("name") if isinstance(children.get(sid), dict) else None
            if not sname:
                sname = sid
            sub_items.append((sid, str(sname), int(count)))
        sub_items.sort(key=lambda x: x[2], reverse=True)

        # Sekcja główna
        lines.append(f"## {main_name}")
        lines.append("")

        # Wykres podkategorii
        sub_chart_path = assets / f"subcategories_{mid.replace('.', '_')}.png"
        save_subcategories_chart(sub_chart_path, main_name, sub_items)
        lines.append("![Podkategorie – " + main_name + "](" + os.path.relpath(sub_chart_path, start=md_dir) + ")")
        lines.append("")

        # Podsekcje: przykłady dla każdej podkategorii (do 10)
        for sid, sname, _ in sub_items:
            examples = summaries_by_sub.get(sid, [])[:10]
            lines.append(f"### {sname}")
            lines.append("")
            if not examples:
                lines.append("_(Brak streszczeń)_")
                lines.append("")
                continue
            for ex in examples:
                # prosta sanitacja linii markdown
                safe = ex.replace("\r", " ").replace("\n", " ").strip()
                lines.append(f"- {safe}")
            lines.append("")

    md_text = "\n".join(lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    return str(md_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generuje raport Markdown z wykresami PNG dla tematu POLITYKA (M)")
    parser.add_argument("--excel", required=True, help="Ścieżka do XLSX z kolumnami llm_categories i llm_summary")
    parser.add_argument("--taxonomy", required=True, help="Ścieżka do taxonomy.json")
    parser.add_argument("--output", required=False, help="Ścieżka wyjściowa pliku .md")
    parser.add_argument("--assets-dir", required=False, help="Katalog na zasoby graficzne (PNG)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    excel_path = os.path.abspath(args.excel)
    taxonomy_path = os.path.abspath(args.taxonomy)
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Nie znaleziono pliku Excel: {excel_path}")
    if not os.path.exists(taxonomy_path):
        raise FileNotFoundError(f"Nie znaleziono pliku taxonomy.json: {taxonomy_path}")

    default_md = str(Path(excel_path).parent / "POLITYKA_MEZCZYZNI_raport.md")
    output_md = os.path.abspath(args.output) if args.output else default_md
    assets_dir = os.path.abspath(args.assets_dir) if args.assets_dir else None

    result = build_markdown(
        excel_path=excel_path,
        taxonomy_path=taxonomy_path,
        output_md_path=output_md,
        assets_dir=assets_dir,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

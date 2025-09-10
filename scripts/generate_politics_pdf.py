#!/usr/bin/env python3
import argparse
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib

# Minimalistyczny styl globalny (A4 portret, stonowane kolory, czyste osie)
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["figure.figsize"] = (8.27, 11.69)  # A4 portret w calach
matplotlib.rcParams["axes.titlesize"] = 14
matplotlib.rcParams["axes.labelsize"] = 11
matplotlib.rcParams["xtick.labelsize"] = 9
matplotlib.rcParams["ytick.labelsize"] = 9
matplotlib.rcParams["axes.grid"] = True
matplotlib.rcParams["grid.alpha"] = 0.15
matplotlib.rcParams["grid.linestyle"] = "-"
matplotlib.rcParams["axes.edgecolor"] = "#E0E0E0"
matplotlib.rcParams["axes.linewidth"] = 0.8
matplotlib.rcParams["figure.dpi"] = 120
matplotlib.rcParams["savefig.bbox"] = "tight"
matplotlib.rcParams["savefig.pad_inches"] = 0.2

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import textwrap


PRIMARY_COLOR = "#2F4F4F"  # ciemny szaroniebieski
ACCENT_COLOR = "#7AA6A6"   # delikatny akcent
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
            # Spróbuj obsłużyć brakujące nazwy (rzadki przypadek)
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
                # sub_id w taxonomy może lub nie istnieć (gdy pojawiła się nowa etykieta) – dodaj dynamicznie
                sub_counts.setdefault(e.main_id, {})
                if e.sub_id not in sub_counts[e.main_id]:
                    sub_counts[e.main_id][e.sub_id] = 0
                sub_counts[e.main_id][e.sub_id] += 1
            else:
                # Nieznana główna kategoria – rejestruj mimo wszystko
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
        summaries = str(row.get("llm_summary", "")).strip()
        if not summaries:
            continue
        score = float(row.get("word_score", 0.0) or 0.0)
        entries = parse_llm_categories(cats_raw)
        for e in entries:
            bucket.setdefault(e.sub_id, [])
            # Przechowuj wg score, by potem wybrać najlepsze
            bucket[e.sub_id].append((score, summaries))

    # Posortuj i zredukuj do listy tekstów (unikalne) dla każdej subkategorii
    result: Dict[str, List[str]] = {}
    for sub_id, items in bucket.items():
        # sort desc by score
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


def wrap_text(text: str, max_chars: int = 92) -> str:
    return "\n".join(textwrap.fill(line, width=max_chars) for line in text.splitlines() if line.strip())


def add_footer(fig: plt.Figure, text: str = "Źródło: fora katolickie; klasyfikacja LLM; wizualizacja własna") -> None:
    fig.text(0.5, 0.02, text, ha="center", va="center", fontsize=8, color=SUBTITLE_COLOR)


def render_title_slide(pdf: PdfPages, title: str, subtitle: Optional[str] = None) -> None:
    fig = plt.figure()  # rozmiar A4 portret z rcParams
    ax = fig.add_subplot(111)
    ax.axis("off")

    ax.text(0.5, 0.65, title, ha="center", va="center", fontsize=22, fontweight="bold", color=TITLE_COLOR)
    if subtitle:
        ax.text(0.5, 0.55, subtitle, ha="center", va="center", fontsize=12, color=SUBTITLE_COLOR)

    # Delikatna linia pod tytułem
    ax.plot([0.2, 0.8], [0.5, 0.5], color=ACCENT_COLOR, lw=1)

    add_footer(fig)
    pdf.savefig(fig)
    plt.close(fig)


def render_main_categories_slide(pdf: PdfPages, taxonomy: Dict[str, Dict], main_counts: Dict[str, int]) -> None:
    # Sortuj malejąco po liczbie
    items = [(mid, taxonomy.get(mid, {}).get("name", mid), main_counts.get(mid, 0)) for mid in main_counts.keys()]
    items.sort(key=lambda x: x[2], reverse=True)

    labels = [f"{name}" for _, name, _ in items]
    values = [v for _, _, v in items]

    fig, ax = plt.subplots()
    y_pos = np.arange(len(labels))
    bars = ax.barh(y_pos, values, color=BAR_COLOR_MAIN, edgecolor="#E8EDED")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, color=TEXT_COLOR)
    ax.invert_yaxis()
    ax.set_xlabel("Liczba przypisań", color=SUBTITLE_COLOR)
    ax.set_title("Kategorie główne (malejąco)", color=TITLE_COLOR, loc="left")

    # Etykiety liczb na końcach słupków
    max_v = max(values) if values else 0
    for i, (bar, v) in enumerate(zip(bars, values)):
        ax.text(bar.get_width() + max(1, 0.01 * (max_v or 1)), bar.get_y() + bar.get_height() / 2,
                str(v), va="center", fontsize=9, color=TEXT_COLOR)

    add_footer(fig)
    pdf.savefig(fig)
    plt.close(fig)


def render_subcategories_slide(pdf: PdfPages, main_name: str, sub_items: List[Tuple[str, str, int]]) -> None:
    # sub_items: list of (sub_id, sub_name, count), already sorted desc
    fig, ax = plt.subplots()
    if not sub_items:
        ax.axis("off")
        ax.text(0.5, 0.5, f"Brak podkategorii dla: {main_name}", ha="center", va="center", fontsize=12, color=TEXT_COLOR)
        add_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)
        return

    # Ogranicz do top N (np. 25) aby uniknąć przeładowania
    sub_items = sub_items[:25]

    labels = [name for _, name, _ in sub_items]
    values = [v for _, _, v in sub_items]

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

    add_footer(fig)
    pdf.savefig(fig)
    plt.close(fig)


def render_examples_slide(pdf: PdfPages, header: str, examples: List[str], max_examples: int = 10) -> None:
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.axis("off")

    # Nagłówek slajdu
    ax.text(0.02, 0.97, header, ha="left", va="top", fontsize=13, fontweight="bold", color=TITLE_COLOR)
    ax.plot([0.02, 0.98], [0.94, 0.94], color=ACCENT_COLOR, lw=0.8)

    # Treść – kolumna jednolita
    y = 0.90
    line_step = 0.06
    shown = 0

    for idx, example in enumerate(examples[:max_examples], start=1):
        wrapped = wrap_text(example, max_chars=110)
        # Multilinia: wypisz linia po linii, aby kontrolować odstępy
        for j, line in enumerate(wrapped.split("\n")):
            prefix = f"{idx}. " if j == 0 else "   "
            ax.text(0.04, y, prefix + line, ha="left", va="top", fontsize=10, color=TEXT_COLOR)
            y -= line_step
            if y < 0.07:
                break
        shown += 1
        if y < 0.07:
            break

    if shown == 0:
        ax.text(0.5, 0.5, "Brak streszczeń do pokazania", ha="center", va="center", fontsize=10, color=SUBTITLE_COLOR)

    add_footer(fig)
    pdf.savefig(fig)
    plt.close(fig)


def build_pdf(
    excel_path: str,
    taxonomy_path: str,
    output_path: str,
    title: str,
) -> str:
    df = pd.read_excel(excel_path)

    required_cols = {"llm_categories", "llm_summary"}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Brak wymaganych kolumn w Excelu: {missing}")

    taxonomy = load_taxonomy(taxonomy_path)
    main_counts, sub_counts = compute_counts(df, taxonomy)
    summaries_by_sub = collect_summaries_by_subcategory(df)

    # Posortuj kategorie główne malejąco
    main_items: List[Tuple[str, str, int]] = [
        (mid, taxonomy.get(mid, {}).get("name", mid), int(main_counts.get(mid, 0))) for mid in main_counts.keys()
    ]
    main_items.sort(key=lambda x: x[2], reverse=True)

    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with PdfPages(output_path) as pdf:
        # Slajd tytułowy
        render_title_slide(pdf, title=title, subtitle=None)
        # Slajd z kategoriami głównymi
        render_main_categories_slide(pdf, taxonomy, main_counts)

        # Dla każdej kategorii głównej (malejąco)
        for mid, main_name, _ in main_items:
            # Zbierz podkategorie wraz z nazwami
            children = taxonomy.get(mid, {}).get("children", {}) or {}
            # sub_counts może zawierać podkategorie spoza taxonomy – scal nazwy
            sub_items: List[Tuple[str, str, int]] = []
            for sid, count in (sub_counts.get(mid, {}) or {}).items():
                sname = children.get(sid, {}).get("name") if isinstance(children.get(sid), dict) else None
                if not sname:
                    sname = sid
                sub_items.append((sid, str(sname), int(count)))
            # Sort malejąco i wyrenderuj
            sub_items.sort(key=lambda x: x[2], reverse=True)
            render_subcategories_slide(pdf, main_name=main_name, sub_items=sub_items)

            # Slajdy z przykładami dla każdej podkategorii
            for sid, sname, _ in sub_items:
                examples = summaries_by_sub.get(sid, [])
                header = f"{main_name} / {sname} – przykłady (do 10)"
                render_examples_slide(pdf, header=header, examples=examples, max_examples=10)

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generuje raport PDF dla tematu POLITYKA (M)")
    parser.add_argument("--excel", required=True, help="Ścieżka do XLSX z kolumnami llm_categories i llm_summary")
    parser.add_argument("--taxonomy", required=True, help="Ścieżka do taxonomy.json")
    parser.add_argument("--output", required=False, help="Ścieżka wyjściowa PDF")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    excel_path = os.path.abspath(args.excel)
    taxonomy_path = os.path.abspath(args.taxonomy)
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Nie znaleziono pliku Excel: {excel_path}")
    if not os.path.exists(taxonomy_path):
        raise FileNotFoundError(f"Nie znaleziono pliku taxonomy.json: {taxonomy_path}")

    out_path = args.output or str(
        Path(excel_path).parent / "POLITYKA_MEZCZYZNI_raport.pdf"
    )
    title = "Analiza tematu POLITYKA na katolickich forach internetowych (posty pisane przez mężczyzn)"

    result = build_pdf(
        excel_path=excel_path,
        taxonomy_path=taxonomy_path,
        output_path=out_path,
        title=title,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

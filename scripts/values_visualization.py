#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generuje interaktywny, lustrzany wykres słupkowy z danymi z Excela:
- po lewej Mężczyźni, po prawej Kobiety,
- pojedynczy słupek podzielony na poparcie / neutralne / sprzeciw,
- hover: liczba wystąpień, unikalne posty, na 1000 słów,
- kliknięcie segmentu: tabela ze szczegółami pod wykresem (tylko dla tego segmentu),
- przełącznik widoku: "Na 1000 słów" vs "Liczba wystąpień".

Wejście:
    values_report.xlsx (arkusze: predictions, aggregates)

Wyjście:
    data/topics/results/visualizations/wykres_wartosci.html
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


# ----------------------- USTAWIENIA -----------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
EXCEL_PATH = REPO_ROOT / "data/topics/results/llm_values_20250903_205827/values_report.xlsx"
VIZ_DIR = REPO_ROOT / "data/topics/results/visualizations"
OUT_HTML = VIZ_DIR / "wykres_wartosci.html"

# Pastelowe kolory (spójne, stonowane)
COLORS = {
    "Mężczyźni": {"poparcie": "#a7c7e7", "neutralne": "#7fb3e6", "sprzeciw": "#5a9bd5"},
    "Kobiety":   {"poparcie": "#f6b3c2", "neutralne": "#f191a5", "sprzeciw": "#e46882"},
}

GENDERS_PL = ["Mężczyźni", "Kobiety"]
POLARITIES_PL = ["poparcie", "neutralne", "sprzeciw"]

GENDER_MAP = {"M": "Mężczyźni", "K": "Kobiety"}
POL_MAP = {"support": "poparcie", "neutral": "neutralne", "oppose": "sprzeciw"}


# ----------------------- FUNKCJE POMOCNICZE -----------------------
def load_data(xlsx_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Wczytuje arkusze 'predictions' i 'aggregates' z Excela.
    Jeśli brakuje 'aggregates', zwraca pusty DataFrame jako fallback.
    """
    pred = pd.read_excel(xlsx_path, sheet_name="predictions", engine="openpyxl")
    try:
        agg = pd.read_excel(xlsx_path, sheet_name="aggregates", engine="openpyxl")
    except Exception:
        agg = pd.DataFrame(columns=["gender", "total_words"])  # fallback

    # Tylko is_present = True
    if "is_present" in pred.columns:
        pred = pred[pred["is_present"] == True].copy()
    else:
        pred = pred.copy()

    # Mapowania na PL
    pred["gender_pl"] = pred["gender"].map(GENDER_MAP).fillna(pred["gender"])
    pred["polarity_pl"] = pred["polarity"].map(POL_MAP).fillna(pred["polarity"])
    return pred, agg


def words_per_gender(agg: pd.DataFrame, pred: pd.DataFrame) -> Dict[str, float]:
    """Zwraca słownik liczby słów na płeć na podstawie arkusza 'aggregates'.
    Jeśli brak/zerowe, fallback do sumy word_count z predictions.
    """
    d: Dict[str, float] = {}
    if not agg.empty and {"gender", "total_words"}.issubset(agg.columns):
        d = (
            agg.groupby("gender")["total_words"]
            .first()
            .rename({"M": "Mężczyźni", "K": "Kobiety"})
            .to_dict()
        )
    if not d or any(v in (0, None) for v in d.values()):
        if "word_count" in pred.columns:
            d = pred.groupby("gender_pl")["word_count"].sum().to_dict()
        else:
            # Bez word_count – użyj liczby rekordów jako przybliżenia, by uniknąć dzielenia przez zero
            d = pred.groupby("gender_pl").size().to_dict()
    return d


def aggregate(pred: pd.DataFrame, words_by_gender: Dict[str, float]) -> Tuple[pd.DataFrame, List[str]]:
    """Agreguje dane po (value, gender_pl, polarity_pl) i liczy per_1000."""
    # Liczności i unikalne posty
    grouped = (
        pred.groupby(["value", "gender_pl", "polarity_pl"])
        .apply(lambda df: pd.Series({"assignments": len(df), "unique_posts": df["post_id"].nunique()}))
        .reset_index()
    )

    # Zapewnij pełną siatkę kombinacji (dla spójnego stackowania)
    values = sorted(pred["value"].dropna().unique().tolist())
    full_index = pd.MultiIndex.from_product([values, GENDERS_PL, POLARITIES_PL],
                                            names=["value", "gender_pl", "polarity_pl"])
    grouped = grouped.set_index(["value", "gender_pl", "polarity_pl"]).reindex(full_index, fill_value=0).reset_index()

    # Wystąpienia na 1000 słów z użyciem total_words per płeć
    grouped["per_1000"] = grouped.apply(
        lambda r: (r["assignments"] / max(float(words_by_gender.get(r["gender_pl"], 1)), 1.0)) * 1000.0, axis=1
    )

    # Kolejność kategorii (wartości) na osi Y: malejąco po sumie per_1000 (K+M)
    ordered_values = (
        grouped.groupby("value")["per_1000"].sum().sort_values(ascending=False).index.tolist()
    )
    return grouped, ordered_values


def to_stacks(grouped: pd.DataFrame, ordered_values: List[str], gender_label: str, metric: str, sign: int) -> List[List[float]]:
    """Buduje listy do wykresu (poziome, z lustrzanym znakiem)."""
    dfg = grouped[grouped["gender_pl"] == gender_label].set_index(["value", "polarity_pl"])
    stacks: List[List[float]] = []
    for pol in POLARITIES_PL:
        arr: List[float] = []
        for val in ordered_values:
            x = dfg.loc[(val, pol), metric] if (val, pol) in dfg.index else 0.0
            arr.append(sign * float(x))
        stacks.append(arr)
    return stacks


def segment_meta(grouped: pd.DataFrame, ordered_values: List[str], gender_label: str):
    """Meta do hover (assignments, unikalne posty, per_1000, value, gender, polarity)."""
    dfg = grouped[grouped["gender_pl"] == gender_label].set_index(["value", "polarity_pl"])
    meta = []
    for pol in POLARITIES_PL:
        rows = []
        for val in ordered_values:
            if (val, pol) in dfg.index:
                a = int(dfg.loc[(val, pol), "assignments"])
                u = int(dfg.loc[(val, pol), "unique_posts"])
                p = float(dfg.loc[(val, pol), "per_1000"])
            else:
                a = u = 0
                p = 0.0
            rows.append((a, u, p, val, gender_label, pol))
        meta.append(rows)
    return meta


def build_figure(grouped: pd.DataFrame, ordered_values: List[str]) -> go.Figure:
    """Buduje wykres (Plotly) + przyciski przełączania metryki."""
    # X dla metryki 'per_1000' (domyślny widok)
    left_p1, left_p2, left_p3  = to_stacks(grouped, ordered_values, "Mężczyźni", "per_1000", sign=-1)
    right_p1, right_p2, right_p3 = to_stacks(grouped, ordered_values, "Kobiety",   "per_1000", sign=+1)

    # X dla metryki 'assignments' (liczba wystąpień)
    ls_c1, ls_c2, ls_c3 = to_stacks(grouped, ordered_values, "Mężczyźni", "assignments", sign=-1)
    rs_c1, rs_c2, rs_c3 = to_stacks(grouped, ordered_values, "Kobiety",   "assignments", sign=+1)

    # Meta do hover
    meta_left  = segment_meta(grouped, ordered_values, "Mężczyźni")
    meta_right = segment_meta(grouped, ordered_values, "Kobiety")

    fig = go.Figure()

    def add_side_traces(x_arrays, meta_arrays, gender_label):
        for i, pol in enumerate(POLARITIES_PL):
            x = x_arrays[i]
            md = np.array(meta_arrays[i], dtype=object)
            hover = []
            for (a, u, p, val, gen, polname) in md:
                hover.append(
                    f"<b>{val}</b><br>"
                    f"{gen} — {polname}<br>"
                    f"Wystąpienia: <b>{a}</b><br>"
                    f"Unikalne posty: <b>{u}</b><br>"
                    f"Na 1000 słów: <b>{p:.3f}</b>"
                )
            fig.add_bar(
                y=ordered_values,
                x=x,
                orientation="h",
                name=f"{gender_label} — {pol}",
                marker_color=COLORS[gender_label][pol],
                hovertemplate="%{customdata}<extra></extra>",
                customdata=np.array(hover),
            )

    add_side_traces([left_p1, left_p2, left_p3], meta_left, "Mężczyźni")
    add_side_traces([right_p1, right_p2, right_p3], meta_right, "Kobiety")

    fig.update_layout(
        barmode="relative",
        bargap=0.15,
        plot_bgcolor="#FAFAF8",
        paper_bgcolor="#FAFAF8",
        height=max(600, 30 * len(ordered_values)),
        margin=dict(l=140, r=140, t=140, b=50),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, title="", font=dict(color="#111111")),
        title=dict(text="<b>Odwołania do wartości według płci</b>", x=0.55, xanchor="center", font=dict(size=28, color="#2D2A26"), pad=dict(b=32)),
        font=dict(color="#111111"),
        xaxis=dict(
            title="Wystąpienia na 1000 słów (lewo: Mężczyźni, prawo: Kobiety)",
            zeroline=True, zerolinewidth=1, zerolinecolor="#A0A4AB",
            showgrid=False,
            tickformat=".2f",
            linecolor="#A0A4AB",
        ),
        yaxis=dict(title="Wartość", showgrid=True, gridcolor="rgba(160,164,171,0.3)", categoryorder="array", categoryarray=ordered_values, linecolor="#A0A4AB"),
        hoverlabel=dict(bgcolor="#FAFAF8", bordercolor="#A0A4AB", font=dict(color="#111111")),
    )

    # Linia środka
    fig.add_shape(type="line", x0=0, x1=0, y0=-0.5, y1=len(ordered_values)-0.5, line=dict(color="#A0A4AB", width=1))

    # Przyciski do przełączania metryki
    update_rate = {"x": [left_p1, left_p2, left_p3, right_p1, right_p2, right_p3]}
    update_counts = {"x": [ls_c1, ls_c2, ls_c3, rs_c1, rs_c2, rs_c3]}
    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                x=1.0, xanchor="right",
                y=1.20, yanchor="top",
                pad=dict(t=6, r=6),
                bgcolor="#FAFAF8",
                bordercolor="#A0A4AB",
                font=dict(color="#111111"),
                buttons=[
                    dict(label="Na 1000 słów", method="update",
                         args=[update_rate, {"xaxis.title.text": "Wystąpienia na 1000 słów (lewo: Mężczyźni, prawo: Kobiety)"}]),
                    dict(label="Liczba wystąpień", method="update",
                         args=[update_counts, {"xaxis.title.text": "Liczba wystąpień (lewo: Mężczyźni, prawo: Kobiety)"}]),
                ],
                showactive=True,
            )
        ]
    )
    return fig


def build_click_table_html(fig: go.Figure, pred: pd.DataFrame) -> str:
    """Zwraca pełny HTML (to_html + wstrzyknięty JS), który obsłuży kliknięcie -> tabela."""
    # Dane do tabeli po kliknięciu
    expo = pred.copy()
    expo["gender_pl"] = expo["gender"].map(GENDER_MAP)
    expo["polarity_pl"] = expo["polarity"].map(POL_MAP)
    cols = ["post_id", "gender_pl", "value", "polarity_pl", "confidence", "reason_short", "evidence_span", "word_count", "content"]
    expo = expo[[c for c in cols if c in expo.columns]]

    def key(v, g, p): return f"{v}|||{g}|||{p}"
    if {"value", "gender_pl", "polarity_pl"}.issubset(expo.columns):
        expo["key"] = expo.apply(lambda r: key(r.get("value"), r.get("gender_pl"), r.get("polarity_pl")), axis=1)
        lookup = {k: c.drop(columns=["key"]).to_dict(orient="records") for k, c in expo.groupby("key")}
    else:
        lookup = {}

    html_base = pio.to_html(fig, full_html=True, include_plotlyjs=True)
    lookup_json = json.dumps(lookup, ensure_ascii=False)
    injection = (
        """
<style>
  body { background: #FAFAF8; }
  .js-plotly-plot, .plotly, .plot-container { background: #FAFAF8 !important; }
</style>
<div id="details" style="font-family:Inter,system-ui,Arial;margin-top:40px;"></div>
<script>
(function(){

  var lookup = """
        + lookup_json
        + """;

  function esc(s) { return (s===null || s===undefined) ? '' : String(s); }

  function renderTable(rows, header) {
    var container = document.getElementById('details');
    container.innerHTML = '';
    var card = document.createElement('div');
    card.innerHTML = header;
    card.style.margin = '0 auto 48px auto';
    card.style.maxWidth = '600px';
    card.style.background = '#FFFFFF';
    card.style.border = '1px solid #E6E6E0';
    card.style.borderRadius = '8px';
    card.style.boxShadow = '0 1px 2px rgba(0,0,0,0.05)';
    card.style.padding = '12px 14px';
    card.style.color = '#2D2A26';
    card.style.lineHeight = '1.35';
    card.style.textAlign = 'left';
    container.appendChild(card);
    var table = document.createElement('table');
    table.style.borderCollapse = 'collapse';
    table.style.width = '100%';
    table.style.fontSize = '14px';
    table.style.fontFamily = 'Inter, system-ui, Arial, sans-serif';
    table.style.background = '#FFFFFF';
    var thead = document.createElement('thead');
    var hdrKeys = ['post_id','gender_pl','value','polarity_pl','confidence','reason_short','evidence_span','word_count','content'];
    var hdrLabels = ['ID posta','Płeć','Wartość','Polaryzacja','Pewność','Uzasadnienie','Fragment','Liczba słów','Treść'];
    var tr = document.createElement('tr');
    hdrLabels.forEach(function(label){
      var th = document.createElement('th');
      th.textContent = label;
      th.style.textAlign = 'left';
      th.style.borderBottom = '1px solid #2D2A26';
      th.style.padding = '8px 10px';
      th.style.position = 'sticky';
      th.style.top = '0';
      th.style.background = '#2D2A26';
      th.style.color = '#FAFAF8';
      th.style.fontWeight = '600';
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    rows.slice(0, 300).forEach(function(r, i){
      var tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid #f0f0f0';
      tr.style.background = (i % 2 === 1) ? '#F3F1EB' : '#FFFFFF';
      var cols = hdrKeys;
      cols.forEach(function(col){
        var td = document.createElement('td');
        td.textContent = esc(r[col]);
        td.style.verticalAlign = 'top';
        td.style.padding = '6px 10px';
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  var gd = document.querySelectorAll('div.js-plotly-plot')[0];
  var selectedKey = null;

  function getCategories(){
    try { return (gd && gd.data && gd.data[0] && gd.data[0].y) ? gd.data[0].y : []; }
    catch(e){ return []; }
  }

  function applyHighlight(value, gender, pol){
    var cats = getCategories();
    (gd.data || []).forEach(function(tr, idx){
      var name = tr.name || '';
      var traceGender = (name.indexOf('Mężczyźni') !== -1) ? 'Mężczyźni' : 'Kobiety';
      var matchesTrace = (traceGender === gender) && (name.indexOf(pol) !== -1);
      var opac = cats.map(function(c){ return (matchesTrace && c === value) ? 1.0 : 0.25; });
      Plotly.restyle(gd, { 'marker.opacity': [opac] }, [idx]);
    });
  }

  function resetHighlight(){
    (gd.data || []).forEach(function(tr, idx){
      Plotly.restyle(gd, { 'marker.opacity': [1] }, [idx]);
    });
  }
  gd.on('plotly_click', function(data){
    if(!data || !data.points || !data.points.length) return;
    var p = data.points[0];
    var name = p.data.name || '';
    var gender = (name.indexOf('Mężczyźni') !== -1) ? 'Mężczyźni' : 'Kobiety';
    var pol = name.split('—').pop().trim();
    var value = p.y;
    var key = value + '|||' + gender + '|||' + pol;
    if(selectedKey === key){
      resetHighlight();
      selectedKey = null;
    } else {
      selectedKey = key;
      applyHighlight(value, gender, pol);
    }
    var rows = lookup[key] || [];
    var header = '<div><b>Wartość:</b> ' + value + '</div>' +
                 '<div><b>Płeć:</b> ' + gender + '</div>' +
                 '<div><b>Polaryzacja:</b> ' + pol + '</div>' +
                 '<div><b>Liczba wystąpień:</b> ' + rows.length + '</div>';
    renderTable(rows, header);
  });

})();
</script>
"""
    )
    return html_base.replace("</body>", injection + "\n</body>")


def main() -> None:
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    if not EXCEL_PATH.exists():
        raise SystemExit(f"Nie znaleziono pliku: {EXCEL_PATH}")
    pred, agg = load_data(EXCEL_PATH)
    if pred.empty:
        raise SystemExit("Brak danych is_present=True w arkuszu 'predictions'.")
    wpg = words_per_gender(agg, pred)
    grouped, ordered_values = aggregate(pred, wpg)
    fig = build_figure(grouped, ordered_values)
    html = build_click_table_html(fig, pred)

    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Zapisano plik: {OUT_HTML.resolve()}")


if __name__ == "__main__":
    main()



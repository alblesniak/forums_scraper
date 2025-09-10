"""
Prompt do identyfikacji preferencji wyborczych (partie i liderzy) z sentymentem.

Zgodnie z procedurą użytkownika:
- batching 10 postów,
- skala sentymentu: bardzo neg (-2) .. bardzo poz (+2),
- confidence < 0.75 -> pominąć cel,
- zwrot wyłącznie JSON (schemat poniżej).
"""

from __future__ import annotations

from typing import Any, Dict, List
import json


PARTY_DICTIONARY = (
    "**Partie (warianty rozpoznawania):**\n"
    "- Prawo i Sprawiedliwość (PiS): `PiS`, `PIS`, `Pi S`, `Prawo i Sprawiedliwość`\n"
    "- Platforma Obywatelska (PO): `Platforma Obywatelska`, `PO` (wyłącznie wielkimi literami)\n"
    "- Koalicja Obywatelska (KO): `Koalicja Obywatelska`, `KO` (wielkimi literami)\n"
    "- Lewica / SLD / Nowa Lewica: `Lewica`, `SLD`, `Nowa Lewica`\n"
    "- PSL: `PSL`, `Polskie Stronnictwo Ludowe`\n"
    "- Konfederacja: `Konfederacja`\n"
    "- Polska 2050: `Polska 2050`, `Hołownia 2050`\n"
    "- Trzecia Droga: `Trzecia Droga`\n"
    "- Nowoczesna (.N): `Nowoczesna`, `.N`\n"
    "- Kukiz’15: `Kukiz’15`, `Kukiz 15`\n"
    "- Porozumienie (Gowina): `Porozumienie`, `Porozumienie Gowina`\n"
    "- Ruch Narodowy: `Ruch Narodowy`\n"
    "- Samoobrona: `Samoobrona`\n"
    "- Solidarna/Suwerenna Polska: `Solidarna Polska`, `Suwerenna Polska`\n"
)


LEADER_DICTIONARY = (
    "**Liderzy (nazwiska, odmiany, przezwiska):**\n"
    "- Jarosław Kaczyński: `Kaczyński`, `Kaczor`\n"
    "- Donald Tusk: `Tusk`\n"
    "- Szymon Hołownia: `Hołownia`\n"
    "- Władysław Kosiniak-Kamysz: `Kosiniak`, `Kamysz`\n"
    "- Sławomir Mentzen: `Mentzen`\n"
    "- Krzysztof Bosak: `Bosak`\n"
    "- Włodzimierz Czarzasty: `Czarzasty`\n"
    "- Adrian Zandberg: `Zandberg`\n"
    "- Robert Biedroń: `Biedroń`\n"
    "- Andrzej Duda: `Duda`\n"
    "- Bronisław Komorowski: `Komorowski`\n"
    "- Rafał Trzaskowski: `Trzaskowski`\n"
    "- Leszek Miller: `Miller`\n"
    "- Janusz Korwin-Mikke: `Korwin`, `Mikke`\n"
    "- Paweł Kukiz: `Kukiz`\n"
    "- Jarosław Gowin: `Gowin`\n"
    "- Roman Giertych: `Giertych`\n"
    "- Andrzej Lepper: `Lepper`\n"
)


DISAMBIG_RULES = (
    "Zasady dezambiguacji i pewności:\n"
    "- `PO` tylko jako akronim wielkimi literami lub obok ‘Platforma/partia’. Nie mylić z przyimkiem ‘po’.\n"
    "- ‘Prawo i sprawiedliwość’ jako wartość ≠ partia PiS.\n"
    "- Sarkazm/ironia: oceń intencję; gdy niejednoznaczne -> neutralny lub pomiń.\n"
    "- Jeden post może zawierać wiele celów (np. PiS negatywny, PO pozytywny).\n"
    "- Cytuj krótki fragment jako evidence; podaj confidence 0–1. Jeśli confidence < 0.75, pomiń cel.\n"
)


def build_system_prompt() -> str:
    return (
        "Jesteś rzetelnym annotatorem politycznym. Dla 10 postów wykryj wzmianki o partiach i/lub liderach\n"
        "oraz przypisz sentyment względem każdego wykrytego celu. Nie zgaduj – gdy brak wysokiej pewności (≥0.75), pomijaj.\n"
        "Zwracasz wyłącznie JSON."
    )


def build_user_prompt(batch_posts: List[Dict[str, Any]]) -> str:
    scale = (
        "Skala sentymentu (z mapą liczbową):\n"
        "- bardzo negatywny = -2\n"
        "- negatywny = -1\n"
        "- neutralny = 0\n"
        "- pozytywny = +1\n"
        "- bardzo pozytywny = +2\n"
    )
    schema = [
        {
            "post_id": "<ID z wejścia>",
            "results": [
                {
                    "target_type": "party|leader",
                    "canonical_name": "<np. Prawo i Sprawiedliwość (PiS)>",
                    "surface_form": "<jak w tekście>",
                    "evidence_span": "<krótki cytat>",
                    "sentiment_label": "bardzo negatywny|negatywny|neutralny|pozytywny|bardzo pozytywny",
                    "sentiment_score": 0,
                    "confidence": 0.0
                }
            ]
        }
    ]
    head = (
        PARTY_DICTIONARY
        + "\n"
        + LEADER_DICTIONARY
        + "\n"
        + DISAMBIG_RULES
        + "\n\n"
        + scale
        + "\nWejście (10 postów):\n"
    )
    data_block = json.dumps(batch_posts, ensure_ascii=False, indent=2)
    schema_block = json.dumps(schema, ensure_ascii=False, indent=2)
    return (
        head
        + data_block
        + "\n\nFormat odpowiedzi (JSON):\n"
        + schema_block
        + "\nZwróć wyłącznie JSON. Jeśli brak pewnych celów – results: []."
    )


__all__ = [
    "build_system_prompt",
    "build_user_prompt",
]



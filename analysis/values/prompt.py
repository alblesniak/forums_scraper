"""
Prompt i taksonomia dla klasyfikacji odwołań do wartości.

Zawiera sformatowaną treść system/user zgodnie z wytycznymi użytkownika.
"""

from __future__ import annotations

from typing import List, Dict, Any


def build_values_system_prompt() -> str:
    return (
        "Jesteś rzetelnym annotatorem treści forum. Twoje zadanie: dla każdego z 10 postów wskazać, na jakie wartości odwołuje się autor.\n"
        "Ważne:\n"
        "- Nie zgaduj. Jeśli nie masz wysokiej pewności — nie przypisuj żadnej wartości.\n"
        "- Dopuszczalne są wiele wartości, ale tylko gdy każda ma mocny, jawny sygnał w tekście.\n"
        "- Zwracaj wyłącznie JSON w podanym schemacie. Nie dodawaj komentarzy, wyjaśnień ani listy rozumowań.\n"
        "- Podawaj krótki powód (≤12 słów) i krótki cytat-evidence z posta.\n"
    )


VALUES_TAXONOMY_TEXT = (
    "## Taksonomia wartości (definicje + granice)\n\n"
    "1. Sprawiedliwość/Prawo – odwołania do legalności, konstytucji, praworządności, sądów, wyroków, równości wobec prawa.\n"
    "   Nie myl z: nazwą partii „Prawo i Sprawiedliwość (PiS)” – to nie jest odwołanie do wartości praworządności per se.\n\n"
    "2. Prawda/Rozum/Nauka – apel do faktów, dowodów, logiki, badań, rzetelnej wiedzy.\n\n"
    "3. Wspólnota/Naród/Patriotyzm – dobro Ojczyzny, narodu, solidarność, suwerenność, patriotyzm.\n\n"
    "4. Rodzina/Małżeństwo/Dzieci – normy i dobro rodziny, małżeństwa, rodziców, dzieci (wychowanie, dzietność).\n\n"
    "5. Bezpieczeństwo/Ład/Porządek – bezpieczeństwo wewn./zewn., porządek, ochrona, granice, stabilność.\n\n"
    "6. Wiara/Bóg (religijność) – jawne odniesienia do Boga, wiary, sakramentów, grzechu jako kategorii religijnej.\n\n"
    "7. Miłosierdzie/Współczucie/Pomoc – troska o słabszych/ubogich/chorych, apel o pomoc, empatię.\n\n"
    "8. Wolność/Sumienie/Godność – wolności (słowa/sumienia), godność osoby, klauzula sumienia.\n\n"
    "9. Moralność/Czystość – normatywne kategorie moralności (grzech/cnota), seksualność (aborcja, pornografia itp.).\n\n"
    "10. Równość/Role płci – równe prawa, parytety, krytyka/obrona patriarchatu, seksizmu; określanie ról płci.\n\n"
    "11. Tradycja/Autorytet/Posłuszeństwo – odwołanie do tradycji, nauczania/autorytetu (np. Kościoła), hierarchii, posłuszeństwa.\n\n"
    "12. Godność/Szacunek/Honor – wymóg szacunku wobec osób/urzędu, honor, potępienie zniewagi/upokorzenia.\n"
    "    Uwaga: jeśli występuje razem z Wolność/Sumienie/Godność, przyznaj obie (o ile są niezależnie wyraźne).\n\n"
    "13. Prawo naturalne/Stworzenie – odwołanie do porządku/naturalności/stworzenia (np. „porządek natury”, „prawo naturalne”).\n\n"
    "Ogólne reguły decyzyjne:\n"
    "- Wartość przypisz tylko wtedy, gdy w tekście jest jawna norma/ocena lub apel (nie samo słowo‑klucz bez znaczenia normatywnego).\n"
    "- Konflikty kategorii: jeśli zdanie spełnia 2+ definicji i masz mocne sygnały dla każdej — przypisz wieloetykietowo.\n"
    "- Niepewne? Ustaw is_present=false i nie wymuszaj etykiety.\n"
    "- Polaryzacja: zaznacz polarity: \"support\" (broni wartość), \"oppose\" (krytykuje ją), \"neutral\" (odwołuje się opisowo).\n"
)


def build_values_user_prompt(batch_posts: List[Dict[str, Any]]) -> str:
    """Buduje treść wiadomości użytkownika: instrukcje + taksonomia + schema + dane 10 postów.

    batch_posts: lista obiektów {post_id, gender, content}
    """
    schema = [
        {
            "post_id": "<ID z wejścia>",
            "gender": "M|K",
            "labels": [
                {
                    "value": "<nazwa z taksonomii>",
                    "is_present": True,
                    "polarity": "support|oppose|neutral",
                    "confidence": 0.0,
                    "reason_short": "<≤12 słów>",
                    "evidence_span": "<krótki cytat>"
                }
            ]
        }
    ]
    header = (
        VALUES_TAXONOMY_TEXT
        + "\n\nReguły dodatkowe:\n"
        + "- Klasyfikacja ma IGNOROWAĆ płeć; pole gender służy wyłącznie raportowaniu.\n"
        + "- Zwróć wyłącznie JSON zgodny ze schematem. Jeśli brak pewności — labels: [].\n\n"
        + "Dane do klasyfikacji (10 postów):\n"
    )
    import json
    data_block = json.dumps(batch_posts, ensure_ascii=False, indent=2)
    schema_block = json.dumps(schema, ensure_ascii=False, indent=2)
    return (
        header
        + data_block
        + "\n\nFormat odpowiedzi (JSON):\n"
        + schema_block
    )


__all__ = [
    "build_values_system_prompt",
    "build_values_user_prompt",
    "VALUES_TAXONOMY_TEXT",
]



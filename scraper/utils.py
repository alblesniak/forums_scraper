import re
from datetime import datetime


def clean_post_content(content):
    """
    Czyści zawartość postu z cytatów, URL-i, obrazów i podpisów
    
    Args:
        content (str): Surowa zawartość HTML postu
        
    Returns:
        str: Wyczyściona zawartość tekstowa postu
    """
    if not content:
        return ""
    
    # Usuń cytaty (div class="quotewrapper")
    content = re.sub(r'<div class="quotewrapper">.*?</div>', '', content, flags=re.DOTALL)
    
    # Usuń podpisy (span class="postbody signature")
    content = re.sub(r'<span class="postbody signature">.*?</span>', '', content, flags=re.DOTALL)
    
    # Usuń obrazy
    content = re.sub(r'<img[^>]*>', '', content)
    
    # Usuń linki (zachowaj tekst)
    content = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', content)
    
    # Usuń adresy URL w tekście (http/https/www)
    content = re.sub(r'https?://[^\s<>"]+', '', content)
    content = re.sub(r'www\.[^\s<>"]+', '', content)
    # Usuń frazy "link z opisem on-line" i podobne
    content = re.sub(r'link z opisem on-line', '', content, flags=re.IGNORECASE)
    
    # Zamień tagi <br> na znaki nowej linii
    content = re.sub(r'<br\s*/?>', '\n', content, flags=re.IGNORECASE)
    
    # Zamień tagi <div> i <span> na znaki nowej linii (aby rozdzielić bloki tekstu)
    content = re.sub(r'</div>', '\n', content)
    content = re.sub(r'</span>', '\n', content)
    content = re.sub(r'<div[^>]*>', '', content)
    content = re.sub(r'<span[^>]*>', '', content)
    
    # Usuń inne tagi HTML, zachowaj tekst
    content = re.sub(r'<[^>]+>', '', content)
    
    # Usuń nadmiarowe białe znaki i znaki nowej linii
    content = re.sub(r'\n\s*\n', '\n', content)  # Usuń puste linie
    content = re.sub(r'\s+', ' ', content)  # Zamień wielokrotne spacje na pojedyncze
    content = re.sub(r'\n\s+', '\n', content)  # Usuń spacje na początku linii
    content = re.sub(r'\s+\n', '\n', content)  # Usuń spacje na końcu linii
    
    # Dodaj spacje między słowami, które zostały połączone po usunięciu tagów HTML
    # Znajdź wzorce typu: mała litera + wielka litera (np. "ETYKAtom" -> "ETYKA tom")
    content = re.sub(r'([a-z])([A-Z])', r'\1 \2', content)
    
    # Dodaj spacje między cyframi a literami (np. "ISSN0014" -> "ISSN 0014")
    content = re.sub(r'([A-Z])(\d)', r'\1 \2', content)
    content = re.sub(r'(\d)([A-Z])', r'\1 \2', content)
    
    # Specjalne przypadki - rozdziel konkretne połączenia
    content = re.sub(r'ETYKAtom', 'ETYKA tom', content)
    content = re.sub(r'SPIS TREŚCIOd', 'SPIS TREŚCI Od', content)
    
    # Usuń nadmiarowe spacje po dodaniu nowych
    content = re.sub(r'\s+', ' ', content)
    
    return content.strip()


def normalize_gender(gender):
    """
    Normalizuje wartość płci do jednolitych oznaczeń
    
    Args:
        gender (str): Surowa wartość płci z forum
        
    Returns:
        str: Znormalizowana wartość płci ('M', 'K' lub None)
    """
    if not gender:
        return None
    
    gender_lower = gender.strip().lower()
    
    if gender_lower in ['mężczyzna', 'mezczyzna', 'm']:
        return 'M'
    elif gender_lower in ['kobieta', 'k']:
        return 'K'
    else:
        # Jeśli nie rozpoznajemy wartości, zwracamy None
        return None


def parse_polish_date(date_string):
    """
    Konwertuje polską datę z formatu "Śr mar 16, 2005 11:07 pm" na format "YYYY:MM:DD HH:MM"
    
    Obsługiwane formaty:
    - "Śr mar 16, 2005 11:07 pm" (Radio Katolik)
    - "27 lip 2025, 16:46" (Dolina Modlitwy)
    - "dzisiaj, 8:12"
    - "wczoraj, 17:30"
    
    Args:
        date_string (str): Data w polskim formacie
        
    Returns:
        str: Data w formacie "YYYY-MM-DD HH:MM:SS" lub None jeśli nie udało się sparsować
    """
    if not date_string:
        return None
    
    # Mapowanie polskich nazw miesięcy na numery
    month_mapping = {
        'sty': 1, 'lut': 2, 'mar': 3, 'kwi': 4, 'kwie': 4, 'maj': 5, 'maja': 5, 'cze': 6,
        'lip': 7, 'sie': 8, 'wrz': 9, 'paź': 10, 'lis': 11, 'gru': 12
    }
    
    try:
        date_clean = date_string.strip()
        
        # Sprawdź czy to "dzisiaj" lub "wczoraj"
        if date_clean.startswith('dzisiaj'):
            # Dla "dzisiaj" używamy aktualnej daty
            today = datetime.now()
            time_match = re.search(r'(\d{1,2}):(\d{2})', date_clean)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                return today.replace(hour=hour, minute=minute).strftime('%Y-%m-%d %H:%M:%S')
            return today.strftime('%Y-%m-%d %H:%M:%S')
        elif date_clean.startswith('wczoraj'):
            # Dla "wczoraj" używamy wczorajszej daty
            from datetime import timedelta
            yesterday = datetime.now() - timedelta(days=1)
            time_match = re.search(r'(\d{1,2}):(\d{2})', date_clean)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                return yesterday.replace(hour=hour, minute=minute).strftime('%Y-%m-%d %H:%M:%S')
            return yesterday.strftime('%Y-%m-%d %H:%M:%S')
        
        # Format Radio Katolik: "Śr mar 16, 2005 11:07 pm"
        # Usuń skróty dni tygodnia na początku (Śr, Pt, Pn, So, N, Cz, Wt)
        date_clean = re.sub(r'^(Śr|Pt|Pn|So|N|Cz|Wt)\s+', '', date_clean)
        
        # Parsuj datę używając regex
        # Format: "mar 16, 2005 11:07 pm" lub "maja 08, 2009 5:05 pm"
        pattern = r'(\w+)\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})\s+(am|pm)'
        match = re.match(pattern, date_clean)
        
        if match:
            month_name, day, year, hour, minute, ampm = match.groups()
            
            # Konwertuj nazwę miesiąca na numer
            month_name_lower = month_name.lower()
            if month_name_lower not in month_mapping:
                return None
            
            month = month_mapping[month_name_lower]
            day = int(day)
            year = int(year)
            hour = int(hour)
            minute = int(minute)
            
            # Konwertuj format 12-godzinny na 24-godzinny
            if ampm.lower() == 'pm' and hour != 12:
                hour += 12
            elif ampm.lower() == 'am' and hour == 12:
                hour = 0
            
            # Utwórz obiekt datetime
            dt = datetime(year, month, day, hour, minute)
            
            # Zwróć w formacie "YYYY-MM-DD HH:MM:SS"
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Format Dolina Modlitwy: "27 lip 2025, 16:46" lub "21 maja 2022, 17:58"
        pattern2 = r'(\d{1,2})\s+(\w+)\s+(\d{4}),\s+(\d{1,2}):(\d{2})'
        match = re.match(pattern2, date_clean)
        
        if match:
            day, month_name, year, hour, minute = match.groups()
            
            # Konwertuj nazwę miesiąca na numer
            month_name_lower = month_name.lower()
            if month_name_lower not in month_mapping:
                return None
            
            month = month_mapping[month_name_lower]
            day = int(day)
            year = int(year)
            hour = int(hour)
            minute = int(minute)
            
            # Utwórz obiekt datetime
            dt = datetime(year, month, day, hour, minute)
            
            # Zwróć w formacie "YYYY-MM-DD HH:MM:SS"
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Jeśli żaden wzorzec nie pasuje, zwróć None
        return None
        
    except (ValueError, AttributeError, KeyError) as e:
        # Jeśli wystąpi błąd podczas parsowania, zwróć None
        return None 


def clean_dolina_modlitwy_post_content(content):
    """
    Czyści zawartość postu z forum Dolina Modlitwy z cytatów, URL-i, obrazów i podpisów
    
    Args:
        content (str): Surowa zawartość HTML postu
        
    Returns:
        str: Wyczyściona zawartość tekstowa postu
    """
    if not content:
        return ""
    
    # Usuń cytaty (blockquote z atrybutem cite)
    content = re.sub(r'<blockquote[^>]*>.*?</blockquote>', '', content, flags=re.DOTALL)
    
    # Usuń podpisy (div z id="sig..." i class="signature")
    content = re.sub(r'<div id="sig[^"]*" class="signature">.*?</div>', '', content, flags=re.DOTALL)
    
    # Usuń elementy notice (informacje o edycji postu)
    content = re.sub(r'<div class="notice">.*?</div>', '', content, flags=re.DOTALL)
    
    # Usuń elementy biblia (specjalne formatowanie cytatów biblijnych)
    # Usuń wszystko od <span class="biblia"> do końca (niepoprawny HTML)
    content = re.sub(r'<span class="biblia"[^>]*>.*$', '', content, flags=re.DOTALL)
    
    # Usuń obrazy
    content = re.sub(r'<img[^>]*>', '', content)
    
    # Usuń linki (zachowaj tekst)
    content = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', content)
    
    # Usuń adresy URL w tekście (http/https/www)
    content = re.sub(r'https?://[^\s<>"]+', '', content)
    content = re.sub(r'www\.[^\s<>"]+', '', content)
    
    # Zamień tagi <br> na znaki nowej linii
    content = re.sub(r'<br\s*/?>', '\n', content, flags=re.IGNORECASE)
    
    # Zamień tagi <div> i <span> na znaki nowej linii (aby rozdzielić bloki tekstu)
    content = re.sub(r'</div>', '\n', content)
    content = re.sub(r'</span>', '\n', content)
    content = re.sub(r'<div[^>]*>', '', content)
    content = re.sub(r'<span[^>]*>', '', content)
    
    # Usuń inne tagi HTML, zachowaj tekst
    content = re.sub(r'<[^>]+>', '', content)
    
    # Usuń nadmiarowe białe znaki i znaki nowej linii
    content = re.sub(r'\n\s*\n', '\n', content)  # Usuń puste linie
    content = re.sub(r'\s+', ' ', content)  # Zamień wielokrotne spacje na pojedyncze
    content = re.sub(r'\n\s+', '\n', content)  # Usuń spacje na początku linii
    content = re.sub(r'\s+\n', '\n', content)  # Usuń spacje na końcu linii
    
    return content.strip() 

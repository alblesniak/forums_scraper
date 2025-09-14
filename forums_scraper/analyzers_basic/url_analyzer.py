"""
Analizator URL-ów i domen dla identyfikacji i kategoryzacji linków zewnętrznych.
"""

import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass

from forums_scraper.fs_core.protocol import Analyzer


@dataclass
class DomainInfo:
    """Informacje o domenie."""
    domain: str
    category: str
    is_religious: bool
    is_media: bool
    is_social: bool
    trust_score: float  # 0.0-1.0


@dataclass
class URLInfo:
    """Informacje o URL-u."""
    url: str
    domain: str
    category: str
    url_type: str  # 'article', 'video', 'image', 'social', 'unknown'
    is_external: bool


class URLAnalyzer(Analyzer):
    """Zaawansowany analizator URL-ów i domen."""
    
    def __init__(self, **kwargs):
        self.include_domain_analysis = kwargs.get('include_domain_analysis', True)
        self.include_url_categorization = kwargs.get('include_url_categorization', True)
        self.max_urls_per_post = kwargs.get('max_urls_per_post', 50)
        
        # Kategorie domen religijnych
        self.religious_domains = {
            'catholic.pl', 'radiomaryja.pl', 'niedziela.pl', 'opoka.org.pl',
            'vatican.va', 'deon.pl', 'aleteia.org', 'wiara.pl', 'dolinamodlitwy.pl',
            'zchrystusem.pl', 'radiokatolik.pl', 'ekai.pl', 'gosc.pl', 'tygodnikpowszechny.pl',
            'fronda.pl', 'pch24.pl', 'naszdziennik.pl', 'idziemy.pl', 'misyjne.pl'
        }
        
        # Kategorie domen medialnych
        self.media_domains = {
            'youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com',
            'tvp.pl', 'polsatnews.pl', 'onet.pl', 'wp.pl', 'interia.pl',
            'gazeta.pl', 'rzeczpospolita.pl', 'se.pl', 'fakt.pl', 'super.pl'
        }
        
        # Kategorie domen społecznościowych
        self.social_domains = {
            'facebook.com', 'twitter.com', 'x.com', 'instagram.com',
            'linkedin.com', 'tiktok.com', 'snapchat.com', 'pinterest.com'
        }
        
        # Kategorie domen edukacyjnych/naukowych
        self.educational_domains = {
            'wikipedia.org', 'britannica.com', 'edu.pl', 'academia.edu',
            'researchgate.net', 'scholar.google.com', 'jstor.org'
        }
    
    async def setup(self):
        """Przygotowanie analizatora."""
        pass
    
    async def close(self):
        """Zamknięcie analizatora."""
        pass
    
    async def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analizuje URL-e i domeny w poście."""
        content_urls = data.get('content_urls', [])
        
        if not content_urls or not isinstance(content_urls, list):
            return {
                'url_analysis': {
                    'total_urls': 0,
                    'domains': [],
                    'categorized_urls': [],
                    'domain_stats': {}
                }
            }
        
        # Ogranicz liczbę URL-ów jeśli jest za dużo
        if len(content_urls) > self.max_urls_per_post:
            content_urls = content_urls[:self.max_urls_per_post]
        
        domains = set()
        categorized_urls = []
        domain_categories = {}
        
        for url in content_urls:
            if not url or not isinstance(url, str):
                continue
                
            try:
                # Wyciągnij domenę
                domain = self._extract_domain(url)
                if not domain:
                    continue
                
                domains.add(domain)
                
                # Kategoryzuj domenę
                domain_info = self._categorize_domain(domain)
                domain_categories[domain] = {
                    'category': domain_info.category,
                    'is_religious': domain_info.is_religious,
                    'is_media': domain_info.is_media,
                    'is_social': domain_info.is_social,
                    'trust_score': domain_info.trust_score
                }
                
                # Kategoryzuj URL
                url_info = self._categorize_url(url, domain_info)
                
                categorized_urls.append({
                    'url': url,
                    'domain': domain,
                    'category': domain_info.category,
                    'url_type': url_info.url_type,
                    'is_external': url_info.is_external
                })
                
            except Exception:
                # Ignoruj błędne URL-e
                continue
        
        # Statystyki domen
        domain_stats = {
            'total_domains': len(domains),
            'religious_domains': len([d for d in domains if self._is_religious_domain(d)]),
            'media_domains': len([d for d in domains if self._is_media_domain(d)]),
            'social_domains': len([d for d in domains if self._is_social_domain(d)]),
            'educational_domains': len([d for d in domains if self._is_educational_domain(d)]),
            'unknown_domains': len([d for d in domains if not self._is_known_domain(d)])
        }
        
        return {
            'url_analysis': {
                'total_urls': len(content_urls),
                'domains': list(domains),
                'categorized_urls': categorized_urls,
                'domain_stats': domain_stats,
                'domain_categories': domain_categories
            }
        }
    
    def _extract_domain(self, url: str) -> Optional[str]:
        """Wyciąga domenę z URL-a."""
        try:
            # Dodaj protokół jeśli brak
            if not url.startswith(('http://', 'https://')):
                if url.startswith('www.'):
                    url = 'https://' + url
                else:
                    url = 'https://' + url
            
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Usuń www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
                
            return domain if domain else None
            
        except Exception:
            return None
    
    def _categorize_domain(self, domain: str) -> DomainInfo:
        """Kategoryzuje domenę."""
        domain_lower = domain.lower()
        
        # Sprawdź kategorie
        is_religious = self._is_religious_domain(domain_lower)
        is_media = self._is_media_domain(domain_lower)
        is_social = self._is_social_domain(domain_lower)
        is_educational = self._is_educational_domain(domain_lower)
        
        # Określ główną kategorię
        if is_religious:
            category = 'religious'
            trust_score = 0.9
        elif is_educational:
            category = 'educational'
            trust_score = 0.8
        elif is_media:
            category = 'media'
            trust_score = 0.7
        elif is_social:
            category = 'social'
            trust_score = 0.6
        else:
            category = 'unknown'
            trust_score = 0.5
        
        return DomainInfo(
            domain=domain,
            category=category,
            is_religious=is_religious,
            is_media=is_media,
            is_social=is_social,
            trust_score=trust_score
        )
    
    def _categorize_url(self, url: str, domain_info: DomainInfo) -> URLInfo:
        """Kategoryzuje konkretny URL."""
        url_lower = url.lower()
        
        # Określ typ URL-a na podstawie rozszerzenia/wzorca
        if any(pattern in url_lower for pattern in ['/watch', '/video', '.mp4', '.avi', '.mov']):
            url_type = 'video'
        elif any(pattern in url_lower for pattern in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            url_type = 'image'
        elif any(pattern in url_lower for pattern in ['/article', '/news', '/post', '/blog']):
            url_type = 'article'
        elif domain_info.is_social:
            url_type = 'social'
        else:
            url_type = 'unknown'
        
        return URLInfo(
            url=url,
            domain=domain_info.domain,
            category=domain_info.category,
            url_type=url_type,
            is_external=True  # Wszystkie URL-e w content_urls są zewnętrzne
        )
    
    def _is_religious_domain(self, domain: str) -> bool:
        """Sprawdza czy domena jest religijna."""
        return (domain in self.religious_domains or
                any(keyword in domain for keyword in ['catholic', 'christian', 'church', 'bible', 'prayer', 'gospel']))
    
    def _is_media_domain(self, domain: str) -> bool:
        """Sprawdza czy domena jest medialna."""
        return (domain in self.media_domains or
                any(keyword in domain for keyword in ['news', 'tv', 'radio', 'media', 'press']))
    
    def _is_social_domain(self, domain: str) -> bool:
        """Sprawdza czy domena jest społecznościowa."""
        return domain in self.social_domains
    
    def _is_educational_domain(self, domain: str) -> bool:
        """Sprawdza czy domena jest edukacyjna."""
        return (domain in self.educational_domains or
                domain.endswith('.edu') or domain.endswith('.edu.pl') or
                'university' in domain or 'academia' in domain)
    
    def _is_known_domain(self, domain: str) -> bool:
        """Sprawdza czy domena jest w znanej kategorii."""
        return (self._is_religious_domain(domain) or
                self._is_media_domain(domain) or
                self._is_social_domain(domain) or
                self._is_educational_domain(domain))


class DomainStatsAnalyzer(Analyzer):
    """Analizator statystyk domen (lżejsza wersja)."""
    
    def __init__(self, **kwargs):
        self.track_popularity = kwargs.get('track_popularity', True)
        
    async def setup(self):
        """Przygotowanie analizatora."""
        pass
    
    async def close(self):
        """Zamknięcie analizatora."""
        pass
    
    async def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Podstawowa analiza statystyk domen."""
        content_urls = data.get('content_urls', [])
        
        if not content_urls:
            return {'domain_stats': {'external_links_count': 0}}
        
        domains = set()
        
        for url in content_urls:
            try:
                parsed = urlparse(url if url.startswith(('http://', 'https://')) else f'https://{url}')
                domain = parsed.netloc.lower()
                if domain.startswith('www.'):
                    domain = domain[4:]
                if domain:
                    domains.add(domain)
            except Exception:
                continue
        
        return {
            'domain_stats': {
                'external_links_count': len(content_urls),
                'unique_domains_count': len(domains),
                'domains': list(domains)
            }
        }

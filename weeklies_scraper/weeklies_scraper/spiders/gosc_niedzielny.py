import scrapy
from datetime import datetime
from weeklies_scraper.items import WeeklyItem


class GoscNiedzielnySpider(scrapy.Spider):
    name = "gosc_niedzielny"
    allowed_domains = ["gosc.pl"]
    start_urls = ["https://www.gosc.pl/wyszukaj/wydania/3.Gosc-Niedzielny"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.info("Rozpoczęto scrapowanie Gościa Niedzielnego")

    def start_requests(self):
        """Rozpocznij scrapowanie od strony głównej tygodnika"""
        # Najpierw zapisz informacje o tygodniku
        weekly_item = WeeklyItem()
        weekly_item['name'] = "Gość Niedzielny"
        weekly_item['url'] = "https://www.gosc.pl"
        weekly_item['description'] = "Tygodnik katolicki - Gość Niedzielny"
        weekly_item['scraped_at'] = datetime.now()
        yield weekly_item
        
        # Następnie przejdź do archiwum wydań
        for url in self.start_urls:
            yield scrapy.Request(url=url, callback=self.parse_archive)

    def parse_archive(self, response):
        """Parsuj stronę archiwum wydań"""
        self.logger.info(f"Parsuję archiwum: {response.url}")
        
        # TODO: Implementuj parsowanie listy wydań
        # Na razie tylko logujemy
        self.logger.info("Parsowanie archiwum - do implementacji")
        
        # Przykład struktury do implementacji:
        # - Znajdź linki do poszczególnych wydań
        # - Dla każdego wydania wywołaj parse_issue()
        
    def parse_issue(self, response):
        """Parsuj konkretne wydanie"""
        self.logger.info(f"Parsuję wydanie: {response.url}")
        
        # TODO: Implementuj parsowanie wydania
        # - Wyciągnij metadane wydania (numer, rok, data)
        # - Znajdź sekcje w wydaniu
        # - Dla każdej sekcji wywołaj parse_section()
        
    def parse_section(self, response):
        """Parsuj sekcję w wydaniu"""
        self.logger.info(f"Parsuję sekcję: {response.url}")
        
        # TODO: Implementuj parsowanie sekcji
        # - Znajdź artykuły w sekcji
        # - Dla każdego artykułu wywołaj parse_article()
        
    def parse_article(self, response):
        """Parsuj artykuł"""
        self.logger.info(f"Parsuję artykuł: {response.url}")
        
        # TODO: Implementuj parsowanie artykułu
        # - Wyciągnij tytuł, treść, autorów, tagi
        # - Zapisz do bazy danych

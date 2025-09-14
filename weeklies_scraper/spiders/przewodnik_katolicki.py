import scrapy
from datetime import datetime
from items import WeeklyItem


class PrzewodnikKatolickiSpider(scrapy.Spider):
    name = "przewodnik_katolicki"
    allowed_domains = ["przewodnik-katolicki.pl"]
    start_urls = ["https://www.przewodnik-katolicki.pl/Archiwum"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.info("Rozpoczęto scrapowanie Przewodnika Katolickiego")

    def start_requests(self):
        """Rozpocznij scrapowanie od strony głównej tygodnika"""
        # Najpierw zapisz informacje o tygodniku
        weekly_item = WeeklyItem()
        weekly_item['name'] = "Przewodnik Katolicki"
        weekly_item['url'] = "https://www.przewodnik-katolicki.pl"
        weekly_item['description'] = "Tygodnik katolicki - Przewodnik Katolicki"
        weekly_item['scraped_at'] = datetime.now()
        yield weekly_item
        
        # Następnie przejdź do archiwum wydań
        for url in self.start_urls:
            yield scrapy.Request(url=url, callback=self.parse_archive)

    def parse_archive(self, response):
        """Parsuj stronę archiwum wydań"""
        self.logger.info(f"Parsuję archiwum: {response.url}")
        
        # TODO: Implementuj parsowanie listy wydań
        self.logger.info("Parsowanie archiwum - do implementacji")
        
    def parse_issue(self, response):
        """Parsuj konkretne wydanie"""
        self.logger.info(f"Parsuję wydanie: {response.url}")
        
        # TODO: Implementuj parsowanie wydania
        
    def parse_section(self, response):
        """Parsuj sekcję w wydaniu"""
        self.logger.info(f"Parsuję sekcję: {response.url}")
        
        # TODO: Implementuj parsowanie sekcji
        
    def parse_article(self, response):
        """Parsuj artykuł"""
        self.logger.info(f"Parsuję artykuł: {response.url}")
        
        # TODO: Implementuj parsowanie artykułu

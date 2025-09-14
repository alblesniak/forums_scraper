# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy
from itemloaders.processors import TakeFirst, Join
from datetime import datetime


class WeeklyItem(scrapy.Item):
    """Główny tygodnik katolicki"""
    name = scrapy.Field(output_processor=TakeFirst(), required=True)
    url = scrapy.Field(output_processor=TakeFirst(), required=True)
    description = scrapy.Field(output_processor=TakeFirst(), required=False)
    scraped_at = scrapy.Field(output_processor=TakeFirst(), required=True)


class IssueItem(scrapy.Item):
    """Wydanie tygodnika"""
    weekly_name = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_name = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_number = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_year = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_date = scrapy.Field(output_processor=TakeFirst(), required=False)
    issue_url = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_cover_url = scrapy.Field(output_processor=TakeFirst(), required=False)
    issue_description = scrapy.Field(output_processor=TakeFirst(), required=False)
    scraped_at = scrapy.Field(output_processor=TakeFirst(), required=True)


class SectionItem(scrapy.Item):
    """Sekcja w tygodniku (np. Kościół, Polska, Świat)"""
    weekly_name = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_number = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_year = scrapy.Field(output_processor=TakeFirst(), required=True)
    section_name = scrapy.Field(output_processor=TakeFirst(), required=True)
    section_url = scrapy.Field(output_processor=TakeFirst(), required=False)
    section_description = scrapy.Field(output_processor=TakeFirst(), required=False)
    scraped_at = scrapy.Field(output_processor=TakeFirst(), required=True)


class ArticleItem(scrapy.Item):
    """Artykuł w tygodniku"""
    weekly_name = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_number = scrapy.Field(output_processor=TakeFirst(), required=True)
    issue_year = scrapy.Field(output_processor=TakeFirst(), required=True)
    section_name = scrapy.Field(output_processor=TakeFirst(), required=False)
    article_title = scrapy.Field(output_processor=TakeFirst(), required=True)
    article_intro = scrapy.Field(output_processor=TakeFirst(), required=False)
    article_authors = scrapy.Field(output_processor=Join("; "), required=False)
    article_url = scrapy.Field(output_processor=TakeFirst(), required=True)
    article_content = scrapy.Field(output_processor=Join("\n"), required=False)
    article_tags = scrapy.Field(output_processor=Join("; "), required=False)
    article_word_count = scrapy.Field(output_processor=TakeFirst(), required=False)
    article_image_urls = scrapy.Field(output_processor=Join("; "), required=False)
    scraped_at = scrapy.Field(output_processor=TakeFirst(), required=True)


class AuthorItem(scrapy.Item):
    """Autor artykułu (osobna tabela)"""
    name = scrapy.Field(output_processor=TakeFirst(), required=True)
    bio = scrapy.Field(output_processor=TakeFirst(), required=False)
    photo_url = scrapy.Field(output_processor=TakeFirst(), required=False)
    social_media = scrapy.Field(output_processor=Join("; "), required=False)
    scraped_at = scrapy.Field(output_processor=TakeFirst(), required=True)

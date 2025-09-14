# Scrapy settings for weeklies_scraper project
# Scraper tygodników katolickich

BOT_NAME = "weeklies_scraper"

SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"

# User agent dla tygodników katolickich
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Concurrent requests - ostrożnie z tygodnikami
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
CONCURRENT_REQUESTS_PER_IP = 2

# Download delay - szanujmy serwery
DOWNLOAD_DELAY = 1.0
RANDOMIZE_DOWNLOAD_DELAY = 0.5

# Timeout settings
DOWNLOAD_TIMEOUT = 30
DNS_TIMEOUT = 20

# Retry settings
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429, 522, 523, 524]

# AutoThrottle - automatyczne dostosowanie prędkości
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
AUTOTHROTTLE_DEBUG = False

# Headers
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Middleware settings
SPIDER_MIDDLEWARES = {
    "middlewares.WeekliesScraperSpiderMiddleware": 543,
}

DOWNLOADER_MIDDLEWARES = {
    "middlewares.WeekliesScraperDownloaderMiddleware": 543,
}

# Item pipelines
ITEM_PIPELINES = {
    "pipelines.WeekliesScraperPipeline": 300,
    "pipelines.SQLitePipeline": 400,
}

# Logging
LOG_LEVEL = "INFO"
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'

# SQLite database settings - wspólna baza dla wszystkich tygodników
SQLITE_DATABASE_PATH = "../data/databases/weeklies_unified.db"

# Wymuś asyncio reactor dla wsparcia async pipeline
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"

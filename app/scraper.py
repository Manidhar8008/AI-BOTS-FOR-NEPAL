import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 10
MAX_URLS = 150

def fetch_sitemap(base_url):
    sitemap_url = urljoin(base_url, "/sitemap.xml")

    try:
        res = requests.get(sitemap_url, headers=HEADERS, timeout=TIMEOUT)

        if res.status_code != 200:
            return [base_url]

        soup = BeautifulSoup(res.text, "xml")
        urls = [loc.text for loc in soup.find_all("loc")]

        return urls[:MAX_URLS]

    except:
        return [base_url]


def prioritize_urls(urls):
    keywords = [
        "notice", "download", "pdf",
        "citizen", "charter",
        "tax", "service",
        "yojana", "budget"
    ]

    priority = []
    others = []

    for url in urls:
        if any(k in url.lower() for k in keywords):
            priority.append(url)
        else:
            others.append(url)

    return priority + others[:30]

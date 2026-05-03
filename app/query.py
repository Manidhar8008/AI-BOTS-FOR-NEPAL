from urllib.parse import urlparse
from scraper import fetch_sitemap, prioritize_urls
from extractor import extract_html, extract_pdf, is_pdf

MAX_QUERY_URLS = 20

def query_mode(base_url, query):
    base_domain = urlparse(base_url).netloc

    urls = fetch_sitemap(base_url)
    urls = prioritize_urls(urls)

    results = []

    for url in urls[:MAX_QUERY_URLS]:

        if base_domain not in url:
            continue

        if is_pdf(url):
            text = extract_pdf(url)
        else:
            text = extract_html(url)

        if not text:
            continue

        if query.lower() in text.lower():
            results.append((url, text[:1000]))

    return results[:5]
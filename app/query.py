from urllib.parse import urlparse
from scraper import fetch_sitemap, prioritize_urls
from extractor import extract_html, extract_pdf, is_pdf

CACHE = 
{
    if url in CACHE:
    text = CACHE[url]
else:
    if is_pdf(url):
        text = extract_pdf(url)
    else:
        text = extract_html(url)

    CACHE[url] = text
}


MAX_QUERY_URLS = 20
CHUNK_SIZE = 500

SYNONYMS = {
    "services": ["service", "facility"],
    "tax": ["tax", "revenue", "fee"],
    "contact": ["contact", "phone", "email", "address"],
    "budget": ["budget", "financial", "plan"],
}


# ================= TEXT CHUNKING =================

def chunk_text(text, size=CHUNK_SIZE):
    return [text[i:i+size] for i in range(0, len(text), size)]


# ================= SCORING =================

def score_chunk(chunk, query_words):
    chunk = chunk.lower()
    score = 0

    for word in query_words:
        if word in chunk:
            score += 2  # base weight

    # boost for important keywords
    boost_words = ["tax", "service", "contact", "budget", "notice"]

    for b in boost_words:
        if b in chunk:
            score += 1

    return score


# ================= QUERY MODE =================

def query_mode(base_url, query):
    base_domain = urlparse(base_url).netloc

    urls = fetch_sitemap(base_url)
    urls = prioritize_urls(urls)

    print(f"📊 Total URLs found: {len(urls)}")

    query_words = [w for w in query.lower().split() if len(w) > 3]

    scored_results = []

    for url in urls[:MAX_QUERY_URLS]:

        if base_domain not in url:
            continue

        print(f"🔍 Checking: {url}")

        if is_pdf(url):
            text = extract_pdf(url)
        else:
            text = extract_html(url)

        if not text:
            continue

        chunks = chunk_text(text)

        for chunk in chunks:
            score = score_chunk(chunk, query_words)

            if score > 0:
                scored_results.append((score, url, chunk))

    # sort by best match
    scored_results.sort(reverse=True, key=lambda x: x[0])

    # deduplicate by URL (avoid same page spam)
    seen = set()
    final_results = []

    for score, url, chunk in scored_results:
        if url not in seen:
            final_results.append((url, chunk[:500]))
            seen.add(url)

        if len(final_results) >= 5:
            break

    return final_results
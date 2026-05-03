import requests
import time
import io
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
from pdfminer.high_level import extract_text

# ================= CONFIG =================
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

MAX_URLS = 150
MAX_PDFS = 50
MAX_WORKERS = 8
TIMEOUT = 10

# ================= HELPERS =================

def normalize_url(base, link):
    return urljoin(base, link.split("#")[0])

def is_valid_url(url, base_domain):
    parsed = urlparse(url)
    return parsed.netloc.endswith(base_domain)

def is_pdf(url):
    return url.lower().endswith(".pdf")

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def chunk_text(text, size=500):
    return [text[i:i+size] for i in range(0, len(text), size)]

# ================= SITEMAP =================

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

    return priority + others[:30]  # limit noise

# ================= EXTRACTORS =================

def extract_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(res.text, "lxml")

        text = soup.get_text(separator=" ")
        return clean_text(text)

    except:
        return None

def extract_pdf(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        pdf_bytes = io.BytesIO(res.content)
        text = extract_text(pdf_bytes)
        return clean_text(text)

    except:
        return None

# ================= STORAGE (TEMP) =================

def store_chunks(tenant_id, source_url, text, content_type):
    chunks = chunk_text(text)

    data = []
    for chunk in chunks:
        data.append({
            "tenant_id": tenant_id,
            "source": source_url,
            "type": content_type,
            "chunk": chunk
        })

    return data

# ================= PIPELINE =================

def process_url(tenant_id, url, base_domain):
    if not is_valid_url(url, base_domain):
        return []

    if is_pdf(url):
        text = extract_pdf(url)
        if text:
            return store_chunks(tenant_id, url, text, "pdf")

    else:
        text = extract_html(url)
        if text:
            return store_chunks(tenant_id, url, text, "html")

    return []

# ================= MAIN =================

def ingest(tenant_id, base_url):
    base_domain = urlparse(base_url).netloc

    print(f"🚀 Starting ingestion for {tenant_id}")

    urls = fetch_sitemap(base_url)

    if not urls:
        print("⚠️ No sitemap found, fallback to base URL only")
        urls = [base_url]

    pdf_count = 0
    all_data = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []

        for url in urls:
            if is_pdf(url):
                if pdf_count >= MAX_PDFS:
                    continue
                pdf_count += 1

            futures.append(executor.submit(process_url, tenant_id, url, base_domain))

        for f in futures:
            result = f.result()
            if result:
                all_data.extend(result)

    print(f"✅ Ingestion complete: {len(all_data)} chunks")
    return all_data


if __name__ == "__main__":
    data = ingest(
        tenant_id="gokarneshwor",
        base_url="https://gokarneshwormun.gov.np/"
    )

    print(f"Total chunks: {len(data)}")
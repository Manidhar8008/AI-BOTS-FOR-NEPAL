import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 10
MAX_URLS = 150


# ================= HELPERS =================

def is_valid(url, base_domain):
    try:
        return urlparse(url).netloc.endswith(base_domain)
    except:
        return False


def normalize(url):
    return url.split("#")[0].strip()


# ================= SITEMAP =================

def fetch_sitemap(base_url):
    base_domain = urlparse(base_url).netloc

    sitemap_urls = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml")
    ]

    all_urls = set()

    for sitemap_url in sitemap_urls:
        try:
            res = requests.get(sitemap_url, headers=HEADERS, timeout=TIMEOUT)

            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, "xml")

            # Case 1: normal sitemap
            locs = [loc.text for loc in soup.find_all("loc")]

            for loc in locs:
                loc = normalize(loc)

                if is_valid(loc, base_domain):
                    all_urls.add(loc)

            if all_urls:
                print(f"✅ Sitemap found: {len(all_urls)} URLs")
                return list(all_urls)[:MAX_URLS]

        except Exception as e:
            continue

    # ================= FALLBACK =================
    print("⚠️ No sitemap found. Using fallback crawl...")

    if base_domain in href:
        return fallback_crawl(base_url, base_domain)
    print(f"➡️ Found link: {href}")


# ================= FALLBACK CRAWL =================

def fallback_crawl(base_url, base_domain):
    visited = set()
    to_visit = [base_url]

    collected = set()

    depth = 0
    MAX_DEPTH = 2  # keep shallow

    while to_visit and len(collected) < MAX_URLS and depth < MAX_DEPTH:
        next_batch = []

        for url in to_visit:
            if url in visited:
                continue

            visited.add(url)

            try:
                res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                soup = BeautifulSoup(res.text, "lxml")

                for a in soup.find_all("a", href=True):
                    href = normalize(urljoin(base_url, a["href"]))

                    if not is_valid(href, base_domain):
                        continue

                    if any(x in href for x in ["javascript:", "mailto:", "#"]):
                        continue

                    if href not in collected:
                        collected.add(href)
                        next_batch.append(href)

                    if len(collected) >= MAX_URLS:
                        break

            except:
                continue

        to_visit = next_batch
        depth += 1

    print(f"✅ Fallback collected: {len(collected)} URLs")
    return list(collected)


# ================= PRIORITIZATION =================

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

    # prioritize important pages first
    final_urls = priority + others[:30]

    print(f"📊 Prioritized URLs: {len(final_urls)} (priority={len(priority)})")

    return final_urls
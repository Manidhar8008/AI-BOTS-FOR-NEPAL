import requests
import io
import re
from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 10


# ================= HELPERS =================

def is_pdf(url):
    return url.lower().endswith(".pdf")


def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n+', ' ', text)
    return text.strip()


def remove_noise(text):
    # remove repeated junk patterns
    noise_patterns = [
        r"Home.*?Contact",
        r"Copyright.*",
        r"All rights reserved.*"
    ]

    for pattern in noise_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return text


# ================= HTML EXTRACTION =================

def extract_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)

        if res.status_code != 200:
            return None

        soup = BeautifulSoup(res.text, "lxml")

        # remove junk elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # 🔥 IMPORTANT: focus on meaningful content
        main_content = None

        # try common content containers
        for selector in ["main", "article", "section", "div"]:
            candidates = soup.find_all(selector)

            for c in candidates:
                text = c.get_text(separator=" ")
                if len(text) > 500:
                    main_content = text
                    break

            if main_content:
                break

        if not main_content:
            main_content = soup.get_text(separator=" ")

        text = clean_text(main_content)
        text = remove_noise(text)

        # filter weak pages
        if not text or len(text) < 300:
            return None

        return text

    except Exception as e:
        print(f"❌ HTML fail: {url}")
        return None


# ================= PDF EXTRACTION =================

def extract_pdf(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)

        if res.status_code != 200:
            return None

        pdf_bytes = io.BytesIO(res.content)

        text = extract_text(pdf_bytes)

        text = clean_text(text)
        text = remove_noise(text)

        # handle broken extraction
        if not text or len(text) < 200:
            return None

        return text

    except Exception as e:
        print(f"❌ PDF fail: {url}")
        return None
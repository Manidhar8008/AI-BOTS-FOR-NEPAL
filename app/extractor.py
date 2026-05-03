import requests
import io
import re
from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 10

def is_pdf(url):
    return url.lower().endswith(".pdf")

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(res.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ")
        text = clean_text(text)

        if not text or len(text) < 300:
            return None

        return text

    except:
        return None


def extract_pdf(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        pdf_bytes = io.BytesIO(res.content)

        text = extract_text(pdf_bytes)
        text = clean_text(text)

        if not text or len(text) < 300:
            return None

        return text

    except:
        return None
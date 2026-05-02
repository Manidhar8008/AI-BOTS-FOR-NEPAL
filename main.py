import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
import re

# 1. Configuration & The Corrected URL
BASE_URL = "https://gokarneshwormun.gov.np/"
OUTPUT_DIR = "data/raw_pdfs/gokarneshwor"

# 2. Standard Browser Headers (So we don't look like a bot)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def setup_directory():
    """Creates the folder structure if it doesn't exist."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📁 Created directory: {OUTPUT_DIR}")

def robust_scrape():
    setup_directory()
    
    visited = set()
    to_visit = [BASE_URL]
    
    print(f"🚀 Starting scrape of {BASE_URL}")

    while to_visit:
        url = to_visit.pop(0)
        
        # Skip if we've been here, or if it's an external link
        if url in visited or not url.startswith(BASE_URL):
            continue
            
        visited.add(url)
        print(f"🔍 Scanning: {url}")
        
        try:
            # 3. Timeouts & Headers
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status() # Check for 404s or 500s
            
            soup = BeautifulSoup(res.text, 'lxml')
            
            for a in soup.find_all('a'):
                href = a.get('href')
                if not href: 
                    continue
                    
                full_url = urljoin(BASE_URL, href)
                
                # 4. Handle PDFs safely
                if full_url.lower().endswith('.pdf'):
                    if full_url not in visited:
                        visited.add(full_url)
                        download_pdf(full_url)
                        
                # Add new internal HTML links to the queue
                elif full_url.startswith(BASE_URL) and full_url not in visited:
                    to_visit.append(full_url)
                    
            # 5. Rate Limiting: Sleep for 1 second between page hits so we don't get banned
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            # 6. Fault Tolerance: Log the error and keep going, don't crash!
            print(f"⚠️ Error accessing {url}: {e}")

def download_pdf(pdf_url):
    """Safely downloads, decodes, sanitizes, and saves a PDF."""
    try:
        print(f"   ⬇️ Downloading PDF: {pdf_url}")
        res = requests.get(pdf_url, headers=HEADERS, timeout=20)
        res.raise_for_status()
        
        # 1. Extract the raw file name from the URL
        raw_filename = pdf_url.split('/')[-1]
        
        # 2. Decode the URL-encoded string back to normal Nepali text
        decoded_filename = unquote(raw_filename)
        
        # 3. Sanitize: Remove illegal Windows characters just to be safe
        safe_filename = re.sub(r'[\\/*?:"<>|]', "", decoded_filename)
        
        # 4. Handle edge case: if the filename ends up empty or too long, give it a fallback
        if not safe_filename:
            safe_filename = f"document_{int(time.time())}.pdf"
        elif len(safe_filename) > 200:
            safe_filename = safe_filename[-200:] # Keep it under Windows limits
            
        filepath = os.path.join(OUTPUT_DIR, safe_filename)
        
        with open(filepath, 'wb') as f:
            f.write(res.content)
        print(f"   ✅ Saved: {safe_filename}")
        
        # Sleep after downloading a file to be polite to the server
        time.sleep(2)
        
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Failed to download PDF {pdf_url}: {e}")
    except OSError as e:
        print(f"   💾 OS Save Error for {pdf_url}: {e}")

if __name__ == "__main__":
    robust_scrape()
    print("🎉 Scraping complete!")
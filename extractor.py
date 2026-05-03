import os
import fitz  # This is PyMuPDF
import json

# Configuration
INPUT_DIR = "data/raw_pdfs/gokarneshwor"
OUTPUT_DIR = "data/structured_text/gokarneshwor"

def setup_directories():
    """Ensure the output directory exists."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📁 Created directory: {OUTPUT_DIR}")

def extract_text_from_pdfs():
    setup_directories()
    
    # Check if we have PDFs to process
    if not os.path.exists(INPUT_DIR) or not os.listdir(INPUT_DIR):
        print(f"⚠️ No PDFs found in {INPUT_DIR}. Run main.py first.")
        return

    print("🚀 Starting PDF Text Extraction...")
    
    for filename in os.listdir(INPUT_DIR):
        if not filename.lower().endswith(".pdf"):
            continue
            
        filepath = os.path.join(INPUT_DIR, filename)
        print(f"📄 Processing: {filename}")
        
        try:
            # 1. Open the PDF
            doc = fitz.open(filepath)
            full_text = ""
            
            # 2. Iterate through pages and extract text
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                full_text += page.get_text("text") + "\n"
                
            # 3. Clean up the text (remove excessive newlines/spaces)
            clean_text = " ".join(full_text.split())
            
            # 4. Package as JSON with basic metadata
            document_data = {
                "source_file": filename,
                "municipality": "gokarneshwor",
                "content": clean_text
            }
            
            # 5. Save the structured data
            json_filename = filename.replace(".pdf", ".json")
            output_filepath = os.path.join(OUTPUT_DIR, json_filename)
            
            # Ensure UTF-8 encoding so Nepali script isn't corrupted
            with open(output_filepath, "w", encoding="utf-8") as f:
                json.dump(document_data, f, ensure_ascii=False, indent=4)
                
            print(f"   ✅ Extracted and saved to: {json_filename}")
            
        except Exception as e:
            print(f"   ❌ Error processing {filename}: {e}")

if __name__ == "__main__":
    extract_text_from_pdfs()
    print("🎉 Extraction complete!")
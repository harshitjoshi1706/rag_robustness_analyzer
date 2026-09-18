"""Extract PDF text in memory, with stable byte-based identity."""
from hashlib import sha256
import pymupdf

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def extract_pdf(uploaded_file):
    pdf_bytes = uploaded_file.getvalue()
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("Please use a PDF smaller than 50 MB.")
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        if document.needs_pass:
            raise ValueError("This PDF is password-protected. Upload an unlocked copy.")
        pages = [{"page_number": n, "text": page.get_text("text")} for n, page in enumerate(document, 1)]
    full_text = "\n\n".join(page["text"] for page in pages)
    if not full_text.strip():
        raise ValueError("No extractable text was found. Apply OCR to scanned PDFs before uploading.")
    return {
        "filename": uploaded_file.name, "document_id": sha256(pdf_bytes).hexdigest(),
        "num_pages": len(pages), "pages": pages, "full_text": full_text,
        "character_count": len(full_text), "word_count": len(full_text.split()),
    }

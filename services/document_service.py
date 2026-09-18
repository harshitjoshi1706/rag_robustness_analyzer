import pymupdf


def extract_pdf(uploaded_file):
    """
    Extract text and basic metadata from a Streamlit uploaded PDF.
    """

    pdf_bytes = uploaded_file.getvalue()

    document = pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    pages = []

    for page_number, page in enumerate(document, start=1):
        text = page.get_text("text")

        pages.append(
            {
                "page_number": page_number,
                "text": text
            }
        )

    full_text = "\n\n".join(
        page["text"] for page in pages
    )

    result = {
        "filename": uploaded_file.name,
        "num_pages": len(document),
        "pages": pages,
        "full_text": full_text,
        "character_count": len(full_text),
        "word_count": len(full_text.split())
    }

    document.close()

    return result
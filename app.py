import streamlit as st

from services.document_service import extract_pdf


st.set_page_config(
    page_title="RAG Robustness Analyzer",
    page_icon="🔎",
    layout="wide",
)

st.title("RAG Robustness Analyzer")

st.write(
    "Upload a PDF and analyze its text before running "
    "the retrieval pipeline."
)

st.divider()

uploaded_file = st.file_uploader(
    "Upload a PDF document",
    type=["pdf"]
)

if uploaded_file is not None:

    try:
        with st.spinner("Processing PDF..."):
            document = extract_pdf(uploaded_file)

        st.success("PDF processed successfully.")

        st.subheader("Document Information")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Pages",
                document["num_pages"]
            )

        with col2:
            st.metric(
                "Words",
                document["word_count"]
            )

        with col3:
            st.metric(
                "Characters",
                document["character_count"]
            )

        st.write(
            f"**File:** {document['filename']}"
        )

        st.divider()

        st.subheader("Extracted Text Preview")

        preview_length = 5000

        preview = document["full_text"][:preview_length]

        st.text_area(
            "Document text",
            preview,
            height=400,
            disabled=True
        )

        if len(document["full_text"]) > preview_length:
            st.caption(
                "Showing the first 5,000 characters only."
            )

        with st.expander("View individual pages"):

            for page in document["pages"]:

                st.markdown(
                    f"### Page {page['page_number']}"
                )

                st.text(
                    page["text"][:3000]
                )

                st.divider()

    except Exception as error:

        st.error(
            f"Could not process the PDF: {error}"
        )
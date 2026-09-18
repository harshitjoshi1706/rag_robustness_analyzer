import streamlit as st
from services.ui import setup

setup("Home", "🏠")
st.header("Explore how chunking shapes retrieval")
st.write("Find evidence in your PDF, compare four chunking strategies, and explore the saved robustness experiment.")
for column, title, description, page, icon in zip(
    st.columns(3),
    ["Single Retrieval", "Compare Chunkers", "Research Dashboard"],
    ["Upload a PDF and search evidence with one strategy.",
     "Ask the same question across Fixed-size, Recursive, Semantic, and Structure-aware chunking.",
     "Explore retrieval quality, noise degradation, efficiency, and confidence intervals from saved results."],
    ["1_Single_Retrieval.py", "2_Compare_Chunkers.py", "3_Research_Dashboard.py"],
    ["🔎", "⚖️", "📊"],
):
    with column, st.container(border=True):
        st.subheader(title)
        st.write(description)
        st.page_link(f"pages/{page}", label=f"Open {title}", icon=icon)
st.divider()
st.subheader("What to expect")
st.write("Retrieval returns source passages, not generated answers. Similarity scores indicate relevance, not factual confidence. PDF page numbers start at 1 and may differ from printed page labels.")
st.info("Use a text-based PDF. Scanned pages need OCR before upload. Your uploaded document and indexes stay in this session; refreshing or ending the session may clear them.")
st.caption("The Research Dashboard reads the bundled research snapshot. Live PDF retrieval does not change it or run the 16-configuration experiment.")

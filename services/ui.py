"""Shared Streamlit presentation; importing this module never loads the backend."""
import streamlit as st

LABELS = {"fixed": "Fixed-size", "recursive": "Recursive", "semantic": "Semantic", "structure": "Structure-aware"}


def setup(title, icon="🔎"):
    st.set_page_config(page_title=f"{title} · RAG Robustness Analyzer", page_icon=icon, layout="wide")
    with st.sidebar:
        st.title("RAG Robustness Analyzer")
        st.page_link("app.py", label="Home", icon="🏠")
        st.page_link("pages/1_Single_Retrieval.py", label="Single Retrieval", icon="🔎")
        st.page_link("pages/2_Compare_Chunkers.py", label="Compare Chunkers", icon="⚖️")
        st.page_link("pages/3_Research_Dashboard.py", label="Research Dashboard", icon="📊")
        st.divider()
        st.caption("Explore a PDF or inspect the completed research experiment.")
    st.title(title)


def show_error(message, error):
    st.error(message)
    with st.expander("Technical details"):
        st.code(str(error), language=None)


def format_pages(pages):
    if pages is None:
        return "Unavailable"
    if isinstance(pages, (str, int)):
        pages = [pages]
    return ", ".join(str(p) for p in pages) or "Unavailable"


def evidence(results, filename):
    if not results:
        st.info("No evidence was returned.")
    for rank, (score, chunk) in enumerate(results, 1):
        with st.container(border=True):
            st.subheader(f"Result {rank}")
            st.caption(f"Similarity {score:.4f} · {chunk.get('token_count', '—')} tokens")
            st.text(f"Source: {filename} · PDF pages: {format_pages(chunk.get('source_page_ids'))}")
            st.text(chunk["text"])

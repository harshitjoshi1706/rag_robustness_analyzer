"""Shared live workflow. Document data and indexes are private to a session."""
from hashlib import sha256
from time import perf_counter
import streamlit as st
from services.document_service import extract_pdf
from services.ui import LABELS, evidence, show_error, format_pages


@st.cache_resource
def load_model():
    from services.research_backend import get_embedding_model
    return get_embedding_model()


def clear_workspace(mode):
    st.session_state.pop(f"{mode}_workspace", None)
    st.session_state.pop(f"{mode}_upload", None)


def upload_changed(mode):
    if st.session_state.get(f"{mode}_upload") is None:
        st.session_state.pop(f"{mode}_workspace", None)


def run(mode):
    state_key = f"{mode}_workspace"
    state = st.session_state.setdefault(state_key, {})
    st.caption("Text-based PDFs · up to 50 MB · source page numbers start at 1")
    upload = st.file_uploader("Upload or replace PDF", type=["pdf"], key=f"{mode}_upload", on_change=upload_changed, args=(mode,))
    if upload is not None:
        identity = sha256(upload.getvalue()).hexdigest()
        if state.get("identity") != identity or state.get("filename") != upload.name:
            state.clear()
            try:
                with st.spinner("Reading PDF…"):
                    document = extract_pdf(upload)
                state.update(identity=identity, filename=upload.name, document=document)
            except Exception as error:
                show_error("Unable to read this PDF. Try an unlocked, text-based PDF under 50 MB.", error)
                return
    if "document" not in state:
        st.info("Upload a PDF to get started.")
        return
    st.button("Clear document and results", key=f"{mode}_clear", on_click=clear_workspace, args=(mode,))
    document = state["document"]
    st.text(f"Current document: {document['filename']}")
    for col, label, value in zip(st.columns(3), ["Pages", "Words", "Characters"], [document["num_pages"], document["word_count"], document["character_count"]]):
        col.metric(label, f"{value:,}")
    with st.expander("Preview source pages"):
        page = st.selectbox("PDF page", range(1, document["num_pages"] + 1), key=f"{mode}_{state['identity']}_page")
        st.text(document["pages"][page - 1]["text"] or "No text on this page.")
    strategy = st.selectbox("Chunking strategy", list(LABELS), format_func=LABELS.get, index=list(LABELS).index(state.get("strategy", "fixed")), key="single_strategy") if mode == "single" else "all"
    if state.get("strategy") != strategy:
        state.pop("indexes", None)
        state.pop("results", None)
        state["strategy"] = strategy
    if st.button("Build retrieval index" if mode == "single" else "Prepare all four strategies", type="primary", key=f"{mode}_build"):
        state.pop("indexes", None)
        state.pop("results", None)
        try:
            from services import research_backend as backend
            with st.status("Preparing document…", expanded=True) as status:
                st.write("Loading the embedding model. The first run may download model files.")
                model = load_model()
                prepared = {}
                for name in ([strategy] if mode == "single" else LABELS):
                    st.write(f"Building {LABELS[name]} chunks and index…")
                    start = perf_counter()
                    chunks = backend.create_chunks(document, name, model)
                    index = backend.build_retrieval_index(chunks, model)
                    prepared[name] = dict(chunks=chunks, index=index, seconds=perf_counter() - start)
                state["indexes"] = prepared
                status.update(label="Ready to search", state="complete", expanded=False)
        except Exception as error:
            show_error("Could not prepare the document. Check the research backend path and model availability, then retry.", error)
    indexes = state.get("indexes")
    if not indexes:
        return
    st.dataframe([{"Strategy": LABELS[name], "Chunks": len(data["chunks"]), "Average tokens": round(sum(c["token_count"] for c in data["chunks"]) / len(data["chunks"]), 1), "Build seconds": round(data["seconds"], 2)} for name, data in indexes.items()], hide_index=True, width="stretch")
    with st.expander("Inspect generated chunks"):
        for name, data in indexes.items():
            st.write(LABELS[name])
            for number, chunk in enumerate(data["chunks"][:10], 1):
                st.caption(f"Chunk {number} · {chunk['token_count']} tokens · PDF pages {format_pages(chunk.get('source_page_ids'))}")
                st.text(chunk["text"])
            st.caption(f"Showing up to 10 of {len(data['chunks'])} chunks.")
    with st.form(f"{mode}_search"):
        question = st.text_input("Question about this PDF", max_chars=2000)
        top_k = st.selectbox("Results per strategy", range(1, 11), index=4)
        submitted = st.form_submit_button("Search evidence")
    if submitted:
        state.pop("results", None)
        if not question.strip():
            st.warning("Enter a question before searching.")
        else:
            try:
                from services.research_backend import search_document
                with st.spinner("Searching evidence…"):
                    results = {name: search_document(question, data["index"], data["chunks"], load_model(), top_k) for name, data in indexes.items()}
                state.update(results=results, question=question.strip(), top_k=top_k)
            except Exception as error:
                show_error("Search failed. Please retry or rebuild the index.", error)
    if "results" in state:
        st.subheader("Retrieved evidence")
        st.text(f"Results for: {state['question']}")
        st.caption(f"Up to {state['top_k']} results per strategy. Similarity is not a confidence or accuracy score.")
        tabs = st.tabs([LABELS[name] for name in state["results"]])
        for tab, results in zip(tabs, state["results"].values()):
            with tab:
                evidence(results, document["filename"])

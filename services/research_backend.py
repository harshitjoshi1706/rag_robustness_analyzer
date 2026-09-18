from pathlib import Path
import sys
import os

from transformers.utils import logging as transformers_logging

transformers_logging.set_verbosity_error()

# rag_robustness_analyzer/
# and rag_chunk_robustness/
# are sibling folders inside RAG_Project/

PROJECTS_ROOT = Path(__file__).resolve().parents[2]

RESEARCH_ROOT = Path(os.environ.get("RAG_RESEARCH_ROOT", str(PROJECTS_ROOT / "rag_chunk_robustness"))).expanduser().resolve()
RESEARCH_SRC = RESEARCH_ROOT / "src"

if not RESEARCH_SRC.exists():
    raise RuntimeError(
        f"Research backend not found at: {RESEARCH_SRC}. "
        "Set RAG_RESEARCH_ROOT to the rag_chunk_robustness repository directory."
    )

if str(RESEARCH_SRC) not in sys.path:
    sys.path.insert(0, str(RESEARCH_SRC))


# Do not create __pycache__ files in the read-only research repository.
_previous_bytecode_setting = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    from embeddings import (
        load_embedding_model,
        embed_chunk_texts,
        embed_query,
    )

    from faiss_index import (
        create_index,
        add_vectors,
    )

    from retrieval_pipeline import (
        CHUNKERS,
        chunk_document,
        retrieve_one,
    )
finally:
    sys.dont_write_bytecode = _previous_bytecode_setting


def get_embedding_model():
    """
    Load the same embedding model used in the research experiment.
    """
    return load_embedding_model(device="cpu")


def build_uploaded_document(document):
    """
    Convert our uploaded-PDF representation into the format expected
    by the research chunking backend.
    """

    paragraphs = []

    for page in document["pages"]:
        page_number = page["page_number"]
        text = page["text"]

        if not text.strip():
            continue

        paragraphs.append(
            {
                "paragraph_id": f"PAGE_{page_number}",
                "page_idx": page_number,
                "text": text,
            }
        )

    if not paragraphs:
        raise ValueError(
            "No extractable text was found in this PDF."
        )

    return {
        "document_id": document.get("document_id", document["filename"]),
        "title": document["filename"],
        "domain": "uploaded_document",
        "noise_level": "uploaded",
        "paragraphs": paragraphs,
    }


def create_chunks(document, chunker_name, model):
    """
    Run one of the original research chunkers on an uploaded PDF.
    """

    if chunker_name not in CHUNKERS:
        raise ValueError(
            f"Unknown chunking strategy: {chunker_name}"
        )

    research_document = build_uploaded_document(document)

    tokenizer = model.tokenizer

    chunks = chunk_document(
        research_document,
        chunker_name,
        tokenizer,
        model,
    )

    return chunks

def build_retrieval_index(chunks, model):
    """
    Embed all generated chunks and build a FAISS index.
    """

    if not chunks:
        raise ValueError("Cannot build an index from empty chunks.")

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    vectors = embed_chunk_texts(
        texts,
        model,
    )

    index = create_index()

    add_vectors(
        index,
        vectors,
    )

    if index.ntotal != len(chunks):
        raise RuntimeError(
            "FAISS index size does not match chunk count."
        )

    return index


def search_document(
    question,
    index,
    chunks,
    model,
    top_k=5,
):
    """
    Retrieve the most relevant chunks for a user question.
    """

    question = question.strip()

    if not question:
        raise ValueError(
            "Question cannot be empty."
        )

    query_vector = embed_query(
        question,
        model,
    )

    top_k = min(
        top_k,
        len(chunks),
    )

    results = retrieve_one(
        index,
        chunks,
        query_vector,
        k=top_k,
    )

    return results

def build_comparison_indexes(document, model):
    """
    Process the same uploaded document with all four chunking
    strategies and build one FAISS index for each strategy.
    """

    comparison_data = {}

    for chunker_name in CHUNKERS:

        chunks = create_chunks(
            document,
            chunker_name,
            model,
        )

        index = build_retrieval_index(
            chunks,
            model,
        )

        comparison_data[chunker_name] = {
            "chunks": chunks,
            "index": index,
        }

    return comparison_data


def compare_chunkers(
    question,
    comparison_data,
    model,
    top_k=3,
):
    """
    Run the same question against all four chunking strategies.
    """

    comparison_results = {}

    for chunker_name, data in comparison_data.items():

        results = search_document(
            question,
            data["index"],
            data["chunks"],
            model,
            top_k=top_k,
        )

        comparison_results[chunker_name] = results

    return comparison_results

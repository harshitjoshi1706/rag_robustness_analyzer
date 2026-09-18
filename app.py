import streamlit as st

from services.document_service import extract_pdf
from services.research_backend import (
    create_chunks,
    get_embedding_model,
    build_retrieval_index,
    search_document,
    build_comparison_indexes,
    compare_chunkers,
)


# -------------------------------------------------
# Constants
# -------------------------------------------------

STRATEGY_LABELS = {
    "fixed": "Fixed-size",
    "recursive": "Recursive",
    "semantic": "Semantic",
    "structure": "Structure-aware",
}


# -------------------------------------------------
# Streamlit page configuration
# -------------------------------------------------

st.set_page_config(
    page_title="RAG Robustness Analyzer",
    page_icon="🔎",
    layout="wide",
)


# -------------------------------------------------
# Load and cache embedding model
# -------------------------------------------------

@st.cache_resource
def load_model():
    return get_embedding_model()


# -------------------------------------------------
# Helper functions
# -------------------------------------------------

def format_pages(pages):
    """
    Convert source page IDs into a readable string.
    """

    if not pages:
        return "Unknown"

    return ", ".join(str(page) for page in pages)


# -------------------------------------------------
# Session state initialization
# -------------------------------------------------

if "chunks" not in st.session_state:
    st.session_state.chunks = None

if "index" not in st.session_state:
    st.session_state.index = None

if "processed_file" not in st.session_state:
    st.session_state.processed_file = None

if "processed_chunker" not in st.session_state:
    st.session_state.processed_chunker = None

if "comparison_data" not in st.session_state:
    st.session_state.comparison_data = None

if "comparison_file" not in st.session_state:
    st.session_state.comparison_file = None


# -------------------------------------------------
# Application header
# -------------------------------------------------

st.title("RAG Robustness Analyzer")

st.write(
    "Upload a PDF, select a chunking strategy, "
    "and retrieve relevant evidence from the document."
)

st.divider()


# -------------------------------------------------
# PDF upload
# -------------------------------------------------

uploaded_file = st.file_uploader(
    "Upload a PDF document",
    type=["pdf"],
)


if uploaded_file is not None:

    try:

        # -------------------------------------------------
        # Extract PDF text
        # -------------------------------------------------

        with st.spinner("Extracting PDF text..."):
            document = extract_pdf(uploaded_file)

        current_filename = document["filename"]

        st.success("PDF processed successfully.")


        # -------------------------------------------------
        # Clear stale single-strategy data
        # -------------------------------------------------

        if (
            st.session_state.processed_file is not None
            and st.session_state.processed_file != current_filename
        ):
            st.session_state.chunks = None
            st.session_state.index = None
            st.session_state.processed_file = None
            st.session_state.processed_chunker = None


        # -------------------------------------------------
        # Clear stale comparison data
        # -------------------------------------------------

        if (
            st.session_state.comparison_file is not None
            and st.session_state.comparison_file != current_filename
        ):
            st.session_state.comparison_data = None
            st.session_state.comparison_file = None


        # -------------------------------------------------
        # Document information
        # -------------------------------------------------

        st.subheader("Document Information")

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Pages",
            document["num_pages"],
        )

        col2.metric(
            "Words",
            document["word_count"],
        )

        col3.metric(
            "Characters",
            document["character_count"],
        )

        st.write(
            f"**File:** {current_filename}"
        )

        st.divider()


        # =================================================
        # SINGLE CHUNKING STRATEGY MODE
        # =================================================

        st.header("Single Strategy Retrieval")

        st.write(
            "Choose one chunking strategy, build its retrieval "
            "index, and search the document."
        )


        # -------------------------------------------------
        # Chunking configuration
        # -------------------------------------------------

        chunker_name = st.selectbox(
            "Select chunking strategy",
            options=[
                "fixed",
                "recursive",
                "semantic",
                "structure",
            ],
            format_func=lambda strategy: STRATEGY_LABELS[strategy],
            key="single_chunker",
        )


        process_button = st.button(
            "Process Document",
            type="primary",
            key="process_single_document",
        )


        # -------------------------------------------------
        # Process document
        # -------------------------------------------------

        if process_button:

            with st.spinner(
                "Creating chunks, embeddings, and FAISS index..."
            ):

                model = load_model()

                # Create chunks using the research backend
                chunks = create_chunks(
                    document,
                    chunker_name,
                    model,
                )

                # Embed chunks and create FAISS index
                faiss_index = build_retrieval_index(
                    chunks,
                    model,
                )

                # Store processed data
                st.session_state.chunks = chunks
                st.session_state.index = faiss_index
                st.session_state.processed_file = current_filename
                st.session_state.processed_chunker = chunker_name

            st.success(
                f"Created {len(chunks)} chunks using "
                f"{STRATEGY_LABELS[chunker_name]} chunking "
                f"and built the FAISS retrieval index."
            )


        # -------------------------------------------------
        # Display processed document
        # -------------------------------------------------

        if (
            st.session_state.chunks is not None
            and st.session_state.index is not None
            and st.session_state.processed_file == current_filename
        ):

            chunks = st.session_state.chunks

            st.divider()

            st.subheader("Processed Document")

            st.write(
                "**Chunking strategy:** "
                f"{STRATEGY_LABELS[st.session_state.processed_chunker]}"
            )


            # -------------------------------------------------
            # Chunk statistics
            # -------------------------------------------------

            token_counts = [
                chunk["token_count"]
                for chunk in chunks
            ]

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Chunks",
                len(chunks),
            )

            col2.metric(
                "Average Tokens",
                round(
                    sum(token_counts) / len(token_counts),
                    1,
                ),
            )

            col3.metric(
                "Maximum Tokens",
                max(token_counts),
            )


            # -------------------------------------------------
            # Chunk preview
            # -------------------------------------------------

            st.subheader("Generated Chunks")

            for chunk_number, chunk in enumerate(
                chunks[:20],
                start=1,
            ):

                with st.expander(
                    f"Chunk {chunk_number} — "
                    f"{chunk['token_count']} tokens"
                ):

                    pages = chunk.get(
                        "source_page_ids",
                        [],
                    )

                    if pages:
                        st.write(
                            f"**Source pages:** "
                            f"{format_pages(pages)}"
                        )

                    st.write(
                        chunk["text"]
                    )

            if len(chunks) > 20:

                st.info(
                    f"Showing the first 20 of "
                    f"{len(chunks)} chunks."
                )


            # =================================================
            # SINGLE-STRATEGY QUESTION RETRIEVAL
            # =================================================

            st.divider()

            st.subheader("Ask a Question")

            st.caption(
                f"Searching {len(chunks)} chunks using "
                f"{STRATEGY_LABELS[st.session_state.processed_chunker]} "
                f"chunking."
            )


            question = st.text_input(
                "Enter your question about the document",
                placeholder=(
                    "Example: What is the main objective "
                    "of this research?"
                ),
                key="single_question",
            )


            top_k = st.slider(
                "Number of retrieved results",
                min_value=1,
                max_value=min(10, len(chunks)),
                value=min(5, len(chunks)),
                key="single_top_k",
            )


            search_button = st.button(
                "Search Document",
                key="single_search_button",
            )


            # -------------------------------------------------
            # Run FAISS retrieval
            # -------------------------------------------------

            if search_button:

                if not question.strip():

                    st.warning(
                        "Please enter a question."
                    )

                else:

                    with st.spinner(
                        "Searching document..."
                    ):

                        model = load_model()

                        results = search_document(
                            question,
                            st.session_state.index,
                            st.session_state.chunks,
                            model,
                            top_k=top_k,
                        )


                    # -------------------------------------------------
                    # Display retrieved evidence
                    # -------------------------------------------------

                    st.subheader(
                        "Retrieved Evidence"
                    )

                    for rank, (score, chunk) in enumerate(
                        results,
                        start=1,
                    ):

                        st.markdown(
                            f"### Result #{rank}"
                        )

                        col1, col2 = st.columns(2)

                        col1.metric(
                            "Similarity Score",
                            f"{score:.4f}",
                        )

                        col2.metric(
                            "Tokens",
                            chunk["token_count"],
                        )

                        pages = chunk.get(
                            "source_page_ids",
                            [],
                        )

                        if pages:
                            st.write(
                                f"**Source pages:** "
                                f"{format_pages(pages)}"
                            )

                        st.write(
                            chunk["text"]
                        )

                        st.divider()


        # =================================================
        # COMPARE CHUNKING STRATEGIES
        # =================================================

        st.divider()

        st.header("Compare Chunking Strategies")

        st.write(
            "Process the same PDF using Fixed-size, Recursive, "
            "Semantic, and Structure-aware chunking, then run "
            "the same question against all four retrieval indexes."
        )


        prepare_comparison = st.button(
            "Prepare All Four Strategies",
            key="prepare_comparison",
        )


        # -------------------------------------------------
        # Build four chunking + FAISS configurations
        # -------------------------------------------------

        if prepare_comparison:

            with st.spinner(
                "Processing the document with all four chunking "
                "strategies. This may take a little while..."
            ):

                model = load_model()

                comparison_data = build_comparison_indexes(
                    document,
                    model,
                )

                st.session_state.comparison_data = (
                    comparison_data
                )

                st.session_state.comparison_file = (
                    current_filename
                )

            st.success(
                "All four chunking strategies are ready."
            )


        # -------------------------------------------------
        # Display comparison mode
        # -------------------------------------------------

        if (
            st.session_state.comparison_data is not None
            and st.session_state.comparison_file
            == current_filename
        ):

            comparison_data = (
                st.session_state.comparison_data
            )


            # -------------------------------------------------
            # Chunking summary
            # -------------------------------------------------

            st.subheader(
                "Chunking Summary"
            )

            summary_rows = []

            for strategy, data in comparison_data.items():

                strategy_chunks = data["chunks"]

                token_counts = [
                    chunk["token_count"]
                    for chunk in strategy_chunks
                ]

                summary_rows.append(
                    {
                        "Strategy":
                            STRATEGY_LABELS[strategy],

                        "Chunks":
                            len(strategy_chunks),

                        "Average Tokens":
                            round(
                                sum(token_counts)
                                / len(token_counts),
                                1,
                            ),

                        "Maximum Tokens":
                            max(token_counts),
                    }
                )


            st.dataframe(
                summary_rows,
                use_container_width=True,
                hide_index=True,
            )


            # -------------------------------------------------
            # Comparison retrieval
            # -------------------------------------------------

            st.subheader(
                "Compare Retrieval"
            )


            comparison_question = st.text_input(
                "Ask the same question across all four strategies",
                placeholder=(
                    "Example: What embedding model "
                    "was used in the experiment?"
                ),
                key="comparison_question",
            )


            comparison_top_k = st.slider(
                "Results per strategy",
                min_value=1,
                max_value=5,
                value=3,
                key="comparison_top_k",
            )


            compare_button = st.button(
                "Compare Retrieval Results",
                key="compare_retrieval_button",
            )


            # -------------------------------------------------
            # Search all four indexes
            # -------------------------------------------------

            if compare_button:

                if not comparison_question.strip():

                    st.warning(
                        "Please enter a question."
                    )

                else:

                    with st.spinner(
                        "Searching all four indexes..."
                    ):

                        model = load_model()

                        comparison_results = compare_chunkers(
                            comparison_question,
                            comparison_data,
                            model,
                            top_k=comparison_top_k,
                        )


                    # -------------------------------------------------
                    # Top-result overview
                    # -------------------------------------------------

                    st.subheader(
                        "Top Result Overview"
                    )

                    overview_rows = []

                    for strategy, results in (
                        comparison_results.items()
                    ):

                        if not results:
                            continue

                        top_score = results[0][0]
                        top_chunk = results[0][1]

                        pages = top_chunk.get(
                            "source_page_ids",
                            [],
                        )

                        overview_rows.append(
                            {
                                "Strategy":
                                    STRATEGY_LABELS[strategy],

                                "Top Similarity":
                                    round(
                                        top_score,
                                        4,
                                    ),

                                "Chunks":
                                    len(
                                        comparison_data[
                                            strategy
                                        ]["chunks"]
                                    ),

                                "Top Source Pages":
                                    format_pages(pages),
                            }
                        )


                    st.dataframe(
                        overview_rows,
                        use_container_width=True,
                        hide_index=True,
                    )


                    # -------------------------------------------------
                    # Detailed comparison results
                    # -------------------------------------------------

                    st.subheader(
                        "Detailed Retrieved Evidence"
                    )


                    strategies = [
                        "fixed",
                        "recursive",
                        "semantic",
                        "structure",
                    ]


                    tabs = st.tabs(
                        [
                            STRATEGY_LABELS[strategy]
                            for strategy in strategies
                        ]
                    )


                    for tab, strategy in zip(
                        tabs,
                        strategies,
                    ):

                        with tab:

                            results = comparison_results[
                                strategy
                            ]

                            for rank, (
                                score,
                                chunk,
                            ) in enumerate(
                                results,
                                start=1,
                            ):

                                st.markdown(
                                    f"### Result #{rank}"
                                )

                                col1, col2 = (
                                    st.columns(2)
                                )

                                col1.metric(
                                    "Similarity",
                                    f"{score:.4f}",
                                )

                                col2.metric(
                                    "Tokens",
                                    chunk["token_count"],
                                )

                                pages = chunk.get(
                                    "source_page_ids",
                                    [],
                                )

                                if pages:

                                    st.write(
                                        f"**Source pages:** "
                                        f"{format_pages(pages)}"
                                    )

                                st.write(
                                    chunk["text"]
                                )

                                st.divider()


    except Exception as error:

        st.error(
            f"Error: {error}"
        )
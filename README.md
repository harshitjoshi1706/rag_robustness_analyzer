# RAG Robustness Analyzer

A Streamlit-only application for exploring PDF retrieval and the completed OHRBench chunking robustness experiment. It returns evidence passages, not generated answers. No API server, frontend build, or paid LLM API is required.

## Setup and run

Tested locally with Python 3.11 and Streamlit 1.64.0 on macOS. The full dependency snapshot is retained in `requirements.txt` to preserve the working research integration. Other platforms may require compatible PyTorch/FAISS wheels; a fresh cross-platform installation has not been validated.

```bash
cd /path/to/rag_robustness_analyzer
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Always start from `app.py`, not an individual page. Open the local URL printed by Streamlit.

Live retrieval uses the existing research source without copying or changing its algorithms. By default, the repositories should be siblings:

```text
RAG_Project/
├── rag_chunk_robustness/src/
└── rag_robustness_analyzer/
```

For a different location, set the path to the research repository (not its `src` directory) before starting Streamlit:

```bash
export RAG_RESEARCH_ROOT="/absolute/path/to/rag_chunk_robustness"
python -m streamlit run app.py
```

Restart Streamlit after changing this path. The adapter imports the research modules by their existing names; avoid other packages with conflicting names such as `embeddings` on the Python path. Packaging the research backend as a namespaced dependency is a separate future change, not part of this application refactor.

The first live indexing operation loads `sentence-transformers/all-MiniLM-L6-v2` on CPU and may download its files into the normal Hugging Face cache. Once cached, the model can run offline. Only the model resource is shared across sessions; uploaded PDFs, chunks, indexes, and questions are session-local. This application does not save uploads to disk. A browser refresh, server restart, or session timeout may lose the current document.

### Dashboard-only installation

The Home page and Research Dashboard work without the research repository or embedding model:

```bash
python -m pip install -r requirements-dashboard.txt
python -m streamlit run app.py
```

Live retrieval requires the full requirements and backend source. Hosting the full app requires provisioning that source plus sufficient CPU and RAM; configuring only the analyzer repository is sufficient for the saved dashboard, not live retrieval.

## Pages and features

- **Home:** workflow overview, navigation, and explanation of retrieval and source attribution.
- **Single Retrieval:** extract a PDF, choose a strategy, build a FAISS index, search, inspect chunks and original page text, and retain evidence across reruns.
- **Compare Chunkers:** build Fixed-size, Recursive, Semantic, and Structure-aware indexes on the same PDF and search one question across all four. Includes chunk counts, token statistics, measured live build time, and evidence tabs.
- **Research Dashboard:** saved retrieval metrics, severe-noise degradation, efficiency, context-verified sensitivity, and bootstrap confidence intervals. It never executes the research experiment.

Uploads use SHA-256 content identity, so a different PDF with the same filename cannot reuse stale results. Each live page keeps its own document workspace. Replacing a document or changing the single strategy invalidates indexes and evidence. Returning to a page retains its processed document even if the uploader widget has been cleared by Streamlit navigation. Use **Clear document and results** to release that workspace. Builds publish indexes only when all requested strategies succeed. Failed searches clear prior evidence to prevent confusion.

PDF text is displayed as literal text. Source page numbers are one-based PDF positions, not printed page labels. Similarity is a ranking signal, not a confidence percentage or a measured accuracy score. Requested result counts are capped by the available chunks.

## Architecture

```text
app.py                         Home
pages/
  1_Single_Retrieval.py         Single-strategy entrypoint
  2_Compare_Chunkers.py         Four-strategy entrypoint
  3_Research_Dashboard.py       Saved experiment visualization
services/
  ui.py                        Shared navigation, errors, evidence rendering
  live_ui.py                   Session lifecycle, indexing and search UI
  document_service.py          In-memory PDF extraction and content identity
  research_backend.py          Adapter to existing research source
  results_service.py           Saved CSV/manifest readers and schema checks
.streamlit/config.toml         Shared theme, upload limit, navigation settings
 data/research_results/        Bundled research snapshot
 tests/test_app.py             Offline regression checks
```

The legacy `services/retrieval_service.py`, if present, is retained but is not used by the new pages. The adapter creates in-memory indexes and suppresses bytecode writes while importing research modules. It does not call experiment runners or index-saving functions.

## Research data

The dashboard reads these files relative to the analyzer repository, independent of the current working directory:

```text
data/research_results/
  final_metrics.csv
  robustness_degradation.csv
  sensitivity_metrics.csv
  efficiency_table.csv
  statistical_results.csv
  experiment_manifest.json
```

These are a snapshot of the completed research, not synthetic demo data. The manifest supplies configuration completion, question counts, model, token budget, and retrieval depth (Top-100 in this snapshot). The primary evaluation contains 8,456 questions; the context-verified subset contains 5,277. Live PDF searches do not update these numbers. Keep the research repository as the source of truth and copy updated artifacts only deliberately. Do not rerun the experiment to start the app.

## Validation

```bash
python -m unittest discover -s tests -v
```

The suite checks PDF identity and rejection paths, saved result loading, all page navigation and dashboard selectors, result persistence, strategy invalidation, comparison indexing, same-name PDF replacement, and clearing a workspace. UI lifecycle tests stub the expensive backend to avoid model downloads. They do not evaluate retrieval quality. A separate local smoke check has exercised the actual cached MiniLM model, all four research chunkers, FAISS indexes, and retrieval on a two-page synthetic PDF without running the experiment.

## Limits and troubleshooting

- Maximum upload size is 50 MB. Scanned/image-only PDFs require external OCR. Password-protected or malformed PDFs are rejected with a recoverable error.
- Large PDFs and semantic chunking can take time and substantial RAM. Processing is synchronous; there is no background queue or cancellation control.
- If a backend is missing, set `RAG_RESEARCH_ROOT` and install full dependencies. Home and the dashboard remain usable.
- If model loading fails, check connectivity or the local Hugging Face cache, then retry. Errors include an expandable technical detail panel.
- If saved results fail to load, restore the six artifacts above with their original schemas. The app never repairs, fabricates, or overwrites research results.
- Public multi-user deployment, authentication, resource quotas, OCR, generated answers, and backend packaging are outside this application's current scope.

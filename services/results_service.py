from pathlib import Path
import json

import pandas as pd


# -------------------------------------------------
# Paths
# -------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RESULTS_DIR = (
    PROJECT_ROOT
    / "data"
    / "research_results"
)


FINAL_METRICS_FILE = RESULTS_DIR / "final_metrics.csv"

ROBUSTNESS_FILE = (
    RESULTS_DIR
    / "robustness_degradation.csv"
)

SENSITIVITY_FILE = (
    RESULTS_DIR
    / "sensitivity_metrics.csv"
)

EFFICIENCY_FILE = (
    RESULTS_DIR
    / "efficiency_table.csv"
)

STATISTICS_FILE = (
    RESULTS_DIR
    / "statistical_results.csv"
)

MANIFEST_FILE = (
    RESULTS_DIR
    / "experiment_manifest.json"
)


# -------------------------------------------------
# Display ordering
# -------------------------------------------------

NOISE_ORDER = [
    "clean",
    "mild",
    "moderate",
    "severe",
]


CHUNKER_ORDER = [
    "fixed",
    "recursive",
    "semantic",
    "structure",
]


CHUNKER_LABELS = {
    "fixed": "Fixed-size",
    "recursive": "Recursive",
    "semantic": "Semantic",
    "structure": "Structure-aware",
}


METRIC_LABELS = {
    "hit_at_1": "Hit@1",
    "hit_at_5": "Hit@5",
    "mrr_at_100": "MRR@100",
}


# -------------------------------------------------
# Validation helpers
# -------------------------------------------------

def _require_file(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Research result file not found: {path}"
        )


def _validate_columns(
    dataframe,
    required_columns,
    filename,
):
    missing = (
        required_columns
        - set(dataframe.columns)
    )

    if missing:
        raise ValueError(
            f"{filename} is missing columns: "
            f"{sorted(missing)}"
        )


def _order_results(dataframe):
    result = dataframe.copy()

    if "chunker" in result.columns:
        result["chunker"] = pd.Categorical(
            result["chunker"],
            categories=CHUNKER_ORDER,
            ordered=True,
        )

    if "noise_level" in result.columns:
        result["noise_level"] = pd.Categorical(
            result["noise_level"],
            categories=NOISE_ORDER,
            ordered=True,
        )

    sort_columns = []

    if "chunker" in result.columns:
        sort_columns.append("chunker")

    if "noise_level" in result.columns:
        sort_columns.append("noise_level")

    if sort_columns:
        result = result.sort_values(
            sort_columns
        )

    return result.reset_index(drop=True)


# -------------------------------------------------
# Manifest
# -------------------------------------------------

def load_manifest():

    _require_file(MANIFEST_FILE)

    with MANIFEST_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


# -------------------------------------------------
# Main metrics
# -------------------------------------------------

def load_final_metrics():

    _require_file(FINAL_METRICS_FILE)

    dataframe = pd.read_csv(
        FINAL_METRICS_FILE
    )

    required_columns = {
        "chunker",
        "noise_level",
        "num_queries",
        "hit_at_1",
        "hit_at_5",
        "mrr_at_100",
        "evaluation_set",
    }

    _validate_columns(
        dataframe,
        required_columns,
        "final_metrics.csv",
    )

    return _order_results(dataframe)


# -------------------------------------------------
# Robustness degradation
# -------------------------------------------------

def load_robustness_degradation():

    _require_file(ROBUSTNESS_FILE)

    dataframe = pd.read_csv(
        ROBUSTNESS_FILE
    )

    required_columns = {
        "evaluation_set",
        "chunker",
        "noise_level",
        "metric",
        "clean_value",
        "noisy_value",
        "absolute_degradation",
        "relative_degradation_percent",
    }

    _validate_columns(
        dataframe,
        required_columns,
        "robustness_degradation.csv",
    )

    return _order_results(dataframe)


# -------------------------------------------------
# Sensitivity results
# -------------------------------------------------

def load_sensitivity_metrics():

    _require_file(SENSITIVITY_FILE)

    dataframe = pd.read_csv(
        SENSITIVITY_FILE
    )

    required_columns = {
        "chunker",
        "noise_level",
        "num_queries",
        "hit_at_1",
        "hit_at_5",
        "mrr_at_100",
        "evaluation_set",
    }

    _validate_columns(
        dataframe,
        required_columns,
        "sensitivity_metrics.csv",
    )

    return _order_results(dataframe)


# -------------------------------------------------
# Efficiency
# -------------------------------------------------

def load_efficiency_metrics():

    _require_file(EFFICIENCY_FILE)

    dataframe = pd.read_csv(
        EFFICIENCY_FILE
    )

    required_columns = {
        "noise_level",
        "chunker",
        "num_documents",
        "num_pages",
        "num_chunks",
        "chunking_time_sec",
        "embedding_time_sec",
        "index_build_time_sec",
        "total_retrieval_time_sec",
        "mean_query_latency_ms",
        "peak_memory_mb",
        "index_size_bytes",
        "status",
    }

    _validate_columns(
        dataframe,
        required_columns,
        "efficiency_table.csv",
    )

    dataframe[
        "total_configuration_time_sec"
    ] = (
        dataframe["chunking_time_sec"]
        + dataframe["embedding_time_sec"]
        + dataframe["index_build_time_sec"]
        + dataframe["total_retrieval_time_sec"]
    )

    dataframe[
        "total_configuration_time_min"
    ] = (
        dataframe[
            "total_configuration_time_sec"
        ]
        / 60
    )

    dataframe["index_size_mb"] = (
        dataframe["index_size_bytes"]
        / (1024 * 1024)
    )

    return _order_results(dataframe)


# -------------------------------------------------
# Statistical results
# -------------------------------------------------

def load_statistical_results():

    _require_file(STATISTICS_FILE)

    dataframe = pd.read_csv(
        STATISTICS_FILE
    )

    required_columns = {
        "evaluation_set",
        "statistic",
        "chunker",
        "noise_level",
        "metric",
        "estimate",
        "ci_95_low",
        "ci_95_high",
        "bootstrap_iterations",
        "seed",
    }

    _validate_columns(
        dataframe,
        required_columns,
        "statistical_results.csv",
    )

    return _order_results(dataframe)


# -------------------------------------------------
# Dashboard summary
# -------------------------------------------------

def get_experiment_summary():

    manifest = load_manifest()

    configurations = manifest.get(
        "configurations",
        {},
    )

    completed = sum(
        status == "complete"
        for status in configurations.values()
    )

    return {
        "run_id":
            manifest.get("run_id"),

        "model":
            manifest.get("model"),

        "embedding_dimension":
            manifest.get(
                "embedding_dimension"
            ),

        "primary_qas":
            manifest.get("primary_qas"),

        "context_verified_qas":
            manifest.get(
                "context_verified_qas"
            ),

        "top_k":
            manifest.get("top_k"),

        "content_token_budget":
            manifest.get(
                "content_token_budget"
            ),

        "completed_configurations":
            completed,

        "total_configurations":
            len(configurations),
    }
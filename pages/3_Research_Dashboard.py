import streamlit as st
import pandas as pd

from services.results_service import (
    CHUNKER_LABELS,
    METRIC_LABELS,
    NOISE_ORDER,
    get_experiment_summary,
    load_final_metrics,
    load_robustness_degradation,
    load_sensitivity_metrics,
    load_efficiency_metrics,
    load_statistical_results,
)


st.set_page_config(
    page_title="Research Dashboard",
    page_icon="📊",
    layout="wide",
)


st.title("Research Dashboard")

st.write(
    "Results from the completed 4 × 4 chunking robustness "
    "experiment on OHRBench."
)


try:

    # =====================================================
    # LOAD DATA
    # =====================================================

    summary = get_experiment_summary()

    final_metrics = load_final_metrics()

    robustness = load_robustness_degradation()

    sensitivity = load_sensitivity_metrics()

    efficiency = load_efficiency_metrics()

    statistics = load_statistical_results()


    # =====================================================
    # EXPERIMENT SUMMARY
    # =====================================================

    st.divider()

    st.header("Experiment Summary")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Configurations",
        (
            f"{summary['completed_configurations']}"
            f"/{summary['total_configurations']}"
        ),
    )

    col2.metric(
        "Primary Questions",
        f"{summary['primary_qas']:,}",
    )

    col3.metric(
        "Context-Verified Questions",
        f"{summary['context_verified_qas']:,}",
    )

    col4.metric(
        "Retrieval Depth",
        f"Top-{summary['top_k']}",
    )


    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Embedding Dimensions",
        summary["embedding_dimension"],
    )

    col2.metric(
        "Chunk Token Budget",
        summary["content_token_budget"],
    )

    col3.metric(
        "Model",
        "all-MiniLM-L6-v2",
    )


    # =====================================================
    # PRIMARY RETRIEVAL PERFORMANCE
    # =====================================================

    st.divider()

    st.header("Primary Retrieval Performance")

    st.caption(
        "Primary evaluation over 8,456 mapped OHRBench questions."
    )


    selected_metric = st.selectbox(
        "Retrieval metric",
        options=[
            "hit_at_1",
            "hit_at_5",
            "mrr_at_100",
        ],
        format_func=lambda metric:
            METRIC_LABELS[metric],
    )


    performance = final_metrics[
        [
            "chunker",
            "noise_level",
            selected_metric,
        ]
    ].copy()


    performance["Strategy"] = (
        performance["chunker"]
        .astype(str)
        .map(CHUNKER_LABELS)
    )


    performance["Noise"] = (
        performance["noise_level"]
        .astype(str)
        .str.title()
    )


    performance_table = (
        performance
        .pivot(
            index="Noise",
            columns="Strategy",
            values=selected_metric,
        )
        .reindex(
            [
                "Clean",
                "Mild",
                "Moderate",
                "Severe",
            ]
        )
    )


    st.line_chart(
        performance_table
    )


    display_performance = (
        performance_table
        .transpose()
        .round(4)
    )


    st.dataframe(
        display_performance,
        use_container_width=True,
    )


    # =====================================================
    # ROBUSTNESS DEGRADATION
    # =====================================================

    st.divider()

    st.header("Robustness Degradation")


    robustness_metric = st.selectbox(
        "Degradation metric",
        options=[
            "hit_at_1",
            "hit_at_5",
            "mrr_at_100",
        ],
        format_func=lambda metric:
            METRIC_LABELS[metric],
        key="robustness_metric",
    )


    severe_degradation = robustness[
        (robustness["evaluation_set"] == "primary")
        & (robustness["noise_level"].astype(str) == "severe")
        & (robustness["metric"] == robustness_metric)
    ].copy()


    severe_degradation["Strategy"] = (
        severe_degradation["chunker"]
        .astype(str)
        .map(CHUNKER_LABELS)
    )


    degradation_chart = (
        severe_degradation
        .set_index("Strategy")[
            "relative_degradation_percent"
        ]
    )


    st.bar_chart(
        degradation_chart
    )


    degradation_display = severe_degradation[
        [
            "Strategy",
            "clean_value",
            "noisy_value",
            "absolute_degradation",
            "relative_degradation_percent",
        ]
    ].copy()


    degradation_display.columns = [
        "Strategy",
        "Clean Score",
        "Severe Score",
        "Absolute Drop",
        "Relative Drop (%)",
    ]


    degradation_display[
        [
            "Clean Score",
            "Severe Score",
            "Absolute Drop",
            "Relative Drop (%)",
        ]
    ] = degradation_display[
        [
            "Clean Score",
            "Severe Score",
            "Absolute Drop",
            "Relative Drop (%)",
        ]
    ].round(4)


    st.dataframe(
        degradation_display,
        use_container_width=True,
        hide_index=True,
    )


    # =====================================================
    # EFFICIENCY
    # =====================================================

    st.divider()

    st.header("Efficiency and Index Growth")


    efficiency_metric = st.selectbox(
        "Efficiency metric",
        options=[
            "num_chunks",
            "total_configuration_time_min",
            "mean_query_latency_ms",
            "index_size_mb",
        ],
        format_func=lambda metric: {
            "num_chunks":
                "Number of Chunks",

            "total_configuration_time_min":
                "Configuration Runtime (minutes)",

            "mean_query_latency_ms":
                "Mean Query Latency (ms)",

            "index_size_mb":
                "Index Size (MB)",
        }[metric],
    )


    efficiency_plot = efficiency[
        [
            "chunker",
            "noise_level",
            efficiency_metric,
        ]
    ].copy()


    efficiency_plot["Strategy"] = (
        efficiency_plot["chunker"]
        .astype(str)
        .map(CHUNKER_LABELS)
    )


    efficiency_plot["Noise"] = (
        efficiency_plot["noise_level"]
        .astype(str)
        .str.title()
    )


    efficiency_chart = (
        efficiency_plot
        .pivot(
            index="Noise",
            columns="Strategy",
            values=efficiency_metric,
        )
        .reindex(
            [
                "Clean",
                "Mild",
                "Moderate",
                "Severe",
            ]
        )
    )


    st.line_chart(
        efficiency_chart
    )


    efficiency_display = efficiency[
        [
            "chunker",
            "noise_level",
            "num_chunks",
            "total_configuration_time_min",
            "mean_query_latency_ms",
            "index_size_mb",
        ]
    ].copy()


    efficiency_display["chunker"] = (
        efficiency_display["chunker"]
        .astype(str)
        .map(CHUNKER_LABELS)
    )


    efficiency_display["noise_level"] = (
        efficiency_display["noise_level"]
        .astype(str)
        .str.title()
    )


    efficiency_display.columns = [
        "Strategy",
        "Noise",
        "Chunks",
        "Runtime (min)",
        "Mean Query Latency (ms)",
        "Index Size (MB)",
    ]


    efficiency_display[
        "Runtime (min)"
    ] = efficiency_display[
        "Runtime (min)"
    ].round(2)


    efficiency_display[
        "Mean Query Latency (ms)"
    ] = efficiency_display[
        "Mean Query Latency (ms)"
    ].round(3)


    efficiency_display[
        "Index Size (MB)"
    ] = efficiency_display[
        "Index Size (MB)"
    ].round(1)


    st.dataframe(
        efficiency_display,
        use_container_width=True,
        hide_index=True,
    )


    # =====================================================
    # SENSITIVITY ANALYSIS
    # =====================================================

    st.divider()

    st.header(
        "Context-Verified Sensitivity Analysis"
    )

    st.caption(
        "Comparison of primary results with the stricter "
        "5,277-question context-verified subset."
    )


    sensitivity_metric = st.selectbox(
        "Sensitivity metric",
        options=[
            "hit_at_1",
            "hit_at_5",
            "mrr_at_100",
        ],
        format_func=lambda metric:
            METRIC_LABELS[metric],
        key="sensitivity_metric",
    )


    primary_severe = final_metrics[
        final_metrics["noise_level"].astype(str)
        == "severe"
    ][
        [
            "chunker",
            sensitivity_metric,
        ]
    ].copy()


    primary_severe = primary_severe.rename(
        columns={
            sensitivity_metric:
                "Primary",
        }
    )


    context_severe = sensitivity[
        sensitivity["noise_level"].astype(str)
        == "severe"
    ][
        [
            "chunker",
            sensitivity_metric,
        ]
    ].copy()


    context_severe = context_severe.rename(
        columns={
            sensitivity_metric:
                "Context-Verified",
        }
    )


    sensitivity_comparison = (
        primary_severe.merge(
            context_severe,
            on="chunker",
        )
    )


    sensitivity_comparison[
        "Strategy"
    ] = (
        sensitivity_comparison["chunker"]
        .astype(str)
        .map(CHUNKER_LABELS)
    )


    sensitivity_comparison = (
        sensitivity_comparison[
            [
                "Strategy",
                "Primary",
                "Context-Verified",
            ]
        ]
        .set_index("Strategy")
        .round(4)
    )


    st.bar_chart(
        sensitivity_comparison
    )


    st.dataframe(
        sensitivity_comparison,
        use_container_width=True,
    )


    # =====================================================
    # BOOTSTRAP CONFIDENCE INTERVALS
    # =====================================================

    st.divider()

    st.header(
        "Bootstrap Confidence Intervals"
    )


    available_statistics = sorted(
        statistics["statistic"]
        .dropna()
        .unique()
        .tolist()
    )


    selected_statistic = st.selectbox(
        "Statistic",
        available_statistics,
    )


    bootstrap_metric = st.selectbox(
        "Bootstrap metric",
        options=[
            "hit_at_1",
            "hit_at_5",
            "mrr_at_100",
        ],
        format_func=lambda metric:
            METRIC_LABELS[metric],
        key="bootstrap_metric",
    )


    bootstrap_rows = statistics[
        (statistics["evaluation_set"] == "primary")
        & (
            statistics["statistic"]
            == selected_statistic
        )
        & (
            statistics["metric"]
            == bootstrap_metric
        )
    ].copy()


    bootstrap_rows["Strategy"] = (
        bootstrap_rows["chunker"]
        .astype(str)
        .map(CHUNKER_LABELS)
    )


    bootstrap_rows["Noise"] = (
        bootstrap_rows["noise_level"]
        .astype(str)
        .str.title()
    )


    bootstrap_display = bootstrap_rows[
        [
            "Strategy",
            "Noise",
            "estimate",
            "ci_95_low",
            "ci_95_high",
            "bootstrap_iterations",
        ]
    ].copy()


    bootstrap_display.columns = [
        "Strategy",
        "Noise",
        "Estimate",
        "95% CI Low",
        "95% CI High",
        "Bootstrap Iterations",
    ]


    bootstrap_display[
        [
            "Estimate",
            "95% CI Low",
            "95% CI High",
        ]
    ] = bootstrap_display[
        [
            "Estimate",
            "95% CI Low",
            "95% CI High",
        ]
    ].round(4)


    st.dataframe(
        bootstrap_display,
        use_container_width=True,
        hide_index=True,
    )


except Exception as error:

    st.error(
        f"Could not load research dashboard: {error}"
    )
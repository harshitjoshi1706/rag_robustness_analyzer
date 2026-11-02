"""Operational jobs are separate from the immutable Research Dashboard."""

import os
import uuid

import pandas as pd
import streamlit as st

from services.platform_client import PlatformClient
from services.ui import LABELS, setup, show_error

setup("Distributed Evaluation", "🧩")
st.caption("New evaluation jobs · Results here are separate from the historical research snapshot.")
st.info(
    "One task evaluates one configuration. Start with one worker on an 8 GB Mac. Full OHRBench jobs can take substantial time and memory."
)
client = PlatformClient()
with st.form("submit_distributed_job"):
    chunkers = st.multiselect("Chunking strategies", list(LABELS), default=["fixed"], format_func=LABELS.get)
    noises = st.multiselect("Noise conditions", ["clean", "mild", "moderate", "severe"], default=["clean"])
    modes = ["research", "smoke"] if os.getenv("RAG_ALLOW_FIXTURE") == "1" else ["research"]
    mode = st.selectbox(
        "Workload",
        modes,
        format_func=lambda value: {
            "research": "Official OHRBench evaluation (8,456 questions)",
            "smoke": "Small real-RAG diagnostic (4 questions; not research results)",
        }[value],
    )
    submitted = st.form_submit_button("Submit evaluation job")
if submitted:
    if not chunkers or not noises:
        st.warning("Select at least one strategy and noise condition.")
    else:
        spec = {
            "mode": mode,
            "configurations": [{"chunker": c, "noise": n} for c in chunkers for n in noises],
        }
        if st.session_state.get("submission_spec") != spec:
            st.session_state.submission_key = str(uuid.uuid4())
            st.session_state.submission_spec = spec
        try:
            job = client.call("/api/jobs", spec, st.session_state.submission_key)
            st.session_state.distributed_job = job["id"]
            st.session_state.pop("submission_spec", None)
            st.success(f"Job accepted: {job['id']}")
        except Exception as exc:
            show_error("Job submission failed. The same request can be retried safely.", exc)

try:
    jobs = client.call("/api/jobs?limit=50")
except Exception as exc:
    show_error("Coordinator unavailable. Start the local platform services.", exc)
    st.stop()
if not jobs:
    st.info("No evaluation jobs yet.")
    st.stop()
ids = [job["id"] for job in jobs]
selected = st.session_state.get("distributed_job")
job_id = st.selectbox(
    "Job",
    ids,
    index=ids.index(selected) if selected in ids else 0,
    format_func=lambda value: next(
        f"{j['created']:.0f} · {j['state']} · {value[:8]}" for j in jobs if j["id"] == value
    ),
)
st.button("Refresh job list")


@st.fragment(run_every="5s")
def progress():
    try:
        job = client.call(f"/api/jobs/{job_id}")
        tasks = client.call(f"/api/jobs/{job_id}/tasks")
        st.subheader(f"{job['state']} · {job['completed']}/{job['total']} completed")
        st.progress(job["completed"] / job["total"])
        st.caption(f"Workload: {job['spec']['mode']} · Input identity: {job['fingerprint']}")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Strategy": LABELS[t["chunker"]],
                        "Noise": t["noise"],
                        "Status": t["state"],
                        "Stage": t["state"]
                        if t["state"] in ("COMPLETED", "FAILED", "CANCELLED")
                        else t.get("progress", {}).get("stage", t["state"]),
                        "Published query batches": t.get("progress", {}).get("published_query_batches", 0),
                        "Attempts": t["attempt"],
                        "Worker": t["worker"],
                        "Error": t["error"],
                    }
                    for t in tasks
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        with st.expander("Task attempts and operational details"):
            for task in tasks:
                st.write(f"{task['chunker']}/{task['noise']}")
                st.json(task["attempts"])
        results = [t["result"] for t in tasks if t["result"] is not None]
        if results:
            st.subheader("Committed configuration results")
            if job["state"] != "COMPLETED":
                st.caption("Partial results: this job is not complete.")
            table = pd.DataFrame(
                [
                    {
                        "Configuration": f"{r['chunker']}/{r['noise']}",
                        "Questions": r["question_count"],
                        "Hit@1": r["hit_at_1"],
                        "Hit@5": r["hit_at_5"],
                        "MRR@100": r["mrr_at_100"],
                        "Cache hit": r["cache_hit"],
                        "Seconds": r["execution"]["duration_seconds"],
                    }
                    for r in results
                ]
            )
            st.dataframe(table, hide_index=True, width="stretch")
            st.bar_chart(table.set_index("Configuration")[["Hit@1", "Hit@5", "MRR@100"]])
            st.download_button(
                "Download committed results",
                data=pd.DataFrame(results).to_json(orient="records"),
                file_name=f"job-{job_id}.json",
                mime="application/json",
            )
        if job["state"] not in ("COMPLETED", "FAILED", "CANCELLED") and st.button("Cancel job"):
            client.call(f"/api/jobs/{job_id}/cancel", {})
            st.rerun()
    except Exception as exc:
        show_error("Could not refresh job progress.", exc)


progress()

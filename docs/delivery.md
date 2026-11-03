# Distributed RAG Evaluation Platform handoff

Finalized 3 November 2026, Asia/Kolkata. Implementation is on
`feature/distributed-evaluation-platform` in the analyzer repository. The research
repository was inspected and tested, with no source or historical-result edits.
Its pre-existing untracked `make_dataset_heatmap.py` remains untouched.

## Implemented functionality

The existing four Streamlit pages remain functional. A new distributed page submits
configuration jobs over HTTP and polls state, task stages, attempts, worker identity,
errors, committed results and comparisons. FastAPI validates and accepts asynchronous
jobs, exposes OpenAPI/health/readiness/metrics, and supports cancellation and submission
idempotency. A durable SQLite dispatch loop schedules independent configurations onto
Redis/Celery. Workers execute the unchanged research runner in isolated CPU subprocesses.

Metadata has transactional claims, attempt records, renewable leases, fencing tokens,
three-attempt exponential retry, stale-worker recovery and one committed result per
logical task. Delivery is at least once; exactly-once execution is not claimed. Shared
query embeddings/FAISS indexes use content identity, local file locks and checksum-last
publication. Data/model/tokenizer baseline hashes reject scientific-input drift.
Partial attempts cannot commit results or overwrite historical artifacts.

Compose provisions the API, Redis, configurable workers, Streamlit, persistent volumes,
Prometheus and Grafana. Metrics aggregate worker state/resource samples from persistent
metadata. Grafana provisions 12 panels. Scripts cover actual broker integration, worker
container loss, coordinator restart and opt-in real OHRBench cold/warm benchmarking.
GitHub Actions builds and validates the local platform; no cloud release or registry
publishing is configured.

Architecture and audit: [architecture.md](architecture.md).
Startup, API, scaling, storage, monitoring, CI, troubleshooting and engineering decisions:
[operations.md](operations.md). Exact executed commands and results:
[validation.md](validation.md).

## Commits and remote status

Six implementation commits precede the final documentation commit:

- `2bdf46d` — repository audit and distributed execution boundaries.
- `559886e` — persistent jobs, isolated workers, caches, API and initial tests.
- `8c34780` — Streamlit distributed evaluation integration.
- `bcd1642` — frozen scientific inputs and task progress contracts.
- `dacb5bd` — Docker, observability, benchmarks, CI and security checks.
- `ade4a99` — narrow public-hash secret-scan exceptions and normalized advisory report.

The final documentation commit is identifiable with
`git log -1 --oneline`; this report is part of that commit, so its own hash is not
embedded recursively. No branch was pushed, no pull request was created, no image
was published and no cloud service was deployed.

## Verification results

- **24/24 tests passed inside the final Linux ARM64 CPU image**, including API/UI,
  concurrency/duplicate claims, leases/retries/cancellation, corruption rejection,
  real four-chunker cold/warm MiniLM/FAISS regression and the original runner's
  67-batch contract using an explicitly labelled deterministic full-count fixture.
- **28/28 original research tests passed** using the actual local official input
  files and cached model. All five original analyzer tests also remain passing.
- Actual Redis/Celery integration passed for asynchronous completion, duplicate
  delivery, real failure/retry, stale lease recovery and frozen real-RAG rankings.
- Actual worker-container kill/restart passed: the interrupted diagnostic job
  completed on attempt 2. Pending work persisted while the coordinator was stopped
  and completed after the coordinator restarted.
- Docker build and Compose validation passed on Apple Silicon/Linux ARM64. All
  required services were healthy. Prometheus reported coordinator `up=1` and Grafana
  returned the provisioned dashboard with 12 panels.
- Ruff lint/format checks, dependency consistency and Git whitespace checks passed.
  Gitleaks found no secrets after three exact public-hash exceptions and removal
  of upstream advisory example payloads (see validation.md). All **34 baseline
  source/result SHA-256 records match**.
- Security updates reduced the audit from 55 findings in four packages to one NLTK
  finding with no listed fix. The final audit exits 1 and is not described as clean.

Exact reproducible commands, test durations, corrected implementation/test-harness
issues, advisory details and machine-readable reports are linked in validation.md.
Tests were actually executed locally; **GitHub-hosted CI has not been run**. Linux
AMD64 image execution remains unvalidated. CI YAML was parsed and the substantive
build/test/integration commands were exercised locally.

## Benchmarks and known limitations

No real OHRBench scaling measurements were fabricated or substituted with synthetic
throughput. Measurements for 1/2/4 workers are **pending**. The historical full study
spanned about 28.7 hours; six full cold/warm reruns are not practical in this session.
Four 2 GiB workers plus services also exceed the target Mac's physical 8 GB budget.
The benchmark script is implemented and opt-in.

Research correctness is verified on frozen diagnostic rankings/metrics, with exact
count/rank/metric comparison. Full distributed equivalence across the actual
8,456-question official study remains pending. The full-count runner fixture is
explicitly synthetic and never presented as an OHRBench result or benchmark.

This implementation supports **one Docker host**. SQLite WAL and file locks must not
be shared across hosts/NFS. PostgreSQL and distributed artifact coordination are
required before multi-host operation. There is no authentication or tenant isolation;
services bind only to localhost. Retention/archival is manual. Sampled RSS/CPU can miss
brief spikes; original Darwin-specific memory profile fields are not used to claim
cross-platform memory accuracy.

Remaining dependency advisory `GHSA-8mgp-746c-j5xp` concerns NLTK parser/perceptron
model-path APIs. This platform uses frozen read-only English sentence-tokenizer data
and does not expose those APIs. It remains documented for maintenance review.

The local test volume retains clearly labelled diagnostic jobs, including intentional
failure records. These do not modify or replace the historical Research Dashboard.

## Exact local commands

The model snapshot and image are already prepared in this workspace. To start or
refresh the complete platform with the conservative default:

```sh
cd /Users/harshitjoshi/RAG_Project/rag_robustness_analyzer
./scripts/local.sh start 1
```

Open [Streamlit](http://localhost:8501), [API documentation](http://localhost:8000/docs),
[Grafana](http://localhost:3000/d/rag-local) or [Prometheus](http://localhost:9090).
At handoff, the stack is left running with **one worker**, normal 90-second leases,
and diagnostic submission disabled.

```sh
# Optional single-host worker counts; assess available RAM first.
docker compose up -d --scale worker=2
docker compose up -d --scale worker=4
# Stop without deleting metadata or artifacts.
./scripts/local.sh stop
```

For a fresh checkout, install requirements and prepare the pinned model once using
the installation commands in operations.md. The research checkout must supply its
existing official parquet/annotation files for real OHRBench jobs.

## Exact continuation plan

1. Review and push with `git push -u origin feature/distributed-evaluation-platform`
   when ready, then observe GitHub-hosted CI and
   retain its logs. No pull request/merge or remote action is assumed complete.
2. On suitable hardware, submit one official configuration and compare its committed
   per-question CSVs/aggregate metrics against the immutable sequential baseline.
   Investigate any ranking/count difference; never regenerate golden files merely
   to make a failing comparison pass.
3. On an idle host with enough RAM, measure a controlled workload with:
   `.venv/bin/python scripts/benchmark.py --allow-heavy --workers 1 2 4`.
   The default runs all sixteen configurations; use `--configurations file.json`
   for a deliberately smaller identical workload with at least four configurations.
   Repeat trials and report hardware, cache conditions, failures and uncertainty.
4. Review the remaining NLTK advisory when a fix becomes available. Change scientific
   dependencies only with explicit regression evidence.
5. For actual multi-host use, replace SQLite/file locking with PostgreSQL and a
   distributed artifact publication protocol before making scaling claims.

## Acceptance status

| Acceptance area | Status |
| --- | --- |
| Both original repositories functional | Verified by existing suites; algorithms/source/results unchanged |
| Asynchronous job submission/status/results | Implemented and integration-tested |
| Redis/Celery and multiple workers | Verified on one host with two workers |
| Real RAG execution | Verified with actual MiniLM/original chunkers/FAISS diagnostic tasks; full official execution validation pending |
| Shared embeddings/indexes and atomic results | Implemented; cold/warm, corruption and duplicate tests passed |
| Worker/coordinator failure recovery | Actual container/process restart tests passed |
| Streamlit live progress and comparisons | Implemented; submission/running UI and legacy pages tested |
| Required Compose services | Built and started healthy on Linux ARM64 |
| Prometheus/Grafana | Live scrape and 12-panel provisioning verified |
| 1/2/4-worker benchmark scripts | Implemented; real measurements pending |
| Sequential scientific equivalence | Frozen small-corpus rankings/metrics passed; full official corpus comparison pending |
| Unit/integration tests | 24 platform tests + 28 original research tests passed |
| GitHub Actions | Implemented/local commands validated; hosted execution pending |
| Documentation | Audit, operation, testing, limits, continuation and delivery records supplied |
| No cloud deployment | Confirmed; no image publishing or external infrastructure creation |

**Not every acceptance criterion is fully validated.** The pending full official
numerical comparison, measured scaling and hosted CI are explicitly outstanding;
the implemented local platform and documented tests are complete.

## Resume bullets supported by executed evidence

- Built a local multi-worker RAG evaluation platform with FastAPI, Celery, Redis,
  SQLite and Docker Compose, preserving an existing research pipeline and Streamlit UI.
- Implemented fenced leases, durable dispatch, bounded retries and idempotent result
  commits; verified duplicate-delivery protection and worker/coordinator crash recovery.
- Added content-validated MiniLM/FAISS artifact reuse and frozen sequential ranking
  regressions across four original chunkers; passed 24 platform and 28 research tests.
- Provisioned Prometheus metrics and a 12-panel Grafana dashboard and implemented
  GitHub Actions for CPU-image, regression, integration and security validation.

These bullets intentionally make no measured speedup, multi-host scale, cloud
production deployment or successful GitHub-hosted CI claim.

## All changed and created files

- [.dockerignore](../.dockerignore)
- [.github/workflows/ci.yml](../.github/workflows/ci.yml)
- [.gitignore](../.gitignore)
- [.gitleaks.toml](../.gitleaks.toml)
- [.gitleaksignore](../.gitleaksignore)
- [Dockerfile](../Dockerfile)
- [README.md](../README.md)
- [compose.yaml](../compose.yaml)
- [docs/architecture.md](../docs/architecture.md)
- [docs/baseline.json](../docs/baseline.json)
- [docs/delivery.md](../docs/delivery.md)
- [docs/dependency-audit-baseline.json](../docs/dependency-audit-baseline.json)
- [docs/dependency-audit.json](../docs/dependency-audit.json)
- [docs/operations.md](../docs/operations.md)
- [docs/tokenizer_baseline.json](../docs/tokenizer_baseline.json)
- [docs/validation.md](../docs/validation.md)
- [monitoring/grafana/provisioning/dashboards/provider.yml](../monitoring/grafana/provisioning/dashboards/provider.yml)
- [monitoring/grafana/provisioning/dashboards/rag.json](../monitoring/grafana/provisioning/dashboards/rag.json)
- [monitoring/grafana/provisioning/datasources/prometheus.yml](../monitoring/grafana/provisioning/datasources/prometheus.yml)
- [monitoring/prometheus.yml](../monitoring/prometheus.yml)
- [pages/4_Distributed_Evaluation.py](../pages/4_Distributed_Evaluation.py)
- [platform_eval/__init__.py](../platform_eval/__init__.py)
- [platform_eval/api.py](../platform_eval/api.py)
- [platform_eval/celery_app.py](../platform_eval/celery_app.py)
- [platform_eval/child.py](../platform_eval/child.py)
- [platform_eval/config.py](../platform_eval/config.py)
- [platform_eval/contracts.py](../platform_eval/contracts.py)
- [platform_eval/coordinator.py](../platform_eval/coordinator.py)
- [platform_eval/data/scientific_baseline.json](../platform_eval/data/scientific_baseline.json)
- [platform_eval/data/smoke.json](../platform_eval/data/smoke.json)
- [platform_eval/data/tokenizers/punkt_tab/README](../platform_eval/data/tokenizers/punkt_tab/README)
- [platform_eval/data/tokenizers/punkt_tab/english/abbrev_types.txt](../platform_eval/data/tokenizers/punkt_tab/english/abbrev_types.txt)
- [platform_eval/data/tokenizers/punkt_tab/english/collocations.tab](../platform_eval/data/tokenizers/punkt_tab/english/collocations.tab)
- [platform_eval/data/tokenizers/punkt_tab/english/ortho_context.tab](../platform_eval/data/tokenizers/punkt_tab/english/ortho_context.tab)
- [platform_eval/data/tokenizers/punkt_tab/english/sent_starters.txt](../platform_eval/data/tokenizers/punkt_tab/english/sent_starters.txt)
- [platform_eval/db.py](../platform_eval/db.py)
- [platform_eval/inputs.py](../platform_eval/inputs.py)
- [platform_eval/metrics.py](../platform_eval/metrics.py)
- [platform_eval/research.py](../platform_eval/research.py)
- [platform_eval/smoke.py](../platform_eval/smoke.py)
- [platform_eval/storage.py](../platform_eval/storage.py)
- [platform_eval/tasks.py](../platform_eval/tasks.py)
- [platform_eval/worker_health.py](../platform_eval/worker_health.py)
- [pyproject.toml](../pyproject.toml)
- [requirements-dashboard.txt](../requirements-dashboard.txt)
- [requirements-dev.txt](../requirements-dev.txt)
- [requirements-lock.txt](../requirements-lock.txt)
- [requirements-ml.txt](../requirements-ml.txt)
- [requirements-platform.txt](../requirements-platform.txt)
- [requirements.txt](../requirements.txt)
- [scripts/benchmark.py](../scripts/benchmark.py)
- [scripts/coordinator_recovery.py](../scripts/coordinator_recovery.py)
- [scripts/integration_check.py](../scripts/integration_check.py)
- [scripts/local.sh](../scripts/local.sh)
- [scripts/prepare_model.py](../scripts/prepare_model.py)
- [scripts/worker_recovery.py](../scripts/worker_recovery.py)
- [services/platform_client.py](../services/platform_client.py)
- [services/research_backend.py](../services/research_backend.py)
- [services/ui.py](../services/ui.py)
- [tests/distributed/__init__.py](../tests/distributed/__init__.py)
- [tests/distributed/test_api.py](../tests/distributed/test_api.py)
- [tests/distributed/test_research.py](../tests/distributed/test_research.py)
- [tests/distributed/test_state.py](../tests/distributed/test_state.py)
- [tests/distributed/test_ui.py](../tests/distributed/test_ui.py)
- [tests/fixtures/sequential_reference.json](../tests/fixtures/sequential_reference.json)

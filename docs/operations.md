# Run and maintain the platform

## Installation and local startup

Keep the two existing repositories as siblings. Python 3.11 is the tested host
runtime. The original standalone UI installation still works as documented in the
README. The platform adds FastAPI/Celery/Redis without requiring it for saved pages.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -c requirements-lock.txt -r requirements-platform.txt -r requirements-ml.txt -r requirements-dashboard.txt -r requirements-dev.txt
.venv/bin/python scripts/prepare_model.py --offline
# If the pinned model is absent locally, omit --offline for the one-time download.
docker compose config --quiet
./scripts/local.sh start 1
```

The model preparation script materializes immutable revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, the locally cached baseline snapshot.
It refuses to overwrite an existing model destination. Model/tokenizer byte hashes
and numeric library versions are included in every scientific input fingerprint.
The baseline English NLTK Punkt tab resource is bundled byte-for-byte (hashes in
`tokenizer_baseline.json`, upstream README retained) so sentence tokenization is
available offline and cannot drift through an unpinned runtime download.
Docker uses Linux CPU PyTorch wheels, runs as UID 1000, and shares one application
image across API, worker and Streamlit services. macOS/arm64 and Linux/amd64 builds
are intended; see validation.md for which platforms were actually exercised.

The research checkout is mounted read-only. Official research execution additionally
needs the existing ignored `data/raw/OHR-Bench_v2.parquet` and `qas_v2.json` inside
that checkout. No dataset download or full OHRBench experiment occurs on startup.
The source checkout at the recorded baseline should be used for reproducibility.
`platform_eval/data/scientific_baseline.json` freezes the actual corpus, annotation,
model and tokenizer hashes. Scientific submissions reject changed data or model
bytes instead of silently reusing the original study label.

Addresses (bound to localhost):

| Service | Address |
| --- | --- |
| Streamlit | http://localhost:8501 |
| API and OpenAPI | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana provisioned dashboard | http://localhost:3000/d/rag-local |

Grafana allows anonymous **viewing** for this localhost-only development stack;
there are no repository credentials. Keep the service bindings on localhost.
There is no authentication/tenant boundary in the coordinator. This is a local
production-style engineering platform, not a publicly exposed hosted service.

```sh
docker compose up -d --scale worker=1
docker compose up -d --scale worker=2
docker compose up -d --scale worker=4
./scripts/local.sh status
./scripts/local.sh logs
./scripts/local.sh stop
```

Each worker container has one Celery prefork execution slot and launches one
research child at a time. Four containers allow four parallel configuration
processes on one host; they do not demonstrate multi-host distribution.
Default per-worker memory cap is 2 GiB and one CPU. API 512 MiB, Streamlit 1 GiB,
Redis 192 MiB, Prometheus/Grafana 256 MiB each. These are caps, not measured needs.
Two workers may pressure an 8 GB Mac; four 2 GiB workers plus services exceed that
machine's physical memory budget. Four-worker experiments are explicitly opt-in;
use more RAM or measure carefully. Increasing Docker Desktop's memory limit cannot
create physical RAM. Keep live PDF indexing idle during evaluation benchmarks.
CPU inference is mandatory; no GPU/CUDA service is configured.

## Configuration

| Variable | Default / purpose |
| --- | --- |
| RAG_RESEARCH_ROOT | Host path to sibling research checkout (non-Docker) |
| RAG_RESEARCH_MOUNT | `../rag_chunk_robustness`, Docker bind source |
| RAG_MODEL_PATH | `var/model` on host, `/models` in containers |
| RAG_MODEL_MOUNT | `./var/model`, read-only model bind source |
| RAG_STORAGE | `var/platform` on host, `/storage` in containers |
| RAG_API_URL | `http://localhost:8000`; Streamlit uses `http://api:8000` in Compose |
| CELERY_BROKER_URL | Host Redis URL; Compose uses internal Redis DNS |
| RAG_MAX_PENDING | 64 outstanding logical configuration tasks (code default) |
| RAG_LEASE_SECONDS | 90 seconds; 15 in isolated crash tests |
| RAG_TASK_TIMEOUT | 21,600 seconds per attempt (six hours) |
| RAG_WORKER_MEMORY | Compose worker cap `2g` |
| RAG_ALLOW_FIXTURE | 0; 1 enables diagnostic/synthetic test-only workloads |

`research` is the default workload. `smoke` runs the real original four chunkers,
MiniLM and FAISS on four fictional diagnostic documents and four questions.
`fixture` exercises delivery only with fixed metrics and no model. Both diagnostics
are explicitly labelled, disabled by default, and excluded from the benchmark script.
Smoke supports clean only. They never appear on the historical Research Dashboard.

## API and job lifecycle

```sh
curl -sS -X POST http://localhost:8000/api/jobs \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: my-experiment-001' \
  -d '{"configurations":[{"chunker":"fixed","noise":"clean"}]}'
curl -sS http://localhost:8000/api/jobs
curl -sS http://localhost:8000/api/jobs/JOB_ID
curl -sS http://localhost:8000/api/jobs/JOB_ID/tasks
curl -sS http://localhost:8000/api/jobs/JOB_ID/results
curl -sS -X POST http://localhost:8000/api/jobs/JOB_ID/cancel
```

Submission returns HTTP 202 after validation and a short metadata transaction, never
model inference. First scientific submission hashes input/model files; subsequent
submissions reuse that coordinator input identity. Workers rehash before execution;
changing inputs underneath a running coordinator causes explicit identity failure.
Restart services after intentionally changing research source/model/data.

Unknown/duplicate configurations are 422; full admission capacity 429 with
Retry-After; an idempotency key reused for a different request is 409; unavailable
scientific inputs 503. A terminal job cannot be cancelled (409). Unknown jobs are
404. `/health` tests process liveness; `/ready` checks DB and Redis connectivity,
not whether datasets or model files exist. OpenAPI response models document job,
task, attempt and result envelope schemas. List jobs accepts limit/offset.

Jobs are PENDING then RUNNING. They become COMPLETED only when every required
configuration is validated and committed. One failed configuration does not cancel
remaining configurations; after all tasks terminate the job becomes FAILED if any
required result is missing. Results explicitly label partial completion. Task retries
are RETRYING and attempts remain queryable with errors and worker IDs. The Streamlit
page polls the HTTP API every five seconds, displays stages and committed query-batch
counts, attempts/errors, operational worker details, metrics and comparisons.
Cancellation fences outstanding work immediately; the supervisor terminates its
child at its next heartbeat. Already committed results remain auditable.

## Persistence, cache and recovery

The `platform-data` volume stores `metadata.sqlite3` with WAL, immutable input
manifests, per-attempt logs/results/query CSVs and reusable query vectors/FAISS caches.
Redis AOF is persistent but not authoritative. Never delete volumes as a restart
procedure. `docker compose stop` preserves them; `docker compose down` also preserves
named volumes unless explicitly given `-v` (destructive).

SQLite uses short BEGIN IMMEDIATE transactions, foreign keys, FULL synchronous writes,
a 30-second busy timeout and WAL on a **local single-host filesystem**. Do not run
multiple Docker hosts against this DB or put WAL/file locks on NFS. A real multi-host
variant needs PostgreSQL plus a distributed artifact store and locking protocol.

A dispatch deadline is durable before Redis publication. If a publish or coordinator
crashes, the same stable task ID can be published again after 30 seconds. Idle
queue-length checks and admission limits bound backlog. Task delivery is at least
once. Claims are transactional; duplicate deliveries for running/terminal work are
ignored. Each attempt receives a random ownership token and renewable lease. An
expired lease is a failed attempt; retries use 2/4-second exponential delays and
terminate after three attempts. The worker cannot commit under an old token.
The coordinator continuously recovers stale work after a restart.

Each research configuration runs in a dedicated child process, preventing mutable
research runner globals/FAISS thread settings from interfering. Parent death is
checked by the child so prefork crashes do not leave model processes alive indefinitely.
Process timeouts terminate the child process group. Attempt output paths are unique;
checksum validation and atomic JSON/CSV writes prevent partial results from committing.
Source/data/model/package fingerprints and configuration/namespace identify artifacts.
A local file lock serializes shared index builds; a separate lock serializes query
embedding generation. Checksums are published last and verified on every cache use.
Invalid generations are renamed for inspection, then rebuilt. There is no automatic
cache eviction while jobs are active, and no untrusted pickle loading. FAISS embeds
its stored vectors; standalone chunk embedding matrices need not be duplicated.

Fresh attempts regenerate query-result batches rather than accepting another
attempt's partial results. Indexes and query embeddings remain reusable. Completed
results are unique per logical task in SQLite. This guarantees one committed valid
result, **not exactly-once computation**. Historical `research/results`,
`research/indexes` and bundled snapshot files are never writable cache destinations.

Back up the volume with services stopped (DB + WAL + referenced artifact trees
together), or use SQLite's backup API plus a coordinated artifact snapshot. Do not
copy only the main DB file while it is running. Disk retention is manual: inspect
job references before archiving old attempts/caches; do not prune active artifacts.

## Monitoring

Prometheus scrapes the single API process. Global task states, attempt counts,
retry counts, duration histograms, job durations and worker availability are derived
from SQLite across **all** workers. Queue depth is the Redis delivery length and
includes duplicates; a failed Redis probe emits NaN plus broker_available=0.
API latency is measured per bounded route template, never arbitrary IDs.
Grafana provisions worker health, active tasks, throughput, latency, queue depth,
failures/retries, API latency and job duration panels, plus active evaluation RSS and CPU-core samples aggregated
from worker heartbeats. These describe evaluation children, excluding Celery/API
parents and Docker VM overhead, and may lag by one heartbeat. Container resource samples are
collected by the benchmark harness; no host cAdvisor exporter is falsely advertised.
Per-attempt CPU/RSS samples are attached to committed results. Sampling can miss
very short spikes; legacy research peak_memory_mb is Darwin-specific and is not
used for cross-platform resource comparisons.

## Benchmarks

Measurements for real OHRBench 1/2/4-worker scaling are **pending**. No speedup is
claimed. Diagnostic tests are not performance measurements for the research workload.

```sh
.venv/bin/python scripts/benchmark.py --help
# Explicitly expensive; requires an idle running project, official inputs and RAM.
.venv/bin/python scripts/benchmark.py --allow-heavy --workers 1 2 4
```

The default workload is all sixteen original configurations. A JSON configuration
list can select a smaller controlled workload with `--configurations file.json`.
Use at least four independent configurations to assess four workers. The same
configuration list and input fingerprint apply to every worker count. Each count
gets a new cache namespace, followed by a warm run in that same namespace. Cold
means no platform embeddings/indexes; OS page caches and downloaded model files are
not flushed. Repeat the complete comparison several times and report distributions,
hardware, Docker CPU/RAM limits, thermal conditions, source/model hashes and failures.
Cached profile construction timings describe the original artifact generation; use
per-attempt execution duration for warm-run end-to-end timing.
The harness refuses to use synthetic/smoke workloads. It records completion time,
configuration/question throughput, speedup T1/Tn and parallel efficiency speedup/n,
worker-container CPU utilization and sampled aggregate peak memory, failures/retries
and cache hit rate. It writes JSON incrementally and a final CSV to var/benchmarks.
CPU percent is a sum across workers (100% = one fully used CPU core). Memory includes
Celery parent/child container usage; host/Docker VM overhead is outside that sample.

## Tests and CI

```sh
.venv/bin/python -m unittest discover -s tests -v
RUN_REAL_RAG_TESTS=1 OMP_NUM_THREADS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m ruff check platform_eval scripts tests/distributed services/platform_client.py pages/4_Distributed_Evaluation.py
.venv/bin/python -m ruff format --check platform_eval scripts tests/distributed services/platform_client.py pages/4_Distributed_Evaluation.py
# Run all original research tests from that repository's cwd; they use local data.
(cd ../rag_chunk_robustness && PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 \
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  ../rag_robustness_analyzer/.venv/bin/python -m unittest discover -s tests -v)

# Isolated local engineering integration; enables diagnostics only.
RAG_ALLOW_FIXTURE=1 RAG_LEASE_SECONDS=15 docker compose up -d --build --wait --scale worker=2
docker compose exec -T api python -m scripts.integration_check --real
# Kills/restarts this project's workers; run only while the project is idle.
.venv/bin/python scripts/worker_recovery.py --allow-worker-kill
.venv/bin/python scripts/coordinator_recovery.py --allow-api-restart
```

The frozen JSON fixture records original sequential outputs at the research baseline
and pinned model revision. Counts, schemas, configuration names, top-100 chunk-ID
ranking sequences and per-question/aggregate Hit@1/Hit@5/MRR are compared exactly
(tolerance zero). Similarity floats and operational timings are intentionally excluded:
backend/platform floating-point differences can affect scores without changing ranks.
A changed ranking fails; references must never be regenerated to conceal a regression.
This diagnostic is not proof of all 8,456-question outputs or full OHRBench speedup.

CI runs on pull requests, feature/main pushes and manual dispatch. It checks out the
pinned research commit, validates Compose, builds the CPU image without publishing,
lints/formats new code, runs API/UI/unit plus real frozen research regressions, runs
original lightweight research tests, starts all services, exercises Redis/Celery,
duplicate delivery, real retry, stale leases and actual worker-container loss. It
uploads logs and dependency advisory diagnostics and stops containers. No full dataset
is downloaded. A dependency advisory job is report-only to avoid silently changing
frozen scientific pins; advisories require review.
Security updates from the inspected environment are explicit: filelock 4.0.0 ->
4.2.4, certifi 2026.7.22 -> 2026.10.18, Pillow 12.3.0 -> 13.0.0, and Streamlit
1.64.0 -> 1.66.1 to support the patched Pillow version. Numerical research package
pins are unchanged. The remaining NLTK advisory concerns parser/perceptron model
import/export paths; this platform only uses sentence segmentation with frozen
read-only English tab data and exposes none of those model-path APIs. No fix was
listed in the advisory database at validation time. Reports are retained in docs. Gitleaks scanning is blocking.
Local validation does not imply a GitHub-hosted workflow has run. There is no cloud
release step, registry publishing, paid infrastructure, automatic merge or deployment.

## Troubleshooting and limits

- Docker socket unavailable: start Docker Desktop, then docker info. An approved
  shell may be needed under a sandbox. Check port conflicts before starting services.
- 503 on submit: inspect docker compose logs api; check the read-only research/model
  binds, official data files and installed numeric package versions. Model preparation
  does not overwrite existing snapshots. Never relabel unrelated model weights MiniLM.
- Task RETRYING/FAILED: inspect the bounded API error and its attempt execution.log
  under /storage/attempts; fix missing inputs and submit a new job after restarting
  services. Three-attempt failures remain terminal and auditable.
- Worker killed/OOM: inspect docker inspect and Docker Desktop resources, reduce to
  one worker and avoid simultaneous live PDF processing. Recoveries should appear
  after the lease timeout. Larger caps are not a substitute for available RAM.
- Cache checksum mismatch: invalid generations are quarantined, not silently accepted.
  Investigate disk failures before removing quarantined copies. No checksums from
  historical artifacts are used to authorize cache writes over those artifacts.
- No worker metrics: allow 15 seconds for heartbeat, then inspect worker logs. Presence
  older than 45 seconds is considered unavailable. API runs one process by design.
- Storage fills over time: results/attempts are durable and intentionally not auto-deleted.
  Retention, authentication, PostgreSQL/object storage, multi-host operation, and full
  corpus numerical regression remain future validation/engineering work.

## Engineering explanation for interviews

The meaningful parallel boundary is an entire configuration: splitting query batches
would add index distribution and ranking/aggregation risks for little benefit on an
8 GB laptop. SQLite is appropriate for short metadata transactions on one host, not
for distributed storage. Redis may redeliver, so fencing and unique logical results
carry correctness; Celery result state cannot be the system of record. Per-attempt
output paths isolate retries, checksum-last publication protects readers from crashes,
and content identity prevents scientifically different runs sharing artifacts. Fresh
subprocesses bound model lifetimes and protect global FAISS/thread/runner state.
The tradeoff is startup and hashing overhead, which must be measured before claiming
speedup. Multi-process execution on a Mac is not evidence of multi-host scaling.

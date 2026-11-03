# Validation record

This file is updated with executed checks at completion. Benchmark measurements and
GitHub-hosted workflow runs must never be inferred from implementation alone.

## Established baseline

- Analyzer baseline: five tests passed.
- Research baseline: 28 tests passed with local official data and cached MiniLM,
  from the research repository's working directory.
- An initial research test invocation from the analyzer cwd failed four relative-path
  data tests. Re-running from the correct cwd passed; no source changes were needed.
- Baseline commit/source/result digests are in baseline.json. Historical artifact
  immutability is checked again before handoff.

## Scientific scope

The frozen diagnostic compares all four original chunkers on a small fictional corpus,
using real pinned MiniLM weights and real FAISS retrieval, to original sequential
helper outputs. Both cold/warm isolated child execution passed with exact ranking,
count and metric equality. It is not a rerun of the full OHRBench study. The historical
manifest records model name but not model weight hashes, so complete historical bitwise
reproducibility cannot be asserted from that manifest alone. New jobs record byte
identities and dependency versions. No golden references were updated after a failure.

## Pending measurements

- Full official OHRBench output comparison through distributed workers.
- Real OHRBench cold/warm timing/CPU/RSS for 1, 2 and 4 workers.
- Multi-host operation (not supported by the SQLite implementation).
- GitHub-hosted CI execution and x86 Linux build, unless separately recorded below.

## Executed final checks — 2 November 2026 (Asia/Kolkata)

| Check | Exact command / context | Observed result |
| --- | --- | --- |
| Host regression | `RUN_REAL_RAG_TESTS=1 OMP_NUM_THREADS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m unittest discover -s tests -v` | 23 tests passed before the additional resource-metrics test; frozen cold/warm rankings and full-count runner fixture included |
| Additional API/resource checks | `.venv/bin/python -m unittest discover -s tests/distributed -p test_api.py -v` | 4 tests passed, including aggregation of samples from two worker identities |
| Final Linux ARM64 full suite | `docker compose exec -T -e RUN_REAL_RAG_TESTS=1 api python -m unittest discover -s tests -v` | All 24 tests passed, 104.283 seconds; no skipped tests |
| Original research suite | From research cwd: `PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ../rag_robustness_analyzer/.venv/bin/python -m unittest discover -s tests -v` | All 28 tests passed after support-library security updates; 4.724 seconds |
| Code quality | `.venv/bin/python -m ruff check platform_eval scripts tests/distributed services/platform_client.py pages/4_Distributed_Evaluation.py` and the same paths with `ruff format --check` | Passed; 27 files formatted |
| Dependency consistency | `.venv/bin/python -m pip check` | No broken requirements |
| Compose validation | `docker compose config --quiet` | Passed |
| CPU image build | `docker compose build api` | Passed on Apple Silicon, Linux ARM64; CPU-only torch 2.14.0+cpu |
| Full stack health | `RAG_ALLOW_FIXTURE=1 RAG_LEASE_SECONDS=15 docker compose up -d --no-build --wait --wait-timeout 180 --scale worker=2` | API, Redis, both workers, Streamlit, Prometheus and Grafana healthy |
| Broker/worker integration | `docker compose exec -T api python -m scripts.integration_check --real` | Passed: asynchronous completion, duplicate publish, actual failed-child retry, stale-lease recovery, real four-chunker MiniLM/FAISS rankings against frozen sequential output |
| Actual worker loss | `.venv/bin/python scripts/worker_recovery.py --allow-worker-kill` | Passed; job `b71cfc65-e792-4cfe-9f44-705aeffcd28b` completed on attempt 2 after killing/restarting worker containers |
| Coordinator loss | `.venv/bin/python scripts/coordinator_recovery.py --allow-api-restart` | Passed; job `a5dfb047-e3fe-4871-aa3b-10e5c3c039ef` persisted while API stopped, then completed after actual API restart |
| Monitoring | HTTP queries from API container to Prometheus `/api/v1/query?query=up` and Grafana `/api/dashboards/uid/rag-local` | Coordinator scrape up=1; provisioned dashboard has 12 panels |
| Live PDF adapter | Actual local pinned model; create_chunks/build_retrieval_index/search_document for all four original chunkers on a small page | All four passed and returned page provenance; no saved study output changed |
| Secret scan | `docker run --rm -v "$PWD:/repo:ro" zricethezav/gitleaks:v8.24.2 detect --source /repo --no-git --redact --gitleaks-ignore-path /repo/.gitleaksignore` | No leaks found |
| Dependency audit | In disposable image: `PYTHONPATH=/tmp/audit python -m pip_audit -r /app/requirements-lock.txt --no-deps --disable-pip --format json --output /reports/dependency-audit.json` (pip-audit 2.9.0) | 55 findings in four packages reduced to one NLTK advisory with no listed fix; audit exits 1, not a clean security pass |
| Immutable baseline | SHA-256 comparison against every entry in `docs/baseline.json` | All 34 research-source and historical-artifact hashes unchanged |
| Git whitespace | `git diff --check` | Passed |
| Workflow syntax | Parsed `.github/workflows/ci.yml` with PyYAML | Parsed; not a GitHub-hosted execution |

The 8,456/5,277-count runner test uses explicitly generated deterministic QAs and
vectors to exercise all 67 original CSV batches and the actual original
`run_configuration` path. Its metrics are test fixtures, not official OHRBench
measurements. The independent four-question regression uses real model inference
and original chunkers, with frozen rankings/metrics from the original sequential
helpers. Neither is presented as a full-corpus numerical equivalence test.

## Issues discovered and corrected during validation

- Unittest discovery under a package named `platform` shadowed Python's standard
  library module. Test package renamed to `tests/distributed`.
- WAL initialization originally ran inside a transaction; moved before transaction
  handling and exercised through concurrent-claim/restart tests.
- Original research tests require their repository cwd; corrected test invocation.
- The first Linux semantic test lacked English Punkt tab data. Bundled exact baseline
  resources and hashes; the real container integration then passed.
- The initial worker crash harness recreated workers with default diagnostic mode
  disabled. It now starts existing containers to preserve their configuration/count.
  Actual crash recovery subsequently passed.
- Patched Pillow 13 required Streamlit 1.66.1; dependency consistency and all UI tests
  passed after updating both pins. Numerical research package versions stayed fixed.

## Security and operational limits

Remaining advisory: `GHSA-8mgp-746c-j5xp` in NLTK 3.10.3. It concerns parser/perceptron
model-artifact import/export APIs with caller-controlled filenames and path-security
bypasses. Those APIs are not exposed or invoked by this platform. Sentence segmentation
uses frozen English tab data with read-only deployment inputs. No patched release
was listed by pip-audit. This is a documented residual dependency finding, not a
claim of zero vulnerabilities. Review it when maintaining the scientific dependency
stack. Full initial/final machine-readable reports are retained in this directory.

Linux x86 CI, GitHub-hosted runs, complete official distributed OHRBench equivalence
and real 1/2/4-worker benchmark measurements remain unvalidated. The original
historical experiment manifest spans about 28.7 hours; repeatedly running the full
study and four 2 GiB workers is not practical within this session on an 8 GB Mac.
Benchmarks remain executable and opt-in, with no fabricated measurements.


## Final handoff checks — 3 November 2026 (Asia/Kolkata)

The normal-mode stack was restored to one worker, diagnostic submission disabled,
and a 90-second lease. All services were healthy and no jobs were outstanding.
The official research input preflight accepted the frozen corpus, annotations and
model without starting an experiment. All 34 recorded baseline hashes still match.

The final secret scan additionally examined newly committed model-hash and audit
artifacts. Three generic-key findings were public SHA-256 tokenizer hashes, and one
was an upstream advisory example in the initial dependency report. The baseline
report now omits advisory descriptions/PoCs while retaining all package versions,
advisory IDs, aliases and fixes. `.gitleaksignore` allows only the three exact public
hash locations; source scanning remains blocking. CI passes that ignore path
explicitly. This does not suppress actual credential findings or entire source files.


## Hosted CI milestone — 3 November 2026 (Asia/Kolkata)

The feature branch was pushed after the additional progress-tracking instruction.
The first [hosted run 41588188213](https://github.com/harshitjoshi1706/rag_robustness_analyzer/actions/runs/41588188213)
passed the Linux AMD64 CPU image build and Compose validation, then failed when Ruff
attempted to create `/app/.ruff_cache`. Diagnostics also failed because an early
Compose mount created a root-owned host `var` directory. Downstream tests were
skipped, not passed. Commit `8026343` fixed this by using standalone no-cache Docker
lint and standalone non-root model preparation before Compose binds are mounted.
An isolated fresh-directory local preparation matched every frozen model hash.

The corrected [hosted run 41588927745](https://github.com/harshitjoshi1706/rag_robustness_analyzer/actions/runs/41588927745)
passed on commit `8026343e3bcd362ef2ac3f64f79a5dd006a7cc6e`, from 11:47 to 11:52 IST:

- Linux AMD64 CPU image build, Compose configuration, lint and formatting passed.
- Fresh pinned MiniLM model preparation passed; no full OHRBench dataset downloaded.
- All **24 platform tests passed in 73.229 seconds**, including real cold/warm
  MiniLM/FAISS frozen ranking regression and the labelled full-count runner fixture.
- Six original lightweight research tests passed: two metric tests, one runner-resume
  test and three semantic tests. This is separate from the 28-test local full suite.
- All services started healthy. Actual Redis/Celery delivery, duplicate handling,
  failed-child retry, stale-owner recovery and real four-chunker comparisons passed.
- Actual worker-container loss recovered on attempt 2 (job
  `bbe644ae-0d23-4c34-9e4b-efe049d82a15`). Coordinator stop/start recovered pending
  work (job `e36bd96f-0701-4ca8-8155-80f28182fe7f`).
- Gitleaks found no leaks. Diagnostics and artifacts uploaded; containers stopped.
- The **report-only dependency audit exited 1** for one known NLTK advisory. Its
  continue-on-error policy permits workflow success; the advisory is not claimed fixed.

The hosted CI and Linux AMD64 gaps listed in the original handoff are now closed.
Full official-corpus numerical equivalence and real scaling measurements remain
pending. [PROGRESS.md](../PROGRESS.md) is the current phase/status record. Push
workflows ignore progress/README/docs-only changes so milestone commits do not
cancel real validation; pull-request validation remains enabled.

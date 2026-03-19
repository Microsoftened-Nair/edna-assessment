# DeepSea eDNA Platform – User Guide

This guide walks you through every surface of the DeepSea eDNA platform: the data-processing pipeline, REST API, React dashboard, and supporting utilities. Follow the sections in order if you are setting up the project for the first time, or jump to the feature you need.

---

## 1. System Overview

The workspace ships with three tightly coupled layers:

1. **Python pipeline (`edna_pipeline`)** – Performs ingestion, quality control, taxonomic assignment, abundance quantification, and report generation for environmental DNA samples.
2. **Flask API (`edna_api`)** – Offers a REST interface for launching runs, orchestrating batches, tracking lifecycle status, and managing reference databases. It persists JSON snapshots under `data/api/` for the dashboard.
3. **React frontend (`frontend/`)** – Provides a dark-themed operations console with real-time telemetry, batch orchestration, database management, and settings (including the GPT‑5‑Codex preview toggle).

Support utilities include the database bootstrapper (`setup_databases.py`), usage examples (`scripts/`, `example_usage.py`), and documentation under `docs/`.

---

## 2. Prerequisites

| Component | Requirement |
|-----------|-------------|
| Python backend | Python 3.9+, BLAST+ binaries (for taxonomy), 8 GB RAM recommended |
| Node tooling | Node.js 18+ (LTS) and npm 9+ |
| Storage | ≥5 GB for recommended databases (up to 600 GB for full `nt` download) |
| OS | Linux, macOS, or WSL2 – tested primarily on Linux |
| Internet | Required for dependency and database downloads |

Install system dependencies first (example uses `conda`):

```bash
conda create -n edna python=3.10
conda activate edna
conda install -c bioconda blast
```

---

## 3. Backend Setup

1. **Install Python requirements**
   ```bash
   pip install -r requirements.txt
   ```

2. **Populate reference databases**
   ```bash
   # Essential bundle (~400 MB)
   python setup_databases.py --recommended

   # Inspect available datasets
   python setup_databases.py --list
   ```

   Setup note: `taxdb` is downloaded from NCBI taxonomy dump and unpacked to `nodes.dmp` and `names.dmp` in `databases/processed/taxdb/` (or your `EDNA_DB_DIR`).
   Runtime note: run processing does not auto-download missing databases; provision databases before submitting runs.

3. **Environment variables (optional)**
   - `EDNA_DB_DIR` – override default database directory (`databases` is the project default).
   - `EDNA_MAX_WORKERS` – adjust `ThreadPoolExecutor` size for run/batch processing.

4. **Start the API server**
   ```bash
   python -m edna_api.server
   ```
   The service listens on `http://127.0.0.1:5000` by default. JSON snapshots for runs and batches are stored under `data/api/runs/` and `data/api/batches/`.

### 3.1 Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Basic readiness probe |
| GET | `/api/dashboard` | Aggregate metrics (totals, success rate, queue depth) |
| GET | `/api/runs` | Recent run summaries |
| POST | `/api/runs` | Launch a new run (`sampleId`, `inputType`, `files`, `configOverrides`) |
| GET | `/api/runs/<run_id>` | Detailed run telemetry |
| POST | `/api/batches` | Kick off a batch (`runs` array mirroring run payload) |
| GET | `/api/batches/<batch_id>` | Batch execution status and per-sample results |
| GET | `/api/databases` | Reference database inventory |
| POST | `/api/databases/<name>/download` | Queue database download |

All write operations respond immediately with a queued status; asynchronous workers update the persisted JSON as tasks progress.

---

## 4. Frontend Setup

1. **Install Node dependencies**
   ```bash
   cd frontend
   npm install
   ```

2. **Configure environment variables** (create `frontend/.env.local` if needed):
   ```bash
   VITE_API_URL=http://127.0.0.1:5000
   VITE_USE_MOCK=false          # set to true for offline demo mode
   ```

3. **Run the development server**
   ```bash
   npm run dev
   ```
   Visit `http://localhost:5173` (default Vite port).

4. **Quality gates**
   ```bash
   npm run lint   # ESLint (TypeScript + React)
   npm run build  # Production bundle check
   ```

---

## 5. Navigating the Operations Console

### 5.1 Typical Frontend Workflow

1. **Start the backend** – Ensure `python -m edna_api.server` is running before opening the UI. The dashboard polls the API every few seconds; if the server is unreachable you will only see mock placeholders.
2. **Launch the React client** – From `frontend/`, run `npm run dev` (for production-like build use `npm run build && npm run preview`). Visit the printed Vite URL, typically `http://localhost:5173`.
3. **Authenticate (if enabled)** – The current build has no auth layer; all routes are public once the SPA loads.
4. **Submit analysis jobs** – Use *Single Run* for a one-off sample or *Batch Runs* to queue multiple samples. Forms validate required FASTQ paths before issuing API POST requests.
5. **Monitor progress** – The UI polls `/api/runs` and `/api/batches/<id>` to reflect lifecycle transitions. Status pills will change from `queued` → `running` → `completed` or `failed`; any backend error message renders inline.
6. **Review outputs** – Open *Results* or the detail pages to examine step metrics, abundance summaries, and stored artifact locations. Download actions are placeholders until direct file serving is wired up.
7. **Manage reference data** – Navigate to *Databases* to trigger downloads via the API. Running downloads display `running`/`pending` states that update as the backend reports progress.
8. **Switch to mock mode (optional)** – Set `VITE_USE_MOCK=true` and restart the dev server to explore the UI without a backend. Mock data simulates lifecycle states but does not persist new runs.

> Tip: The sidebar card labeled *Realtime Monitoring* is a forward-looking call-to-action. The button currently has no effect until WebSocket streaming is implemented in the API.

### 5.2 Page Directory

| Section | Capabilities |
|---------|--------------|
| **Dashboard** | View aggregate telemetry, review recent run performance, inspect taxonomic distribution charts. Status pills reflect `queued`, `running`, `pending`, `completed`, or `failed` states pushed by the API. |
| **Single Run** | Submit ad‑hoc analyses. Supply sample ID, select single/paired FASTQ, set optional output directory, and launch. The latest response card displays lifecycle status, timestamps, output path, and error messages if the pipeline fails. |
| **Batch Runs** | Build multi-sample batches with dynamic form entries. Submitting triggers `/api/batches`; the telemetry card surfaces success counts, total time, and failure reasons. |
| **Results** | Browse recent runs with status pills, key metrics (duration, classified count, confidence, reads), and quick links to detail pages. |
| **Run / Batch Details** | Drill into pipeline step status, per-step outcomes, diversity metrics, and any error messages from the backend. |
| **Databases** | Enumerate reference datasets, initiate downloads, and monitor progress. Pending tasks are tracked via the API. |
| **Logs** | Placeholder view for future integration of server or pipeline log streams. |
| **Settings** | Toggle the "Enable GPT-5-Codex (Preview)" feature flag. (Persisting this toggle via the API is planned; currently local state only.) |

Use the sidebar menu to switch sections. The layout is responsive and optimized for widescreen usage with dark background and green accent palette.

---

## 6. Direct Pipeline Usage (Python API)

For scripted workflows or integration testing, access the core pipeline directly:

```python
from edna_pipeline.pipeline import DeepSeaEDNAPipeline

pipeline = DeepSeaEDNAPipeline(db_dir="demo_databases")

result = pipeline.process_sample(
    input_files=("reads_R1.fastq", "reads_R2.fastq"),
    sample_id="ridge_01",
    output_dir="results/ridge_01"
)

if not result["success"]:
    raise RuntimeError(result["error"])

classification = next(step for step in result["pipeline_steps"] if step["step"] == "taxonomic_classification")
print("Classified ASVs:", classification["results"]["total_classified"])
```

Batch processing is similar:

```python
samples = [
    {"files": "sampleA.fastq", "sample_id": "sample_a"},
    {"files": ("sampleB_R1.fastq", "sampleB_R2.fastq"), "sample_id": "sample_b"},
]

summary = pipeline.process_batch(samples, output_dir="batch_output")
print(summary["successful_samples"], "of", summary["total_samples"], "completed")
```

Refer to `USAGE.md` for a full walkthrough of CLI scripts, configuration flags, output artifacts, and troubleshooting advice.

---

## 7. Database Operations

- **List databases**: `python setup_databases.py --list`
- **Download essential bundle**: `python setup_databases.py --recommended`
- **Download specific datasets**: `python setup_databases.py --databases taxdb ITS_eukaryote_sequences`
- **Clean residual archives**:
  ```bash
  python - <<'PY'
  from edna_pipeline.database_manager import DatabaseManager
  DatabaseManager("demo_databases").cleanup_downloads(keep_processed=True)
  PY
  ```

Large downloads (`nt_euk`, `core_nt`, `nt`) require significant disk space and time; ensure adequate resources before initiating.

---

## 8. Automation & Persistence Notes

- **Status persistence** – Runs and batches are serialized to `data/api/runs/*.json` and `data/api/batches/*.json`. The frontend polls these records to maintain UI state across restarts.
- **Thread pools** – The API uses a `ThreadPoolExecutor` (2 workers for single runs, 1 for batches by default). Tune worker counts for your hardware via constructor arguments or environment variables.
- **Logging** – API activity is logged to `data/api/logs/api.log`. Review this file when investigating backend issues.

---

## 9. Testing & Verification

| Layer | Command |
|-------|---------|
| Frontend lint | `cd frontend && npm run lint` |
| Frontend build smoke test | `cd frontend && npm run build` |
| Backend unit tests | `pytest` (from repo root, where tests are available) |
| End-to-end manual test | Launch API + frontend, ensure run submission updates the dashboard and result pages |

---

## 10. Troubleshooting Cheatsheet

| Symptom | Resolution |
|---------|------------|
| `npm run lint` fails with missing config | Ensure `frontend/eslint.config.js` exists (see Section 4). |
| Frontend shows mock data | Set `VITE_USE_MOCK=false` and restart `npm run dev`. Verify backend reachable at `VITE_API_URL`. |
| API run stuck in `queued` | Check backend logs at `data/api/logs/api.log`; ensure ThreadPoolExecutor workers are free and database paths valid. |
| BLAST errors during processing | Reinstall BLAST+, confirm databases downloaded via `setup_databases.py --recommended`, verify read access to `demo_databases`. |
| Large downloads fail | Resume with specific `--databases` invocation; confirm disk space using `df -h`. |

---

## 11. Next Steps

- Wire the Settings toggle to backend persistence (feature flag endpoint).
- Add WebSocket or server-sent events for real-time status streaming.
- Harden the API with authentication and input validation before production deployment.

For additional examples or API documentation, consult `USAGE.md`, `README.md`, and the module docstrings in `edna_pipeline/` and `edna_api/`.

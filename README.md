# Deep-Sea eDNA Pipeline

End-to-end toolkit for analyzing environmental DNA (eDNA) sequencing data from marine/deep-sea samples.

The repository includes:

- A Python analysis pipeline (`edna_pipeline/`) for preprocessing reads, assigning taxonomy, and generating abundance/diversity outputs.
- A Flask API (`edna_api/`) to run jobs and monitor status programmatically.
- A React dashboard (`frontend/`) to operate the pipeline visually.

## What This Project Does (Plain Language)

Think of seawater or sediment as a "DNA soup." Organisms leave behind tiny bits of DNA. This project takes those DNA reads (FASTQ files) and:

1. Cleans and denoises the reads.
2. Groups similar reads into ASVs (Amplicon Sequence Variants).
3. Compares sequences to reference databases (BLAST + k-mer methods).
4. Estimates what organisms are present, with confidence scores.
5. Produces summary files you can inspect or feed into downstream ecology analysis.

In short: upload reads in, get biodiversity/taxonomy outputs out.

## Project Status And Scope

- The Python pipeline is the most complete and reliable way to run analyses.
- The API and frontend are available, but API endpoints are JWT-protected; this must be configured when running the UI against the real backend.
- For a full UI/API walkthrough, see `docs/USER_GUIDE.md`.

## Requirements

## System

- Linux/macOS (WSL2 recommended on Windows)
- Python 3.9+
- `pip`

## External Bioinformatics Tools

- BLAST+ (required for taxonomy assignment)
- VSEARCH (recommended for merging/denoising/chimera workflow)
- `taxonkit` (optional fallback for taxonomy lineage resolution)
- R + DADA2 (optional fallback path when VSEARCH is unavailable)

Install examples:

```bash
# Recommended if you have conda
conda install -c bioconda blast vsearch taxonkit

# Ubuntu/Debian alternatives
sudo apt-get install ncbi-blast+ vsearch
```

Verify:

```bash
blastn -version
vsearch --version
taxonkit version   # optional
```

## Quick Start (Pipeline Only)

This is the fastest path to a real run.

1. Create and activate a Python environment

```bash
python3 -m venv virt
source virt/bin/activate
```

2. Install Python dependencies

```bash
pip install -r requirements.txt
```

Notes:

- `requirements.txt` contains runtime dependencies required for the current pipeline + API.
- Optional heavyweight experimentation packages (for future deep-learning or notebook exploration), such as `torch`, `transformers`, `matplotlib`, `seaborn`, `plotly`, and `rpy2`, are intentionally not installed by default.

3. Download reference databases

```bash
# Recommended bundle (~400 MB)
python setup_databases.py --recommended

# Optional: inspect available choices
python setup_databases.py --list
```

Notes:

- `taxdb` is downloaded from NCBI taxonomy dump (`taxdump.tar.gz`) and setup extracts `nodes.dmp` and `names.dmp` into `databases/processed/taxdb/`.
- Runtime sample processing does not auto-download missing databases. Run setup first (or use the API database download endpoints) before launching analyses.

4. Run a simple example

```bash
python example_usage.py --create-sample 20 --output-dir test_results
```

5. Run on your own file

```bash
python example_usage.py --input /path/to/sample.fastq --output-dir results
```

For paired reads, use the Python API shown below.

## Minimal Python API Example

```python
from edna_pipeline import DeepSeaEDNAPipeline

pipeline = DeepSeaEDNAPipeline(db_dir="databases")

# Single-end:
result = pipeline.process_sample(
        input_files="/path/to/sample.fastq",
        sample_id="sample_001",
        output_dir="results"
)

# Paired-end:
# result = pipeline.process_sample(
#     input_files=("/path/to/sample_R1.fastq", "/path/to/sample_R2.fastq"),
#     sample_id="sample_002",
#     output_dir="results"
# )

print(result["success"], result.get("error"))
```

## What Gets Generated

For each sample, outputs are written under `results/<sample_id>/` (or your chosen output directory), including:

- Preprocessed reads and ASV artifacts
- `taxonomic_assignments.csv` and related taxonomy summaries
- Abundance/diversity metrics
- `pipeline_results.json` (full run record)

## API And Frontend (Optional)

Use this if you want a service + dashboard instead of running scripts directly.

## Start API

```bash
python -m edna_api.server
```

Backend defaults:

- Base URL: `http://localhost:8000`
- API prefix: `/api`
- Health endpoint: `GET /api/health`
- Default database dir: `databases` (override with `EDNA_DB_DIR`)

Authentication note:

- Most run/database endpoints require JWT auth.
- Login endpoint: `POST /api/auth/login`
- Default seeded user is created in SQLite if DB is empty:
    - username: `admin`
    - password: `password123`

## Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Use environment variables for real backend mode:

```bash
export VITE_API_URL="http://localhost:8000/api"
export VITE_USE_MOCK="false"
```

Important: frontend API calls currently do not automatically attach JWT tokens. If you run against real protected endpoints, add auth handling or use mock mode.

## How The Pipeline Works (Simple Mental Model)

1. Input: FASTQ reads (single-end or paired-end).
2. Cleaning: quality filtering + denoising/chimera handling.
3. ASVs: convert cleaned reads into representative sequence variants.
4. Taxonomy: compare ASVs to reference databases and infer taxonomy with confidence.
5. Ecology outputs: abundance tables and diversity metrics.
6. Reporting: machine-readable JSON/CSV artifacts for inspection and downstream analysis.

## Key Files And Folders

- `edna_pipeline/`: core analysis logic.
- `edna_api/`: Flask API server and job management.
- `frontend/`: React operations dashboard.
- `setup_databases.py`: download/manage NCBI-based reference databases.
- `example_usage.py`: runnable demo script.
- `docs/USER_GUIDE.md`: deeper operator documentation.
- `USAGE.md`: additional usage examples.

## Troubleshooting

- `ModuleNotFoundError` for optional research packages (for example `torch` or `transformers`)
    - These are not required for core pipeline/API execution and are not part of the default runtime dependency set.
    - Install them only if you are using those optional workflows.

- `blastn: command not found`
    - Install BLAST+ and re-check `blastn -version`.
- Paired-end merge or denoising errors mentioning VSEARCH
    - Install VSEARCH and ensure it is on your PATH.
- Taxonomy lineage fallback warnings
    - Install `taxonkit` as fallback, or ensure `taxdb` is present by running `python setup_databases.py --databases taxdb`.
- Missing databases
    - Re-run `python setup_databases.py --recommended` and verify disk space.

## Recommended Next Reads

- `docs/USER_GUIDE.md` for API/UI operational details.
- `USAGE.md` for expanded script and output examples.
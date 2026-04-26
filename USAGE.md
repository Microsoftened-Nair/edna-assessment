# eDNA Classification Workflow Usage Guide

## Current Scope

The backend runs a full embeddings-to-classification workflow:

1. Upload FASTA files from the frontend.
2. Start single-run or batch-run analysis.
3. Run pretrained DNABERT2 embedding inference.
4. Save `.npz` embedding artifacts.
5. Classify sequences from embeddings.
6. Generate a detailed HTML report.
7. Stream live run progress back to the frontend.

## Requirements

- Python 3.8+
- Dependencies in `requirements.txt`
- Access to pretrained model `zhihan1996/DNABERT-2-117M`

## Start Backend API

```bash
source virt/bin/activate
python -m edna_api.server
```

Backend runs on `http://127.0.0.1:8000`.

## Start Frontend

```bash
cd frontend
npm run dev
```

Frontend uses API base `http://127.0.0.1:8000/api` by default.

## Frontend Workflow

1. Open Single Run or Batch Run.
2. Upload FASTA files.
3. Click start/schedule.
4. Watch status and progress updates in UI.
5. Open the generated HTML report from run details.
6. Download embeddings, taxonomy CSV/JSON, and summary artifacts.

## API Endpoints In Use

- `POST /api/auth/login`
- `POST /api/uploads`
- `POST /api/runs`
- `GET /api/runs/<run_id>`
- `GET /api/runs/recent`
- `POST /api/runs/batch`
- `GET /api/runs/batch/<batch_id>`
- `GET /api/dashboard`
- `GET /api/files`
- `GET /api/logs`

## Run Output

For each run, backend saves:

- `{output_dir}/{sample_id}_dnabert2_embeddings.npz`
- `data/api/classifications/{sample_id}_taxonomic_classifications.csv`
- `data/api/classifications/{sample_id}_taxonomic_classifications.json`
- `data/api/classifications/{sample_id}_classification_summary.json`
- `data/api/reports/{sample_id}_classification_report.html`

NPZ payload contains:

- `sequence_ids`
- `embeddings`
- `model_name`
- `max_length`

## Classification Behavior

- Supervised mode: provide `configOverrides.classification.model_bundle` with a joblib bundle containing a `classifier` key.
- Fallback mode: if no bundle is provided, embeddings are clustered into OTU-like labels to ensure classification outputs and visual report are still generated.

## Direct Script Usage

You can run the same embeddings path without the API:

```bash
source virt/bin/activate
python scripts/run_pretrained_dnabert2.py \
  --input-fasta path/to/input.fasta \
  --output results/dnabert2_pretrained_embeddings.npz
```

## Notes

- Upload endpoint currently accepts FASTA-family extensions only (`.fasta`, `.fa`, `.fna`, including `.gz`).
